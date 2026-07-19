"""Safely add one managed ``source_id`` to an existing legacy concept pair."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from editor.db.concept_edit_service import _find_one
from editor.db.concept_edit_service import _supports_transactions
from editor.db.concept_edit_service import _update_one
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.repository import SourceRepository


class ConceptSourceLinkStatus(str, Enum):
    """Stable outcomes for the explicit legacy Source-link action."""

    SUCCESS = "success"
    ALREADY_LINKED = "already_linked"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_INACTIVE = "target_inactive"
    CONCEPT_NOT_FOUND = "concept_not_found"
    LATEX_NOT_FOUND = "latex_not_found"
    STALE_IDENTITY = "stale_identity"
    LINK_MISMATCH = "link_mismatch"
    ALREADY_LINKED_TO_DIFFERENT_SOURCE = "already_linked_to_different_source"
    FAILED_COMPENSATED = "failed_compensated"
    PARTIAL_RECOVERY_REQUIRED = "partial_recovery_required"


@dataclass(frozen=True)
class ConceptSourceLinkResult:
    """Structured result that never hides an ambiguous two-document state."""

    status: ConceptSourceLinkStatus
    message: str
    concept_matched_count: int = 0
    concept_modified_count: int = 0
    latex_matched_count: int = 0
    latex_modified_count: int = 0
    transaction_used: bool = False

    @property
    def success(self) -> bool:
        """Return whether the pair is verified at the requested final link."""
        return self.status in {
            ConceptSourceLinkStatus.SUCCESS,
            ConceptSourceLinkStatus.ALREADY_LINKED,
        }


@dataclass(frozen=True)
class _Preflight:
    concept: dict[str, Any]
    latex: dict[str, Any]


class _AbortTransactionError(RuntimeError):
    def __init__(self, result: ConceptSourceLinkResult) -> None:
        super().__init__(result.message)
        self.result = result


def _result(
    status: ConceptSourceLinkStatus,
    message: str,
    *,
    concept_result: Any = None,
    latex_result: Any = None,
    transaction_used: bool = False,
) -> ConceptSourceLinkResult:
    return ConceptSourceLinkResult(
        status=status,
        message=message,
        concept_matched_count=int(getattr(concept_result, "matched_count", 0)),
        concept_modified_count=int(getattr(concept_result, "modified_count", 0)),
        latex_matched_count=int(getattr(latex_result, "matched_count", 0)),
        latex_modified_count=int(getattr(latex_result, "modified_count", 0)),
        transaction_used=transaction_used,
    )


def _preflight(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    target_source_id: str,
    session: Any = None,
) -> _Preflight | ConceptSourceLinkResult:
    identity = {"id": concept_id, "source": source}
    concept = _find_one(database.concepts, identity, session)
    if concept is None:
        return _result(
            ConceptSourceLinkStatus.CONCEPT_NOT_FOUND,
            "The original legacy concept no longer exists.",
            transaction_used=session is not None,
        )

    latex = _find_one(database.latex_documents, identity, session)
    if latex is None:
        return _result(
            ConceptSourceLinkStatus.LATEX_NOT_FOUND,
            "The matching LaTeX document is missing; no link was written.",
            transaction_used=session is not None,
        )

    concept_has_link = "source_id" in concept
    latex_has_link = "source_id" in latex
    concept_link = concept.get("source_id")
    latex_link = latex.get("source_id")

    if concept_has_link and latex_has_link and isinstance(concept_link, str):
        if concept_link == latex_link == target_source_id:
            return _result(
                ConceptSourceLinkStatus.ALREADY_LINKED,
                "Concept and LaTeX document are already linked to this Source.",
                transaction_used=session is not None,
            )
        if concept_link == latex_link:
            return _result(
                ConceptSourceLinkStatus.ALREADY_LINKED_TO_DIFFERENT_SOURCE,
                "The pair is already linked to a different managed Source.",
                transaction_used=session is not None,
            )

    if concept_has_link or latex_has_link:
        return _result(
            ConceptSourceLinkStatus.LINK_MISMATCH,
            "Concept and LaTeX Source-link states do not match exactly.",
            transaction_used=session is not None,
        )

    if expected_source_id is not None:
        return _result(
            ConceptSourceLinkStatus.STALE_IDENTITY,
            "The pair no longer has the expected Source-link state.",
            transaction_used=session is not None,
        )
    return _Preflight(concept=concept, latex=latex)


def _legacy_compare_and_set(document: Mapping[str, Any]) -> dict[str, Any]:
    query = deepcopy(dict(document))
    query["source_id"] = {"$exists": False}
    return query


def _after_link(document: Mapping[str, Any], target_source_id: str) -> dict[str, Any]:
    updated = deepcopy(dict(document))
    updated["source_id"] = target_source_id
    return updated


def _verified_pair(
    database: Any,
    *,
    concept_id: str,
    source: str,
    concept_after: Mapping[str, Any],
    latex_after: Mapping[str, Any],
    session: Any = None,
) -> bool:
    identity = {"id": concept_id, "source": source}
    return (
        _find_one(database.concepts, identity, session) == concept_after
        and _find_one(database.latex_documents, identity, session) == latex_after
    )


def _success(
    concept_result: Any,
    latex_result: Any,
    *,
    transaction_used: bool,
) -> ConceptSourceLinkResult:
    return _result(
        ConceptSourceLinkStatus.SUCCESS,
        "The legacy concept pair is linked to the existing managed Source.",
        concept_result=concept_result,
        latex_result=latex_result,
        transaction_used=transaction_used,
    )


def _compensate_concept(
    database: Any,
    *,
    concept_after: Mapping[str, Any],
) -> Any:
    return _update_one(
        database.concepts,
        deepcopy(dict(concept_after)),
        {"$unset": {"source_id": ""}},
    )


def _compensated_or_partial(
    database: Any,
    *,
    concept_id: str,
    source: str,
    original_concept: Mapping[str, Any],
    original_latex: Mapping[str, Any],
    concept_after: Mapping[str, Any],
    concept_result: Any = None,
    latex_result: Any = None,
    detail: str,
) -> ConceptSourceLinkResult:
    try:
        compensation = _compensate_concept(
            database,
            concept_after=concept_after,
        )
    except Exception:
        compensation = None

    identity = {"id": concept_id, "source": source}
    current_concept = _find_one(database.concepts, identity)
    current_latex = _find_one(database.latex_documents, identity)
    if current_concept == original_concept and current_latex == original_latex:
        return _result(
            ConceptSourceLinkStatus.FAILED_COMPENSATED,
            f"{detail} The Source link was safely removed from the concept.",
            concept_result=concept_result or compensation,
            latex_result=latex_result,
        )
    return _result(
        ConceptSourceLinkStatus.PARTIAL_RECOVERY_REQUIRED,
        f"{detail} The original two-document state could not be fully restored.",
        concept_result=concept_result or compensation,
        latex_result=latex_result,
    )


def _transactional_link(
    database: Any,
    client: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    target_source_id: str,
) -> ConceptSourceLinkResult:
    try:
        with client.start_session() as session:

            def callback(active_session):
                preflight = _preflight(
                    database,
                    concept_id=concept_id,
                    source=source,
                    expected_source_id=expected_source_id,
                    target_source_id=target_source_id,
                    session=active_session,
                )
                if isinstance(preflight, ConceptSourceLinkResult):
                    return preflight

                concept_after = _after_link(preflight.concept, target_source_id)
                latex_after = _after_link(preflight.latex, target_source_id)
                try:
                    concept_result = _update_one(
                        database.concepts,
                        _legacy_compare_and_set(preflight.concept),
                        {"$set": {"source_id": target_source_id}},
                        active_session,
                    )
                except Exception as exc:
                    raise _AbortTransactionError(
                        _result(
                            ConceptSourceLinkStatus.FAILED_COMPENSATED,
                            f"Concept link failed and the transaction was aborted: {exc}",
                            transaction_used=True,
                        )
                    ) from exc
                if getattr(concept_result, "matched_count", 0) != 1:
                    return _result(
                        ConceptSourceLinkStatus.STALE_IDENTITY,
                        "The concept changed before the transactional link.",
                        concept_result=concept_result,
                        transaction_used=True,
                    )

                try:
                    latex_result = _update_one(
                        database.latex_documents,
                        _legacy_compare_and_set(preflight.latex),
                        {"$set": {"source_id": target_source_id}},
                        active_session,
                    )
                except Exception as exc:
                    raise _AbortTransactionError(
                        _result(
                            ConceptSourceLinkStatus.FAILED_COMPENSATED,
                            f"LaTeX link failed and the transaction was aborted: {exc}",
                            concept_result=concept_result,
                            transaction_used=True,
                        )
                    ) from exc
                if getattr(latex_result, "matched_count", 0) != 1:
                    raise _AbortTransactionError(
                        _result(
                            ConceptSourceLinkStatus.FAILED_COMPENSATED,
                            "The LaTeX document changed; the transaction was aborted.",
                            concept_result=concept_result,
                            latex_result=latex_result,
                            transaction_used=True,
                        )
                    )
                if not _verified_pair(
                    database,
                    concept_id=concept_id,
                    source=source,
                    concept_after=concept_after,
                    latex_after=latex_after,
                    session=active_session,
                ):
                    raise _AbortTransactionError(
                        _result(
                            ConceptSourceLinkStatus.FAILED_COMPENSATED,
                            "The final transactional link could not be verified; it was aborted.",
                            concept_result=concept_result,
                            latex_result=latex_result,
                            transaction_used=True,
                        )
                    )
                return _success(
                    concept_result,
                    latex_result,
                    transaction_used=True,
                )

            return session.with_transaction(callback)
    except _AbortTransactionError as exc:
        return exc.result
    except Exception as exc:
        return _result(
            ConceptSourceLinkStatus.PARTIAL_RECOVERY_REQUIRED,
            f"Transactional Source link could not be verified: {exc}",
            transaction_used=True,
        )


def _fallback_link(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    target_source_id: str,
) -> ConceptSourceLinkResult:
    preflight = _preflight(
        database,
        concept_id=concept_id,
        source=source,
        expected_source_id=expected_source_id,
        target_source_id=target_source_id,
    )
    if isinstance(preflight, ConceptSourceLinkResult):
        return preflight

    concept_after = _after_link(preflight.concept, target_source_id)
    latex_after = _after_link(preflight.latex, target_source_id)
    try:
        concept_result = _update_one(
            database.concepts,
            _legacy_compare_and_set(preflight.concept),
            {"$set": {"source_id": target_source_id}},
        )
    except Exception as exc:
        identity = {"id": concept_id, "source": source}
        current = _find_one(database.concepts, identity)
        if current == preflight.concept:
            return _result(
                ConceptSourceLinkStatus.FAILED_COMPENSATED,
                f"Concept link failed before any verified change: {exc}",
            )
        if current == concept_after:
            return _compensated_or_partial(
                database,
                concept_id=concept_id,
                source=source,
                original_concept=preflight.concept,
                original_latex=preflight.latex,
                concept_after=concept_after,
                detail=f"Concept link response failed: {exc}.",
            )
        return _result(
            ConceptSourceLinkStatus.PARTIAL_RECOVERY_REQUIRED,
            f"Concept link failed and its final state is ambiguous: {exc}",
        )

    if getattr(concept_result, "matched_count", 0) != 1:
        return _result(
            ConceptSourceLinkStatus.STALE_IDENTITY,
            "The concept changed after preflight; no LaTeX write was attempted.",
            concept_result=concept_result,
        )

    identity = {"id": concept_id, "source": source}
    if _find_one(database.concepts, identity) != concept_after:
        return _result(
            ConceptSourceLinkStatus.STALE_IDENTITY,
            "The concept update response did not match the requested Source link.",
            concept_result=concept_result,
        )

    latex_result = None
    latex_error: Exception | None = None
    try:
        latex_result = _update_one(
            database.latex_documents,
            _legacy_compare_and_set(preflight.latex),
            {"$set": {"source_id": target_source_id}},
        )
    except Exception as exc:
        latex_error = exc

    current_latex = _find_one(database.latex_documents, identity)
    if current_latex == latex_after and _find_one(database.concepts, identity) == concept_after:
        return _success(
            concept_result,
            latex_result,
            transaction_used=False,
        )

    detail = (
        f"LaTeX link failed: {latex_error}."
        if latex_error is not None
        else "LaTeX compare-and-set or final verification failed."
    )
    return _compensated_or_partial(
        database,
        concept_id=concept_id,
        source=source,
        original_concept=preflight.concept,
        original_latex=preflight.latex,
        concept_after=concept_after,
        concept_result=concept_result,
        latex_result=latex_result,
        detail=detail,
    )


def link_concept_to_existing_managed_source(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    target_source_id: str,
) -> ConceptSourceLinkResult:
    """Link one exact legacy pair to one existing active Source selected by ID."""
    target = SourceRepository(database).get_by_id(target_source_id)
    if target is None:
        return _result(
            ConceptSourceLinkStatus.TARGET_NOT_FOUND,
            "The selected managed Source no longer exists in the active database.",
        )
    if target.status is not SourceStatus.ACTIVE:
        return _result(
            ConceptSourceLinkStatus.TARGET_INACTIVE,
            "The selected managed Source is no longer active.",
        )

    client = getattr(database, "client", None)
    if _supports_transactions(client):
        return _transactional_link(
            database,
            client,
            concept_id=concept_id,
            source=source,
            expected_source_id=expected_source_id,
            target_source_id=target_source_id,
        )
    return _fallback_link(
        database,
        concept_id=concept_id,
        source=source,
        expected_source_id=expected_source_id,
        target_source_id=target_source_id,
    )
