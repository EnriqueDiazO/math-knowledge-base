"""Safe partial-write workflow tests for the S1B UI."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from editor.source_catalog.workflows import ReferenceSavePlan
from editor.source_catalog.workflows import allow_source_creation
from editor.source_catalog.workflows import execute_add_source
from editor.source_catalog.workflows import outcome_status
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus


class _Service:
    def __init__(self) -> None:
        self.source = Source(name="Created")
        self.calls: list[tuple] = []
        self.reference_results: list[CatalogResult[Reference]] = []

    def create_source(self, source, *, allow_duplicate: bool):
        self.calls.append(("create_source", source, allow_duplicate))
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=self.source,
            persisted=True,
        )

    def create_reference(self, data, *, allow_duplicate: bool, import_context: str):
        self.calls.append(("create_reference", data, allow_duplicate, import_context))
        if self.reference_results:
            return self.reference_results.pop(0)
        reference = Reference.model_validate(data)
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=reference,
            persisted=True,
        )

    def associate_reference(self, reference_id: str, source_id: str):
        self.calls.append(("associate_reference", reference_id, source_id))
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=Reference(title="Existing", source_ids=[source_id]),
            persisted=True,
        )


def test_weak_duplicate_never_blocks_source_creation() -> None:
    weak = DuplicateMatch(
        entity_id=Source(name="Other").source_id,
        classification=DuplicateClassification.WEAK,
    )
    possible = DuplicateMatch(
        entity_id=Source(name="Possible").source_id,
        classification=DuplicateClassification.POSSIBLE,
    )

    assert allow_source_creation([weak], confirmed=False) is True
    assert allow_source_creation([possible], confirmed=False) is False
    assert allow_source_creation([possible], confirmed=True) is True


def test_add_source_without_reference_is_valid() -> None:
    service = _Service()

    outcome = execute_add_source(service, Source(name="Minimal"))

    assert outcome.source_created
    assert outcome.references == ()
    assert outcome_status(outcome) == CatalogResultStatus.SUCCESS


def test_add_source_creates_manual_doi_only_reference() -> None:
    service = _Service()
    candidate = Reference(doi="10.1000/only")

    outcome = execute_add_source(
        service,
        Source(name="With reference"),
        [ReferenceSavePlan(label="manual", candidate=candidate)],
    )

    assert outcome.references[0].result.persisted
    call = next(item for item in service.calls if item[0] == "create_reference")
    assert call[1]["source_ids"] == [service.source.source_id]
    assert call[1]["doi"] == "10.1000/only"


def test_add_source_can_associate_an_existing_reference() -> None:
    service = _Service()
    existing = Reference(title="Existing")

    outcome = execute_add_source(
        service,
        Source(name="Association"),
        [ReferenceSavePlan(label="existing", existing_reference_id=existing.reference_id)],
    )

    assert outcome.references[0].action == "associate"
    assert (
        "associate_reference",
        existing.reference_id,
        service.source.source_id,
    ) in service.calls


def test_reference_failure_keeps_source_and_reports_partial_without_delete() -> None:
    service = _Service()
    service.reference_results.append(
        CatalogResult(
            CatalogResultStatus.ERROR,
            errors=("reference validation failed",),
            persisted=False,
        )
    )

    outcome = execute_add_source(
        service,
        Source(name="Partial"),
        [ReferenceSavePlan(label="broken", candidate=Reference(title="Candidate"))],
    )

    assert outcome.source_created
    assert outcome.partial
    assert outcome_status(outcome) == CatalogResultStatus.WARNING
    assert all(not call[0].startswith("delete") for call in service.calls)


def test_source_conflict_prevents_all_reference_writes() -> None:
    service = _Service()

    def conflict_source(source, *, allow_duplicate: bool):
        service.calls.append(("create_source", source, allow_duplicate))
        return CatalogResult(CatalogResultStatus.CONFLICT, persisted=False)

    service.create_source = conflict_source
    outcome = execute_add_source(
        service,
        Source(name="Conflict"),
        [ReferenceSavePlan(label="never", candidate=Reference(title="Never"))],
    )

    assert not outcome.source_created
    assert outcome.references == ()
    assert [call[0] for call in service.calls] == ["create_source"]
