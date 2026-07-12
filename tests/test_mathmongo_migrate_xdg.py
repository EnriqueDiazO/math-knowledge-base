"""Tests for conservative copy-only XDG migration."""

# ruff: noqa: D103

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathmongo.migrate_xdg import migrate_copy
from mathmongo.migrate_xdg import plan_migration


def env(tmp_path: Path) -> dict[str, str]:
    legacy = tmp_path / "legacy checkout"
    return {
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "MATHMONGO_LEGACY_ROOT": str(legacy),
        "PATH": "",
    }


def test_dry_plan_writes_nothing_and_excludes_runtime_noise(tmp_path: Path) -> None:
    environment = env(tmp_path)
    legacy = Path(environment["MATHMONGO_LEGACY_ROOT"])
    (legacy / "media/images").mkdir(parents=True)
    (legacy / "media/images/keep.png").write_bytes(b"image")
    (legacy / "media/images/skip.log").write_bytes(b"log")
    (legacy / ".git").mkdir()
    (legacy / ".git/secret").write_text("skip")
    (legacy / "runtime/cornell_streamlit_preview").mkdir(parents=True)
    (legacy / "runtime/cornell_streamlit_preview/old.pdf").write_bytes(b"preview")

    records = plan_migration(environment)

    assert [Path(record.source).name for record in records] == ["keep.png"]
    assert not Path(environment["XDG_DATA_HOME"]).exists()
    assert not Path(environment["XDG_STATE_HOME"]).exists()


def test_plan_excludes_caches_previews_virtualenvs_tex_aux_and_graph_symlinks(tmp_path: Path) -> None:
    environment = env(tmp_path)
    legacy = Path(environment["MATHMONGO_LEGACY_ROOT"])
    data = legacy / "data"
    data.mkdir(parents=True)
    (data / "keep.json").write_text("keep")

    for cache_name in (
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        "build_cache",
        "model-cache",
    ):
        cache = data / cache_name
        cache.mkdir()
        (cache / "noise.bin").write_bytes(b"cache")
    previews = data / "previews"
    previews.mkdir()
    (previews / "page.pdf").write_bytes(b"preview")
    (data / "document_preview.pdf").write_bytes(b"preview")

    virtualenv = data / "custom-python-environment"
    (virtualenv / "bin").mkdir(parents=True)
    (virtualenv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (virtualenv / "bin/python").write_bytes(b"python")

    tex_suffixes = (
        ".aux",
        ".bbl",
        ".bcf",
        ".blg",
        ".dvi",
        ".fdb_latexmk",
        ".fls",
        ".lof",
        ".log",
        ".lot",
        ".nav",
        ".out",
        ".run.xml",
        ".snm",
        ".synctex.gz",
        ".toc",
        ".vrb",
        ".xdv",
    )
    for suffix in tex_suffixes:
        (data / f"document{suffix}").write_bytes(b"auxiliary")
    for temporary_name in ("document.bak", "editor.swp", "editor.swo", "draft~"):
        (data / temporary_name).write_bytes(b"temporary")

    nested_git = data / ".git"
    nested_git.mkdir()
    (nested_git / "secret").write_text("skip")
    (legacy / "relation_preview_graph.html").write_text("preview")
    (legacy / "relation_preview.json").write_text("preview")
    outside = tmp_path / "outside.html"
    outside.write_text("outside")
    (legacy / "knowledge_graph.html").symlink_to(outside)

    records = plan_migration(environment)

    assert [Path(record.source).name for record in records] == ["keep.json"]
    assert not Path(environment["XDG_DATA_HOME"]).exists()
    assert not Path(environment["XDG_STATE_HOME"]).exists()


def test_copy_manifest_idempotence_conflict_and_source_preservation(tmp_path: Path) -> None:
    environment = env(tmp_path)
    source = Path(environment["MATHMONGO_LEGACY_ROOT"]) / "media/images/picture.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original")

    first, manifest = migrate_copy(environment)
    assert first[0].status == "copied"
    assert source.read_bytes() == b"original"
    destination = Path(first[0].destination)
    assert destination.read_bytes() == b"original"
    assert json.loads(manifest.read_text())["policy"] == "copy-verify-preserve-source"

    second, _ = migrate_copy(environment)
    assert second[0].status == "verified"
    destination.write_bytes(b"user changed destination")
    third = plan_migration(environment)
    assert third[0].status == "conflict"
    migrate_copy(environment)
    assert destination.read_bytes() == b"user changed destination"
    assert source.read_bytes() == b"original"


def test_different_sources_for_one_destination_are_conflicts_and_never_copied(tmp_path: Path) -> None:
    environment = env(tmp_path)
    legacy = Path(environment["MATHMONGO_LEGACY_ROOT"])
    runtime_source = legacy / "runtime/knowledge_graphs/legacy/knowledge_graph.html"
    root_source = legacy / "knowledge_graph.html"
    runtime_source.parent.mkdir(parents=True)
    runtime_source.write_bytes(b"runtime version")
    root_source.write_bytes(b"root version")

    planned = plan_migration(environment)

    assert len(planned) == 2
    assert {record.status for record in planned} == {"conflict"}
    assert len({record.destination for record in planned}) == 1
    destination = Path(planned[0].destination)
    assert not destination.exists()

    copied, manifest = migrate_copy(environment)

    assert {record.status for record in copied} == {"conflict"}
    assert not destination.exists()
    assert runtime_source.read_bytes() == b"runtime version"
    assert root_source.read_bytes() == b"root version"
    assert {record["status"] for record in json.loads(manifest.read_text())["records"]} == {"conflict"}


def test_identical_sources_for_one_destination_are_copied_once(tmp_path: Path) -> None:
    environment = env(tmp_path)
    legacy = Path(environment["MATHMONGO_LEGACY_ROOT"])
    runtime_source = legacy / "runtime/knowledge_graphs/legacy/knowledge_graph.html"
    root_source = legacy / "knowledge_graph.html"
    runtime_source.parent.mkdir(parents=True)
    runtime_source.write_bytes(b"same graph")
    root_source.write_bytes(b"same graph")

    planned = plan_migration(environment)

    assert len(planned) == 2
    assert [record.status for record in planned] == ["copy", "duplicate"]
    assert len({record.destination for record in planned}) == 1

    copied, manifest = migrate_copy(environment)

    assert len(copied) == 2
    assert [record.status for record in copied] == ["copied", "duplicate"]
    assert Path(copied[0].destination).read_bytes() == b"same graph"
    assert runtime_source.read_bytes() == b"same graph"
    assert root_source.read_bytes() == b"same graph"
    manifest_records = json.loads(manifest.read_text())["records"]
    assert len(manifest_records) == 2
    assert {record["source"] for record in manifest_records} == {
        str(runtime_source),
        str(root_source),
    }
    assert [record.status for record in plan_migration(environment)] == [
        "verified",
        "duplicate",
    ]


def test_copy_rejects_a_dangling_destination_symlink(tmp_path: Path) -> None:
    environment = env(tmp_path)
    source = Path(environment["MATHMONGO_LEGACY_ROOT"]) / "media/images/picture.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    destination = Path(environment["XDG_DATA_HOME"]) / "mathmongo/media/images/picture.png"
    destination.parent.mkdir(parents=True)
    redirected = destination.with_name("redirected.png")
    destination.symlink_to(redirected.name)

    records, _ = migrate_copy(environment)

    assert records[0].status == "conflict"
    assert destination.is_symlink()
    assert not redirected.exists()
    assert source.read_bytes() == b"source"


def test_copy_rejects_a_symlink_manifest_leaf(tmp_path: Path) -> None:
    environment = env(tmp_path)
    manifest_dir = Path(environment["XDG_STATE_HOME"]) / "mathmongo/migrations"
    manifest_dir.mkdir(parents=True)
    outside = tmp_path / "outside-manifest.json"
    manifest = manifest_dir / "xdg-migration-v1.json"
    manifest.symlink_to(outside)

    with pytest.raises(ValueError, match="Symbolic links"):
        migrate_copy(environment)

    assert manifest.is_symlink()
    assert not outside.exists()


def test_plan_does_not_follow_a_symlinked_legacy_root(tmp_path: Path) -> None:
    environment = env(tmp_path)
    outside = tmp_path / "outside-legacy"
    source = outside / "media/images/private.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"private")
    legacy = Path(environment["MATHMONGO_LEGACY_ROOT"])
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.symlink_to(outside, target_is_directory=True)

    assert plan_migration(environment) == []
    assert source.read_bytes() == b"private"
    assert not Path(environment["XDG_DATA_HOME"]).exists()
