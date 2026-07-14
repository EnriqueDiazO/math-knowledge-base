"""Focused integrity, streaming, and HTTP Range tests for S5A."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

import pytest
from test_advanced_reader_api import API_PREFIX
from test_advanced_reader_api import BackendHarness
from test_advanced_reader_api import make_backend_harness

from mathmongo.advanced_reader import document_access
from mathmongo.advanced_reader.range_requests import RangeErrorCode
from mathmongo.advanced_reader.range_requests import RangeRequestError
from mathmongo.advanced_reader.range_requests import parse_range_header
from mathmongo.advanced_reader.security import sanitized_inline_filename
from mathmongo.reading_space.service import ReaderContext
from mathmongo.source_documents.models import PdfDocument


def _pdf_url(harness: BackendHarness) -> str:
    return f"{API_PREFIX}/documents/{harness.pdf.document_id}/pdf"


def _error_code(response) -> str:
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["request_id"]
    return str(payload["error"]["code"])


def test_full_pdf_and_head_have_exact_private_inline_headers(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        response = client.get(_pdf_url(harness))
        head = client.head(_pdf_url(harness))

    version = harness.pdf.pdf.current_version
    expected_filename = sanitized_inline_filename(version.original_filename)
    assert response.status_code == head.status_code == 200
    assert response.content == harness.pdf_bytes
    assert head.content == b""
    for current in (response, head):
        assert current.headers["content-type"] == "application/pdf"
        assert current.headers["accept-ranges"] == "bytes"
        assert current.headers["content-length"] == str(len(harness.pdf_bytes))
        assert current.headers["etag"] == f'"{version.sha256}"'
        assert current.headers["content-disposition"] == (f'inline; filename="{expected_filename}"')
        assert current.headers["x-content-type-options"] == "nosniff"
        assert current.headers["cache-control"] == "no-store, private"
        assert "content-range" not in current.headers
    assert expected_filename.isascii()
    assert "/" not in expected_filename and "\\" not in expected_filename
    assert harness.document_service.full_read_calls == []


@pytest.mark.parametrize(
    ("range_header", "expected_start", "expected_end"),
    [
        ("bytes=2-11", 2, 11),
        ("bytes=7-", 7, None),
        ("bytes=-9", -9, None),
    ],
)
def test_single_range_forms_return_exact_206_interval(
    tmp_path: Path,
    range_header: str,
    expected_start: int,
    expected_end: int | None,
) -> None:
    harness = make_backend_harness(tmp_path)
    size = len(harness.pdf_bytes)
    if expected_start < 0:
        start = size + expected_start
        end = size - 1
    else:
        start = expected_start
        end = size - 1 if expected_end is None else expected_end
    with harness.client() as client:
        response = client.get(_pdf_url(harness), headers={"Range": range_header})

    assert response.status_code == 206
    assert response.content == harness.pdf_bytes[start : end + 1]
    assert response.headers["content-range"] == f"bytes {start}-{end}/{size}"
    assert response.headers["content-length"] == str(end - start + 1)
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "application/pdf"


def test_requested_end_beyond_file_is_clamped_and_head_range_matches(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    size = len(harness.pdf_bytes)
    headers = {"Range": "bytes=5-999999"}
    with harness.client() as client:
        response = client.get(_pdf_url(harness), headers=headers)
        head = client.head(_pdf_url(harness), headers=headers)

    assert response.status_code == head.status_code == 206
    assert response.content == harness.pdf_bytes[5:]
    assert head.content == b""
    assert (
        response.headers["content-range"]
        == head.headers["content-range"]
        == (f"bytes 5-{size - 1}/{size}")
    )
    assert response.headers["content-length"] == head.headers["content-length"] == str(size - 5)


@pytest.mark.parametrize(
    "range_header",
    [
        "items=0-1",
        "bytes=",
        "bytes=-0",
        "bytes=5-4",
        "bytes=999999-",
        "bytes=a-b",
        "bytes=1-2-3",
    ],
)
def test_invalid_ranges_return_bounded_416_with_known_size(
    tmp_path: Path,
    range_header: str,
) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        response = client.get(_pdf_url(harness), headers={"Range": range_header})

    assert response.status_code == 416
    assert _error_code(response) == "invalid_range"
    assert response.headers["content-range"] == f"bytes */{len(harness.pdf_bytes)}"
    assert response.headers["accept-ranges"] == "bytes"
    assert str(tmp_path) not in response.text


def test_multiple_ranges_are_rejected_separately(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        response = client.get(
            _pdf_url(harness),
            headers={"Range": "bytes=0-1,4-5"},
        )

    assert response.status_code == 416
    assert _error_code(response) == "multiple_ranges_not_supported"
    assert response.headers["content-range"] == f"bytes */{len(harness.pdf_bytes)}"


def test_pure_range_parser_has_typed_safe_failures() -> None:
    parsed = parse_range_header("bytes=-999", 10)
    assert (parsed.start, parsed.end, parsed.length, parsed.content_range) == (
        0,
        9,
        10,
        "bytes 0-9/10",
    )
    with pytest.raises(RangeRequestError) as multiple:
        parse_range_header("bytes=0-1,3-4", 10)
    assert multiple.value.code == RangeErrorCode.MULTIPLE
    with pytest.raises(RangeRequestError) as invalid:
        parse_range_header("bytes=10-", 10)
    assert invalid.value.code == RangeErrorCode.INVALID
    assert "10" not in str(invalid.value)


def test_range_streaming_uses_bounded_pread_and_never_full_payload_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = b"%PDF-1.7\n" + b"x" * (document_access.VERIFY_CHUNK_BYTES + 12_345)
    harness = make_backend_harness(tmp_path, pdf_bytes=pdf_bytes)
    observed_sizes: list[int] = []
    real_pread = document_access.os.pread

    def tracked_pread(descriptor: int, size: int, offset: int) -> bytes:
        observed_sizes.append(size)
        return real_pread(descriptor, size, offset)

    monkeypatch.setattr(document_access.os, "pread", tracked_pread)
    with harness.client() as client:
        response = client.get(
            _pdf_url(harness),
            headers={"Range": "bytes=0-31"},
        )

    assert response.status_code == 206
    assert response.content == pdf_bytes[:32]
    assert harness.document_service.full_read_calls == []
    assert observed_sizes
    assert max(observed_sizes) <= document_access.VERIFY_CHUNK_BYTES
    assert len(pdf_bytes) not in observed_sizes
    assert 32 in observed_sizes


def test_missing_blob_integrity_tamper_and_symlink_fail_closed(tmp_path: Path) -> None:
    cases = ("missing", "tampered", "symlink")
    for case in cases:
        root = tmp_path / case
        harness = make_backend_harness(root)
        version = harness.pdf.pdf.current_version
        blob = harness.document_service.storage.path_for_version(version)
        if case == "missing":
            blob.unlink()
            expected = (404, "blob_missing")
        elif case == "tampered":
            blob.write_bytes(b"%PDF-1.7\n" + b"z" * (len(harness.pdf_bytes) - 9))
            blob.chmod(0o600)
            expected = (409, "integrity_error")
        else:
            blob.unlink()
            outside = root / "outside secret.pdf"
            outside.write_bytes(harness.pdf_bytes)
            outside.chmod(0o600)
            blob.symlink_to(outside)
            expected = (409, "integrity_error")
        with harness.client() as client:
            response = client.get(_pdf_url(harness))
        assert (response.status_code, _error_code(response)) == expected
        assert str(root) not in response.text


def test_noncanonical_logical_path_cannot_select_an_arbitrary_file(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    version = harness.pdf.pdf.current_version
    unsafe_version = version.model_copy(update={"logical_path": "../../outside.pdf"})
    unsafe_pdf_payload = PdfDocument.model_construct(
        versions=[unsafe_version],
        current_version_id=unsafe_version.version_id,
    )
    unsafe_document = harness.pdf.model_copy(update={"pdf": unsafe_pdf_payload})
    previous = harness.reading_service.contexts[harness.pdf.document_id]
    harness.reading_service.contexts[harness.pdf.document_id] = ReaderContext(
        document=unsafe_document,
        source=previous.source,
        reference=previous.reference,
        reading_state=previous.reading_state,
        effective_status=previous.effective_status,
    )
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-secret")

    with harness.client() as client:
        response = client.get(_pdf_url(harness))

    assert response.status_code == 409
    assert _error_code(response) == "integrity_error"
    assert str(outside) not in response.text
    assert b"secret" not in response.content
