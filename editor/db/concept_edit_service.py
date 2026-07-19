"""Safe non-identity updates for existing concepts and their LaTeX documents."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class ConceptEditStatus(str, Enum):
    """Stable outcomes returned to Edit Concept without claiming false success."""

    SUCCESS = "success"
    CONCEPT_NOT_FOUND = "concept_not_found"
    LATEX_NOT_FOUND = "latex_not_found"
    STALE_IDENTITY = "stale_identity"
    FAILED_COMPENSATED = "failed_compensated"
    PARTIAL_RECOVERY_REQUIRED = "partial_recovery_required"


@dataclass(frozen=True)
class ConceptEditResult:
    """Result and MongoDB match counts for one identity-preserving update."""

    status: ConceptEditStatus
    message: str
    concept_matched_count: int = 0
    concept_modified_count: int = 0
    latex_matched_count: int = 0
    latex_modified_count: int = 0
    transaction_used: bool = False

    @property
    def success(self) -> bool:
        """Return whether both documents reached the requested final state."""
        return self.status is ConceptEditStatus.SUCCESS


@dataclass(frozen=True)
class _Preflight:
    concept: dict[str, Any]
    latex: dict[str, Any]


class _AbortTransactionError(RuntimeError):
    def __init__(self, result: ConceptEditResult) -> None:
        super().__init__(result.message)
        self.result = result


IDENTITY_FIELDS = frozenset({"id", "source", "source_id"})
EDITABLE_CONCEPT_FIELDS = frozenset(
    {
        "titulo",
        "tipo_titulo",
        "categorias",
        "es_algoritmo",
        "pasos_algoritmo",
        "comentario",
        "image_ids",
        "citekey",
        "referencia",
        "contexto_docente",
        "metadatos_tecnicos",
    }
)


def _result(
    status: ConceptEditStatus,
    message: str,
    *,
    concept_result: Any = None,
    latex_result: Any = None,
    transaction_used: bool = False,
) -> ConceptEditResult:
    return ConceptEditResult(
        status=status,
        message=message,
        concept_matched_count=int(getattr(concept_result, "matched_count", 0)),
        concept_modified_count=int(getattr(concept_result, "modified_count", 0)),
        latex_matched_count=int(getattr(latex_result, "matched_count", 0)),
        latex_modified_count=int(getattr(latex_result, "modified_count", 0)),
        transaction_used=transaction_used,
    )


def _find_one(collection: Any, query: dict[str, Any], session: Any = None):
    if session is None:
        return collection.find_one(query)
    return collection.find_one(query, session=session)


def _update_one(
    collection: Any,
    query: dict[str, Any],
    update: dict[str, Any],
    session: Any = None,
):
    if session is None:
        return collection.update_one(query, update, upsert=False)
    return collection.update_one(query, update, upsert=False, session=session)


def _has_expected_source_id(
    document: Mapping[str, Any],
    expected_source_id: str | None,
) -> bool:
    if expected_source_id is None:
        return "source_id" not in document
    return document.get("source_id") == expected_source_id


def _preflight(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    session: Any = None,
) -> _Preflight | ConceptEditResult:
    identity = {"id": concept_id, "source": source}
    concept = _find_one(database.concepts, identity, session)
    if concept is None:
        return _result(
            ConceptEditStatus.CONCEPT_NOT_FOUND,
            "The original concept no longer exists.",
            transaction_used=session is not None,
        )

    latex = _find_one(database.latex_documents, identity, session)
    if latex is None:
        return _result(
            ConceptEditStatus.LATEX_NOT_FOUND,
            "The matching LaTeX document is missing; no changes were written.",
            transaction_used=session is not None,
        )

    if not _has_expected_source_id(concept, expected_source_id):
        return _result(
            ConceptEditStatus.STALE_IDENTITY,
            "The concept Source link changed after it was loaded.",
            transaction_used=session is not None,
        )
    if not _has_expected_source_id(latex, expected_source_id):
        return _result(
            ConceptEditStatus.STALE_IDENTITY,
            "The concept and LaTeX Source links are inconsistent.",
            transaction_used=session is not None,
        )
    return _Preflight(concept=concept, latex=latex)


def _after_set(document: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    updated = deepcopy(dict(document))
    updated.update(deepcopy(dict(values)))
    return updated


def _restore_update(
    original: Mapping[str, Any],
    changed_fields: set[str],
) -> dict[str, Any]:
    set_values = {
        field: deepcopy(original[field])
        for field in changed_fields
        if field in original
    }
    unset_values = {field: "" for field in changed_fields if field not in original}
    update: dict[str, Any] = {}
    if set_values:
        update["$set"] = set_values
    if unset_values:
        update["$unset"] = unset_values
    return update


def _supports_transactions(client: Any) -> bool:
    if client is None or not callable(getattr(client, "start_session", None)):
        return False
    # MongoClient resolves unknown attributes as database names, so inspect only
    # attributes actually declared by a test adapter or its type.
    instance_values = getattr(client, "__dict__", {})
    explicit = (
        instance_values.get("supports_transactions")
        if isinstance(instance_values, dict)
        else None
    )
    if explicit is None:
        explicit = getattr(type(client), "supports_transactions", None)
    if isinstance(explicit, bool):
        return explicit
    topology = getattr(client, "topology_description", None)
    topology_name = getattr(topology, "topology_type_name", "")
    return topology_name in {
        "ReplicaSetWithPrimary",
        "Sharded",
        "LoadBalanced",
    }


def _success_result(
    concept_result: Any,
    latex_result: Any,
    *,
    transaction_used: bool,
) -> ConceptEditResult:
    return _result(
        ConceptEditStatus.SUCCESS,
        "Concept and LaTeX document updated without changing identity.",
        concept_result=concept_result,
        latex_result=latex_result,
        transaction_used=transaction_used,
    )


def _transactional_update(
    database: Any,
    client: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    concept_set: dict[str, Any],
    latex_set: dict[str, Any],
) -> ConceptEditResult:
    try:
        with client.start_session() as session:

            def callback(active_session):
                preflight = _preflight(
                    database,
                    concept_id=concept_id,
                    source=source,
                    expected_source_id=expected_source_id,
                    session=active_session,
                )
                if isinstance(preflight, ConceptEditResult):
                    return preflight

                try:
                    concept_result = _update_one(
                        database.concepts,
                        preflight.concept,
                        {"$set": concept_set},
                        active_session,
                    )
                except Exception as exc:
                    raise _AbortTransactionError(
                        _result(
                            ConceptEditStatus.FAILED_COMPENSATED,
                            f"Concept update failed and the transaction was aborted: {exc}",
                            transaction_used=True,
                        )
                    ) from exc
                if getattr(concept_result, "matched_count", 0) != 1:
                    return _result(
                        ConceptEditStatus.STALE_IDENTITY,
                        "The concept changed before the transactional update.",
                        concept_result=concept_result,
                        transaction_used=True,
                    )

                try:
                    latex_result = _update_one(
                        database.latex_documents,
                        preflight.latex,
                        {"$set": latex_set},
                        active_session,
                    )
                except Exception as exc:
                    raise _AbortTransactionError(
                        _result(
                            ConceptEditStatus.FAILED_COMPENSATED,
                            f"LaTeX update failed and the transaction was aborted: {exc}",
                            concept_result=concept_result,
                            transaction_used=True,
                        )
                    ) from exc
                if getattr(latex_result, "matched_count", 0) != 1:
                    raise _AbortTransactionError(
                        _result(
                            ConceptEditStatus.FAILED_COMPENSATED,
                            "LaTeX changed before update; the transaction was aborted.",
                            concept_result=concept_result,
                            latex_result=latex_result,
                            transaction_used=True,
                        )
                    )
                return _success_result(
                    concept_result,
                    latex_result,
                    transaction_used=True,
                )

            return session.with_transaction(callback)
    except _AbortTransactionError as exc:
        return exc.result
    except Exception as exc:
        return _result(
            ConceptEditStatus.PARTIAL_RECOVERY_REQUIRED,
            f"Transactional update could not be verified: {exc}",
            transaction_used=True,
        )


def _compensate_concept(
    database: Any,
    *,
    original: dict[str, Any],
    expected_after: dict[str, Any],
    changed_fields: set[str],
):
    return _update_one(
        database.concepts,
        expected_after,
        _restore_update(original, changed_fields),
    )


def _fallback_update(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    concept_set: dict[str, Any],
    latex_set: dict[str, Any],
) -> ConceptEditResult:
    preflight = _preflight(
        database,
        concept_id=concept_id,
        source=source,
        expected_source_id=expected_source_id,
    )
    if isinstance(preflight, ConceptEditResult):
        return preflight

    concept_after = _after_set(preflight.concept, concept_set)
    latex_after = _after_set(preflight.latex, latex_set)
    changed_fields = set(concept_set)

    try:
        concept_result = _update_one(
            database.concepts,
            preflight.concept,
            {"$set": concept_set},
        )
    except Exception as exc:
        current = _find_one(
            database.concepts,
            {"id": concept_id, "source": source},
        )
        if current == preflight.concept:
            return _result(
                ConceptEditStatus.FAILED_COMPENSATED,
                f"Concept update failed before any verified change: {exc}",
            )
        if current == concept_after:
            try:
                compensation = _compensate_concept(
                    database,
                    original=preflight.concept,
                    expected_after=concept_after,
                    changed_fields=changed_fields,
                )
            except Exception:
                compensation = None
            if getattr(compensation, "matched_count", 0) == 1:
                return _result(
                    ConceptEditStatus.FAILED_COMPENSATED,
                    "Concept update response failed; the verified change was restored.",
                )
        return _result(
            ConceptEditStatus.PARTIAL_RECOVERY_REQUIRED,
            f"Concept update failed and its final state could not be restored: {exc}",
        )

    if getattr(concept_result, "matched_count", 0) != 1:
        return _result(
            ConceptEditStatus.STALE_IDENTITY,
            "The concept changed before update; no LaTeX write was attempted.",
            concept_result=concept_result,
        )

    latex_result = None
    latex_error: Exception | None = None
    try:
        latex_result = _update_one(
            database.latex_documents,
            preflight.latex,
            {"$set": latex_set},
        )
    except Exception as exc:
        latex_error = exc

    if latex_error is None and getattr(latex_result, "matched_count", 0) == 1:
        return _success_result(
            concept_result,
            latex_result,
            transaction_used=False,
        )

    current_latex = _find_one(
        database.latex_documents,
        {"id": concept_id, "source": source},
    )
    if current_latex == latex_after:
        return _success_result(
            concept_result,
            latex_result,
            transaction_used=False,
        )

    try:
        compensation = _compensate_concept(
            database,
            original=preflight.concept,
            expected_after=concept_after,
            changed_fields=changed_fields,
        )
    except Exception:
        compensation = None

    if (
        getattr(compensation, "matched_count", 0) == 1
        and current_latex == preflight.latex
    ):
        detail = str(latex_error) if latex_error is not None else "matched_count was 0"
        return _result(
            ConceptEditStatus.FAILED_COMPENSATED,
            f"LaTeX update failed ({detail}); the concept update was restored.",
            concept_result=concept_result,
            latex_result=latex_result,
        )

    return _result(
        ConceptEditStatus.PARTIAL_RECOVERY_REQUIRED,
        "LaTeX update failed and the original two-document state was not fully restored.",
        concept_result=concept_result,
        latex_result=latex_result,
    )


def update_concept_fields_preserving_identity(
    database: Any,
    *,
    concept_id: str,
    source: str,
    expected_source_id: str | None,
    changes: Mapping[str, Any],
    contenido_latex: str,
    now: datetime | None = None,
) -> ConceptEditResult:
    """Update only non-identity fields and keep concept/LaTeX identity aligned."""
    change_keys = set(changes)
    forbidden = sorted(change_keys & IDENTITY_FIELDS)
    if forbidden:
        return _result(
            ConceptEditStatus.STALE_IDENTITY,
            f"Identity fields are immutable during ordinary edits: {', '.join(forbidden)}.",
        )

    unsupported = sorted(change_keys - EDITABLE_CONCEPT_FIELDS)
    if unsupported:
        return _result(
            ConceptEditStatus.STALE_IDENTITY,
            f"Unsupported ordinary edit fields: {', '.join(unsupported)}.",
        )

    timestamp = now or datetime.now()
    concept_set = deepcopy(dict(changes))
    concept_set["contenido_latex"] = contenido_latex
    concept_set["ultima_actualizacion"] = timestamp
    latex_set = {
        "contenido_latex": contenido_latex,
        "ultima_actualizacion": timestamp,
    }

    client = getattr(database, "client", None)
    if _supports_transactions(client):
        return _transactional_update(
            database,
            client,
            concept_id=concept_id,
            source=source,
            expected_source_id=expected_source_id,
            concept_set=concept_set,
            latex_set=latex_set,
        )
    return _fallback_update(
        database,
        concept_id=concept_id,
        source=source,
        expected_source_id=expected_source_id,
        concept_set=concept_set,
        latex_set=latex_set,
    )
