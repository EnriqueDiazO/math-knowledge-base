"""Focused S5B transport, capability, and mutation-security coverage."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from test_advanced_reader_api import API_PREFIX
from test_advanced_reader_api import BASE_URL
from test_advanced_reader_api import make_backend_harness

from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import VisualAnnotationAnchor
from mathmongo.reading_annotations.models import utc_now
from mathmongo.reading_annotations.models import visual_text_sha256
from mathmongo.reading_annotations.repository import S4Page
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationServiceResult


class _IndexManager:
    def __init__(self, initialized: bool = True) -> None:
        self.initialized = initialized
        self.apply_calls = 0

    def plan(self):
        return SimpleNamespace(initialized=self.initialized)

    def apply(self):  # pragma: no cover - a transport regression would call it
        self.apply_calls += 1
        raise AssertionError("Advanced Reader must never apply indexes")


class _VisualService:
    def __init__(self, harness) -> None:
        self.harness = harness
        self.items: dict[str, DocumentAnnotation] = {}
        self.create_calls = 0
        self.update_calls = 0
        self.lifecycle_calls: list[tuple[str, str]] = []
        self.block_writes = False

    @staticmethod
    def _result(status, value=None):
        return ReadingAnnotationServiceResult(status, value)

    def create_visual_annotation(self, **values):
        self.create_calls += 1
        if self.block_writes:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE)
        quote = " ".join(values["quote_text"].split())
        anchor = VisualAnnotationAnchor(
            version_id=values["version_id"],
            document_sha256=values["document_sha256"],
            pdf_page=values["pdf_page"],
            capture_rotation=values["capture_rotation"],
            rects=values["rects"],
            text_sha256=visual_text_sha256(quote),
        )
        candidate = DocumentAnnotation(
            schema_version=2,
            annotation_id=values["annotation_id"],
            document_id=values["document_id"],
            source_id=self.harness.source.source_id,
            reference_id=self.harness.reference.reference_id,
            kind=values["kind"],
            page_number=values["pdf_page"],
            quote_text=quote,
            body=values["body"],
            color_label=values["color_label"],
            tags=values["tags"],
            visual_anchor=anchor,
        )
        existing = self.items.get(candidate.annotation_id)
        if existing is not None:
            comparable = (
                "kind",
                "quote_text",
                "body",
                "color_label",
                "tags",
                "visual_anchor",
            )
            if all(getattr(existing, field) == getattr(candidate, field) for field in comparable):
                return self._result(ReadingAnnotationOperationStatus.IDENTICAL, existing)
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, existing)
        self.items[candidate.annotation_id] = candidate
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, candidate)

    def get_visual_annotation(self, annotation_id: str):
        item = self.items.get(annotation_id)
        return self._result(
            ReadingAnnotationOperationStatus.SUCCESS
            if item
            else ReadingAnnotationOperationStatus.NOT_FOUND,
            item,
        )

    def list_visual_annotations(
        self,
        document_id: str,
        *,
        pdf_page=None,
        status=AnnotationStatus.ACTIVE,
        page=1,
        page_size=50,
    ):
        items = [item for item in self.items.values() if item.document_id == document_id]
        if pdf_page is not None:
            items = [item for item in items if item.page_number == pdf_page]
        if status is not None:
            items = [item for item in items if item.status == status]
        items.sort(key=lambda item: (item.page_number or 0, item.annotation_id))
        start = (page - 1) * page_size
        value = S4Page(tuple(items[start : start + page_size]), page, page_size, len(items))
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)

    def update_visual_annotation_presentation(self, annotation_id: str, **values):
        self.update_calls += 1
        current = self.items.get(annotation_id)
        if current is None:
            return self._result(ReadingAnnotationOperationStatus.NOT_FOUND)
        payload = current.model_dump(mode="python")
        payload.update(values)
        payload.pop("user_scope", None)
        updated = DocumentAnnotation.model_validate({**current.model_dump(mode="python"), **values})
        self.items[annotation_id] = updated
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, updated)

    def _lifecycle(self, annotation_id: str, status: AnnotationStatus):
        current = self.items.get(annotation_id)
        if current is None:
            return self._result(ReadingAnnotationOperationStatus.NOT_FOUND)
        timestamp = utc_now()
        updated = DocumentAnnotation.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": status,
                "updated_at": timestamp,
                "archived_at": timestamp if status == AnnotationStatus.ARCHIVED else None,
            }
        )
        self.items[annotation_id] = updated
        self.lifecycle_calls.append((annotation_id, status.value))
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, updated)

    def archive_visual_annotation(self, annotation_id: str):
        return self._lifecycle(annotation_id, AnnotationStatus.ARCHIVED)

    def reactivate_visual_annotation(self, annotation_id: str):
        return self._lifecycle(annotation_id, AnnotationStatus.ACTIVE)


@pytest.fixture
def visual_harness(tmp_path):
    harness = make_backend_harness(tmp_path)
    service = _VisualService(harness)
    indexes = _IndexManager()
    dependencies = replace(
        harness.dependencies,
        annotation_service=service,  # type: ignore[arg-type]
        annotation_index_manager=indexes,  # type: ignore[arg-type]
    )
    harness.app.state.advanced_reader_dependencies = dependencies
    return harness, service, indexes


def _payload(harness, annotation_id: str | None = None):
    return {
        "annotation_id": annotation_id or f"ann_{uuid4()}",
        "version_id": harness.pdf.pdf.current_version.version_id,
        "document_sha256": harness.pdf.pdf.current_version.sha256,
        "pdf_page": 2,
        "kind": "highlight",
        "quote_text": "  selectable   theorem  ",
        "rects": [{"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.05}],
        "capture_rotation": 0,
        "color_label": "yellow",
        "body": "",
        "tags": ["geometry"],
    }


def _write_headers():
    return {"Origin": BASE_URL, "Content-Type": "application/json"}


def test_metadata_capabilities_reflect_indexes_without_applying_them(visual_harness) -> None:
    harness, _, indexes = visual_harness
    with harness.client() as client:
        ready = client.get(f"{API_PREFIX}/documents/{harness.pdf.document_id}")
    assert ready.status_code == 200
    capabilities = ready.json()["capabilities"]
    assert capabilities["persistent_highlights"] is True
    assert capabilities["persistent_underlines"] is True
    assert capabilities["visual_annotation_editing"] is True
    assert capabilities["visual_annotation_archiving"] is True
    assert capabilities["concept_linking"] is False
    assert indexes.apply_calls == 0


def test_create_retry_list_get_update_archive_and_reactivate(visual_harness) -> None:
    harness, service, _ = visual_harness
    payload = _payload(harness)
    document_path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    with harness.client() as client:
        created = client.post(document_path, json=payload, headers={"Origin": BASE_URL})
        identical = client.post(document_path, json=payload, headers={"Origin": BASE_URL})
        listed = client.get(document_path, params={"pdf_page": 2, "status": "active"})
        fetched = client.get(f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}")
        updated = client.patch(
            f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}",
            json={
                "kind": "underline",
                "color_label": "purple",
                "body": "proof context",
                "tags": ["proof"],
            },
            headers={"Origin": BASE_URL},
        )
        archived = client.post(
            f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}/archive",
            json={},
            headers={"Origin": BASE_URL},
        )
        reactivated = client.post(
            f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}/reactivate",
            json={},
            headers={"Origin": BASE_URL},
        )

    assert created.status_code == 201 and created.headers["x-write-result"] == "success"
    assert identical.status_code == 200 and identical.headers["x-write-result"] == "identical"
    assert service.create_calls == 2 and len(service.items) == 1
    assert created.json()["quote_text"] == "selectable theorem"
    assert created.json()["visual_status"] == "exact"
    assert set(created.json()["visual_anchor"]) == {
        "version_id",
        "document_sha256",
        "coordinate_space",
        "capture_rotation",
        "rects",
    }
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert updated.json()["kind"] == "underline"
    assert updated.json()["color_label"] == "purple"
    assert archived.json()["status"] == "archived"
    assert reactivated.json()["status"] == "active"


def test_conflict_and_forbidden_geometry_patch_are_write_safe(visual_harness) -> None:
    harness, service, _ = visual_harness
    payload = _payload(harness)
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    with harness.client() as client:
        assert client.post(path, json=payload, headers={"Origin": BASE_URL}).status_code == 201
        conflict_payload = {**payload, "body": "different"}
        conflict = client.post(path, json=conflict_payload, headers={"Origin": BASE_URL})
        geometry = client.patch(
            f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}",
            json={"rects": [{"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.1}]},
            headers={"Origin": BASE_URL},
        )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "visual_annotation_conflict"
    assert geometry.status_code == 422
    assert service.update_calls == 0
    assert len(service.items) == 1


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({"Content-Type": "application/json"}, 403, "same_origin_required"),
        ({"Origin": BASE_URL, "Content-Type": "text/plain"}, 415, "json_required"),
        (
            {
                "Origin": "http://127.0.0.1:9999",
                "Content-Type": "application/json",
            },
            403,
            "internal_error",
        ),
    ],
)
def test_visual_writes_require_same_origin_json(
    visual_harness,
    headers,
    status,
    code,
) -> None:
    harness, service, _ = visual_harness
    with harness.client() as client:
        response = client.post(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations",
            content="{}",
            headers=headers,
        )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert service.create_calls == 0


def test_request_size_and_invalid_payload_are_bounded_without_leaking_selection(
    visual_harness,
    caplog,
) -> None:
    harness, service, _ = visual_harness
    secret = "/home/private.pdf selectable-secret"
    oversized = {**_payload(harness), "body": secret + ("x" * 70_000)}
    with harness.client() as client:
        too_large = client.post(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations",
            json=oversized,
            headers={"Origin": BASE_URL},
        )
        invalid_payload = {
            **_payload(harness),
            "rects": [{"x": float("nan"), "y": 0, "width": 1, "height": 1}],
        }
        invalid = client.post(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations",
            content=json.dumps(invalid_payload, allow_nan=True),
            headers=_write_headers(),
        )
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "request_too_large"
    assert invalid.status_code == 422
    assert service.create_calls == 0
    assert secret not in caplog.text
    assert "/home/private.pdf" not in caplog.text


@pytest.mark.parametrize("content_length", [b"invalid", b"-1", b"65537"])
def test_invalid_or_oversized_declared_length_is_rejected_before_body_consumption(
    visual_harness,
    content_length,
) -> None:
    harness, service, _ = visual_harness
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    receive_calls = 0
    sent = []

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        raise AssertionError("The request body must not be consumed")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "server": ("127.0.0.1", 8766),
        "client": ("127.0.0.1", 32000),
        "scheme": "http",
        "method": "POST",
        "root_path": "",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [
            (b"host", b"127.0.0.1:8766"),
            (b"origin", BASE_URL.encode("ascii")),
            (b"content-type", b"application/json"),
            (b"content-length", content_length),
        ],
    }

    anyio.run(harness.app, scope, receive, send)

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
    assert receive_calls == 0
    assert service.create_calls == 0


def test_valid_body_without_declared_length_is_measured_and_supported(visual_harness) -> None:
    harness, service, _ = visual_harness
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    body = json.dumps(_payload(harness)).encode("utf-8")
    sent = []
    receive_calls = 0

    async def exercise() -> None:
        async def receive():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                return {"type": "http.request", "body": body, "more_body": False}
            await anyio.sleep_forever()

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "server": ("127.0.0.1", 8766),
            "client": ("127.0.0.1", 32000),
            "scheme": "http",
            "method": "POST",
            "root_path": "",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [
                (b"host", b"127.0.0.1:8766"),
                (b"origin", BASE_URL.encode("ascii")),
                (b"content-type", b"application/json"),
            ],
        }
        await harness.app(scope, receive, send)

    anyio.run(exercise)

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 201
    assert receive_calls >= 1
    assert service.create_calls == 1


@pytest.mark.parametrize("capture_rotation", [False, 0.0, 90.0])
def test_create_rejects_non_integer_capture_rotation_before_service(
    visual_harness,
    capture_rotation,
) -> None:
    harness, service, _ = visual_harness
    payload = {**_payload(harness), "capture_rotation": capture_rotation}
    with harness.client() as client:
        response = client.post(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations",
            json=payload,
            headers={"Origin": BASE_URL},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_visual_annotation"
    assert service.create_calls == 0


def test_create_and_patch_reject_nul_body_before_service(visual_harness) -> None:
    harness, service, _ = visual_harness
    payload = _payload(harness)
    create_path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    update_path = f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}"
    with harness.client() as client:
        invalid_create = client.post(
            create_path,
            json={**payload, "body": "unsafe\x00body"},
            headers={"Origin": BASE_URL},
        )
        assert (
            client.post(
                create_path,
                json=payload,
                headers={"Origin": BASE_URL},
            ).status_code
            == 201
        )
        invalid_patch = client.patch(
            update_path,
            json={"body": "unsafe\x00body"},
            headers={"Origin": BASE_URL},
        )

    assert invalid_create.status_code == 422
    assert invalid_patch.status_code == 422
    assert invalid_create.json()["error"]["code"] == "invalid_visual_annotation"
    assert invalid_patch.json()["error"]["code"] == "invalid_visual_annotation"
    assert service.create_calls == 1
    assert service.update_calls == 0


@pytest.mark.parametrize(
    ("content", "content_type"),
    [("not-json", "application/json"), ('{"unexpected":true}', "application/json")],
)
def test_lifecycle_requires_a_closed_empty_json_object(
    visual_harness,
    content,
    content_type,
) -> None:
    harness, service, _ = visual_harness
    payload = _payload(harness)
    create_path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    lifecycle_path = f"{API_PREFIX}/visual-annotations/{payload['annotation_id']}/archive"
    with harness.client() as client:
        assert (
            client.post(create_path, json=payload, headers={"Origin": BASE_URL}).status_code == 201
        )
        response = client.post(
            lifecycle_path,
            content=content,
            headers={"Origin": BASE_URL, "Content-Type": content_type},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_visual_annotation"
    assert service.lifecycle_calls == []


def test_optional_page_map_failure_never_turns_a_persisted_create_into_500(
    visual_harness,
) -> None:
    harness, service, _ = visual_harness
    harness.page_map_service.error = RuntimeError("optional Page Map unavailable")
    payload = _payload(harness)
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/visual-annotations"
    with harness.client() as client:
        created = client.post(path, json=payload, headers={"Origin": BASE_URL})
        listed = client.get(path)

    assert created.status_code == 201
    assert created.json()["page_label"] is None
    assert listed.status_code == 200
    assert listed.json()["items"][0]["page_label"] is None
    assert payload["annotation_id"] in service.items
