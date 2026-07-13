"""Focused S4.2 Document page-map domain and persistence tests."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import hashlib
from datetime import datetime
from datetime import timezone

import pytest
from pydantic import ValidationError
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.document_page_maps.errors import DocumentPageMapConflictError
from mathmongo.document_page_maps.indexes import DOCUMENT_PAGE_MAP_INDEXES
from mathmongo.document_page_maps.indexes import DOCUMENT_PAGE_MAPS_COLLECTION
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager
from mathmongo.document_page_maps.indexes import PageMapIndexState
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import ManualPageOverride
from mathmongo.document_page_maps.models import PageLabelRule
from mathmongo.document_page_maps.models import PageLabelStyle
from mathmongo.document_page_maps.models import PageMapStatus
from mathmongo.document_page_maps.models import compute_book_page_label
from mathmongo.document_page_maps.repository import DocumentPageMapRepository
from mathmongo.document_page_maps.service import DocumentPageMapService
from mathmongo.document_page_maps.service import PageLabelMatch
from mathmongo.document_page_maps.service import PageMapOperationStatus
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument

PDF_BYTES = b"%PDF-1.7\npage map\n%%EOF\n"


def _pdf(source: Source, *, status: str = "active") -> SourceDocument:
    digest = hashlib.sha256(PDF_BYTES).hexdigest()
    version = PdfVersion(
        sha256=digest,
        size_bytes=len(PDF_BYTES),
        logical_path=f"source_documents/blobs/sha256/{digest[:2]}/{digest}.pdf",
        original_filename="mapped.pdf",
    )
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="Mapped PDF",
        status=status,
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _web(source: Source) -> SourceDocument:
    return SourceDocument(
        source_id=source.source_id,
        kind="web",
        title="Web",
        web=WebDocument(url_raw="https://example.test/page-map"),
    )


def _database(*, ready: bool = True):
    source = Source(name="Page Map Source")
    other = Source(name="Other Source")
    pdf = _pdf(source)
    archived = _pdf(source, status="archived")
    web = _web(source)
    database = FakeDatabase(
        "page-map-focused",
        {
            "sources": [source.model_dump(mode="python"), other.model_dump(mode="python")],
            "source_documents": [
                pdf.model_dump(mode="python"),
                archived.model_dump(mode="python"),
                web.model_dump(mode="python"),
            ],
        },
        allowed_document_writes=(DOCUMENT_PAGE_MAPS_COLLECTION,),
        allowed_index_writes=(DOCUMENT_PAGE_MAPS_COLLECTION,),
    )
    if ready:
        DocumentPageMapIndexManager(database).apply()
    return database, source, other, pdf, archived, web


def test_models_are_strict_versioned_utc_and_have_stable_ids() -> None:
    source = Source(name="Models")
    document = _pdf(source)
    rule = PageLabelRule(
        pdf_start_page=2,
        pdf_end_page=5,
        label_start=1,
        label_style="roman_lower",
        label_prefix="p. ",
    )
    override = ManualPageOverride(pdf_page=3, book_page_label="plate A")
    page_map = DocumentPageMap(
        document_id=document.document_id,
        source_id=source.source_id,
        rules=[rule],
        manual_overrides=[override],
    )

    assert page_map.schema_version == 1
    assert page_map.page_map_id.startswith("pmap_")
    assert rule.rule_id.startswith("prule_")
    assert page_map.user_scope == "local"
    assert page_map.status == PageMapStatus.ACTIVE
    assert page_map.created_at.tzinfo == timezone.utc
    assert rule.label_style == PageLabelStyle.ROMAN_LOWER
    for values in (
        {"page_map_id": "bad"},
        {"document_id": "doc_bad"},
        {"source_id": "src_bad"},
        {"user_scope": "remote"},
        {"unknown": True},
    ):
        payload = {
            "document_id": document.document_id,
            "source_id": source.source_id,
            **values,
        }
        with pytest.raises(ValidationError):
            DocumentPageMap.model_validate(payload)
    with pytest.raises(ValidationError, match="timezone-aware"):
        DocumentPageMap(
            document_id=document.document_id,
            source_id=source.source_id,
            created_at=datetime(2026, 7, 12),
        )


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_rule_label_start_types_are_strict(value) -> None:
    with pytest.raises(ValidationError):
        PageLabelRule(
            pdf_start_page=1,
            label_start=value,
            label_style="arabic",
        )


def test_rule_ranges_overlaps_overrides_and_archive_state_are_coherent() -> None:
    source = Source(name="Consistency")
    document = _pdf(source)
    with pytest.raises(ValidationError, match="pdf_end_page"):
        PageLabelRule(pdf_start_page=5, pdf_end_page=4, label_start=1)
    first = PageLabelRule(pdf_start_page=1, pdf_end_page=4, label_start=1)
    overlap = PageLabelRule(pdf_start_page=4, pdf_end_page=8, label_start=4)
    with pytest.raises(ValidationError, match="overlap"):
        DocumentPageMap(
            document_id=document.document_id,
            source_id=source.source_id,
            rules=[overlap, first],
        )
    duplicate_id = PageLabelRule(
        rule_id=first.rule_id,
        pdf_start_page=10,
        label_start=10,
    )
    with pytest.raises(ValidationError, match="unique rule_id"):
        DocumentPageMap(
            document_id=document.document_id,
            source_id=source.source_id,
            rules=[first, duplicate_id],
        )
    with pytest.raises(ValidationError, match="unique"):
        DocumentPageMap(
            document_id=document.document_id,
            source_id=source.source_id,
            manual_overrides=[
                ManualPageOverride(pdf_page=2, book_page_label="a"),
                ManualPageOverride(pdf_page=2, book_page_label="b"),
            ],
        )
    timestamp = datetime.now(timezone.utc)
    archived = DocumentPageMap(
        document_id=document.document_id,
        source_id=source.source_id,
        status="archived",
        created_at=timestamp,
        updated_at=timestamp,
    )
    assert archived.archived_at == timestamp
    with pytest.raises(ValidationError, match="active page map"):
        DocumentPageMap(
            document_id=document.document_id,
            source_id=source.source_id,
            archived_at=timestamp,
        )


def test_label_computation_supports_all_styles_prefixes_gaps_and_override_precedence() -> None:
    source = Source(name="Labels")
    document = _pdf(source)
    page_map = DocumentPageMap(
        document_id=document.document_id,
        source_id=source.source_id,
        rules=[
            PageLabelRule(
                pdf_start_page=1,
                pdf_end_page=3,
                label_start=1,
                label_style="roman_lower",
            ),
            PageLabelRule(
                pdf_start_page=5,
                pdf_end_page=6,
                label_start=4,
                label_style="roman_upper",
                label_prefix="R-",
            ),
            PageLabelRule(
                pdf_start_page=7,
                pdf_end_page=9,
                label_start=10,
                label_style="arabic",
                label_prefix="p.",
            ),
            PageLabelRule(
                pdf_start_page=10,
                label_start="cover",
                label_style="literal",
                label_prefix="special-",
            ),
        ],
        manual_overrides=[ManualPageOverride(pdf_page=8, book_page_label="plate")],
    )

    assert compute_book_page_label(page_map, 1) == "i"
    assert compute_book_page_label(page_map, 3) == "iii"
    assert compute_book_page_label(page_map, 4) is None
    assert compute_book_page_label(page_map, 6) == "R-V"
    assert compute_book_page_label(page_map, 7) == "p.10"
    assert compute_book_page_label(page_map, 8) == "plate"
    assert compute_book_page_label(page_map, 20) == "special-cover"
    with pytest.raises(ValueError, match="strict integer"):
        compute_book_page_label(page_map, True)


def test_repository_and_index_construction_are_lazy_and_apply_is_explicit() -> None:
    database, *_ = _database(ready=False)
    before = database.events
    repository = DocumentPageMapRepository(database)
    manager = DocumentPageMapIndexManager(database)
    service = DocumentPageMapService(database)

    assert repository.database is database
    assert service.database is database
    assert database.events == before
    plan = manager.plan()
    assert len(plan.missing) == len(DOCUMENT_PAGE_MAP_INDEXES) == 3
    assert not database.write_events
    applied = manager.apply()
    assert applied.initialized
    assert all(item.state == PageMapIndexState.PRESENT for item in manager.status())
    active = next(
        item for item in applied.statuses if item.spec.name.endswith("active_identity_unique")
    )
    assert active.spec.unique
    assert active.spec.partial_filter_expression == {"status": "active"}
    installed = next(
        item
        for item in database._indexes[DOCUMENT_PAGE_MAPS_COLLECTION]
        if item["name"] == active.spec.name
    )
    installed["partialFilterExpression"] = {"status": "archived"}
    conflicted = next(item for item in manager.status() if item.spec.name == active.spec.name)
    assert conflicted.state == PageMapIndexState.CONFLICT


def test_repository_detects_corrupt_multiple_active_maps() -> None:
    database, source, _, pdf, _, _ = _database()
    first = DocumentPageMap(document_id=pdf.document_id, source_id=source.source_id)
    second = DocumentPageMap(document_id=pdf.document_id, source_id=source.source_id)
    database._documents[DOCUMENT_PAGE_MAPS_COLLECTION].extend(
        [first.model_dump(mode="python"), second.model_dump(mode="python")]
    )

    with pytest.raises(DocumentPageMapConflictError, match="Multiple active"):
        DocumentPageMapRepository(database).get_active(pdf.document_id)


def test_repository_insert_get_list_replace_archive_reactivate_and_reset() -> None:
    database, source, _, pdf, _, _ = _database()
    repository = DocumentPageMapRepository(database)
    page_map = repository.insert(
        DocumentPageMap(
            document_id=pdf.document_id,
            source_id=source.source_id,
            rules=[PageLabelRule(pdf_start_page=1, label_start=1)],
            manual_overrides=[ManualPageOverride(pdf_page=2, book_page_label="two")],
        )
    )

    loaded = repository.get_by_id(page_map.page_map_id)
    active = repository.get_active(pdf.document_id)
    listed = repository.list_by_document(pdf.document_id, page=1, page_size=1)
    archived = repository.archive(page_map.page_map_id)
    reactivated = repository.reactivate(page_map.page_map_id)
    reset = repository.reset(page_map.page_map_id)

    assert loaded.page_map_id == page_map.page_map_id
    assert loaded.created_at.tzinfo == timezone.utc
    assert active.page_map_id == page_map.page_map_id
    assert listed.total == 1 and listed.pages == 1
    assert archived.status == PageMapStatus.ARCHIVED and archived.archived_at is not None
    assert reactivated.status == PageMapStatus.ACTIVE and reactivated.archived_at is None
    assert reset.page_map_id == page_map.page_map_id
    assert reset.rules == [] and reset.manual_overrides == []
    assert not hasattr(repository, "delete") and not hasattr(repository, "delete_one")


def test_service_write_gate_and_quick_rule_current_page_maps_to_one() -> None:
    database, _, _, pdf, _, _ = _database(ready=False)
    service = DocumentPageMapService(database)
    blocked = service.set_quick_rule(pdf.document_id, current_pdf_page=12)

    assert blocked.status == PageMapOperationStatus.INVALID_STATE
    assert DOCUMENT_PAGE_MAPS_COLLECTION not in database.list_collection_names()

    DocumentPageMapIndexManager(database).apply()
    created = service.set_quick_rule(pdf.document_id, current_pdf_page=12)
    at_start = service.compute_page_label(pdf.document_id, 12)
    next_page = service.compute_page_label(pdf.document_id, 15)

    assert created.completed
    assert created.value.rules[0].label_start == 1
    assert at_start.value.book_page_label == "1"
    assert at_start.value.matched_by == PageLabelMatch.RULE
    assert next_page.value.book_page_label == "4"


def test_service_add_update_rule_detects_overlap_and_preserves_rule_id() -> None:
    database, _, _, pdf, _, _ = _database()
    service = DocumentPageMapService(database)
    first = service.add_rule(
        pdf.document_id,
        pdf_start_page=1,
        pdf_end_page=4,
        label_start=1,
        label_style="roman_lower",
    )
    second = service.add_rule(
        pdf.document_id,
        pdf_start_page=5,
        pdf_end_page=10,
        label_start=1,
        label_style="arabic",
    )
    conflict = service.add_rule(
        pdf.document_id,
        pdf_start_page=4,
        pdf_end_page=7,
        label_start=1,
        label_style="arabic",
    )
    rule_id = first.value.rules[0].rule_id
    updated = service.update_rule(
        pdf.document_id,
        rule_id,
        pdf_start_page=1,
        pdf_end_page=3,
        label_start=3,
        label_style="roman_upper",
        label_prefix="F-",
    )

    assert first.completed and second.completed
    assert conflict.status == PageMapOperationStatus.CONFLICT
    changed = next(item for item in updated.value.rules if item.rule_id == rule_id)
    assert changed.rule_id == rule_id
    assert changed.label_style == PageLabelStyle.ROMAN_UPPER
    assert service.compute_page_label(pdf.document_id, 2).value.book_page_label == "F-IV"


def test_service_override_wins_upserts_and_reset_retains_active_identity() -> None:
    database, _, _, pdf, _, _ = _database()
    service = DocumentPageMapService(database)
    created = service.set_quick_rule(pdf.document_id, current_pdf_page=1)
    original_id = created.value.page_map_id
    first = service.upsert_override(
        pdf.document_id,
        pdf_page=2,
        book_page_label="plate A",
    )
    second = service.upsert_override(
        pdf.document_id,
        pdf_page=2,
        book_page_label="plate B",
    )
    computed = service.compute_page_label(pdf.document_id, 2)
    reset = service.reset_page_map(pdf.document_id)

    assert first.value.page_map_id == original_id == second.value.page_map_id
    assert len(second.value.manual_overrides) == 1
    assert computed.value.book_page_label == "plate B"
    assert computed.value.matched_by == PageLabelMatch.OVERRIDE
    assert reset.value.page_map_id == original_id
    assert reset.value.status == PageMapStatus.ACTIVE
    assert reset.value.rules == [] and reset.value.manual_overrides == []
    assert service.compute_page_label(pdf.document_id, 2).value.matched_by == (
        PageLabelMatch.UNMAPPED
    )


def test_service_archive_new_active_and_reactivation_conflict() -> None:
    database, _, _, pdf, _, _ = _database()
    service = DocumentPageMapService(database)
    first = service.set_quick_rule(pdf.document_id, current_pdf_page=1).value
    archived = service.archive_page_map(first.page_map_id)
    archived_page = service.list_page_maps(pdf.document_id, status="archived")
    second = service.set_quick_rule(pdf.document_id, current_pdf_page=5).value
    conflict = service.reactivate_page_map(first.page_map_id)
    service.archive_page_map(second.page_map_id)
    reactivated = service.reactivate_page_map(first.page_map_id)

    assert archived.value.status == PageMapStatus.ARCHIVED
    assert archived_page.completed
    assert [item.page_map_id for item in archived_page.value.items] == [first.page_map_id]
    assert second.page_map_id != first.page_map_id
    assert conflict.status == PageMapOperationStatus.CONFLICT
    assert reactivated.completed and reactivated.value.status == PageMapStatus.ACTIVE


def test_service_validates_document_source_pdf_active_and_local_scope_without_mutation() -> None:
    database, source, other, pdf, archived, web = _database()
    service = DocumentPageMapService(database)
    before_sources = database["sources"].documents
    before_documents = database["source_documents"].documents
    missing = _pdf(source)

    assert service.set_quick_rule(missing.document_id, current_pdf_page=1).status == (
        PageMapOperationStatus.NOT_FOUND
    )
    assert service.set_quick_rule(web.document_id, current_pdf_page=1).status == (
        PageMapOperationStatus.BLOCKED
    )
    assert service.set_quick_rule(archived.document_id, current_pdf_page=1).status == (
        PageMapOperationStatus.ARCHIVED
    )
    assert (
        service.set_quick_rule(
            pdf.document_id,
            current_pdf_page=1,
            user_scope="remote",
        ).status
        == PageMapOperationStatus.INVALID_STATE
    )

    corrupt = DocumentPageMap(
        document_id=pdf.document_id,
        source_id=other.source_id,
    )
    DocumentPageMapRepository(database).insert(corrupt)
    assert service.get_page_map(pdf.document_id).status == PageMapOperationStatus.CONFLICT
    assert database["sources"].documents == before_sources
    assert database["source_documents"].documents == before_documents


def test_archived_document_map_remains_readable_but_cannot_change_or_reactivate() -> None:
    database, _, _, pdf, _, _ = _database()
    service = DocumentPageMapService(database)
    page_map = service.set_quick_rule(pdf.document_id, current_pdf_page=3).value
    document = next(
        item
        for item in database._documents["source_documents"]
        if item["document_id"] == pdf.document_id
    )
    document["status"] = "archived"
    document["archived_at"] = document["updated_at"]

    assert service.compute_page_label(pdf.document_id, 3).value.book_page_label == "1"
    assert (
        service.upsert_override(
            pdf.document_id,
            pdf_page=3,
            book_page_label="blocked",
        ).status
        == PageMapOperationStatus.ARCHIVED
    )
    service.archive_page_map(page_map.page_map_id)
    assert service.reactivate_page_map(page_map.page_map_id).status == (
        PageMapOperationStatus.ARCHIVED
    )


def test_imports_are_side_effect_free_and_public_api_is_stable() -> None:
    import mathmongo.document_page_maps as package
    import mathmongo.document_page_maps.indexes as indexes
    import mathmongo.document_page_maps.models as models

    assert package.DocumentPageMap is models.DocumentPageMap
    assert package.DocumentPageMapService is DocumentPageMapService
    assert indexes.DOCUMENT_PAGE_MAPS_COLLECTION == "document_page_maps"
