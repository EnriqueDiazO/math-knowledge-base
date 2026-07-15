"""Focused S5C search, creation, idempotence, lifecycle, and security tests."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import re
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from test_advanced_reader_api import API_PREFIX
from test_advanced_reader_api import make_backend_harness

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.concept_evidence import VisualConceptEvidenceRepository
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import EvidenceLinkStatus
from mathmongo.reading_annotations.models import VisualAnnotationAnchor
from mathmongo.reading_annotations.models import utc_now
from mathmongo.reading_annotations.models import visual_text_sha256
from mathmongo.reading_annotations.repository import S4Page
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationServiceResult


class FakeCursor:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = [dict(item) for item in items]

    def sort(self, specification):
        for key, direction in reversed(specification):
            self.items.sort(key=lambda item: str(item.get(key, "")), reverse=direction < 0)
        return self

    def skip(self, amount: int):
        self.items = self.items[amount:]
        return self

    def limit(self, amount: int):
        self.items = self.items[:amount]
        return self

    def __iter__(self):
        return iter(self.items)


def _match_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and "$regex" in expected:
        values = actual if isinstance(actual, list) else [actual]
        return any(
            re.search(str(expected["$regex"]), str(value or ""), re.IGNORECASE) is not None
            for value in values
        )
    return actual == expected


def _matches(item: dict[str, Any], selector: dict[str, Any]) -> bool:
    if "$and" in selector:
        return all(_matches(item, clause) for clause in selector["$and"])
    if "$or" in selector:
        return any(_matches(item, clause) for clause in selector["$or"])
    return all(_match_value(item.get(key), value) for key, value in selector.items())


class ConceptCollection:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.find_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.find_one_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def find(self, selector, projection):
        self.find_calls.append((selector, projection))
        return FakeCursor([item for item in self.items if _matches(item, selector)])

    def find_one(self, selector, projection):
        self.find_one_calls.append((selector, projection))
        return next((dict(item) for item in self.items if _matches(item, selector)), None)


class FakeDatabase:
    def __init__(self, concepts: list[dict[str, Any]]) -> None:
        self.concepts = ConceptCollection(concepts)

    def __getitem__(self, name: str):
        if name == "concepts":
            return self.concepts
        raise AssertionError(f"unexpected collection: {name}")


class AggregateCollection:
    def __init__(self) -> None:
        self.pipeline: list[dict[str, Any]] | None = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return []


class AggregateDatabase:
    def __init__(self) -> None:
        self.evidence = AggregateCollection()

    def __getitem__(self, _name: str):
        return self.evidence


class ConceptService:
    def __init__(self, database: FakeDatabase, annotation: DocumentAnnotation) -> None:
        self.database = database
        self.annotation = annotation
        self.links: dict[str, ConceptEvidenceLink] = {}
        self.create_calls: list[dict[str, Any]] = []

    @staticmethod
    def _result(status, value=None, message=""):
        return ReadingAnnotationServiceResult(status, value, message)

    def get_visual_annotation(self, annotation_id: str):
        if annotation_id != self.annotation.annotation_id:
            return self._result(ReadingAnnotationOperationStatus.NOT_FOUND)
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, self.annotation)

    def create_concept_evidence_link(self, **values):
        self.create_calls.append(dict(values))
        concept = self.database.concepts.find_one(
            {"id": values["concept_legacy_id"], "source": values["concept_legacy_source"]},
            {"_id": 1},
        )
        if concept is None:
            return self._result(
                ReadingAnnotationOperationStatus.BLOCKED,
                message="Legacy concept does not exist.",
            )
        candidate = ConceptEvidenceLink(**values)
        existing = self.links.get(candidate.evidence_link_id)
        if existing is not None:
            if existing.model_dump(exclude={"created_at", "updated_at"}) == candidate.model_dump(
                exclude={"created_at", "updated_at"}
            ):
                return self._result(ReadingAnnotationOperationStatus.IDENTICAL, existing)
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, existing)
        if any(
            item.annotation_id == candidate.annotation_id
            and item.concept_legacy_id == candidate.concept_legacy_id
            and item.concept_legacy_source == candidate.concept_legacy_source
            and item.link_type == candidate.link_type
            for item in self.links.values()
        ):
            return self._result(ReadingAnnotationOperationStatus.CONFLICT)
        self.links[candidate.evidence_link_id] = candidate
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, candidate)

    def list_annotation_evidence(self, annotation_id: str, *, status, page, page_size):
        items = [item for item in self.links.values() if item.annotation_id == annotation_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        return self._result(
            ReadingAnnotationOperationStatus.SUCCESS,
            S4Page(tuple(items), page, page_size, len(items)),
        )

    def archive_evidence_link(self, evidence_link_id: str):
        return self._lifecycle(evidence_link_id, EvidenceLinkStatus.ARCHIVED)

    def reactivate_evidence_link(self, evidence_link_id: str):
        if self.annotation.status.value == "archived":
            return self._result(
                ReadingAnnotationOperationStatus.ARCHIVED,
                message="Evidence Annotation target is archived.",
            )
        return self._lifecycle(evidence_link_id, EvidenceLinkStatus.ACTIVE)

    def _lifecycle(self, evidence_link_id: str, status: EvidenceLinkStatus):
        current = self.links.get(evidence_link_id)
        if current is None:
            return self._result(ReadingAnnotationOperationStatus.NOT_FOUND)
        timestamp = utc_now()
        updated = ConceptEvidenceLink.model_validate(
            {
                **current.model_dump(mode="python"),
                "status": status,
                "updated_at": timestamp,
                "archived_at": timestamp if status == EvidenceLinkStatus.ARCHIVED else None,
            }
        )
        self.links[evidence_link_id] = updated
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, updated)


class ReadyIndexes:
    def plan(self):
        return SimpleNamespace(initialized=True)


@pytest.fixture
def concept_harness(tmp_path):
    harness = make_backend_harness(tmp_path)
    version = harness.pdf.pdf.current_version
    quote = "A compact definition"
    annotation = DocumentAnnotation(
        schema_version=2,
        annotation_id=f"ann_{uuid4()}",
        document_id=harness.pdf.document_id,
        source_id=harness.source.source_id,
        reference_id=harness.reference.reference_id,
        kind="highlight",
        page_number=2,
        quote_text=quote,
        color_label="yellow",
        visual_anchor=VisualAnnotationAnchor(
            version_id=version.version_id,
            document_sha256=version.sha256,
            pdf_page=2,
            capture_rotation=0,
            rects=[{"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.04}],
            text_sha256=visual_text_sha256(quote),
        ),
    )
    database = FakeDatabase(
        [
            {
                "id": "compactness",
                "source": "TopologyBook",
                "title": "Compacidad",
                "type": "definition",
                "categories": ["Topología"],
                "tags": ["cover"],
                "latex": "must not leave projection",
            },
            {
                "id": "compactness",
                "source": "TopologyBook",
                "title": "Duplicate identity",
            },
            {
                "id": "heine-borel",
                "source": "AnalysisBook",
                "name": "Teorema de Heine–Borel",
                "tipo": "theorem",
                "categorias": ["Análisis"],
            },
        ]
    )
    service = ConceptService(database, annotation)
    dependencies = replace(
        harness.dependencies,
        annotation_service=service,
        annotation_index_manager=ReadyIndexes(),
    )
    harness.dependencies = dependencies
    harness.app = create_app(dependencies)
    return harness, service, database


def write_headers() -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:8766", "Sec-Fetch-Site": "same-origin"}


def test_search_and_detail_are_projected_escaped_paginated_and_exact(concept_harness) -> None:
    harness, _, database = concept_harness
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/concepts/search", params={"q": "Compact", "limit": 20})
        literal = client.get(f"{API_PREFIX}/concepts/search", params={"q": ".*", "limit": 20})
        detail = client.get(
            f"{API_PREFIX}/concepts/detail",
            params={"concept_id": "compactness", "concept_source": "TopologyBook"},
        )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0] == {
        "concept_legacy_id": "compactness",
        "concept_legacy_source": "TopologyBook",
        "title": "Compacidad",
        "concept_type": "definition",
        "categories": ["Topología"],
        "tags": ["cover"],
        "evidence_count": None,
        "evidence_in_document_count": None,
        "warning": None,
    }
    assert literal.json()["items"] == []
    assert detail.status_code == 200
    assert "latex" not in detail.text and "_id" not in detail.json()
    projection = database.concepts.find_calls[0][1]
    assert projection.get("latex") is None and projection["_id"] == 0


@pytest.mark.parametrize("query", ["", "x" * 161])
def test_search_rejects_empty_or_oversized_queries_without_echo(concept_harness, query) -> None:
    harness, _, _ = concept_harness
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/concepts/search", params={"q": query})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "concept_query_invalid"
    if query:
        assert query not in response.text


def test_create_derives_annotation_associations_and_retries_identically(concept_harness) -> None:
    harness, service, _ = concept_harness
    evidence_id = f"ev_{uuid4()}"
    payload = {
        "evidence_link_id": evidence_id,
        "concept_legacy_id": "compactness",
        "concept_legacy_source": "TopologyBook",
        "link_type": "definition_source",
        "comment": "Primary definition",
    }
    path = f"{API_PREFIX}/visual-annotations/{service.annotation.annotation_id}/concept-evidence"
    with harness.client() as client:
        created = client.post(path, json=payload, headers=write_headers())
        retry = client.post(path, json=payload, headers=write_headers())
        listed = client.get(path, params={"status": "all"})

    assert created.status_code == 201 and created.headers["X-Write-Result"] == "success"
    assert retry.status_code == 200 and retry.json()["result"] == "identical"
    assert len(service.links) == 1
    call = service.create_calls[0]
    assert call["source_id"] == service.annotation.source_id
    assert call["reference_id"] == service.annotation.reference_id
    assert call["annotation_id"] == service.annotation.annotation_id
    assert "document_id" not in call and "page_number" not in call and "note_id" not in call
    item = listed.json()["items"][0]
    assert item["annotation"]["pdf_page"] == 2
    assert item["annotation"]["kind"] == "highlight"
    assert item["concept"]["concept_legacy_id"] == "compactness"


def test_create_rejects_extra_fields_cross_origin_missing_concept_and_mismatch(
    concept_harness,
) -> None:
    harness, service, _ = concept_harness
    path = f"{API_PREFIX}/visual-annotations/{service.annotation.annotation_id}/concept-evidence"
    payload = {
        "evidence_link_id": f"ev_{uuid4()}",
        "concept_legacy_id": "missing",
        "concept_legacy_source": "TopologyBook",
        "link_type": "definition_source",
        "comment": None,
    }
    with harness.client() as client:
        cross_origin = client.post(
            path,
            json=payload,
            headers={"Origin": "https://example.test", "Sec-Fetch-Site": "cross-site"},
        )
        extra = client.post(
            path, json={**payload, "document_id": harness.pdf.document_id}, headers=write_headers()
        )
        missing = client.post(path, json=payload, headers=write_headers())
        anchor = service.annotation.visual_anchor
        service.annotation = DocumentAnnotation.model_validate(
            {
                **service.annotation.model_dump(mode="python"),
                "visual_anchor": {
                    **anchor.model_dump(mode="python"),
                    "document_sha256": "f" * 64,
                },
            }
        )
        mismatch = client.post(
            path, json={**payload, "evidence_link_id": f"ev_{uuid4()}"}, headers=write_headers()
        )

    assert cross_origin.status_code == 403
    assert extra.status_code == 422
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "concept_not_found"
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "annotation_version_mismatch"


def test_archive_and_reactivate_link_do_not_change_annotation(concept_harness) -> None:
    harness, service, _ = concept_harness
    evidence_id = f"ev_{uuid4()}"
    service.links[evidence_id] = ConceptEvidenceLink(
        evidence_link_id=evidence_id,
        concept_legacy_id="compactness",
        concept_legacy_source="TopologyBook",
        source_id=service.annotation.source_id,
        reference_id=service.annotation.reference_id,
        annotation_id=service.annotation.annotation_id,
        link_type="related_context",
    )
    original = service.annotation
    with harness.client() as client:
        archived = client.post(
            f"{API_PREFIX}/concept-evidence/{evidence_id}/archive",
            json={},
            headers=write_headers(),
        )
        reactivated = client.post(
            f"{API_PREFIX}/concept-evidence/{evidence_id}/reactivate",
            json={},
            headers=write_headers(),
        )

    assert archived.status_code == 200 and archived.json()["item"]["status"] == "archived"
    assert reactivated.status_code == 200 and reactivated.json()["item"]["status"] == "active"
    assert service.annotation == original


def test_document_join_keeps_links_for_archived_visual_annotations() -> None:
    database = AggregateDatabase()
    result = VisualConceptEvidenceRepository(database).list_visual_evidence_by_document(
        f"doc_{uuid4()}",
        status=None,
    )

    assert result.items == ()
    assert database.evidence.pipeline is not None
    joined_match = database.evidence.pipeline[3]["$match"]
    assert "_annotation.status" not in joined_match
    assert joined_match["_annotation.visual_anchor"] == {"$ne": None}


def test_capabilities_are_composed_without_applying_indexes(concept_harness) -> None:
    harness, _, _ = concept_harness
    with harness.client() as client:
        metadata = client.get(f"{API_PREFIX}/documents/{harness.pdf.document_id}").json()
    capabilities = metadata["capabilities"]
    assert capabilities["concept_search"] is True
    assert capabilities["annotation_concept_links"] is True
    assert capabilities["concept_link_archive"] is True
    assert capabilities["concept_link_reactivate"] is True
    assert capabilities["concept_linking"] is True
