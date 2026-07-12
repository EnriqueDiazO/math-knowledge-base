"""Security and integrity coverage for the read-only S1C1 ZIP boundary."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import json
import os
import stat
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest

from mathmongo.source_catalog_migration import zip_reader
from mathmongo.source_catalog_migration.inventory import build_inventory
from mathmongo.source_catalog_migration.zip_reader import HARD_MAX_COMPRESSION_RATIO
from mathmongo.source_catalog_migration.zip_reader import HARD_MAX_MEMBER_BYTES
from mathmongo.source_catalog_migration.zip_reader import HARD_MAX_MEMBERS
from mathmongo.source_catalog_migration.zip_reader import HARD_MAX_TOTAL_BYTES
from mathmongo.source_catalog_migration.zip_reader import InputChangedError
from mathmongo.source_catalog_migration.zip_reader import ZipSafetyLimits
from mathmongo.source_catalog_migration.zip_reader import ZipValidationError
from mathmongo.source_catalog_migration.zip_reader import identify_input
from mathmongo.source_catalog_migration.zip_reader import private_temporary_workspace
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export
from mathmongo.source_catalog_migration.zip_reader import verify_input_unchanged

BASE = "mathkb_export_test"
AUTHORITATIVE_ARCHIVE = "mathkb_export_20260712_073927.zip"
AUTHORITATIVE_SHA256 = "9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8"


def _concept(
    concept_id: str = "concept-1",
    source: str = "Exact_Source-Name",
    *,
    with_reference: bool = True,
) -> dict[str, Any]:
    document: dict[str, Any] = {"id": concept_id, "source": source}
    if with_reference:
        document["referencia"] = {
            "tipo_referencia": "libro",
            "fuente": "Synthetic reference",
            "paginas": "1-2",
        }
    return document


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _regular_info(name: str, *, compression: int = zipfile.ZIP_DEFLATED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.compress_type = compression
    return info


def _write_member(
    archive: zipfile.ZipFile,
    name: str,
    data: bytes,
    *,
    compression: int = zipfile.ZIP_DEFLATED,
    info: zipfile.ZipInfo | None = None,
) -> None:
    member = info or _regular_info(name, compression=compression)
    archive.writestr(member, data, compress_type=compression)


def _write_export(
    path: Path,
    *,
    collections: dict[str, object] | None = None,
    media: dict[str, bytes] | None = None,
    metadata: object | None = None,
    raw_metadata: bytes | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    collection_payloads = {"concepts": [_concept()]} if collections is None else dict(collections)
    media_payloads = {} if media is None else dict(media)
    if metadata is None:
        counts: dict[str, int] = {}
        for name, payload in collection_payloads.items():
            if not isinstance(payload, list):
                raise AssertionError(f"Explicit metadata is required for raw {name} payloads")
            counts[name] = len(payload)
        metadata = {
            "exported_at": "2026-07-12T07:39:27.161327Z",
            "collections": counts,
            "media_files": {name: len(data) for name, data in media_payloads.items()},
        }

    with zipfile.ZipFile(path, "w") as archive:
        _write_member(
            archive,
            f"{BASE}/metadata.json",
            raw_metadata if raw_metadata is not None else _json_bytes(metadata),
            compression=compression,
        )
        for name, payload in collection_payloads.items():
            data = payload if isinstance(payload, bytes) else _json_bytes(payload)
            _write_member(
                archive,
                f"{BASE}/collections/{name}.json",
                data,
                compression=compression,
            )
        for name, data in media_payloads.items():
            _write_member(
                archive,
                f"{BASE}/{name}",
                data,
                compression=compression,
            )
    return path


def _append_member(
    path: Path,
    name: str,
    data: bytes = b"payload",
    *,
    info: zipfile.ZipInfo | None = None,
) -> None:
    with zipfile.ZipFile(path, "a") as archive:
        _write_member(archive, name, data, info=info)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_valid_synthetic_export_is_loaded_without_inventing_format_metadata(
    tmp_path: Path,
) -> None:
    archive = _write_export(
        tmp_path / "valid.zip",
        collections={
            "concepts": [_concept(), _concept("concept-2", with_reference=False)],
            "latex_documents": [
                {"id": "concept-1", "source": "Exact_Source-Name"},
                {"id": "concept-2", "source": "Exact_Source-Name"},
            ],
        },
        media={"media/images/example.png": b"synthetic-png"},
    )

    loaded = read_legacy_export(archive, database_name="MathV0")
    inventory = build_inventory(loaded)

    assert loaded.zip_safety.validated is True
    assert loaded.zip_safety.member_count == 4
    assert loaded.zip_safety.file_count == 4
    assert loaded.input_snapshot.database_name == "MathV0"
    assert loaded.input_snapshot.format_name == "mathkb_legacy_export"
    assert loaded.input_snapshot.format_version == "unversioned"
    assert loaded.input_snapshot.format_version_source == "layout_inference"
    assert loaded.input_snapshot.counts == {"concepts": 2, "latex_documents": 2}
    assert inventory.source_counts == {"Exact_Source-Name": 2}
    assert inventory.concepts_with_reference == 1
    assert inventory.concepts_without_reference == 1
    assert inventory.coupled_collections.concept_counterparts_in_latex_documents == 2
    assert loaded.member_sha256[f"{BASE}/collections/concepts.json"]


def test_reader_parses_the_anchored_inode_during_a_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _write_export(
        tmp_path / "authoritative.zip",
        collections={"concepts": [_concept("AAAA")]},
    )
    replacement = _write_export(
        tmp_path / "replacement.zip",
        collections={"concepts": [_concept("BBBB")]},
    )
    aside = tmp_path / "authoritative-aside.zip"
    original_zip_file = zip_reader.zipfile.ZipFile
    swapped = False

    def swap_during_open(file, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            os.replace(archive, aside)
            os.replace(replacement, archive)
            try:
                opened = original_zip_file(file, *args, **kwargs)
            finally:
                os.replace(archive, replacement)
                os.replace(aside, archive)
            return opened
        return original_zip_file(file, *args, **kwargs)

    monkeypatch.setattr(zip_reader.zipfile, "ZipFile", swap_during_open)

    try:
        loaded = read_legacy_export(archive)
    except InputChangedError:
        loaded = None

    assert swapped is True
    if loaded is not None:
        assert loaded.collections["concepts"][0]["id"] == "AAAA"
    with zipfile.ZipFile(archive) as restored_archive:
        restored = json.loads(restored_archive.read(f"{BASE}/collections/concepts.json"))
    assert restored[0]["id"] == "AAAA"


def test_authoritative_export_is_validated_read_only_when_available() -> None:
    project_root = Path(__file__).resolve().parents[1]
    archive = project_root / AUTHORITATIVE_ARCHIVE
    if not archive.is_file():
        pytest.skip("The approved, untracked authoritative ZIP is not present")

    before = identify_input(archive)
    loaded = read_legacy_export(archive, database_name="MathV0")
    inventory = build_inventory(loaded)
    verify_input_unchanged(archive, before)

    assert before.sha256 == AUTHORITATIVE_SHA256
    assert loaded.input_snapshot.sha256 == AUTHORITATIVE_SHA256
    assert loaded.input_snapshot.size_bytes == 7_202_896
    assert loaded.zip_safety.member_count == 29
    assert loaded.zip_safety.file_count == 26
    assert loaded.zip_safety.total_uncompressed_bytes == 9_999_843
    assert loaded.zip_safety.maximum_compression_ratio == pytest.approx(8.736501)
    assert loaded.input_snapshot.counts == {
        "backlog_items": 3,
        "concepts": 186,
        "deliverables": 2,
        "knowledge_graph_maps": 2,
        "latex_documents": 187,
        "latex_notes": 34,
        "media_assets": 10,
        "relations": 136,
        "weekly_reviews": 0,
        "worklog_entries": 5,
    }
    assert len(inventory.source_counts) == 16
    assert inventory.concepts_with_reference == 145
    assert inventory.concepts_without_reference == 41
    assert inventory.coupled_collections.concept_counterparts_in_latex_documents == 186
    assert inventory.coupled_collections.orphan_latex_documents == 1
    assert identify_input(archive) == before


@pytest.mark.parametrize(
    ("member_name", "expected_code"),
    (
        (f"{BASE}/../escape.json", "path_traversal"),
        (f"{BASE}/./collections/escape.json", "unsafe_path"),
        ("/absolute/escape.json", "absolute_path"),
        ("C:/absolute/escape.json", "absolute_path"),
        (rf"{BASE}\media\escape.png", "unsafe_path"),
    ),
)
def test_unsafe_member_paths_fail_closed(
    tmp_path: Path,
    member_name: str,
    expected_code: str,
) -> None:
    archive = _write_export(tmp_path / "unsafe-path.zip")
    _append_member(archive, member_name)

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    (
        (stat.S_IFLNK | 0o777, "symlink_member"),
        (stat.S_IFIFO | 0o600, "nonregular_member"),
    ),
)
def test_symlink_and_nonregular_members_are_rejected(
    tmp_path: Path,
    mode: int,
    expected_code: str,
) -> None:
    archive = _write_export(tmp_path / "member-type.zip")
    name = f"{BASE}/media/special"
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    _append_member(archive, name, b"target", info=info)

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == expected_code


def test_input_symlink_and_nonregular_file_are_rejected(tmp_path: Path) -> None:
    archive = _write_export(tmp_path / "target.zip")
    symlink = tmp_path / "input-link.zip"
    symlink.symlink_to(archive)
    fifo = tmp_path / "input.pipe"
    os.mkfifo(fifo)

    with pytest.raises(ZipValidationError) as symlink_error:
        read_legacy_export(symlink)
    with pytest.raises(ZipValidationError) as fifo_error:
        read_legacy_export(fifo)

    assert symlink_error.value.code == "input_symlink"
    assert fifo_error.value.code == "input_not_regular"


def test_duplicate_member_name_is_rejected(tmp_path: Path) -> None:
    archive = _write_export(tmp_path / "duplicate.zip")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        _append_member(archive, f"{BASE}/metadata.json", _json_bytes({}))

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == "duplicate_member"


def test_unicode_normalization_collision_is_rejected(tmp_path: Path) -> None:
    nfc_name = "media/images/caf\N{LATIN SMALL LETTER E WITH ACUTE}.png"
    nfd_name = "media/images/cafe\N{COMBINING ACUTE ACCENT}.png"
    archive = _write_export(
        tmp_path / "unicode-collision.zip",
        media={nfc_name: b"first", nfd_name: b"second"},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == "duplicate_member"


def test_declared_collection_count_must_equal_json_array_count(tmp_path: Path) -> None:
    archive = _write_export(
        tmp_path / "count-mismatch.zip",
        collections={"concepts": [_concept()]},
        metadata={"collections": {"concepts": 2}, "media_files": {}},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == "collection_count_mismatch"


def test_declared_collection_set_must_equal_member_set(tmp_path: Path) -> None:
    archive = _write_export(
        tmp_path / "collection-set-mismatch.zip",
        collections={"concepts": [_concept()], "relations": []},
        metadata={"collections": {"concepts": 1}, "media_files": {}},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == "collection_count_mismatch"


@pytest.mark.parametrize(
    "declared_media",
    (
        {"media/images/example.png": 4},
        {},
        {"media/images/missing.png": 3},
    ),
)
def test_declared_media_names_and_sizes_must_match_members(
    tmp_path: Path,
    declared_media: dict[str, int],
) -> None:
    archive = _write_export(
        tmp_path / "media-mismatch.zip",
        media={"media/images/example.png": b"abc"},
        metadata={"collections": {"concepts": 1}, "media_files": declared_media},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == "media_size_mismatch"


def test_unsupported_collection_and_unexpected_member_are_rejected(tmp_path: Path) -> None:
    unsupported_collection = _write_export(
        tmp_path / "unsupported-collection.zip",
        collections={"concepts": [_concept()], "secrets": []},
        metadata={"collections": {"concepts": 1, "secrets": 0}, "media_files": {}},
    )
    unexpected_member = _write_export(tmp_path / "unexpected-member.zip")
    _append_member(unexpected_member, f"{BASE}/README.txt")

    with pytest.raises(ZipValidationError) as collection_error:
        read_legacy_export(unsupported_collection)
    with pytest.raises(ZipValidationError) as member_error:
        read_legacy_export(unexpected_member)

    assert collection_error.value.code == "unexpected_member"
    assert member_error.value.code == "unexpected_member"


def test_content_hash_detects_change_even_when_size_and_mtime_are_restored(
    tmp_path: Path,
) -> None:
    archive = _write_export(tmp_path / "changed.zip")
    expected = identify_input(archive)
    before = bytearray(archive.read_bytes())
    before[len(before) // 2] ^= 0x01
    archive.write_bytes(before)
    current_stat = archive.stat()
    os.utime(archive, ns=(current_stat.st_atime_ns, expected.modified_ns))

    with pytest.raises(InputChangedError) as caught:
        verify_input_unchanged(archive, expected)

    assert caught.value.code == "input_changed"
    assert archive.stat().st_size == expected.size_bytes
    assert archive.stat().st_mtime_ns == expected.modified_ns


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    (
        (ZipSafetyLimits(max_members=1), "member_limit"),
        (ZipSafetyLimits(max_member_bytes=16), "member_size_limit"),
        (ZipSafetyLimits(max_total_bytes=16), "total_size_limit"),
    ),
)
def test_member_and_size_limits_fail_before_payload_parsing(
    tmp_path: Path,
    limits: ZipSafetyLimits,
    expected_code: str,
) -> None:
    archive = _write_export(tmp_path / f"{expected_code}.zip")

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive, limits=limits)

    assert caught.value.code == expected_code


def test_compression_ratio_limit_rejects_highly_compressible_member(tmp_path: Path) -> None:
    archive = _write_export(
        tmp_path / "compression-ratio.zip",
        media={"media/zeros.bin": b"\0" * 8_192},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(
            archive,
            limits=ZipSafetyLimits(max_compression_ratio=10.0),
        )

    assert caught.value.code == "compression_ratio_limit"
    assert caught.value.member == f"{BASE}/media/zeros.bin"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"max_members": HARD_MAX_MEMBERS + 1},
        {"max_member_bytes": HARD_MAX_MEMBER_BYTES + 1},
        {"max_total_bytes": HARD_MAX_TOTAL_BYTES + 1},
        {"max_compression_ratio": HARD_MAX_COMPRESSION_RATIO + 0.1},
    ),
)
def test_configurable_limits_cannot_exceed_hard_ceilings(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ZipSafetyLimits(**kwargs)  # type: ignore[arg-type]


def test_private_temporary_workspace_is_0700_and_cleaned(tmp_path: Path) -> None:
    parent = tmp_path / "external-temporary-root"
    parent.mkdir()

    with private_temporary_workspace(parent=parent) as workspace:
        retained_path = workspace
        assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
        (workspace / "bounded.json").write_text("{}", encoding="utf-8")

    assert not retained_path.exists()
    assert list(parent.iterdir()) == []


def test_private_temporary_workspace_cleans_up_after_error(tmp_path: Path) -> None:
    parent = tmp_path / "external-temporary-root"
    parent.mkdir()
    retained_path: Path | None = None

    with pytest.raises(RuntimeError, match="synthetic failure"):
        with private_temporary_workspace(parent=parent) as workspace:
            retained_path = workspace
            (workspace / "partial.json").write_text("partial", encoding="utf-8")
            raise RuntimeError("synthetic failure")

    assert retained_path is not None
    assert not retained_path.exists()
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    ("raw_metadata", "expected_code"),
    (
        (b"{", "invalid_json"),
        (b"\xff", "invalid_utf8"),
    ),
)
def test_invalid_metadata_encoding_or_json_is_rejected(
    tmp_path: Path,
    raw_metadata: bytes,
    expected_code: str,
) -> None:
    archive = _write_export(
        tmp_path / f"{expected_code}.zip",
        raw_metadata=raw_metadata,
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    (
        (b"[", "invalid_json"),
        (_json_bytes({"id": "not-an-array"}), "invalid_collection"),
        (_json_bytes(["not-an-object"]), "invalid_collection"),
        (b"\xff", "invalid_utf8"),
    ),
)
def test_invalid_collection_json_is_rejected(
    tmp_path: Path,
    payload: bytes,
    expected_code: str,
) -> None:
    archive = _write_export(
        tmp_path / f"collection-{expected_code}.zip",
        collections={"concepts": payload},
        metadata={"collections": {"concepts": 1}, "media_files": {}},
    )

    with pytest.raises(ZipValidationError) as caught:
        read_legacy_export(archive)

    assert caught.value.code == expected_code


def test_reader_never_extracts_or_creates_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _write_export(tmp_path / "read-only.zip")
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("must remain unchanged", encoding="utf-8")
    archive_hash = _sha256(archive)
    names_before = sorted(path.name for path in tmp_path.iterdir())

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ZIP inspection must not extract or allocate a workspace")

    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    monkeypatch.setattr(
        "mathmongo.source_catalog_migration.zip_reader.tempfile.mkdtemp",
        forbidden,
    )

    loaded = read_legacy_export(archive)

    assert loaded.input_snapshot.sha256 == archive_hash
    assert _sha256(archive) == archive_hash
    assert sentinel.read_text(encoding="utf-8") == "must remain unchanged"
    assert sorted(path.name for path in tmp_path.iterdir()) == names_before
