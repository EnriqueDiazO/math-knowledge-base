"""Shared Source Catalog UI context, status, and safe presentation helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from editor.source_catalog.state import begin_operation
from editor.source_catalog.state import clear_completed_operation
from editor.source_catalog.state import finish_operation
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.indexes import IndexPlan
from mathmongo.source_catalog.indexes import IndexStatus
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import SourceCatalogService

_MONGO_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s'\"<>]+", re.IGNORECASE)
_CREDENTIAL_RE = re.compile(
    r"(?i)(?P<prefix>[\"']?(?:password|passwd|pwd|token|secret|api[_-]?key|"
    r"access[_-]?token|authorization)[\"']?\s*[=:]\s*)"
    r"(?P<value>[\"'][^\"']*[\"']|[^,;}\]]+)"
)
_PYDANTIC_INPUT_RE = re.compile(r"input_value=.*?(?=,\s*input_type=|\]\s*$)", re.DOTALL)
_FILE_URI_RE = re.compile(r"(?i)file:///(?:[^\s,;:'\"<>\])]+)")
_WINDOWS_PATH_RE = re.compile(r"(?i)(?<![\w\\])[a-z]:\\(?:[^\\\s,;:'\"<>\])]+\\?)+")
_INTERNAL_PATH_RE = re.compile(
    r"(?<![\w/])/(?:home|Users|root|tmp|var|opt|srv|mnt|workspace|private|usr|etc|Library)"
    r"(?:/[^\s,;:'\"<>\])]+)+"
)
MAX_SAFE_ERROR_CHARS = 600


@dataclass(frozen=True, slots=True)
class CatalogUIContext:
    """All S1B dependencies bound to one explicit active database."""

    connection_label: str
    database_name: str
    database: Any
    source_repository: SourceRepository
    reference_repository: ReferenceRepository
    service: SourceCatalogService
    index_manager: SourceCatalogIndexManager


@dataclass(frozen=True, slots=True)
class CatalogStatusSnapshot:
    """Read-only collection and index status for one real database."""

    database_name: str
    source_collection_exists: bool
    reference_collection_exists: bool
    index_statuses: tuple[IndexStatus, ...]
    plan: IndexPlan

    @property
    def initialized(self) -> bool:
        """Return whether all approved indexes are present without conflicts."""
        return not self.plan.missing and not self.plan.conflicts


def resolve_database(connection: Any) -> Any:
    """Extract a PyMongo Database from the selected application connection."""
    database = getattr(connection, "db", None)
    if database is None and hasattr(connection, "list_collection_names"):
        database = connection
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("The selected connection does not expose an active MongoDB database.")
    return database


def real_database_name(database: Any) -> str:
    """Return the real PyMongo database name, never a connection label."""
    name = getattr(database, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("The active MongoDB database has no usable real name.")
    return name


def build_catalog_context(connection_label: str, connection: Any) -> CatalogUIContext:
    """Build S1B services from an already-selected connection without reconnecting."""
    database = resolve_database(connection)
    database_name = real_database_name(database)
    sources = SourceRepository(database)
    references = ReferenceRepository(database)
    service = SourceCatalogService(
        database,
        source_repository=sources,
        reference_repository=references,
    )
    return CatalogUIContext(
        connection_label=str(connection_label or "<unlabeled connection>"),
        database_name=database_name,
        database=database,
        source_repository=sources,
        reference_repository=references,
        service=service,
        index_manager=SourceCatalogIndexManager(database),
    )


def inspect_catalog_status(context: CatalogUIContext) -> CatalogStatusSnapshot:
    """Inspect collections and approved indexes without causing a write."""
    collection_names = set(context.database.list_collection_names())
    statuses = context.index_manager.status()
    plan = context.index_manager.plan()
    return CatalogStatusSnapshot(
        database_name=context.database_name,
        source_collection_exists="sources" in collection_names,
        reference_collection_exists="references" in collection_names,
        index_statuses=statuses,
        plan=plan,
    )


def initialize_catalog_indexes(
    context: CatalogUIContext,
    *,
    confirmation_text: str,
    confirmed: bool,
) -> IndexPlan:
    """Apply indexes only after exact real-name confirmation."""
    if not confirmed or confirmation_text.strip() != context.database_name:
        raise ValueError("Catalog initialization requires the exact real database name.")
    return context.index_manager.apply()


def safe_error_message(error: object) -> str:
    """Redact connection secrets, input bodies, traces, and excessive detail."""
    message = str(error or "Unknown error")
    message = _MONGO_URI_RE.sub("<redacted MongoDB URI>", message)
    message = _CREDENTIAL_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>",
        message,
    )
    message = _PYDANTIC_INPUT_RE.sub("input_value=<redacted>", message)
    message = _FILE_URI_RE.sub("<redacted local path>", message)
    message = _WINDOWS_PATH_RE.sub("<redacted local path>", message)
    message = _INTERNAL_PATH_RE.sub("<redacted local path>", message)
    message = message.replace("Traceback (most recent call last):", "")
    message = " ".join(message.split())
    if len(message) > MAX_SAFE_ERROR_CHARS:
        message = message[: MAX_SAFE_ERROR_CHARS - 1].rstrip() + "…"
    return message or "The operation failed without a safe diagnostic message."


def split_values(value: str) -> list[str]:
    """Split comma/newline UI values without applying domain normalization."""
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,\n]", value) if item.strip()]


def render_active_database(ui: Any, context: CatalogUIContext) -> None:
    """Always show both the connection label and authoritative database name."""
    ui.info(f"Base activa: **{context.database_name}**")
    safe_label = safe_error_message(context.connection_label)
    ui.caption(f"Conexión: {safe_label} · Base MongoDB real: {context.database_name}")


def render_catalog_result(ui: Any, result: CatalogResult[Any], *, success: str) -> None:
    """Render typed service outcomes without exposing exception internals."""
    details = [
        safe_error_message(value)
        for value in (result.message, *result.warnings, *result.errors)
        if value
    ]
    detail = " · ".join(details)
    if result.status == CatalogResultStatus.SUCCESS:
        ui.success(success)
    elif result.status == CatalogResultStatus.WARNING:
        ui.warning(detail or success)
    elif result.status == CatalogResultStatus.CONFLICT:
        ui.error(f"Conflicto: {detail or 'se requiere una decisión explícita.'}")
    elif result.status == CatalogResultStatus.BLOCKED:
        blockers = (
            ", ".join(safe_error_message(blocker) for blocker in result.blockers)
            or "vínculos existentes"
        )
        ui.error(f"Operación bloqueada: {blockers}")
    elif result.status == CatalogResultStatus.NOT_FOUND:
        ui.warning(detail or "El registro ya no existe en la base activa.")
    else:
        ui.error(f"Error de base/validación: {detail or 'operación no completada.'}")


def _index_rows(statuses: tuple[IndexStatus, ...]) -> list[dict[str, str]]:
    return [
        {
            "collection": item.spec.collection,
            "index": item.spec.name,
            "state": item.state.value,
            "detail": item.detail,
        }
        for item in statuses
    ]


def _missing_index_rows(plan: IndexPlan) -> list[dict[str, str]]:
    return [
        {
            "collection": spec.collection,
            "index": spec.name,
            "keys": ", ".join(f"{field}:{direction}" for field, direction in spec.keys),
            "unique": "sí" if spec.unique else "no",
        }
        for spec in plan.missing
    ]


def _index_plan_fingerprint(plan: IndexPlan) -> str:
    """Return a deterministic, non-secret identity for one observed index plan."""
    payload = tuple(
        (
            status.spec.collection,
            status.spec.name,
            status.spec.keys,
            status.spec.unique,
            status.state.value,
        )
        for status in plan.statuses
    )
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def render_catalog_status(ui: Any, context: CatalogUIContext) -> CatalogStatusSnapshot | None:
    """Render read-only status and an explicitly confirmed initialization action."""
    ui.subheader("Catalog Status")
    try:
        snapshot = inspect_catalog_status(context)
    except Exception as exc:
        ui.error(f"Database error while reading catalog status: {safe_error_message(exc)}")
        return None

    missing_count = len(snapshot.plan.missing)
    conflict_count = len(snapshot.plan.conflicts)
    if snapshot.initialized:
        ui.success(f"Catalog ready · Source y Reference en {context.database_name}.")
    else:
        ui.warning(
            "Catalog missing · "
            f"{missing_count} índice(s) pendiente(s), "
            f"{conflict_count} conflicto(s)."
        )

    with ui.expander("Advanced catalog diagnostics", expanded=False):
        ui.caption(
            "Colecciones: "
            f"sources={'sí' if snapshot.source_collection_exists else 'no'} · "
            f"references={'sí' if snapshot.reference_collection_exists else 'no'}"
        )
        ui.dataframe(_index_rows(snapshot.index_statuses), width="stretch", hide_index=True)
        ui.write(
            f"Plan: {len(snapshot.plan.present)} presentes, "
            f"{missing_count} faltantes, "
            f"{conflict_count} diferencias."
        )
        if snapshot.plan.missing:
            ui.write("Índices faltantes que Initialize aplicaría:")
            ui.dataframe(
                _missing_index_rows(snapshot.plan),
                width="stretch",
                hide_index=True,
            )
        if snapshot.plan.conflicts:
            ui.error(
                "Hay conflictos de definición de índices. Initialize no puede resolverlos; "
                "se requiere revisión humana antes de escribir."
            )

    plan_fingerprint = _index_plan_fingerprint(snapshot.plan)
    plan_state_key = state_key("index_plan_fingerprint")
    if ui.session_state.get(plan_state_key) != plan_fingerprint:
        ui.session_state.pop(state_key("index_confirmation_text"), None)
        ui.session_state.pop(state_key("index_confirmation_checkbox"), None)
        ui.session_state[plan_state_key] = plan_fingerprint
    if snapshot.initialized:
        clear_completed_operation(ui.session_state, "initialize_indexes")

    with ui.expander("Initialize catalog indexes", expanded=False):
        ui.warning(
            "Esta acción escribe índices únicamente en la base real mostrada arriba. "
            "No se ejecuta automáticamente."
        )
        with ui.form(key=state_key("index_apply_form"), clear_on_submit=False):
            confirmation_text = ui.text_input(
                "Escribe el nombre real de la base para confirmar",
                key=state_key("index_confirmation_text"),
            )
            confirmed = ui.checkbox(
                f"Confirmo aplicar el plan exclusivamente en {context.database_name}",
                key=state_key("index_confirmation_checkbox"),
            )
            can_apply = bool(snapshot.plan.missing) and not snapshot.plan.conflicts
            apply_clicked = ui.form_submit_button(
                "Initialize catalog indexes",
                disabled=not can_apply,
            )
        if apply_clicked:
            if not confirmed or confirmation_text.strip() != context.database_name:
                ui.warning(
                    "Initialization was not executed: type the exact real database name "
                    "and check the confirmation box."
                )
            else:
                token = f"indexes:{context.database_name}:{plan_fingerprint}"
                if not begin_operation(ui.session_state, "initialize_indexes", token):
                    ui.info("La inicialización ya fue procesada para esta confirmación.")
                else:
                    succeeded = False
                    try:
                        applied = initialize_catalog_indexes(
                            context,
                            confirmation_text=confirmation_text,
                            confirmed=confirmed,
                        )
                        succeeded = not applied.missing and not applied.conflicts
                        ui.success(
                            f"Índices del catálogo verificados en {context.database_name}: "
                            f"{len(applied.present)} presentes."
                        )
                    except Exception as exc:
                        ui.error(f"Index initialization failed: {safe_error_message(exc)}")
                    finally:
                        finish_operation(
                            ui.session_state,
                            "initialize_indexes",
                            token,
                            succeeded=succeeded,
                        )
    return snapshot


def duplicate_groups(matches: list[Any] | tuple[Any, ...]) -> dict[str, list[Any]]:
    """Group typed duplicate matches for separate UI sections."""
    groups = {"exact": [], "strong": [], "possible": [], "weak": []}
    for match in matches:
        key = getattr(getattr(match, "classification", None), "value", "")
        if key in groups:
            groups[key].append(match)
    return groups


def render_duplicate_preview(ui: Any, matches: list[Any] | tuple[Any, ...]) -> None:
    """Render exact/strong/possible/weak duplicate evidence separately."""
    groups = duplicate_groups(matches)
    labels = {
        "exact": "Coincidencias exactas",
        "strong": "Duplicados fuertes",
        "possible": "Posibles duplicados",
        "weak": "Sugerencias débiles",
    }
    for level in ("exact", "strong", "possible", "weak"):
        values = groups[level]
        if not values:
            continue
        ui.markdown(f"**{labels[level]}**")
        for match in values:
            evidence = ", ".join(
                item.evidence_type.value for item in getattr(match, "evidence", ())
            )
            ui.write(f"- `{match.entity_id}` · {evidence or level}")
    if not any(groups.values()):
        ui.success("No se encontraron candidatos duplicados en la base activa.")


__all__ = [
    "CatalogStatusSnapshot",
    "CatalogUIContext",
    "MAX_SAFE_ERROR_CHARS",
    "build_catalog_context",
    "duplicate_groups",
    "initialize_catalog_indexes",
    "inspect_catalog_status",
    "real_database_name",
    "render_active_database",
    "render_catalog_result",
    "render_catalog_status",
    "render_duplicate_preview",
    "resolve_database",
    "safe_error_message",
    "split_values",
]
