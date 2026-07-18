"""Streamlit page for create-only imports and safe existing-database updates."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from editor.utils.db_import import import_zip_into_database
from editor.utils.db_import import inspect_export_zip
from editor.utils.db_update import ConflictPolicy
from editor.utils.db_update import DatabaseUpdateApplyError
from editor.utils.db_update import DatabaseUpdatePlan
from editor.utils.db_update import ExistingDatabaseTarget
from editor.utils.db_update import UpdateStrategy
from editor.utils.db_update import analyze_database_update
from editor.utils.db_update import apply_database_update
from editor.utils.db_update import bind_existing_database
from editor.utils.db_update import inspect_update_archive
from editor.utils.db_update import restore_failed_update
from editor.utils.db_update import validate_database_name
from mathkb_config import IMPORT_TIMEOUT_SECONDS
from mathmongo.paths import get_backups_dir
from mathmongo.paths import get_runtime_dir
from mathmongo.paths import validate_mutable_path

CREATE_MODE = "Crear base nueva"
UPDATE_MODE = "Actualizar base existente"

STRATEGY_LABELS = {
    "Fusión segura": UpdateStrategy.SAFE_MERGE,
    "El respaldo prevalece": UpdateStrategy.BACKUP_WINS,
    "Conservar versión actual": UpdateStrategy.KEEP_CURRENT,
}

STRATEGY_DESCRIPTIONS = (
    (
        "Fusión segura",
        "agrega ausentes, omite idénticos y deja los conflictos sin cambios para revisión "
        "(recomendada).",
    ),
    (
        "El respaldo prevalece",
        "agrega ausentes y permite reemplazar cada conflicto con el respaldo sólo tras "
        "confirmarlo.",
    ),
    (
        "Conservar versión actual",
        "agrega únicamente ausentes y conserva siempre la versión actual cuando hay conflicto.",
    ),
)

_PLAN_KEY = "database_update_plan"
_FAILURE_KEY = "database_update_failure"


def list_existing_update_databases(mongo: Any) -> list[str]:
    """List safe existing targets from the active MongoDB server."""
    client = getattr(mongo, "client", None)
    if client is None or not hasattr(client, "list_database_names"):
        return []
    names: list[str] = []
    for name in client.list_database_names():
        try:
            names.append(validate_database_name(name, update=True))
        except ValueError:
            continue
    return sorted(set(names), key=lambda value: (value != "MathV0", value.casefold()))


def validate_new_database_target(mongo: Any, raw_name: object) -> str:
    """Require an exact safe name that does not exist on the active server."""
    name = validate_database_name(raw_name, update=False)
    client = getattr(mongo, "client", None)
    if client is None or not hasattr(client, "list_database_names"):
        raise ValueError("The active connection cannot verify existing databases")
    if name in client.list_database_names():
        raise ValueError("Create mode requires a database name that does not exist")
    return name


def new_database_target(mongo: Any, database_name: str) -> ExistingDatabaseTarget:
    """Bind one already-validated absent name without initializing collections."""
    name = validate_new_database_target(mongo, database_name)
    return ExistingDatabaseTarget(client=mongo.client, db=mongo.client[name])


@contextmanager
def _staged_upload(uploaded_file: Any) -> Iterator[Path]:
    runtime_root = validate_mutable_path(get_runtime_dir())
    import_runtime = validate_mutable_path(
        runtime_root / "imports",
        allowed_root=runtime_root,
    )
    import_runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    import_runtime.chmod(0o700)
    path = validate_mutable_path(
        import_runtime / f"database-import-{uuid4().hex}.zip",
        allowed_root=import_runtime,
    )
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(uploaded_file.getbuffer())
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("Unable to stage the uploaded database archive")
            written += count
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _render_archive_preview(ui: Any, inspection: dict[str, Any]) -> None:
    ui.subheader("Vista previa")
    exported_at = inspection["metadata"].get("exported_at")
    if exported_at:
        ui.write(f"Exportado: {exported_at}")
    rows = [
        {"Colección": name, "Documentos": count}
        for name, count in sorted(inspection["collections"].items())
    ]
    ui.dataframe(rows, hide_index=True, width="stretch")
    unmanaged = inspection.get("unmanaged_collections", [])
    if unmanaged:
        ui.warning("El respaldo contiene colecciones no administradas: " + ", ".join(unmanaged))
    ui.success("El respaldo es válido.")


def _render_create_mode(ui: Any, archive_path: Path, current_mongo: Any) -> None:
    ui.subheader("Crear una base nueva")
    new_name = ui.text_input("Nombre de la base nueva", placeholder="p. ej. MathV1")
    validation_error: str | None = None
    validated_name: str | None = None
    if new_name:
        try:
            validated_name = validate_new_database_target(current_mongo, new_name)
        except ValueError as exc:
            validation_error = str(exc)
            ui.warning(validation_error)
    clicked = ui.button(
        "Importar en base nueva",
        disabled=validated_name is None,
        type="primary",
    )
    if not clicked or validated_name is None:
        return
    try:
        target = new_database_target(current_mongo, validated_name)
        report = import_zip_into_database(archive_path, target, new_database=True)
        target.ensure_indexes()
    except Exception as exc:
        ui.error(
            "No se pudo crear la base nueva. No se sobrescribió ninguna base existente. "
            f"Detalle: {exc}"
        )
        return
    imported = sum(report.imported_counts.values())
    ui.success(f"La base '{validated_name}' fue creada con {imported} documentos importados.")


def _plan_matches_upload(
    plan: DatabaseUpdatePlan | None,
    *,
    archive_sha256: str,
    target: str,
    strategy: UpdateStrategy,
) -> bool:
    return bool(
        plan
        and plan.archive_sha256 == archive_sha256
        and plan.target_database == target
        and plan.strategy is strategy
    )


def _summarize_blocking_issues(issues: Iterable[Any]) -> tuple[str, ...]:
    counts = Counter((issue.collection, issue.reason) for issue in issues)
    return tuple(
        f"{collection}: {reason}" + (f" ({count} casos)" if count > 1 else "")
        for (collection, reason), count in counts.items()
    )


def _render_plan(ui: Any, plan: DatabaseUpdatePlan) -> dict[str, ConflictPolicy | str]:
    ui.subheader("Plan de actualización")
    totals = plan.totals
    rows = [
        {
            "Colección": item.name,
            "Actuales": item.current_documents,
            "Respaldo": item.backup_documents,
            "Idénticos": item.identical,
            "Nuevos": item.new,
            "Conflictos": item.conflicts,
            "Inválidos": item.invalid,
            "Blobs nuevos": totals["blobs_new"] if item.name == "source_documents" else 0,
            "Blobs presentes": (totals["blobs_existing"] if item.name == "source_documents" else 0),
            "Acción": item.proposed_action,
            "Gestión": "Administrada" if item.managed else "No administrada",
        }
        for item in plan.collection_plans
    ]
    ui.dataframe(rows, hide_index=True, width="stretch")
    metrics = ui.columns(4)
    metrics[0].metric("Nuevos", totals["new"])
    metrics[1].metric("Idénticos", totals["identical"])
    metrics[2].metric("Conflictos", totals["conflicts"])
    metrics[3].metric("Inválidos", totals["invalid"])
    ui.caption(
        f"Blobs PDF: {totals['blobs_new']} nuevos, {totals['blobs_existing']} presentes. "
        f"Medios: {totals['media_new']} nuevos, {totals['media_existing']} presentes."
    )
    for warning in plan.warnings:
        ui.warning(warning)
    for message in _summarize_blocking_issues(plan.blocking_issues):
        ui.error(message)

    policies: dict[str, ConflictPolicy | str] = {}
    if plan.conflicts:
        ui.subheader("Conflictos")
        ui.info(
            "No se muestran IDs completos ni documentos. Selecciona una política para cada "
            "conflicto antes de actualizar."
        )
        for ordinal, action in enumerate(plan.conflicts, start=1):
            options: list[str] = ["Seleccionar", "Conservar versión actual"]
            if plan.strategy is UpdateStrategy.BACKUP_WINS and action.replace_allowed:
                options.append("Usar versión del respaldo")
            selected = ui.selectbox(
                f"Conflicto {ordinal} en {action.collection}",
                options,
                key=f"database_update_conflict_{plan.fingerprint}_{action.token}",
            )
            if selected == "Conservar versión actual":
                policies[action.token] = ConflictPolicy.KEEP_CURRENT
            elif selected == "Usar versión del respaldo":
                policies[action.token] = ConflictPolicy.USE_BACKUP
    return policies


def _render_recovery(ui: Any, current_mongo: Any, target_name: str) -> None:
    failure = ui.session_state.get(_FAILURE_KEY)
    if not isinstance(failure, DatabaseUpdateApplyError):
        return
    if failure.target_database != target_name:
        return
    ui.error(
        f"La actualización se detuvo después de {len(failure.operations)} operaciones. "
        "No se declaró éxito parcial."
    )
    ui.info(f"Respaldo previo validado: {failure.backup_path}")
    recovery_confirmation = ui.text_input(
        f"Escribe {target_name} para restaurar el estado previo",
        key="database_update_recovery_confirmation",
    )
    if ui.button(
        "Restaurar respaldo previo",
        disabled=recovery_confirmation != target_name,
    ):
        try:
            target = bind_existing_database(current_mongo, target_name)
            report = restore_failed_update(
                failure,
                target,
                confirmation=recovery_confirmation,
            )
        except Exception as exc:
            ui.error(f"No se pudo completar la recuperación: {exc}")
        else:
            ui.session_state.pop(_FAILURE_KEY, None)
            ui.success(
                f"Se revirtieron {report.reverted_operations} operaciones usando el respaldo "
                "previo validado."
            )


def _render_update_selection(
    ui: Any,
    current_mongo: Any,
) -> tuple[str, UpdateStrategy] | None:
    """Render the existing target and strategy before the archive uploader."""
    databases = list_existing_update_databases(current_mongo)
    if not databases:
        ui.error("No hay bases existentes elegibles para actualizar en este servidor.")
        return None
    target_name = ui.selectbox("Base de destino", databases)
    strategy_label = ui.selectbox("Estrategia", list(STRATEGY_LABELS))
    for label, description in STRATEGY_DESCRIPTIONS:
        ui.caption(f"**{label}:** {description}")
    return target_name, STRATEGY_LABELS[strategy_label]


def _render_update_mode(
    ui: Any,
    archive_path: Path,
    inspection: dict[str, Any],
    current_mongo: Any,
    *,
    target_name: str,
    strategy: UpdateStrategy,
) -> None:
    target = bind_existing_database(current_mongo, target_name)

    if ui.button("Analizar actualización", type="primary"):
        try:
            with ui.spinner("Analizando sin escribir..."):
                ui.session_state[_PLAN_KEY] = analyze_database_update(
                    archive_path,
                    target,
                    strategy=strategy,
                )
            ui.session_state.pop(_FAILURE_KEY, None)
        except Exception as exc:
            ui.session_state.pop(_PLAN_KEY, None)
            ui.error(f"No se pudo generar el plan de actualización: {exc}")

    plan = ui.session_state.get(_PLAN_KEY)
    if not _plan_matches_upload(
        plan,
        archive_sha256=inspection["archive_sha256"],
        target=target_name,
        strategy=strategy,
    ):
        plan = None
    if plan is None:
        _render_recovery(ui, current_mongo, target_name)
        return

    policies = _render_plan(ui, plan)
    ui.info(
        "Antes de la primera escritura se creará y validará un respaldo completo bajo "
        f"{get_backups_dir() / 'database-updates' / target_name}."
    )
    confirmation = ui.text_input(
        f"Escribe exactamente {target_name} para confirmar",
        key=f"database_update_confirmation_{plan.fingerprint}",
    )
    policies_complete = len(policies) == len(plan.conflicts)
    enabled = plan.can_apply and confirmation == target_name and policies_complete
    cancel_column, apply_column = ui.columns(2)
    if cancel_column.button("Cancelar"):
        ui.session_state.pop(_PLAN_KEY, None)
        ui.session_state.pop(_FAILURE_KEY, None)
        ui.rerun()
    if apply_column.button(
        f"Actualizar {target_name}",
        disabled=not enabled,
        type="primary",
    ):
        try:
            with ui.spinner("Creando respaldo y aplicando el plan..."):
                report = apply_database_update(
                    archive_path,
                    target,
                    plan,
                    conflict_policies=policies,
                )
        except DatabaseUpdateApplyError as exc:
            ui.session_state[_FAILURE_KEY] = exc
            ui.error(str(exc))
            ui.info(f"Respaldo previo disponible: {exc.backup_path}")
        except Exception as exc:
            ui.error(f"La actualización no inició: {exc}")
        else:
            ui.session_state.pop(_PLAN_KEY, None)
            ui.session_state.pop(_FAILURE_KEY, None)
            ui.success(
                f"{target_name} fue actualizada. Se agregaron {report.inserted} documentos, "
                f"se omitieron {report.identical} idénticos y quedaron "
                f"{report.conflicts_preserved} conflictos sin modificar."
            )
            if report.replaced:
                ui.warning(f"El respaldo prevaleció en {report.replaced} conflictos confirmados.")
            if report.conflicts_preserved:
                ui.warning(
                    f"No se modificaron {report.conflicts_preserved} documentos porque la base "
                    "y el respaldo contienen versiones diferentes."
                )
            ui.info(f"Respaldo previo validado: {report.backup_path}")
    _render_recovery(ui, current_mongo, target_name)


def render_database_import_page(ui: Any, current_mongo: Any) -> None:
    """Render both import modes while keeping all writes inside services."""
    ui.header("Database Import")
    ui.caption(f"Tiempo limite: {IMPORT_TIMEOUT_SECONDS}s")
    if current_mongo is None:
        ui.error("Database Import requiere una conexión MongoDB activa.")
        return
    mode = ui.radio(
        "Modo de importación",
        [CREATE_MODE, UPDATE_MODE],
        horizontal=True,
    )
    update_selection = _render_update_selection(ui, current_mongo) if mode == UPDATE_MODE else None
    if mode == UPDATE_MODE and update_selection is None:
        return
    uploaded_file = ui.file_uploader("Carga un respaldo de base (.zip)", type=["zip"])
    if uploaded_file is None:
        return
    with _staged_upload(uploaded_file) as archive_path:
        try:
            inspection = (
                inspect_export_zip(archive_path)
                if mode == CREATE_MODE
                else inspect_update_archive(archive_path)
            )
            _render_archive_preview(ui, inspection)
            ui.divider()
            if mode == CREATE_MODE:
                _render_create_mode(ui, archive_path, current_mongo)
            else:
                assert update_selection is not None
                target_name, strategy = update_selection
                _render_update_mode(
                    ui,
                    archive_path,
                    inspection,
                    current_mongo,
                    target_name=target_name,
                    strategy=strategy,
                )
        except Exception as exc:
            ui.error(f"El respaldo no es válido y no se escribió ningún dato: {exc}")


__all__ = [
    "CREATE_MODE",
    "STRATEGY_LABELS",
    "UPDATE_MODE",
    "list_existing_update_databases",
    "new_database_target",
    "render_database_import_page",
    "validate_new_database_target",
]
