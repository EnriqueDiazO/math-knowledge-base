"""Maintenance page; extracted without import-time rendering."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from editor.utils.cleanup_exports import cleanup_old_graph_runtime_files
from editor.utils.cleanup_exports import delete_files_safely
from editor.utils.cleanup_exports import empty_directory_contents_safely
from editor.utils.cleanup_exports import find_legacy_root_graph_files
from editor.utils.cleanup_exports import format_bytes
from editor.utils.cleanup_exports import list_deletable_files
from editor.utils.cleanup_exports import move_legacy_root_graph_files_to_runtime
from editor.utils.cleanup_exports import scan_cleanup_dirs
from mathkb_config import CLEANUP_BACKUP_DIR
from mathkb_config import CLEANUP_LOG_FILE
from mathkb_config import EXPORT_CLEANUP_DIRS
from mathkb_config import GRAPH_CLEANUP_DIRS
from mathkb_config import GRAPH_RUNTIME_DIR
from mathkb_config import PROJECT_ROOT


def _cleanup_display_path(path: str | Path) -> str:
    target = Path(path).expanduser()
    try:
        return str(target.resolve(strict=False).relative_to(PROJECT_ROOT))
    except ValueError:
        return str(target)


def _cleanup_candidate_size(path: Path) -> int:
    try:
        if path.is_dir() and not path.is_symlink():
            return sum(_cleanup_candidate_size(child) for child in path.iterdir())
        return path.lstat().st_size
    except OSError:
        return 0


def _cleanup_candidate_rows(candidates: list[Path], limit: int = 30) -> list[dict]:
    rows = []
    for path in candidates[:limit]:
        rows.append(
            {
                "Ruta": _cleanup_display_path(path),
                "Tipo": "carpeta" if path.is_dir() and not path.is_symlink() else "archivo",
                "Tamaño": format_bytes(_cleanup_candidate_size(path)),
            }
        )
    return rows


def _collect_cleanup_candidates(paths: list[Path], mode: str, older_than_days: int | None = None) -> list[Path]:
    candidates: list[Path] = []
    for path in paths:
        candidates.extend(list_deletable_files(path, mode=mode, older_than_days=older_than_days))
    return sorted(candidates, key=lambda item: str(item).lower())


def _merge_cleanup_results(results: list[dict]) -> dict:
    merged = {
        "deleted_files": 0,
        "deleted_dirs": 0,
        "moved_files": 0,
        "moved_dirs": 0,
        "bytes_freed": 0,
        "errors": [],
        "backup_dir": "",
    }
    for result in results:
        for key in ("deleted_files", "deleted_dirs", "moved_files", "moved_dirs", "bytes_freed"):
            merged[key] += int(result.get(key, 0) or 0)
        merged["errors"].extend(result.get("errors", []) or [])
        if result.get("backup_dir"):
            merged["backup_dir"] = result["backup_dir"]
    return merged


def _render_cleanup_candidates(title: str, candidates: list[Path]) -> None:
    st.markdown(f"**{title}: {len(candidates)} elementos**")
    if not candidates:
        st.info("No hay candidatos para esta acción.")
        return
    total_bytes = sum(_cleanup_candidate_size(path) for path in candidates)
    st.caption(f"Tamaño aproximado: {format_bytes(total_bytes)}")
    st.dataframe(pd.DataFrame(_cleanup_candidate_rows(candidates)), width="stretch", hide_index=True)
    if len(candidates) > 30:
        st.caption(f"Mostrando 30 de {len(candidates)} elementos candidatos.")


def _render_cleanup_result(result: dict) -> None:
    moved = int(result.get("moved_files", 0) or 0)
    deleted = int(result.get("deleted_files", 0) or 0)
    dirs = int(result.get("deleted_dirs", 0) or 0) + int(result.get("moved_dirs", 0) or 0)
    action = "movidos a respaldo" if moved else "eliminados"
    st.success(
        f"Limpieza completada. Archivos {action}: {moved or deleted}. "
        f"Carpetas procesadas: {dirs}. Espacio liberado: {format_bytes(result.get('bytes_freed', 0))}."
    )
    if result.get("backup_dir"):
        st.info(f"Respaldo creado en `{result['backup_dir']}`.")
    if result.get("errors"):
        st.warning("Algunos archivos no pudieron procesarse.")
        st.write(result["errors"][:10])


def _render_cleanup_maintenance_page() -> None:
    st.title("🧹 Mantenimiento / Limpieza de exportaciones")
    monitored_paths = list(EXPORT_CLEANUP_DIRS) + list(GRAPH_CLEANUP_DIRS)

    st.info(
        "Estas acciones sólo operan sobre archivos generados en disco. "
        "No borran conceptos, relaciones ni documentos en MongoDB."
    )
    st.caption(f"Respaldos: `{CLEANUP_BACKUP_DIR}` · Log: `{CLEANUP_LOG_FILE}`")

    st.markdown("**Carpetas monitoreadas**")
    st.write([str(path) for path in monitored_paths])

    if st.button("🔍 Escanear carpetas de exportación", key="cleanup_scan_dirs"):
        st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)

    scan_results = st.session_state.get("cleanup_scan_results")
    if scan_results:
        stats_rows = [
            {
                "Carpeta": _cleanup_display_path(result["path"]),
                "Existe": "sí" if result["exists"] else "no",
                "Permitida": "sí" if result["allowed"] else "no",
                "Archivos": result["files"],
                "Subcarpetas": result["subdirs"],
                "Tamaño": result["total_size"],
                "Última modificación": result["newest_modified"],
                "Extensiones": ", ".join(
                    f"{extension}:{count}" for extension, count in result["extensions"].items()
                ),
            }
            for result in scan_results
        ]
        st.dataframe(pd.DataFrame(stats_rows), width="stretch", hide_index=True)
        with st.expander("Vista previa de archivos encontrados", expanded=False):
            for result in scan_results:
                st.markdown(f"**{_cleanup_display_path(result['path'])}**")
                if result["preview"]:
                    st.write(result["preview"])
                else:
                    st.caption("Sin archivos detectados.")
    else:
        st.info("Presiona Escanear carpetas para ver conteos, tamaños y una vista previa.")

    move_to_backup = st.checkbox(
        "📦 Mover a respaldo en vez de borrar",
        value=True,
        key="cleanup_move_to_backup",
    )

    st.divider()
    st.subheader("🧹 Limpiar temporales de compilación")
    temp_candidates = _collect_cleanup_candidates(monitored_paths, mode="temp")
    _render_cleanup_candidates("Temporales detectados", temp_candidates)
    confirm_temp = st.checkbox(
        "Entiendo que esto procesará sólo temporales de compilación dentro de las carpetas permitidas.",
        key="cleanup_confirm_temp",
    )
    if st.button("🧹 Limpiar temporales de compilación", key="cleanup_delete_temp"):
        if not confirm_temp:
            st.error("Marca la confirmación antes de limpiar temporales.")
        else:
            _render_cleanup_result(delete_files_safely(temp_candidates, move_to_backup=move_to_backup))
            st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)

    st.divider()
    st.subheader("🕒 Limpiar exportaciones antiguas")
    age_options = {"1 día": 1, "7 días": 7, "30 días": 30, "90 días": 90}
    age_label = st.selectbox(
        "Borrar archivos con antigüedad mayor a",
        list(age_options),
        index=2,
        key="cleanup_old_age",
    )
    old_candidates = _collect_cleanup_candidates(
        monitored_paths,
        mode="old_exports",
        older_than_days=age_options[age_label],
    )
    _render_cleanup_candidates("Exportaciones antiguas detectadas", old_candidates)
    confirm_old = st.checkbox(
        "Entiendo que esto procesará PDF, HTML, JSON, ZIP y TeX antiguos en carpetas permitidas.",
        key="cleanup_confirm_old",
    )
    if st.button("🧹 Limpiar exportaciones antiguas", key="cleanup_delete_old"):
        if not confirm_old:
            st.error("Marca la confirmación antes de limpiar exportaciones antiguas.")
        else:
            _render_cleanup_result(delete_files_safely(old_candidates, move_to_backup=move_to_backup))
            st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)

    st.divider()
    st.subheader("🧭 Temporales de grafos")
    graph_hours = st.number_input(
        "Eliminar temporales de grafos con más de horas",
        min_value=1,
        max_value=24 * 30,
        value=24,
        step=1,
        key="cleanup_graph_runtime_hours",
    )
    confirm_graph = st.checkbox(
        f"Entiendo que esto sólo limpiará HTML/JSON antiguos en `{GRAPH_RUNTIME_DIR}`.",
        key="cleanup_confirm_graph_runtime",
    )
    if st.button("🧹 Limpiar temporales de grafos", key="cleanup_delete_graph_runtime"):
        if not confirm_graph:
            st.error("Marca la confirmación antes de limpiar temporales de grafos.")
        else:
            _render_cleanup_result(cleanup_old_graph_runtime_files(max_age_hours=int(graph_hours)))
            st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)

    legacy_graph_files = find_legacy_root_graph_files()
    _render_cleanup_candidates("Archivos legacy de grafo en la raíz", legacy_graph_files)
    confirm_legacy = st.checkbox(
        "Entiendo que esto copiará archivos legacy de grafo a runtime y conservará los originales.",
        key="cleanup_confirm_legacy_graphs",
    )
    if st.button("📦 Copiar grafos legacy a runtime", key="cleanup_move_legacy_graphs"):
        if not confirm_legacy:
            st.error("Marca la confirmación antes de mover archivos legacy.")
        else:
            _render_cleanup_result(move_legacy_root_graph_files_to_runtime())
            st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)

    st.divider()
    st.subheader("🗑️ Vaciar carpetas de exportación")
    st.warning(
        "Esta acción procesa todo el contenido de las carpetas monitoreadas, preservando las carpetas raíz. "
        "Requiere checkbox y la palabra LIMPIAR."
    )
    all_candidates = _collect_cleanup_candidates(monitored_paths, mode="all")
    _render_cleanup_candidates("Contenido que se procesaría", all_candidates)
    confirm_all = st.checkbox(
        "Entiendo que esto vaciará contenido exportado en disco y no tocará MongoDB.",
        key="cleanup_confirm_all",
    )
    confirm_word = st.text_input("Escribe LIMPIAR para confirmar", key="cleanup_confirm_word")
    if st.button("🗑️ Vaciar carpetas de exportación", key="cleanup_empty_dirs"):
        if not confirm_all or confirm_word.strip() != "LIMPIAR":
            st.error("Activa la confirmación y escribe LIMPIAR exactamente.")
        else:
            results = [
                empty_directory_contents_safely(path, move_to_backup=move_to_backup)
                for path in monitored_paths
            ]
            _render_cleanup_result(_merge_cleanup_results(results))
            st.session_state["cleanup_scan_results"] = scan_cleanup_dirs(monitored_paths)
