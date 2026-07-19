import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import bibtexparser
import pandas as pd
import streamlit as st
from bson import ObjectId
from streamlit_ace import st_ace

from editor.db.concept_edit_service import ConceptEditStatus
from editor.db.concept_edit_service import update_concept_fields_preserving_identity
from editor.db.concept_repository import concept_exists
from editor.database_import_page import render_database_import_page
from editor.pdf_preview import PdfPreviewError
from editor.pdf_preview import clear_pdf_preview
from editor.pdf_preview import generate_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.reading_space.reader_page import render_reading_space_page
from editor.reading_space.state import READING_SPACE_NAV_LABEL
from editor.reading_space.state import add_reading_space_navigation
from editor.reading_space.state import apply_pending_navigation as apply_pending_reading_navigation
from editor.reading_space.state import sync_database_state as sync_reading_database_state

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit.components.v1 as components
from helpers.concept_builders import build_concept_metadata
from pdf_export import generar_pdf_desde_formulario

from db.concept_repository import insert_concept_with_latex_atomic
from editor.document_builder import render_document_builder_page
from editor.helpers.managed_source_selection import can_save_with_managed_source
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from editor.helpers.managed_source_selection import source_labels
from editor.helpers.tipo_aplicacion import TipoAplicacion
from editor.helpers.tipo_contexto import NivelContexto
from editor.helpers.tipo_formalidad import GradoFormalidad
from editor.helpers.tipo_presentacion import TipoPresentacion
from editor.helpers.tipo_referencia import TipoReferencia
from editor.helpers.tipo_relacion import TipoRelacion
from editor.helpers.tipo_simbolico import NivelSimbolico
from editor.helpers.tipo_titulo import TipoTitulo
from editor.source_catalog.add_source_page import render_add_source_page
from editor.source_catalog.edit_source_page import render_edit_source_page
from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.shared import safe_error_message as safe_catalog_error
from editor.source_catalog.state import ADD_SOURCE_NAV_LABEL
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import NAVIGATION_WIDGET
from editor.source_catalog.state import add_source_catalog_navigation
from editor.source_catalog.state import apply_pending_navigation
from editor.source_catalog.state import consume_legacy_concept_open
from editor.source_catalog.state import state_key as source_catalog_state_key
from editor.source_catalog.state import sync_database_state
from editor.utils.cleanup_exports import cleanup_old_graph_runtime_files
from editor.utils.cleanup_exports import delete_files_safely
from editor.utils.cleanup_exports import empty_directory_contents_safely
from editor.utils.cleanup_exports import find_legacy_root_graph_files
from editor.utils.cleanup_exports import format_bytes
from editor.utils.cleanup_exports import list_deletable_files
from editor.utils.cleanup_exports import move_legacy_root_graph_files_to_runtime
from editor.utils.cleanup_exports import scan_cleanup_dirs
from editor.utils.db_export import export_database_to_zip
from editor.utils.knowledge_graph_sync import add_concepts_to_graph_state
from editor.utils.knowledge_graph_sync import concept_graph_node_errors
from editor.utils.knowledge_graph_sync import concept_graph_node_warnings
from editor.utils.knowledge_graph_sync import concept_key
from editor.utils.knowledge_graph_sync import concept_table_rows
from editor.utils.knowledge_graph_sync import concepts_by_keys
from editor.utils.knowledge_graph_sync import default_sync_settings
from editor.utils.knowledge_graph_sync import detect_missing_source_concepts
from editor.utils.knowledge_graph_sync import find_available_concepts
from editor.utils.knowledge_graph_sync import graph_state_integrity_issues
from editor.utils.knowledge_graph_sync import incomplete_node_ids
from editor.utils.knowledge_graph_sync import infer_concept_types_from_graph_state
from editor.utils.knowledge_graph_sync import infer_sources_from_graph_state
from editor.utils.knowledge_graph_sync import isolated_node_ids
from editor.utils.knowledge_graph_sync import map_node_rows
from editor.utils.knowledge_graph_sync import merge_ordered_values
from editor.utils.knowledge_graph_sync import merge_preserved_graph_items
from editor.utils.knowledge_graph_sync import primary_sources
from editor.utils.knowledge_graph_sync import remove_nodes_from_graph_state
from editor.utils.knowledge_graph_sync import repair_incomplete_graph_nodes
from editor.utils.knowledge_graph_sync import utc_timestamp
from editor.utils.media_assets import ALLOWED_IMAGE_EXTENSIONS
from editor.utils.media_assets import LATEX_IMAGE_EXTENSIONS
from editor.utils.media_assets import detach_media_asset_from_concept
from editor.utils.media_assets import detect_heavy_tikz
from editor.utils.media_assets import get_concept_media_assets
from editor.utils.media_assets import html_image_snippet
from editor.utils.media_assets import latex_includegraphics_snippet
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import resolve_media_asset_path
from editor.utils.media_assets import save_media_asset
from editor.validators.concept_validator import validate_new_concept_identity
from editor.validators.concept_validator import validate_semantic_duplicate
from exporters_latex.exportadorlatex import ExportadorLatex
from exporters_latex.latex_compile import latex_timeout_message
from exporters_latex.latex_compile import output_tail
from exporters_latex.latex_compile import run_latex_until_stable
from exporters_latex.latex_validation import validate_latex_fragment
from exporters_quarto.quarto_exporter import QuartoBookExporter

# Render preview graph using the same renderer as "Knowledge Graph"
from mathdatabase.mathmongo import MathMongo
from mathdatabase.mathmongo import MongoIndexInitializationError
from mathkb_config import CLEANUP_BACKUP_DIR
from mathkb_config import CLEANUP_LOG_FILE
from mathkb_config import EXPORT_CLEANUP_DIRS
from mathkb_config import EXPORT_COLLECTIONS
from mathkb_config import EXPORT_TIMEOUT_SECONDS
from mathkb_config import GRAPH_CLEANUP_DIRS
from mathkb_config import GRAPH_RUNTIME_DIR
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS
from mathkb_config import PROJECT_ROOT
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.paths import get_backups_dir
from mathmongo.paths import get_exports_dir
from mathmongo.paths import get_latex_runtime_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path
from schemas.schemas import ConceptoBase
from visualizations.grafoconocimiento import GrafoConocimiento

DEBUG_KNOWLEDGE_GRAPH = os.getenv("DEBUG_KNOWLEDGE_GRAPH", "0") == "1"


def _concept_pdf_download_name(concept_data: dict) -> str:
    """Return a safe leaf filename without exposing an internal filesystem path."""
    concept_id = str(concept_data.get("id") or "concept")
    concept_type = str(concept_data.get("tipo") or "concept")
    safe_id = concept_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_type = concept_type.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"{safe_id or 'concept'}_{safe_type or 'concept'}.pdf"


def _generate_concept_pdf_preview(
    namespace: str,
    concept_data: dict,
    *,
    context_identity: str,
    allowed_root: Path,
) -> None:
    """Generate, validate, and store one concept preview for internal rendering."""
    try:
        with st.spinner("🔄 Generando PDF..."):
            generate_pdf_preview(
                st.session_state,
                namespace,
                generator=lambda: generar_pdf_desde_formulario(concept_data),
                allowed_root=allowed_root,
                file_name=_concept_pdf_download_name(concept_data),
                context_identity=context_identity,
            )
        st.success("✅ PDF generado y disponible en la vista previa.")
    except PdfPreviewError as exc:
        st.error(f"❌ No se pudo preparar la vista previa PDF. {exc}")
    except Exception as exc:
        diagnostic = getattr(exc, "diagnostic", {})
        known_stages = {
            "Generar contenido LaTeX",
            "Preparar datos",
            "Escribir archivo TEX",
            "Analizar TEX con ChkTeX",
            "Ejecutar compilador LaTeX",
            "Verificar PDF generado",
            "Entregar PDF",
        }
        stage = diagnostic.get("stage") if isinstance(diagnostic, dict) else None
        safe_stage = stage if stage in known_stages else "Generar PDF"
        st.error(
            "❌ No se pudo generar el PDF. "
            f"Etapa: {safe_stage}. Revisa el contenido LaTeX y vuelve a intentarlo."
        )


def _kg_debug(message: str, **kwargs) -> None:
    if DEBUG_KNOWLEDGE_GRAPH:
        detail = " ".join(f"{key}={value}" for key, value in kwargs.items())
        print(f"[KG] {message}" + (f" {detail}" if detail else ""))


def _parse_knowledge_graph_state_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Pega primero el JSON del estado actual del grafo.")

    payload = json.loads(text)
    graph_state = payload.get("graph_state", payload) if isinstance(payload, dict) else None
    if not isinstance(graph_state, dict):
        raise ValueError("El JSON debe ser un objeto con el estado del grafo.")
    if not isinstance(graph_state.get("nodes"), list) or not isinstance(graph_state.get("edges"), list):
        raise ValueError("El estado debe incluir listas 'nodes' y 'edges'.")
    return graph_state


def _knowledge_graph_map_label(doc: dict) -> str:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    sources = filters.get("sources") or []
    concept_types = filters.get("concept_types") or []
    relation_types = filters.get("relation_types") or []
    updated_at = doc.get("updated_at") or doc.get("created_at")
    if isinstance(updated_at, datetime):
        updated_text = updated_at.strftime("%Y-%m-%d %H:%M")
    else:
        updated_text = str(updated_at or "sin fecha")
    return (
        f"{doc.get('name', 'Mapa sin nombre')} · {updated_text} · "
        f"{len(sources)} fuentes · {len(concept_types)} tipos · {len(relation_types)} relaciones"
    )


def _knowledge_graph_map_id_query(map_id: object) -> dict:
    id_text = str(map_id)
    candidates = [id_text]
    try:
        candidates.append(ObjectId(id_text))
    except Exception:
        pass
    return {"_id": {"$in": candidates}}


def _find_knowledge_graph_map(maps_col, map_id: object) -> dict | None:
    return maps_col.find_one(_knowledge_graph_map_id_query(map_id))


def _knowledge_graph_state_counts(graph_state: dict) -> tuple[int, int]:
    if not isinstance(graph_state, dict):
        return 0, 0
    nodes = graph_state.get("nodes") if isinstance(graph_state.get("nodes"), list) else []
    edges = graph_state.get("edges") if isinstance(graph_state.get("edges"), list) else []
    return len(nodes), len(edges)


def merge_sources_before_widget_creation(map_id: object, saved_sources: list[str], graph_state: dict) -> list[str]:
    """Merge saved sources with graph-inferred sources before Streamlit widgets exist."""
    del map_id
    return merge_ordered_values(saved_sources, infer_sources_from_graph_state(graph_state))


def merge_concept_types_before_widget_creation(
    map_id: object,
    saved_types: list[str],
    graph_state: dict,
) -> list[str]:
    """Merge saved concept types with graph-inferred types before widgets exist."""
    del map_id
    return merge_ordered_values(saved_types, infer_concept_types_from_graph_state(graph_state))


def _kg_edit_form_state_key(map_id: str) -> str:
    return f"kg_edit_form_state_{map_id}"


def _kg_edit_pending_widget_key(map_id: str) -> str:
    return f"kg_edit_pending_widget_updates_{map_id}"


def _kg_edit_widget_keys(map_id: str) -> dict[str, str]:
    return {
        "name": f"kg_edit_name_widget_{map_id}",
        "description": f"kg_edit_description_widget_{map_id}",
        "tags": f"kg_edit_tags_widget_{map_id}",
        "sources": f"kg_edit_sources_widget_{map_id}",
        "concept_types": f"kg_edit_concept_types_widget_{map_id}",
        "relation_types": f"kg_edit_relation_types_widget_{map_id}",
        "max_depth": f"kg_edit_max_depth_widget_{map_id}",
        "use_pasted_state_json": f"kg_edit_use_pasted_state_json_widget_{map_id}",
        "graph_state_json": f"kg_edit_graph_state_json_widget_{map_id}",
    }


def _kg_edit_form_state_from_doc(map_id: str, edit_doc: dict, graph_state: dict) -> dict:
    filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
    return {
        "name": edit_doc.get("name", ""),
        "description": edit_doc.get("description", ""),
        "tags": ", ".join(edit_doc.get("tags", []) or []),
        "sources": merge_sources_before_widget_creation(map_id, filters.get("sources", []), graph_state),
        "concept_types": merge_concept_types_before_widget_creation(
            map_id,
            filters.get("concept_types", []),
            graph_state,
        ),
        "relation_types": list(filters.get("relation_types", []) or []),
        "max_depth": min(5, max(1, int(filters.get("max_depth", 3) or 3))),
        "use_pasted_state_json": False,
        "graph_state_json": "",
    }


def _queue_kg_edit_widget_update(map_id: str, updates: dict) -> None:
    pending_key = _kg_edit_pending_widget_key(map_id)
    pending = st.session_state.get(pending_key, {})
    if not isinstance(pending, dict):
        pending = {}
    pending.update(updates)
    st.session_state[pending_key] = pending


def _sync_kg_edit_form_state_from_graph(map_id: str, graph_state: dict) -> dict:
    form_state_key = _kg_edit_form_state_key(map_id)
    form_state = st.session_state.get(form_state_key, {})
    if not isinstance(form_state, dict):
        form_state = {}
    form_state["sources"] = merge_sources_before_widget_creation(
        map_id,
        form_state.get("sources", []),
        graph_state,
    )
    form_state["concept_types"] = merge_concept_types_before_widget_creation(
        map_id,
        form_state.get("concept_types", []),
        graph_state,
    )
    st.session_state[form_state_key] = form_state
    return form_state


def _apply_kg_edit_widget_updates_before_creation(map_id: str, form_state: dict, graph_state: dict) -> dict:
    widget_keys = _kg_edit_widget_keys(map_id)
    pending_key = _kg_edit_pending_widget_key(map_id)
    pending = st.session_state.pop(pending_key, {})
    if not isinstance(pending, dict):
        pending = {}

    for field, key in widget_keys.items():
        base_value = pending.get(field, form_state.get(field))
        if field == "sources":
            current_value = st.session_state.get(key, base_value)
            value = merge_sources_before_widget_creation(map_id, current_value, graph_state)
            st.session_state[key] = value
            form_state[field] = value
        elif field == "concept_types":
            current_value = st.session_state.get(key, base_value)
            value = merge_concept_types_before_widget_creation(map_id, current_value, graph_state)
            st.session_state[key] = value
            form_state[field] = value
        elif key not in st.session_state or field in pending:
            st.session_state[key] = base_value
            form_state[field] = base_value
        else:
            form_state[field] = st.session_state[key]

    st.session_state[_kg_edit_form_state_key(map_id)] = form_state
    return widget_keys


def _knowledge_graph_map_summary(doc: dict) -> dict:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
    sources = filters.get("sources", []) if isinstance(filters.get("sources"), list) else []
    concept_types = filters.get("concept_types", []) if isinstance(filters.get("concept_types"), list) else []
    relation_types = filters.get("relation_types", []) if isinstance(filters.get("relation_types"), list) else []
    nodes, edges = _knowledge_graph_state_counts(doc.get("graph_state", {}))
    updated_at = doc.get("updated_at") or doc.get("created_at")
    updated_text = updated_at.strftime("%Y-%m-%d %H:%M") if isinstance(updated_at, datetime) else str(updated_at or "")
    description = str(doc.get("description", "") or "")
    return {
        "Nombre": doc.get("name", "Mapa sin nombre"),
        "Descripción": description[:90] + ("..." if len(description) > 90 else ""),
        "Tags": ", ".join(tags),
        "Fuentes": ", ".join(sources),
        "Tipos concepto": ", ".join(concept_types),
        "Tipos relación": ", ".join(relation_types),
        "Última actualización": updated_text,
        "Nodos": nodes,
        "Aristas": edges,
    }


def _render_knowledge_graph_map_html(graph_state: dict, map_key: str) -> str:
    del map_key
    grafo = GrafoConocimiento([], [])
    return grafo.exportar_html(salida=None, initial_state=graph_state)


def _render_knowledge_graph_map_metadata(doc: dict) -> None:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")
    st.caption(doc.get("description", "") or "Sin descripción.")
    st.write(f"**Tags:** {', '.join(tags) if tags else 'Sin tags'}")
    st.write(f"**Fuentes:** {', '.join(filters.get('sources', []) or []) or 'Sin fuentes'}")
    st.write(f"**Tipos de concepto:** {', '.join(filters.get('concept_types', []) or []) or 'Sin tipos'}")
    st.write(f"**Tipos de relación:** {', '.join(filters.get('relation_types', []) or []) or 'Sin relaciones'}")
    st.write(f"**Max depth:** {filters.get('max_depth', 'N/D')}")
    if created_at:
        st.write(f"**Creado:** {created_at}")
    if updated_at:
        st.write(f"**Actualizado:** {updated_at}")


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


def _media_tags_from_text(raw: str) -> list[str]:
    return [tag.strip() for tag in (raw or "").split(",") if tag.strip()]


def _render_tikz_weight_warnings(latex: str) -> None:
    for warning in detect_heavy_tikz(latex):
        st.warning(warning)


def _render_media_asset_preview(asset: dict) -> None:
    path = Path(asset.get("path") or "")
    actual_path = resolve_media_asset_path(asset)
    suffix = path.suffix.lower()
    if not media_path_exists(asset):
        st.error(f"Imagen faltante: {asset.get('path')}")
        return
    if suffix == ".pdf":
        st.write(f"PDF image asset: `{asset.get('path')}`")
    else:
        st.image(str(actual_path), caption=asset.get("description") or asset.get("filename"))


def _render_concept_media_manager(
    mongo: MathMongo,
    concept_id: str,
    source: str,
    *,
    prefix: str,
    latex_insert_key: str,
    insert_flag_key: str,
) -> list[dict]:
    st.subheader("🖼️ Images")
    st.caption("Use rutas relativas como `media/images/name.png`; evita rutas absolutas.")

    if not concept_id or not source:
        st.info("Define ID y source antes de asociar imágenes.")
        return []

    uploaded_files = st.file_uploader(
        "Upload image assets",
        type=[ext.lstrip(".") for ext in ALLOWED_IMAGE_EXTENSIONS],
        accept_multiple_files=True,
        key=f"{prefix}_media_upload",
    )
    media_description = st.text_input("Image description/caption", key=f"{prefix}_media_description")
    media_tags = st.text_input("Image tags (comma-separated)", key=f"{prefix}_media_tags")

    if st.button("Guardar imágenes", key=f"{prefix}_save_media"):
        if not uploaded_files:
            st.warning("Selecciona al menos una imagen.")
        else:
            saved_assets = []
            for uploaded in uploaded_files:
                try:
                    asset = save_media_asset(
                        mongo,
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                        concept_id=concept_id,
                        source=source,
                        tags=_media_tags_from_text(media_tags),
                        description=media_description,
                    )
                    saved_assets.append(asset)
                except Exception as exc:
                    st.error(f"No se pudo guardar {uploaded.name}: {exc}")
            if saved_assets:
                st.success(f"Guardadas {len(saved_assets)} imagen(es).")
                for asset in saved_assets:
                    st.code(latex_includegraphics_snippet(asset, caption=media_description), language="latex")

    assets = get_concept_media_assets(mongo, concept_id, source)
    if not assets:
        st.info("Este concepto todavía no tiene imágenes asociadas.")
        return []

    for asset in assets:
        label = f"{asset.get('filename', 'image')} · {asset.get('path', '')}"
        with st.expander(label, expanded=False):
            _render_media_asset_preview(asset)
            suffix = Path(asset.get("path") or "").suffix.lower()
            if suffix == ".svg":
                st.warning("SVG se puede previsualizar en HTML, pero pdflatex no lo incluye sin conversión.")
            elif suffix not in LATEX_IMAGE_EXTENSIONS:
                st.warning("Este formato puede no compilar con pdflatex.")
            latex_snippet = latex_includegraphics_snippet(
                asset,
                caption=asset.get("description") or asset.get("filename") or "",
            )
            st.code(latex_snippet, language="latex")
            st.code(html_image_snippet(asset), language="html")
            if st.button("Insertar LaTeX", key=f"{prefix}_insert_media_{asset.get('asset_id')}"):
                st.session_state[latex_insert_key] = latex_snippet
                st.session_state[insert_flag_key] = True
                st.rerun()
            delete_unused = st.checkbox(
                "Eliminar archivo si queda sin uso",
                key=f"{prefix}_delete_unused_{asset.get('asset_id')}",
            )
            if st.button("Desasociar imagen", key=f"{prefix}_detach_media_{asset.get('asset_id')}"):
                deleted = detach_media_asset_from_concept(
                    mongo,
                    asset_id=asset.get("asset_id"),
                    concept_id=concept_id,
                    source=source,
                    delete_if_unreferenced=delete_unused,
                )
                if deleted:
                    st.success("Imagen desasociada y archivo eliminado porque no tenía más referencias.")
                else:
                    st.success("Imagen desasociada del concepto.")
                st.rerun()

    return assets


def _source_from_graph_endpoint(value) -> str | None:
    if not isinstance(value, str) or "@" not in value:
        return None
    source = value.rsplit("@", 1)[1].strip()
    return source or None


def _knowledge_graph_source_options(mongo: MathMongo, saved_maps: list[dict] | None = None) -> list[str]:
    sources = set()

    for source in mongo.concepts.distinct("source"):
        if isinstance(source, str) and source.strip():
            sources.add(source.strip())

    for field in ("desde", "hasta"):
        for endpoint in mongo.relations.distinct(field):
            source = _source_from_graph_endpoint(endpoint)
            if source:
                sources.add(source)

    for doc in saved_maps or []:
        for field in ("primary_map_source", "primary_source", "map_sources"):
            value = doc.get(field)
            for source in value if isinstance(value, list) else [value]:
                if isinstance(source, str) and source.strip():
                    sources.add(source.strip())
        filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
        for source in filters.get("sources", []) or []:
            if isinstance(source, str) and source.strip():
                sources.add(source.strip())
        for source in infer_sources_from_graph_state(doc.get("graph_state", {})):
            sources.add(source)

    return sorted(sources, key=str.lower)


def _build_knowledge_graph_state_from_filters(
    mongo: MathMongo,
    sources: list[str],
    relation_types: list[str],
    concept_types: list[str],
    previous_state: dict | None = None,
) -> dict:
    clean_sources = [source for source in sources or [] if source]
    clean_relations = [relation for relation in relation_types or [] if relation]
    clean_types = [concept_type for concept_type in concept_types or [] if concept_type]

    concept_query = {}
    if clean_sources:
        concept_query["source"] = {"$in": clean_sources}
    if clean_types:
        concept_query["tipo"] = {"$in": clean_types}
    concepts = list(mongo.concepts.find(concept_query))

    relation_query = {}
    if clean_sources:
        source_pattern = "|".join(re.escape(source) for source in clean_sources)
        relation_query["$or"] = [
            {"desde": {"$regex": f"@({source_pattern})$"}},
            {"hasta": {"$regex": f"@({source_pattern})$"}},
        ]
    if clean_relations:
        relation_query["tipo"] = {"$in": clean_relations}
    relations = list(mongo.relations.find(relation_query))

    grafo = GrafoConocimiento(concepts, relations)
    grafo.construir_grafo(tipos_relacion=clean_relations, tipos_concepto=clean_types)
    return grafo.to_graph_state(previous_state=previous_state)


def _knowledge_graph_concept_selector(concepts: list[dict], key: str) -> list[dict]:
    if not concepts:
        return []

    rows = concept_table_rows(concepts)
    rows_df = pd.DataFrame(rows)
    edited_rows = st.data_editor(
        rows_df,
        key=key,
        hide_index=True,
        width="stretch",
        column_config={
            "Agregar": st.column_config.CheckboxColumn("Agregar", default=False),
        },
        disabled=["Título", "Tipo", "Source", "ID interno", "Actualizado"],
    )
    if isinstance(edited_rows, pd.DataFrame):
        edited_records = edited_rows.to_dict("records")
    else:
        edited_records = edited_rows
    selected_keys = {
        str(row.get("ID interno"))
        for row in edited_records
        if isinstance(row, dict) and row.get("Agregar") and row.get("ID interno")
    }
    return concepts_by_keys(concepts, selected_keys)


def _knowledge_graph_node_id_selector(rows: list[dict], key: str) -> list[str]:
    if not rows:
        return []

    edited_rows = st.data_editor(
        pd.DataFrame(rows),
        key=key,
        hide_index=True,
        width="stretch",
        column_config={
            "Quitar": st.column_config.CheckboxColumn("Quitar", default=False),
        },
        disabled=["Título", "Tipo", "Source", "ID interno", "Entrantes", "Salientes", "Estado"],
    )
    if isinstance(edited_rows, pd.DataFrame):
        edited_records = edited_rows.to_dict("records")
    else:
        edited_records = edited_rows
    return [
        str(row.get("ID interno"))
        for row in edited_records
        if isinstance(row, dict) and row.get("Quitar") and row.get("ID interno")
    ]


def _bib_to_referencia(entry: dict) -> dict:
    get = entry.get

    # Autor/es
    autores = []
    if get("author"):
        for a in get("author").split(" and "):
            autores.append(a.strip())
    autores_str = "; ".join(autores) if autores else None

    # Fuente (journal/booktitle/publisher/title como fallback)
    fuente = get("journal") or get("booktitle") or get("publisher") or get("title")

    # Año
    try:
        anio = int(get("year")) if get("year") and get("year").isdigit() else None
    except Exception:
        anio = None

    # Varios campos
    paginas = get("pages").replace("--", "-").strip() if get("pages") else None
    edicion = get("edition")
    tomo = get("volume")
    capitulo = get("chapter")
    seccion = get("number") or get("issue")
    editorial = get("publisher")
    doi = get("doi")
    url = get("url")
    issbn = get("isbn") or get("issn")  # OJO: en tu modelo el campo se llama "issbn"

    return {
        "autor": autores_str,
        "fuente": fuente,
        "anio": anio,
        "tomo": tomo,
        "edicion": edicion,
        "paginas": paginas,
        "capitulo": capitulo,
        "seccion": seccion,
        "editorial": editorial,
        "doi": doi,
        "url": url,
        "issbn": issbn,
    }

def _parse_bibtex(file_bytes: bytes) -> list[dict]:
    if not bibtexparser:
        raise RuntimeError("Falta bibtexparser. Instala con: pip install bibtexparser==1.4.0")
    db = bibtexparser.loads(file_bytes.decode("utf-8", errors="ignore"))
    return db.entries or []
# ---------------------------------------------------------

def _normalize_ref_dict(ref: dict) -> dict:
    """Normaliza la referencia para soportar:
    - esquema nuevo: tipo_referencia, issbn
    - esquema viejo: tipo, isbn
    - citekey opcional.
    """  # noqa: D205
    if not isinstance(ref, dict):
        return {}

    # soporta ambos nombres de campo
    tipo = ref.get("tipo_referencia") or ref.get("tipo")
    issbn = ref.get("issbn") or ref.get("isbn")  # tu modelo usa issbn

    out = dict(ref)
    if tipo is not None:
        out["tipo_referencia"] = tipo
    if issbn is not None:
        out["issbn"] = issbn

    return out


def load_last_reference_by_source(db, source: str) -> dict | None:
    """
    Busca el último concepto (fecha_creacion DESC) del mismo source
    que tenga un campo 'referencia' utilizable.
    """  # noqa: D205, D212
    if not source or not isinstance(source, str) or not source.strip():
        return None

    query = {
        "source": source,
        "referencia": {"$exists": True, "$ne": None},
    }
    projection = {"referencia": 1, "id": 1, "titulo": 1, "fecha_creacion": 1, "_id": 0}

    doc = db.concepts.find_one(query, projection=projection, sort=[("fecha_creacion", -1)])
    if not doc:
        return None

    ref = _normalize_ref_dict(doc.get("referencia") or {})
    # “utilizable” = al menos autor o fuente o citekey (ajústalo si quieres)
    if not (ref.get("autor") or ref.get("fuente") or ref.get("citekey")):
        return None

    # (opcional) Adjunta metadatos para debug
    ref["__from_concept_id"] = doc.get("id")
    ref["__from_concept_title"] = doc.get("titulo")
    ref["__from_concept_date"] = doc.get("fecha_creacion")

    return ref



# Page configuration
st.set_page_config(
    page_title="Math Knowledge Base",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Custom CSS for better styling
st.markdown("""
<style>
    :root {
        --bg: #0B0F19;
        --panel: #111827;
        --panel-2: #0F172A;
        --border: #243244;
        --text: #E5E7EB;
        --muted: #9CA3AF;
        --accent: #60A5FA;
        --good: #22C55E;
        --bad: #EF4444;
    }

    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: var(--text);
        text-align: center;
        margin-bottom: 2rem;
    }

    /* Cards */
    .metric-card {
        background-color: var(--panel);
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border-left: 4px solid var(--accent);
        border: 1px solid var(--border);
    }

    .concept-card {
        background-color: var(--panel);
        color: var(--text);
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        margin-bottom: 1rem;
        box-shadow: none;
    }


    /* MVP: make Recent Concepts a fixed-height scroll panel */
    .recent-concepts-panel {
        max-height: 520px;
        overflow-y: auto;
        padding-right: 0.5rem;
    }

    .latex-preview {
        background-color: #0B1220;
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        font-family: monospace;
    }

    .db-connection-card {
        background-color: #0B1220;
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        margin-bottom: 1rem;
    }

    .db-status-connected {
        color: var(--good);
        font-weight: bold;
    }

    .db-status-disconnected {
        color: var(--bad);
        font-weight: bold;
    }

    /* Buttons */
    .stButton > button {
        width: 100%;
        border-radius: 0.75rem;
        background: var(--panel);
        color: var(--text);
        border: 1px solid var(--border);
    }

    /* Sidebar fix (you were forcing light) */
    [data-testid="stSidebar"] {
        background-color: var(--panel-2);
    }
</style>
""", unsafe_allow_html=True)

# Database connection management
class DatabaseManager:
    def __init__(self):
        self.connections = {}
        self.current_connection = None

    def add_connection(self, name, mongo_uri, db_name):
        """Add a new database connection."""
        try:
            connection = MathMongo(mongo_uri, db_name)
            self.connections[name] = {
                'connection': connection,
                'uri': mongo_uri,
                'db_name': db_name,
                'status': 'connected'
            }
            return True
        except MongoIndexInitializationError as e:
            safe_error = sanitize_mongo_error(e, mongo_uri)
            st.error(
                "MongoDB conectado para "
                f"{name}, pero falló la inicialización de índices:\n\n{safe_error}"
            )
            return False
        except Exception as e:
            safe_error = sanitize_mongo_error(e, mongo_uri)
            st.error(f"No se pudo conectar a MongoDB para {name}: {safe_error}")
            return False

    def get_connection(self, name):
        """Get a specific database connection."""
        return self.connections.get(name, {}).get('connection')

    def list_connections(self):
        """List all available connections."""
        return list(self.connections.keys())

    def get_current_connection(self):
        """Get the currently active connection."""
        return self.current_connection

    def set_current_connection(self, name):
        """Set the current active connection."""
        if name in self.connections:
            self.current_connection = self.connections[name]['connection']
            return True
        return False

# Initialize database manager in session state
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()
    app_settings = resolve_config()

    # Add default connections
    st.session_state.db_manager.add_connection(
        "MathMongo (Current)",
        app_settings.mongo_uri,
        app_settings.mongo_database,
    )

    # Add MathV0 connection
    st.session_state.db_manager.add_connection(
        "MathV0",
        app_settings.mongo_uri,
        "MathV0",
    )

    # Set current connection
    st.session_state.db_manager.set_current_connection("MathMongo (Current)")

# Database connection sidebar
st.sidebar.title("🧮 Math Knowledge Base")
st.sidebar.markdown("---")

# Database connection section
st.sidebar.subheader("🗄️ Database Connection")

# Show current connection
current_db = None
for name, conn_info in st.session_state.db_manager.connections.items():
    if st.session_state.db_manager.get_current_connection() == conn_info['connection']:
        current_db = name
        break

if current_db:
    st.sidebar.markdown(f"""
    <div class="db-connection-card">
        <strong>Current Database:</strong><br>
        {current_db}<br>
        <span class="db-status-connected">✅ Connected</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div class="db-connection-card">
        <strong>Current Database:</strong><br>
        <span class="db-status-disconnected">❌ Not Connected</span>
    </div>
    """, unsafe_allow_html=True)

# Database switcher
available_dbs = st.session_state.db_manager.list_connections()
if available_dbs:
    selected_db = st.sidebar.selectbox(
        "Switch Database",
        available_dbs,
        index=available_dbs.index(current_db) if current_db in available_dbs else 0
    )

    if selected_db != current_db:
        if st.session_state.db_manager.set_current_connection(selected_db):
            st.sidebar.success(f"✅ Switched to {selected_db}")
            st.rerun()

# Add new database connection
with st.sidebar.expander("➕ Add New Database", expanded=False):
    new_db_name = st.text_input("Database Name", placeholder="e.g., MathV1, ResearchDB")
    new_db_uri = st.text_input(
        "MongoDB URI",
        value=resolve_config().mongo_uri,
        type="password",
    )
    new_db_collection = st.text_input("Database Name", placeholder="e.g., mathmongo")

    if st.button("Add Connection"):
        if new_db_name and new_db_uri and new_db_collection:
            if st.session_state.db_manager.add_connection(new_db_name, new_db_uri, new_db_collection):
                st.success(f"✅ Added {new_db_name}")
                st.rerun()
        else:
            st.error("Please fill in all fields")

# Test database connection
if st.sidebar.button("🔍 Test Connection"):
    current_conn = st.session_state.db_manager.get_current_connection()
    if current_conn:
        try:
            # Test connection by getting collection count
            concept_count = current_conn.concepts.count_documents({})
            st.sidebar.success(f"✅ Connection successful! {concept_count} concepts found.")
        except Exception as e:
            st.sidebar.error(f"❌ Connection failed: {e}")
    else:
        st.sidebar.error("❌ No active connection")

st.sidebar.markdown("---")

# Get current database connection
db = st.session_state.db_manager.get_current_connection()
catalog_context = None
catalog_context_error = None
if db is not None:
    try:
        catalog_context = build_catalog_context(current_db or "<unlabeled connection>", db)
        sync_database_state(
            st.session_state,
            connection_label=catalog_context.connection_label,
            database_name=catalog_context.database_name,
            database=catalog_context.database,
        )
        sync_reading_database_state(
            st.session_state,
            connection_label=catalog_context.connection_label,
            database_name=catalog_context.database_name,
            database=catalog_context.database,
        )
    except Exception as exc:
        catalog_context_error = safe_catalog_error(exc)


def _cuaderno_is_installed(conn) -> bool:
    """Detecta si el modo cuaderno está instalado en la DB actual.

    Se considera instalado si existen las 4 colecciones base.
    """
    try:
        if conn is None:
            return False
        mongo_db = getattr(conn, "db", None)
        if mongo_db is None:
            return False
        names = set(mongo_db.list_collection_names())
        required = {
            "worklog_entries",
            "backlog_items",
            "weekly_reviews",
            "deliverables",
            "latex_notes",
            "knowledge_graph_maps",
            "media_assets",
        }
        return required.issubset(names)
    except Exception:
        return False


CPI_NAV_LABEL = "🧩 CPI"

nav_options = [
    "🏠 Dashboard",
    "➕ Add Concept",
    "✏️ Edit Concept",
    "📚 Browse Concepts",
    "🔗 Manage Relations",
    "📊 Knowledge Graph",
    "📄 Document Builder",
    "📤 Export",
    "📦 Database Export",
    "📥 Database Import",
    "🧹 Maintenance",
    "⚙️ Settings",
]
nav_options = add_source_catalog_navigation(nav_options)
nav_options = add_reading_space_navigation(nav_options)
if _cuaderno_is_installed(db):
    nav_options.append("🧪 Cuaderno")
    nav_options.append("🧾 Cornell")
    nav_options.append(CPI_NAV_LABEL)

apply_pending_navigation(st.session_state, nav_options)
apply_pending_reading_navigation(
    st.session_state,
    nav_options,
    navigation_key=NAVIGATION_WIDGET,
)
if st.session_state.get(NAVIGATION_WIDGET) not in nav_options:
    st.session_state.pop(NAVIGATION_WIDGET, None)
selected_page = st.sidebar.selectbox(
    "Navigation",
    nav_options,
    key=NAVIGATION_WIDGET,
)
page = "CPI" if selected_page == CPI_NAV_LABEL else selected_page


# Source Catalog pages
if page == ADD_SOURCE_NAV_LABEL:
    if catalog_context is None:
        st.error(
            "Source Catalog is unavailable for the selected connection: "
            f"{catalog_context_error or 'no active MongoDB database.'}"
        )
    else:
        render_add_source_page(catalog_context)

elif page == EDIT_SOURCE_NAV_LABEL:
    if catalog_context is None:
        st.error(
            "Source Catalog is unavailable for the selected connection: "
            f"{catalog_context_error or 'no active MongoDB database.'}"
        )
    else:
        render_edit_source_page(catalog_context)

elif page == READING_SPACE_NAV_LABEL:
    if catalog_context is None:
        st.error(
            "Reading Space is unavailable for the selected connection: "
            f"{catalog_context_error or 'no active MongoDB database.'}"
        )
    else:
        render_reading_space_page(catalog_context)

# Dashboard page
elif page == "🏠 Dashboard":
    st.markdown('<h1 class="main-header">Math Knowledge Base</h1>', unsafe_allow_html=True)

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    # Show current database info
    st.info(f"📊 Currently connected to: **{current_db}**")

    # Statistics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("📚 Total Concepts", concept_count)

    with col2:
        relation_count = db.relations.count_documents({})
        st.metric("🔗 Total Relations", relation_count)

    with col3:
        sources = db.concepts.distinct("source")
        st.metric("📁 Sources", len(sources))

    with col4:
        categories = db.concepts.distinct("categorias")
        st.metric("🏷️ Categories", len(categories))

    st.markdown("---")

    # Recent concepts
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📝 Recent Concepts")
        recent_concepts = list(db.concepts.find().sort("fecha_creacion", -1).limit(2))

        if recent_concepts:
            st.markdown('<div class=\"recent-concepts-panel\">', unsafe_allow_html=True)
            for concept in recent_concepts:
                with st.container():
                    st.markdown(f"""
                    <div class="concept-card">
                        <h4>{concept.get('titulo', concept['id'])}</h4>
                        <p><strong>Type:</strong> {concept['tipo']} | <strong>Source:</strong> {concept['source']}</p>
                        <p><strong>Categories:</strong> {', '.join(concept.get('categorias', []))}</p>
                        <p><strong>Created:</strong> {concept.get('fecha_creacion', 'Unknown')}</p>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No concepts found. Add your first concept!")

    with col2:
        st.subheader("📊 Quick Stats")

        # --- MVP: filter Quick Stats by Source (All vs selected) ---
        # Behavior:
        # - If "All sources" is enabled, charts use the full dataset.
        # - If disabled, user must select at least one source and charts are filtered.
        try:
            all_sources = st.toggle("All sources", value=True, key="qs_all_sources")
        except Exception:
            # Streamlit versions without st.toggle
            all_sources = st.checkbox("All sources", value=True, key="qs_all_sources")

        # Load available sources (sanitized)
        try:
            available_sources = db.concepts.distinct("source")
            available_sources = sorted(
                [s for s in available_sources if isinstance(s, str) and s.strip()],
                key=lambda x: x.lower(),
            )
        except Exception:
            available_sources = []

        selected_sources = []
        if not all_sources:
            selected_sources = st.multiselect(
                "Sources (min 1)",
                options=available_sources,
                default=available_sources[:1] if available_sources else [],
                key="qs_selected_sources",
            )
            if not selected_sources:
                st.warning("Select at least one source to filter Quick Stats.")

        # Build optional MongoDB match stage
        match_stage = None
        if (not all_sources) and selected_sources:
            match_stage = {"source": {"$in": selected_sources}}

        # Concept types distribution
        types_pipeline = []
        if match_stage:
            types_pipeline.append({"$match": match_stage})
        types_pipeline += [
            {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]

        type_data = list(db.concepts.aggregate(types_pipeline))
        if type_data:
            df_types = pd.DataFrame(type_data)
            st.bar_chart(df_types.set_index("_id")["count"])
        else:
            if match_stage:
                st.info("No data for the selected source filter.")

        # Top categories
        category_pipeline = []
        if match_stage:
            category_pipeline.append({"$match": match_stage})
        category_pipeline += [
            {"$unwind": "$categorias"},
            {"$group": {"_id": "$categorias", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]

        top_categories = list(db.concepts.aggregate(category_pipeline))
        if top_categories:
            st.write("**Top Categories:**")
            for cat in top_categories:
                st.write(f"• {cat['_id']}: {cat['count']}")

            # --- MVP: Relaciones (Sankey) por Source y Tipo ---
            # Flujo: Source (origen) -> Tipo de relacion -> Source (destino)
            # Util para ver conectividad entre fuentes y distribucion de tipos.
            with st.expander("🔗 Relations Flow (Sankey)", expanded=False):
                st.caption(
                    "MVP: resume relaciones como flujo Source -> Tipo -> Source. "
                    "Si desactivaste 'All sources' arriba, el grafico se filtra por esas sources."
                    )

                try:
                    import plotly.graph_objects as go
                except Exception:
                    st.warning("Plotly no esta disponible. Instala con: pip install plotly")
                else:
                    rels = list(db.relations.find({}, {"_id": 0, "desde": 1, "hasta": 1, "tipo": 1}))

                    def _src(key):
                        if isinstance(key, str) and "@" in key:
                            return key.rsplit("@", 1)[-1].strip()
                        return None

                    triples = []
                    for r in rels:
                        fs = _src(r.get("desde"))
                        ts = _src(r.get("hasta"))
                        rt = r.get("tipo") or "relacion"
                        if not fs or not ts:
                            continue
                        if (not all_sources) and selected_sources:
                            # Mantener relaciones donde al menos uno de los endpoints pertenece al filtro
                            if (fs not in selected_sources) and (ts not in selected_sources):
                                continue
                        triples.append((fs, rt, ts))

                    if not triples:
                        st.info("No hay relaciones suficientes para graficar con este filtro.")
                    else:
                        from collections import Counter

                        c_st = Counter((fs, rt) for fs, rt, ts in triples)
                        c_tt = Counter((rt, ts) for fs, rt, ts in triples)

                        node_ids = []
                        labels = []

                        def add_node(nid, label):
                            if nid not in node_ids:
                                node_ids.append(nid)
                                labels.append(label)

                        for fs, rt, ts in triples:
                            add_node(f"S:{fs}", fs)
                            add_node(f"T:{rt}", rt)
                            add_node(f"S:{ts}", ts)

                        idx = {nid: i for i, nid in enumerate(node_ids)}

                        sources = []
                        targets = []
                        values = []

                        for (fs, rt), v in c_st.items():
                            sources.append(idx[f"S:{fs}"])
                            targets.append(idx[f"T:{rt}"])
                            values.append(v)

                        #for (rt, ts), v in c_tt.items():
                        #    sources.append(idx[f"T:{rt}"])
                        #    targets.append(idx[f"S:{ts}"])
                        #    values.append(v)

                        fig = go.Figure(
                            data=[
                                go.Sankey(
                                    node=dict(label=labels, pad=12, thickness=12),
                                    link=dict(source=sources, target=targets, value=values),
                                )
                            ]
                        )
                        fig.update_layout(height=600, margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig, width='stretch')

            # --- MVP: Relaciones (Sankey) a nivel de conceptos ---
            # Flujo: Concepto (desde) -> Tipo de relacion -> Concepto (hasta)
            # Nota: usa llaves flexibles para soportar esquemas {desde/hasta/tipo} o {from/to/relation_type}.
            with st.expander("Concepts Flow (Sankey) [MVP]", expanded=False):
                st.caption(
                    "MVP: resume relaciones como flujo Concept -> Tipo -> Concept. "
                    "Incluye limites para evitar sobrecargar el grafico."
                )

                # Controles MVP
                c1, c2 = st.columns(2)
                with c1:
                    max_edges = st.slider(
                        "max_edges",
                        min_value=50,
                        max_value=2000,
                        value=400,
                        step=50,
                        help="Limite de relaciones (agregadas) que se grafican",
                        key="concept_sankey_max_edges",
                    )
                with c2:
                    top_concepts = st.slider(
                        "top_concepts",
                        min_value=10,
                        max_value=400,
                        value=60,
                        step=10,
                        help="Limite de conceptos por frecuencia (nodos)",
                        key="concept_sankey_top_concepts",
                    )

                try:
                    import plotly.graph_objects as go
                except Exception:
                    st.warning("Plotly no esta disponible. Instala con: pip install plotly")
                else:
                    from collections import Counter

                    def _pick(d: dict, *keys):
                        for k in keys:
                            v = d.get(k)
                            if v is not None and v != "":
                                return v
                        return None

                    def _parse_endpoint(v):
                        # Soporta:
                        # - string "id@source"
                        # - dict {id: '...', source: '...'} (o llaves equivalentes)
                        if isinstance(v, str):
                            if "@" in v:
                                a, b = v.split("@", 1)
                                a = (a or "").strip()
                                b = (b or "").strip()
                                if a and b:
                                    return f"{a}@{b}"
                            return None
                        if isinstance(v, dict):
                            cid = _pick(v, "id", "concept_id", "from_id", "to_id")
                            csrc = _pick(v, "source", "concept_source", "from_source", "to_source")
                            if isinstance(cid, str) and isinstance(csrc, str) and cid.strip() and csrc.strip():
                                return f"{cid.strip()}@{csrc.strip()}"
                        return None

                    def _src_from_key(k: str) -> str | None:
                        if isinstance(k, str) and "@" in k:
                            return k.rsplit("@", 1)[-1].strip()
                        return None

                    # Cargar relaciones (proyeccion amplia para compatibilidad)
                    try:
                        rels = list(
                            db.relations.find(
                                {},
                                {
                                    "_id": 0,
                                    "desde": 1,
                                    "hasta": 1,
                                    "tipo": 1,
                                    "from": 1,
                                    "to": 1,
                                    "relation_type": 1,
                                    "type": 1,
                                },
                            )
                        )
                    except Exception as e:
                        st.error(f"❌ Error cargando relaciones: {e}")
                        rels = []

                    triples = []
                    for r in rels:
                        a = _pick(r, "desde", "from")
                        b = _pick(r, "hasta", "to")
                        rt = _pick(r, "tipo", "relation_type", "type") or "relacion"

                        a_key = _parse_endpoint(a)
                        b_key = _parse_endpoint(b)
                        if not a_key or not b_key:
                            continue

                        # Respeta filtro por source del Dashboard (Quick Stats)
                        if (not all_sources) and selected_sources:
                            sa = _src_from_key(a_key)
                            sb = _src_from_key(b_key)
                            if (sa not in selected_sources) and (sb not in selected_sources):
                                continue

                        triples.append((a_key, str(rt), b_key))

                    if not triples:
                        st.info("No hay relaciones suficientes para graficar a nivel de conceptos con este filtro.")
                    else:
                        # -----------------------------
                        # Split por clases de relación
                        # -----------------------------
                        available_types = sorted({rt for _a, rt, _b in triples}, key=lambda x: str(x).lower())

                        def _render_concept_sankey(triples_in, selected_types, key_suffix: str):
                            # Filtrar por tipo
                            if selected_types:
                                triples_t = [(a, rt, b) for (a, rt, b) in triples_in if rt in set(selected_types)]
                            else:
                                triples_t = []

                            if not triples_t:
                                st.info("No hay relaciones para los tipos seleccionados (con el filtro actual).")
                                return

                            # Top conceptos por frecuencia (nodos)
                            freq = Counter()
                            for a_key, _rt, b_key in triples_t:
                                freq[a_key] += 1
                                freq[b_key] += 1

                            top_nodes = {k for k, _ in freq.most_common(int(top_concepts))}
                            triples_f = [(a, rt, b) for (a, rt, b) in triples_t if a in top_nodes and b in top_nodes]

                            if not triples_f:
                                st.info("No hay relaciones despues de aplicar el limite de top_concepts.")
                                return

                            # Agregar edges identicos y limitar por max_edges
                            edge_counts = Counter(triples_f)
                            top_edges = edge_counts.most_common(int(max_edges))

                            # Labels: mostrar TITULOS en lugar de IDs
                            # - Intenta usar concept.titulo / concept.title / concept.name
                            # - Si no hay titulo, cae a id
                            # - Si el titulo colisiona en multiples sources, desambigua con " — <source>"
                            def _split_key(k: str):
                                if not isinstance(k, str) or "@" not in k:
                                    return None, None
                                cid, csrc = k.split("@", 1)
                                cid = (cid or "").strip()
                                csrc = (csrc or "").strip()
                                if not cid or not csrc:
                                    return None, None
                                return cid, csrc

                            # Cache: key "id@source" -> title (solo para nodos usados)
                            concept_title_by_key = {}
                            try:
                                or_conditions = []
                                for k in top_nodes:
                                    cid, csrc = _split_key(k)
                                    if cid and csrc:
                                        or_conditions.append({"id": cid, "source": csrc})

                                if or_conditions:
                                    for doc in db.concepts.find(
                                        {"$or": or_conditions},
                                        {"_id": 0, "id": 1, "source": 1, "titulo": 1, "title": 1, "name": 1},
                                    ):
                                        _id = (doc.get("id") or "").strip()
                                        _src = (doc.get("source") or "").strip()
                                        if not _id or not _src:
                                            continue
                                        key = f"{_id}@{_src}"
                                        title = (doc.get("titulo") or doc.get("title") or doc.get("name") or "").strip()
                                        if title:
                                            concept_title_by_key[key] = title
                            except Exception:
                                concept_title_by_key = {}

                            # Detectar colisiones de titulo
                            title_counts = Counter()
                            for k in top_nodes:
                                cid, csrc = _split_key(k)
                                if not cid or not csrc:
                                    continue
                                key = f"{cid}@{csrc}"
                                t = concept_title_by_key.get(key) or cid
                                title_counts[t] += 1

                            def _concept_label(k: str) -> str:
                                cid, csrc = _split_key(k)
                                if not cid or not csrc:
                                    return str(k)
                                key = f"{cid}@{csrc}"
                                t = (concept_title_by_key.get(key) or cid).strip()
                                if title_counts.get(t, 0) > 1:
                                    return f"{t} — {csrc}"
                                return t

                            # Construir nodos y enlaces para Sankey: C -> T -> C
                            node_ids = []
                            labels = []

                            def add_node(nid: str, label: str):
                                if nid not in node_ids:
                                    node_ids.append(nid)
                                    labels.append(label)

                            for (a_key, rt, b_key), _v in top_edges:
                                add_node(f"C:{a_key}", _concept_label(a_key))
                                add_node(f"T:{rt}", rt)
                                add_node(f"C:{b_key}", _concept_label(b_key))

                            idx = {nid: i for i, nid in enumerate(node_ids)}

                            sources = []
                            targets = []
                            values = []

                            # Agregar dos capas de links: (C->T) y (T->C)
                            c_ct = Counter()
                            c_tc = Counter()
                            for (a_key, rt, b_key), v in top_edges:
                                c_ct[(a_key, rt)] += v
                                c_tc[(rt, b_key)] += v

                            for (a_key, rt), v in c_ct.items():
                                sources.append(idx[f"C:{a_key}"])
                                targets.append(idx[f"T:{rt}"])
                                values.append(v)

                            for (rt, b_key), v in c_tc.items():
                                sources.append(idx[f"T:{rt}"])
                                targets.append(idx[f"C:{b_key}"])
                                values.append(v)

                            fig = go.Figure(
                                data=[
                                    go.Sankey(
                                        node=dict(label=labels, pad=12, thickness=12),
                                        link=dict(source=sources, target=targets, value=values),
                                    )
                                ]
                            )
                            fig.update_layout(height=650, margin=dict(l=10, r=10, t=10, b=10))
                            st.plotly_chart(fig, width='stretch', key=f"concept_sankey_{key_suffix}")

                        tab_dep, tab_log = st.tabs(["🧠 Dependencies", "⚖️ Logical / Critical"])

                        with tab_dep:
                            default_dep = [t for t in ["requiere_concepto", "deriva_de"] if t in available_types]
                            sel_dep = st.multiselect(
                                "Relation types (Dependencies)",
                                options=available_types,
                                default=default_dep if default_dep else available_types[: min(3, len(available_types))],
                                help="Tipos de relación enfocados en prerequisitos y derivación.",
                                key="concept_sankey_types_dependencies",
                            )
                            _render_concept_sankey(triples, sel_dep, "dep")

                        with tab_log:
                            default_log = [t for t in ["equivalente", "implica", "contradice", "contrasta_con", "contra_ejemplo"] if t in available_types]
                            sel_log = st.multiselect(
                                "Relation types (Logical/Critical)",
                                options=available_types,
                                default=default_log if default_log else available_types[: min(5, len(available_types))],
                                help="Tipos de relación lógicos o críticos (equivalencias, implicaciones, contradicciones, etc.).",
                                key="concept_sankey_types_logical",
                                )
                            _render_concept_sankey(triples, sel_log, "log")
            # --- end MVP: concept-level sankey ---

# Add Concept page
elif page == "🧪 Cuaderno":
    from cuaderno_page import render_cuaderno
    render_cuaderno(db, _cuaderno_is_installed)
elif page == "🧾 Cornell":
    from editor.cornell.streamlit_page import render_cornell_page
    render_cornell_page(db)
elif page == "CPI":
    from editor.cpi.streamlit_page import render_cpi_page
    render_cpi_page(db)
elif page == "➕ Add Concept":
    st.title("➕ Add New Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    managed_source_repository = None
    managed_sources = ()
    managed_source_labels = {}
    managed_source_catalog_error = None
    if catalog_context is None:
        managed_source_catalog_error = catalog_context_error or "no active Source Catalog"
    else:
        managed_source_repository = catalog_context.source_repository
        try:
            managed_sources = load_active_sources(managed_source_repository)
            managed_source_labels = source_labels(managed_sources)
        except Exception as exc:
            managed_source_catalog_error = safe_catalog_error(exc)

    st.info(f"📊 Adding concept to: **{current_db}**")
    st.markdown("### 📘 Concept Type")
    # Concept type selection
    concept_type = st.selectbox(
        "Concept Type",
        ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"],
        help="Select the type of mathematical concept you want to add",
    )

    # Basic information
    st.subheader("📋 Basic Information")

    selected_source_id = None
    selected_source_preview = None
    source = None
    source_id = None
    source_selection_valid = False
    col1, col2 = st.columns(2)
    with col1:
        concept_id = st.text_input("ID", placeholder="e.g., def:grupo_001", help="Unique identifier for the concept")

        if managed_source_catalog_error is not None:
            st.error(
                "No se pudieron cargar las Sources administradas: "
                f"{managed_source_catalog_error}"
            )
        elif not managed_sources:
            st.warning(
                "No hay Sources disponibles. Crea primero una Source desde Add Source."
            )
        else:
            managed_source_ids = [source.source_id for source in managed_sources]
            selected_source_id = st.selectbox(
                "Source",
                options=managed_source_ids,
                index=None,
                placeholder="Select a managed Source",
                format_func=lambda value: managed_source_labels[value],
                help="Select an active Source managed from Add Source.",
                key=source_catalog_state_key("add_concept_source_id"),
            )
            selected_source_preview = next(
                (
                    candidate
                    for candidate in managed_sources
                    if candidate.source_id == selected_source_id
                ),
                None,
            )
            source_selection_valid = can_save_with_managed_source(
                selected_source_preview
            )
            if source_selection_valid:
                source = selected_source_preview.name
                source_id = selected_source_preview.source_id
        
        if source:
            try:
                docs = list(
                    db.concepts.find(
                        {"source": source},
                        {"id": 1, "titulo": 1, "_id": 0}
                    )
                )
                    # Normaliza y ordena por id
                items = sorted(
                        [
                            {"id": d.get("id", "").strip(),
                             "titulo": (d.get("titulo") or "").strip()}
                            for d in docs
                            if isinstance(d.get("id"), str)
                        ],
                        key=lambda x: x["id"]
                )
            except Exception:
                items = []
            
            st.markdown("#### Existing IDs for this source")
            if items:
                show_n = 50
                lines = []
                for it in items[-show_n:]:
                    if it["titulo"]:
                        lines.append(f"{it['id']}  —  {it['titulo']}")
                    else:
                        lines.append(f"{it['id']}")
                text = "\n".join(lines)
                st.text_area(
                    "Existing IDs (latest 10)",
                    value="\n".join(lines),
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.caption("No concepts yet for this source.")

    with col2:
        titulo = st.text_input("Title (Optional)", placeholder="e.g., Definition of Group")
        tipo_titulo = st.selectbox("Title Type", [t.value for t in TipoTitulo])

    # 1. Categorías base (predefinidas)
    categorias_base = [
    "Algebra", "Analysis", "Topology", "Geometry", "Number Theory",
    "Combinatorics", "Logic", "Statistics", "Calculus"]

    # 2. Categorías adicionales ya existentes en la base de datos
    categorias_db = db.concepts.distinct("categorias")
    categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

    # 3. Opcional: incluir categorías sugeridas por usuarios previos
    try:
        categorias_sugeridas = [doc["nombre"] for doc in db.categorias.find()]
    except Exception:
        categorias_sugeridas = []

    # 4. Combinar todas las categorías conocidas y eliminar duplicados
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas))

    # 🔒 Asegurar estado inicial
    if 'categorias_seleccionadas' not in st.session_state:
        st.session_state.categorias_seleccionadas = []

    # 5. Input para nueva categoría
    nueva_categoria = st.text_input("➕ Add New Category (Optional)", placeholder="e.g., Discrete Math")

    # 6. Agregar a lista si es nueva
    if nueva_categoria:
        nueva_categoria = nueva_categoria.strip()
        if nueva_categoria and nueva_categoria not in st.session_state.categorias_seleccionadas:
            st.session_state.categorias_seleccionadas.append(nueva_categoria)

    # ⚠️ Agregar seleccionadas a las opciones visibles
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas + st.session_state.categorias_seleccionadas))

    # 7. Mostrar multiselect
    st.session_state.categorias_seleccionadas = st.multiselect("Categories",
    options=categorias_existentes,
    default=st.session_state.categorias_seleccionadas,
    help="Select relevant mathematical categories")

    # 8. Resultado final para guardar
    categorias = st.session_state.categorias_seleccionadas

    # LaTeX content with helper toolbar
    st.subheader("📝 LaTeX Content")

    # LaTeX Helper Toolbar
    st.write("**🔧 LaTeX Helper Tools:**")

    # Main structures
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📝 Definition", key="btn_def"):
            st.session_state.latex_insert = r"\begin{definition}{% add Name or leave it in blank}" + "\n" + r"% Definition content here" + "\n" + r"\end{definition}"

        if st.button("📋 Theorem", key="btn_theorem"):
            st.session_state.latex_insert = r"\begin{theorem}{% add Name or leave it in blank}" + "\n" + r"% Theorem statement here" + "\n" + r"\end{theorem}"

        if st.button("📖 Proof", key="btn_proof"):
            st.session_state.latex_insert = r"\begin{proof}" + "\n" + r"% Proof content here" + "\n" + r"\end{proof}"

        if st.button("📊 Example", key="btn_example"):
            st.session_state.latex_insert = r"\begin{example}{% add Name or leave it in blank}" + "\n" + r"% Example content here" + "\n" + r"\end{example}"

    with col2:
        if st.button("📋 Lemma", key="btn_lemma"):
            st.session_state.latex_insert = r"\begin{lemma}{% add Name or leave it in blank}" + "\n" + r"% Lemma statement here" + "\n" + r"\end{lemma}"

        if st.button("📋 Proposition", key="btn_prop"):
            st.session_state.latex_insert = r"\begin{proposition}{% add Name or leave it in blank}" + "\n" + r"% Proposition statement here" + "\n" + r"\end{proposition}"

        if st.button("📋 Corollary", key="btn_corollary"):
            st.session_state.latex_insert = r"\begin{corollary}{% add Name or leave it in blank}" + "\n" + r"% Corollary statement here" + "\n" + r"\end{corollary}"

        if st.button("📋 Remark", key="btn_remark"):
            st.session_state.latex_insert = r"\begin{remark}{% add Name or leave it in blank}" + "\n" + r"% Remark content here" + "\n" + r"\end{remark}"

    with col3:
        if st.button("🔢 Equation", key="btn_eq"):
            st.session_state.latex_insert = r"\begin{equation}" + "\n" + r"% Equation here" + "\n" + r"\end{equation}"

        if st.button("🔢 Align", key="btn_align"):
            st.session_state.latex_insert = r"\begin{align}" + "\n" + r"% Multiple equations here" + "\n" + r"\end{align}"

        if st.button("🔢 Matrix", key="btn_matrix"):
            st.session_state.latex_insert = r"\begin{pmatrix}" + "\n" + r"a & b \\" + "\n" + r"c & d" + "\n" + r"\end{pmatrix}"

        if st.button("🔢 Cases", key="btn_cases"):
            st.session_state.latex_insert = r"\begin{cases}" + "\n" + r"% Case 1 \\" + "\n" + r"% Case 2" + "\n" + r"\end{cases}"

    with col4:
        if st.button("📋 Itemize", key="btn_itemize"):
            st.session_state.latex_insert = r"\begin{itemize}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{itemize}"

        if st.button("📋 Enumerate", key="btn_enumerate"):
            st.session_state.latex_insert = r"\begin{enumerate}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{enumerate}"

        if st.button("📋 Description", key="btn_description"):
            st.session_state.latex_insert = r"\begin{description}" + "\n" + r"\item[Term 1] Description 1" + "\n" + r"\item[Term 2] Description 2" + "\n" + r"\end{description}"

        if st.button("📋 Quote", key="btn_quote"):
            st.session_state.latex_insert = r"\begin{quote}" + "\n" + r"% Quoted text here" + "\n" + r"\end{quote}"

        if st.button("🧩 Code", key="btn_code_listing"):
            st.session_state["latex_insert"] = (
                r"\begin{lstlisting}[language=ValorLanguage, caption=NombreParaCaption]" "\n"
                r"# Comentario" "\n"
                r"codigo" "\n"
                r"\end{lstlisting}"
            )
        if st.button("🌳 Dir Tree", key="btn_dir_tree"):
            st.session_state["latex_insert"] = (
                r"\dirtree{%" "\n"
                r".1 main folder." "\n"
                r".2 subfolder." "\n"
                r".3 subsubfolder." "\n"
                r".4 subsubsubfolder." "\n"
                r"}")

    # Mathematical symbols and operators
    st.write("**🔢 Mathematical Symbols:**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("∑ Sum", key="btn_sum"):
            st.session_state.latex_insert = r"\sum_{i=1}^{n}"
        if st.button("∏ Product", key="btn_prod"):
            st.session_state.latex_insert = r"\prod_{i=1}^{n}"
        if st.button("∫ Integral", key="btn_int"):
            st.session_state.latex_insert = r"\int_{a}^{b}"
        if st.button("∂ Partial", key="btn_partial"):
            st.session_state.latex_insert = r"\partial"

    with col2:
        if st.button("∞ Infinity", key="btn_inf"):
            st.session_state.latex_insert = r"\infty"
        if st.button("→ Arrow", key="btn_arrow"):
            st.session_state.latex_insert = r"\rightarrow"
        if st.button("↔ Bidirectional", key="btn_bidir"):
            st.session_state.latex_insert = r"\leftrightarrow"
        if st.button("∈ Belongs", key="btn_in"):
            st.session_state.latex_insert = r"\in"

    with col3:
        if st.button("⊂ Subset", key="btn_subset"):
            st.session_state.latex_insert = r"\subset"
        if st.button("∪ Union", key="btn_union"):
            st.session_state.latex_insert = r"\cup"
        if st.button("∩ Intersection", key="btn_intersection"):
            st.session_state.latex_insert = r"\cap"
        if st.button("∅ Empty Set", key="btn_empty"):
            st.session_state.latex_insert = r"\emptyset"

    with col4:
        if st.button("∀ For All", key="btn_forall"):
            st.session_state.latex_insert = r"\forall"
        if st.button("∃ Exists", key="btn_exists"):
            st.session_state.latex_insert = r"\exists"
        if st.button("∴ Therefore", key="btn_therefore"):
            st.session_state.latex_insert = r"\therefore"
        if st.button("∵ Because", key="btn_because"):
            st.session_state.latex_insert = r"\because"

    # Greek letters
    st.write("**🇬🇷 Greek Letters:**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("α Alpha", key="btn_alpha"):
            st.session_state.latex_insert = r"\alpha"
        if st.button("β Beta", key="btn_beta"):
            st.session_state.latex_insert = r"\beta"
        if st.button("γ Gamma", key="btn_gamma"):
            st.session_state.latex_insert = r"\gamma"
        if st.button("δ Delta", key="btn_delta"):
            st.session_state.latex_insert = r"\delta"

    with col2:
        if st.button("ε Epsilon", key="btn_epsilon"):
            st.session_state.latex_insert = r"\epsilon"
        if st.button("θ Theta", key="btn_theta"):
            st.session_state.latex_insert = r"\theta"
        if st.button("λ Lambda", key="btn_lambda"):
            st.session_state.latex_insert = r"\lambda"
        if st.button("μ Mu", key="btn_mu"):
            st.session_state.latex_insert = r"\mu"

    with col3:
        if st.button("π Pi", key="btn_pi"):
            st.session_state.latex_insert = r"\pi"
        if st.button("σ Sigma", key="btn_sigma"):
            st.session_state.latex_insert = r"\sigma"
        if st.button("τ Tau", key="btn_tau"):
            st.session_state.latex_insert = r"\tau"
        if st.button("φ Phi", key="btn_phi"):
            st.session_state.latex_insert = r"\phi"

    with col4:
        if st.button("χ Chi", key="btn_chi"):
            st.session_state.latex_insert = r"\chi"
        if st.button("ψ Psi", key="btn_psi"):
            st.session_state.latex_insert = r"\psi"
        if st.button("ω Omega", key="btn_omega"):
            st.session_state.latex_insert = r"\omega"
        if st.button("Γ Gamma", key="btn_Gamma"):
            st.session_state.latex_insert = r"\Gamma"

    # Initialize latex_insert in session state if not exists
    if 'latex_insert' not in st.session_state:
        st.session_state.latex_insert = ""

    # Show current insertion if any
    if st.session_state.latex_insert:
        st.info(f"**Ready to insert:** `{st.session_state.latex_insert}`")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Insert at Cursor", key="insert_btn"):
                st.session_state.insert_latex = True
        with col2:
            if st.button("❌ Clear", key="clear_insert"):
                st.session_state.latex_insert = ""
                st.session_state.insert_latex = False

    # LaTeX text area
    # -------------------------
    # LaTeX editor (state real + remount para inserciones)
    # -------------------------
    # Estado real del texto (NO es el key del widget)
    if "latex_text" not in st.session_state:
       st.session_state["latex_text"] = ""
    # Revisión para forzar re-mount del componente cuando insertas
    if "latex_editor_rev" not in st.session_state:
        st.session_state["latex_editor_rev"] = 0
    # Flags de inserción
    if "latex_insert" not in st.session_state:
        st.session_state["latex_insert"] = ""
    if "insert_latex" not in st.session_state:
        st.session_state["insert_latex"] = False


    # Handle insertion (DEBE IR ANTES del st_ace)
    if st.session_state.get("insert_latex") and st.session_state.get("latex_insert"):
        current_text = st.session_state.get("latex_text", "") or ""
        to_insert = st.session_state["latex_insert"]

        if current_text and not current_text.endswith("\n"):
            current_text += "\n"

        st.session_state["latex_text"] = current_text + to_insert + "\n"
        # limpiar flags
        st.session_state["insert_latex"] = False
        st.session_state["latex_insert"] = ""
        # IMPORTANT: fuerza re-mount para que el nuevo value se refleje
        st.session_state["latex_editor_rev"] += 1
        st.rerun()

    contenido_latex = st_ace(
        value=st.session_state["latex_text"],
        language="latex",
        theme="monokai",
        font_size=16,
        tab_size=2,
        height=800,
        wrap=True,
        show_gutter=True,
        auto_update=True,
        key=f"latex_editor_{st.session_state['latex_editor_rev']}"
    )
    # Sincronizar el contenido del editor con el estado
    st.session_state["latex_text"] = contenido_latex or ""
    # Este es el contenido que usarás para guardar en DB
    contenido_latex = st.session_state["latex_text"]
    _render_tikz_weight_warnings(contenido_latex)
    concept_media_assets = _render_concept_media_manager(
        db,
        concept_id,
        source,
        prefix="add_concept",
        latex_insert_key="latex_insert",
        insert_flag_key="insert_latex",
    )
    ###----

    # Algorithm section

    st.subheader("⚙️ Algorithm Information")
    col1, col2 = st.columns(2)
    with col1:
        es_algoritmo = st.checkbox("Is this an algorithm?")
    with col2:
        if es_algoritmo:
            pasos_algoritmo = st.text_area("Algorithm Steps", placeholder="Enter algorithm steps...")

    st.subheader("📚 Reference Information")
    if st.button("📋 Cargar referencia del concepto anterior", key="load_prev_ref"):
        try:
            ref = load_last_reference_by_source(db, source)
            if not ref:
                st.warning(f"⚠️ No se encontró ninguna referencia previa para el source: {source!r}")
            else:
                # Poblar session_state (Add Concept usa claves edit_ref_*)
                st.session_state["edit_ref_tipo"] = ref.get("tipo_referencia", st.session_state.get("edit_ref_tipo", "libro"))
                st.session_state["edit_ref_autor"] = ref.get("autor", "") or ""
                st.session_state["edit_ref_fuente"] = ref.get("fuente", "") or ""
                st.session_state["edit_ref_anio"] = ref.get("anio", 2024) or 2024
                st.session_state["edit_ref_tomo"] = ref.get("tomo", "") or ""
                st.session_state["edit_ref_edicion"] = ref.get("edicion", "") or ""
                st.session_state["edit_ref_paginas"] = ref.get("paginas", "") or ""
                st.session_state["edit_ref_capitulo"] = ref.get("capitulo", "") or ""
                st.session_state["edit_ref_seccion"] = ref.get("seccion", "") or ""
                st.session_state["edit_ref_editorial"] = ref.get("editorial", "") or ""
                st.session_state["edit_ref_doi"] = ref.get("doi", "") or ""
                st.session_state["edit_ref_url"] = ref.get("url", "") or ""
                st.session_state["edit_ref_issbn"] = ref.get("issbn", "") or ""
                st.session_state["edit_ref_citekey"] = ref.get("citekey", "") or ""

                # Debug opcional (puedes quitarlo)
                with st.expander("Debug (loaded from last concept)", expanded=False):
                    st.write({
                    "from_id": ref.get("__from_concept_id"),
                    "from_title": ref.get("__from_concept_title"),
                    "from_date": ref.get("__from_concept_date"),
                })

                st.success("✅ Referencia cargada desde el último concepto de este source. Puedes editar los campos.")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Error cargando referencia previa: {e}")


    

    with st.expander("Add / Edit Reference", expanded=False):
        # --- Carga opcional de BibTeX ---
        st.write("Opcional: cargar desde un archivo BibTeX")
        bib_file_add = st.file_uploader("Cargar .bib", type=["bib"], key="bib_add")

        if bib_file_add is not None:
            try:
                bib_entries = _parse_bibtex(bib_file_add.getvalue())
                if bib_entries:
                    keys = [
                            (e.get("ID", "(sin key)"), f'{e.get("title","(sin título)")[:60]}')
                            for e in bib_entries
                        ]
                    idx = st.selectbox(
                            "Selecciona entrada",
                            list(range(len(keys))),
                            format_func=lambda i: f"{keys[i][0]} — {keys[i][1]}",
                            key="bib_choice_edit",
                    )

                    selected_bib_entry_edit = bib_entries[idx]

                    if st.button("Usar esta entrada", key="use_bib_edit"):
                        ref_dict = _bib_to_referencia(selected_bib_entry_edit)
                        st.session_state["edit_ref_tipo"] = ref_dict["tipo_referencia"]
                        st.session_state["edit_ref_autor"] = ref_dict["autor"] or ""
                        st.session_state["edit_ref_fuente"] = ref_dict["fuente"] or ""
                        st.session_state["edit_ref_anio"] = ref_dict["anio"] or 2024
                        st.session_state["edit_ref_tomo"] = ref_dict["tomo"] or ""
                        st.session_state["edit_ref_edicion"] = ref_dict["edicion"] or ""
                        st.session_state["edit_ref_paginas"] = ref_dict["paginas"] or ""
                        st.session_state["edit_ref_capitulo"] = ref_dict["capitulo"] or ""
                        st.session_state["edit_ref_seccion"] = ref_dict["seccion"] or ""
                        st.session_state["edit_ref_editorial"] = ref_dict["editorial"] or ""
                        st.session_state["edit_ref_doi"] = ref_dict["doi"] or ""
                        st.session_state["edit_ref_url"] = ref_dict["url"] or ""
                        st.session_state["edit_ref_issbn"] = ref_dict["issbn"] or ""
                        st.session_state["edit_ref_citekey"] = selected_bib_entry_edit.get("ID")
                        st.success("Campos de referencia actualizados desde BibTeX.")
                        st.rerun()  # <-- fuerza refresco de widgets
                else:
                    st.info("El archivo .bib no contiene entradas.")
            except Exception as e:
                st.error(f"No se pudo leer el .bib: {e}")

            # --- Campos editables enlazados a session_state (claves edit_ref_*) ---
        col1, col2 = st.columns(2)
        with col1:
            ref_tipo = st.selectbox(
                    "Reference Type",
                    [t.value for t in TipoReferencia],
                    key="edit_ref_tipo",
            )
            ref_autor = st.text_input("Author", key="edit_ref_autor")
            ref_fuente = st.text_input("Source/Title", key="edit_ref_fuente")
            ref_anio = st.number_input(
                    "Year",
                    min_value=1800, max_value=3000,
                    value=st.session_state.get("edit_ref_anio"),
                    key="edit_ref_anio",
            )

        with col2:
            ref_tomo = st.text_input("Volume", key="edit_ref_tomo")
            ref_edicion = st.text_input("Edition", key="edit_ref_edicion")
            ref_paginas = st.text_input("Pages", key="edit_ref_paginas")
            ref_capitulo = st.text_input("Chapter", key="edit_ref_capitulo")

        ref_seccion = st.text_input("Section", key="edit_ref_seccion")
        ref_editorial = st.text_input("Publisher", key="edit_ref_editorial")
        ref_doi = st.text_input("DOI", key="edit_ref_doi")
        ref_url = st.text_input("URL", key="edit_ref_url")
        ref_issbn = st.text_input("ISBN", key="edit_ref_issbn")

        # Citekey opcional (si lo guardas en tu modelo)
        st.text_input("Citekey (opcional)", key="edit_ref_citekey")

    # Teaching context
    st.subheader("🎓 Teaching Context")
    with st.expander("Add Teaching Context", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            nivel_contexto = st.selectbox("Context Level", [n.value for n in NivelContexto])
        with col2:
            grado_formalidad = st.selectbox("Formality Degree", [g.value for g in GradoFormalidad])

    # Technical metadata
    st.subheader("🔧 Technical Metadata")
    with st.expander("Add Technical Metadata", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            usa_notacion_formal = st.checkbox("Uses Formal Notation", value=True)
            incluye_demostracion = st.checkbox("Includes Proof")
            es_definicion_operativa = st.checkbox("Is Operational Definition")
            es_concepto_fundamental = st.checkbox("Is Fundamental Concept")

        with col2:
            requiere_conceptos_previos = st.text_area("Required Previous Concepts", placeholder="Enter concepts separated by commas")
            incluye_ejemplo = st.checkbox("Includes Example")
            es_autocontenible = st.checkbox("Is Self-Contained", value=True)

        tipo_presentacion = st.selectbox("Presentation Type", [t.value for t in TipoPresentacion])
        nivel_simbolico = st.selectbox("Symbolic Level", [n.value for n in NivelSimbolico])
        tipo_aplicacion = st.multiselect("Application Type", [t.value for t in TipoAplicacion])

    # Comment
    comentario = st.text_area("Comment (Optional)", placeholder="Additional comments or notes...")

    # Submit button
    if st.button(
        "💾 Save Concept",
        type="primary",
        disabled=not source_selection_valid,
    ):
        if managed_source_repository is None or not selected_source_id:
            st.error("❌ Select an active managed Source before saving.")
            st.stop()
        try:
            selected_source = resolve_active_source(
                managed_source_repository,
                selected_source_id,
            )
        except Exception as exc:
            st.error(
                "No se pudieron cargar las Sources administradas: "
                f"{safe_catalog_error(exc)}"
            )
            st.stop()
        if not can_save_with_managed_source(selected_source):
            st.error(
                "❌ The selected Source is no longer active or available. "
                "Choose another managed Source."
            )
            st.stop()
        source = selected_source.name
        source_id = selected_source.source_id

        # 1. Campos requeridos (primero)
        if not concept_id or not source or not contenido_latex:
            st.error("❌ Please fill in all required fields: ID, Source, and LaTeX Content")
            st.stop()
        # 2. Identidad lógica (id, source)
        errors = validate_new_concept_identity(db, concept_id, source)
        for err in errors:
            st.error(err)
        if errors:
            st.stop()

        # 3. Duplicado semántico
        errors = validate_semantic_duplicate(db, titulo, concept_type, source)
        for err in errors:
            st.error(err)
        if errors:
            st.stop()

        #if titulo and semantic_duplicate_exists(db, titulo, concept_type, source):

            #st.error("❌ Ya existe un concepto con el mismo TITULO y tipo desde este source.")
            #st.info("💡 Usa un ID distinto solo si el concepto es realmente diferente, o edita el existente.")
            #st.stop()
        # 4. Guardado
        try:
            # Build concept data
            concept_data = {
                "id": concept_id,
                "tipo": concept_type,
                "titulo": titulo if titulo else None,
                "tipo_titulo": tipo_titulo,
                "categorias": categorias,
                "contenido_latex": contenido_latex,
                "es_algoritmo": es_algoritmo,
                "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                "comentario": comentario if comentario else None,
                "source": source,
                "source_id": source_id,
                "image_ids": [asset["asset_id"] for asset in concept_media_assets],
                "fecha_creacion": datetime.now(),
                "ultima_actualizacion": datetime.now(),
                # NOTE: We keep concept.citekey for backward compatibility with existing exporters.
                # The authoritative citekey should live inside concept.referencia.citekey.
                "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                }

            # Add reference if provided
            if ref_autor or ref_fuente:
                concept_data["referencia"] = {
                    "tipo_referencia": ref_tipo,
                    "autor": ref_autor if ref_autor else None,
                    "fuente": ref_fuente if ref_fuente else None,
                    "anio": ref_anio if ref_anio else None,
                    "tomo": ref_tomo if ref_tomo else None,
                    "edicion": ref_edicion if ref_edicion else None,
                    "paginas": ref_paginas if ref_paginas else None,
                    "capitulo": ref_capitulo if ref_capitulo else None,
                    "seccion": ref_seccion if ref_seccion else None,
                    "editorial": ref_editorial if ref_editorial else None,
                    "doi": ref_doi if ref_doi else None,
                    "url": ref_url if ref_url else None,
                    "issbn": ref_issbn if ref_issbn else None,
                    # NEW: Persist citekey at reference-level (needed for stable Quarto/BibTeX export).
                    "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

            # Add teaching context if provided
            if nivel_contexto or grado_formalidad:
                concept_data["contexto_docente"] = {
                    "nivel_contexto": nivel_contexto,
                    "grado_formalidad": grado_formalidad
                    }

                # Add technical metadata if provided
            if usa_notacion_formal is not None or incluye_demostracion is not None:
                concept_data["metadatos_tecnicos"] = {
                        "usa_notacion_formal": usa_notacion_formal,
                        "incluye_demostracion": incluye_demostracion,
                        "es_definicion_operativa": es_definicion_operativa,
                        "es_concepto_fundamental": es_concepto_fundamental,
                        "requiere_conceptos_previos": [c.strip() for c in requiere_conceptos_previos.split(',')] if requiere_conceptos_previos else None,
                        "incluye_ejemplo": incluye_ejemplo,
                        "es_autocontenible": es_autocontenible,
                        "tipo_presentacion": tipo_presentacion,
                        "nivel_simbolico": nivel_simbolico,
                        "tipo_aplicacion": tipo_aplicacion if tipo_aplicacion else None
                    }

                # Create concept object
            concepto = ConceptoBase(**concept_data)

                # Save to database
            if concept_exists(db, concepto.id, source):
                existing = db.concepts.find_one(
                        {"id": concepto.id, "source": source},
                        {"_id": 1, "id": 1, "source": 1, "titulo": 1, "fecha_creacion": 1, "ultima_actualizacion": 1},
                    )
                st.warning("⚠️ Este concepto ya existe. Usa ✏️ Edit Concept o cambia el ID.")
                if existing:
                    st.json(existing)
                st.stop()
            concepto_dict = build_concept_metadata(concepto)
            now = datetime.now()
            insert_concept_with_latex_atomic(
                    db,
                    concepto.id,
                    source,
                    concepto_dict,
                    contenido_latex,
                    now,
                )

            st.success(f"✅ Concept '{concept_id}' saved successfully to {current_db}!")
            st.balloons()

        except Exception as e:
            st.error(f"❌ Error saving concept: {e}")

    # PDF Generation Button
    st.markdown("---")
    st.subheader("📄 Generar PDF")
    add_pdf_context = pdf_preview_context(
        "add_concept",
        current_db,
        source,
        concept_id,
    )
    concept_pdf_root = get_exports_dir(
        configured=resolve_config().export_directory
    ) / "concepts"

    # Check if we have the minimum required data for PDF generation
    if concept_id and source and contenido_latex:
        if st.button("📄 Generar vista previa PDF", type="secondary"):
            # Build concept data for PDF generation
            pdf_concept_data = {
                "id": concept_id,
                "tipo": concept_type,
                "titulo": titulo if titulo else concept_id,
                "categorias": categorias,
                "contenido_latex": contenido_latex,
                "source": source,
                "comentario": comentario if comentario else None
            }

            # Add reference if provided
            if ref_autor or ref_fuente:
                pdf_concept_data["referencia"] = {
                    "tipo_referencia": ref_tipo,
                    "autor": ref_autor if ref_autor else None,
                    "fuente": ref_fuente if ref_fuente else None,
                    "anio": ref_anio if ref_anio else None,
                    "tomo": ref_tomo if ref_tomo else None,
                    "edicion": ref_edicion if ref_edicion else None,
                    "paginas": ref_paginas if ref_paginas else None,
                    "capitulo": ref_capitulo if ref_capitulo else None,
                    "seccion": ref_seccion if ref_seccion else None,
                    "editorial": ref_editorial if ref_editorial else None,
                    "doi": ref_doi if ref_doi else None,
                    "url": ref_url if ref_url else None,
                    "issbn": ref_issbn if ref_issbn else None
                }

            _generate_concept_pdf_preview(
                "add_concept",
                pdf_concept_data,
                context_identity=add_pdf_context,
                allowed_root=concept_pdf_root,
            )
    else:
        clear_pdf_preview(st.session_state, "add_concept")
        st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")

    render_pdf_preview(
        st,
        st.session_state,
        "add_concept",
        context_identity=add_pdf_context,
    )

# Edit Concept page
elif page == "✏️ Edit Concept":
    st.title("✏️ Edit Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Editing concepts in: **{current_db}**")

    # Concept selection
    st.subheader("🔍 Select Concept to Edit")

    legacy_target = consume_legacy_concept_open(st.session_state)
    legacy_source_key = source_catalog_state_key("legacy_edit_filter_source")
    legacy_type_key = source_catalog_state_key("legacy_edit_filter_type")
    legacy_concept_key = source_catalog_state_key("legacy_edit_concept")
    legacy_last_selected_key = source_catalog_state_key("legacy_last_selected_concept")
    available_legacy_sources = [
        value
        for value in db.concepts.distinct("source")
        if isinstance(value, str) and value
    ]
    source_options = ["All", *available_legacy_sources]
    type_options = [
        "All",
        *[
            value
            for value in db.concepts.distinct("tipo")
            if isinstance(value, str) and value
        ],
    ]
    if legacy_target is not None:
        if legacy_target["source"] in available_legacy_sources:
            st.session_state[legacy_source_key] = legacy_target["source"]
            st.session_state[legacy_type_key] = "All"
            st.info(
                "Opened from Source Catalog using the exact legacy identity "
                f"`{legacy_target['id']}@{legacy_target['source']}`."
            )
        else:
            st.warning("The exact legacy Source is not available in the active database.")
    if st.session_state.get(legacy_source_key) not in source_options:
        st.session_state.pop(legacy_source_key, None)
    if st.session_state.get(legacy_type_key) not in type_options:
        st.session_state.pop(legacy_type_key, None)

    col1, col2 = st.columns(2)

    with col1:
        # Filter by source
        filter_source = st.selectbox(
            "Filter by Source",
            source_options,
            key=legacy_source_key,
        )

    with col2:
        # Filter by type
        filter_type = st.selectbox(
            "Filter by Type",
            type_options,
            key=legacy_type_key,
        )

    # Build query for concept selection
    query = {}
    if filter_source != "All":
        query["source"] = filter_source
    if filter_type != "All":
        query["tipo"] = filter_type

    # Get concepts for selection
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))

    if not concepts:
        st.warning("⚠️ No concepts found with the selected filters.")
        st.stop()

    # Create concept options for selection
    concept_options = []
    concept_map = {}

    for concept in concepts:
        display_name = (
            f"{concept.get('titulo', concept['id'])} "
            f"({concept['tipo']} - {concept['source']}) · {concept['id']}"
        )
        concept_options.append(display_name)
        concept_map[display_name] = concept

    if legacy_target is not None:
        target_display = next(
            (
                display
                for display, concept in concept_map.items()
                if str(concept.get("id")) == legacy_target["id"]
                and concept.get("source") == legacy_target["source"]
            ),
            None,
        )
        if target_display is not None:
            st.session_state[legacy_concept_key] = target_display
        else:
            st.warning("The exact legacy concept was not found with the active filters.")
    if st.session_state.get(legacy_concept_key) not in concept_options:
        st.session_state.pop(legacy_concept_key, None)

    # Concept selector
    selected_concept_display = st.selectbox(
        "Choose Concept to Edit",
        concept_options,
        help="Select the concept you want to edit",
        key=legacy_concept_key,
    )
    # Handle concept selection and data loading
    if selected_concept_display:
        selected_concept = concept_map[selected_concept_display]
        original_concept_id = str(selected_concept["id"])
        original_source = str(selected_concept["source"])
        original_source_id = selected_concept.get("source_id")

        # Check if concept has changed and update session state
        selected_concept_key = (
            original_concept_id,
            original_source,
        )
        if (
            st.session_state.get(legacy_last_selected_key) != selected_concept_key
        ):

            # IDs are only unique together with their exact legacy Source.
            st.session_state[legacy_last_selected_key] = selected_concept_key

            # Get LaTeX content from database
            latex_doc = db.latex_documents.find_one({
                "id": original_concept_id,
                "source": original_source,
            })
            current_latex = latex_doc['contenido_latex'] if latex_doc else ""

            # Update all form fields in session state
            st.session_state.pop("edit_id", None)
            st.session_state.pop("edit_source", None)
            st.session_state.edit_titulo = selected_concept.get("titulo", "")
            st.session_state.edit_tipo_titulo = selected_concept.get("tipo_titulo", "ninguno")
            st.session_state["edit_latex_text"] = current_latex
            # estado para remount del editor en Edit Concept
            # fuerza re-mount REAL cuando cambias de concepto (evita que ACE se quede pegado)
            st.session_state["edit_latex_editor_rev"] = st.session_state.get("edit_latex_editor_rev", 0) + 1
            st.session_state["edit_latex_insert"] = ""
            st.session_state["edit_insert_latex"] = False

            st.session_state.edit_comentario = selected_concept.get("comentario", "")
            st.session_state.edit_es_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_categorias = selected_concept.get("categorias", [])
            st.session_state.edit_referencia = selected_concept.get("referencia", {})
            st.session_state.edit_pasos_algoritmo = selected_concept.get("pasos_algoritmo", [])
            st.session_state.edit_contexto_docente = selected_concept.get("contexto_docente", {})
            st.session_state.edit_metadatos_tecnicos = selected_concept.get("metadatos_tecnicos", {})

            # Initialize reference fields in session state
            ref = selected_concept.get("referencia", {})
            st.session_state.edit_ref_tipo = ref.get('tipo_referencia', 'libro')
            st.session_state.edit_ref_autor = ref.get('autor', '')
            st.session_state.edit_ref_fuente = ref.get('fuente', '')
            st.session_state.edit_ref_anio = ref.get('anio', 2024)
            st.session_state.edit_ref_tomo = ref.get('tomo', '')
            st.session_state.edit_ref_edicion = ref.get('edicion', '')
            st.session_state.edit_ref_paginas = ref.get('paginas', '')
            st.session_state.edit_ref_capitulo = ref.get('capitulo', '')
            st.session_state.edit_ref_seccion = ref.get('seccion', '')
            st.session_state.edit_ref_editorial = ref.get('editorial', '')
            st.session_state.edit_ref_doi = ref.get('doi', '')
            st.session_state.edit_ref_url = ref.get('url', '')
            st.session_state.edit_ref_issbn = ref.get('issbn', '')
            # Citekey can be stored either at concept-level (legacy) or inside referencia (preferred).
            st.session_state.edit_ref_citekey = (
                (selected_concept.get("citekey") or "")
                or (ref.get('citekey') or '')
            )

            # Initialize teaching context fields in session state
            context = selected_concept.get("contexto_docente", {})
            st.session_state.edit_nivel = context.get('nivel_contexto', 'introductorio')
            st.session_state.edit_formalidad = context.get('grado_formalidad', 'informal')

            # Initialize technical metadata fields in session state
            meta = selected_concept.get("metadatos_tecnicos", {})
            st.session_state.edit_notacion = meta.get('usa_notacion_formal', True)
            st.session_state.edit_demostracion = meta.get('incluye_demostracion', False)
            st.session_state.edit_operativa = meta.get('es_definicion_operativa', False)
            st.session_state.edit_fundamental = meta.get('es_concepto_fundamental', False)
            st.session_state.edit_previos = ', '.join(meta.get('requiere_conceptos_previos', [])) if meta.get('requiere_conceptos_previos') else ""
            st.session_state.edit_ejemplo = meta.get('incluye_ejemplo', False)
            st.session_state.edit_autocontenible = meta.get('es_autocontenible', True)
            st.session_state.edit_presentacion = meta.get('tipo_presentacion', 'expositivo')
            st.session_state.edit_simbolico = meta.get('nivel_simbolico', 'bajo')
            st.session_state.edit_aplicacion = meta.get('tipo_aplicacion', [])

            # Initialize algorithm fields in session state
            st.session_state.edit_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_pasos = '\n'.join(selected_concept.get("pasos_algoritmo", [])) if selected_concept.get("pasos_algoritmo") else ""

            # Clear any pending LaTeX insertions
            st.session_state.edit_latex_insert = ""
            st.session_state.edit_insert_latex = False

            # Force rerun to update all widgets
            st.rerun()

        # Display header
        st.markdown("---")
        st.subheader(f"✏️ Editing: {selected_concept.get('titulo', selected_concept['id'])}")

        # Basic information
        st.subheader("📋 Basic Information")

        col1, col2 = st.columns(2)
        with col1:
            st.caption("ID (immutable)")
            st.code(original_concept_id, language=None)
            st.caption("Source snapshot (immutable)")
            st.code(original_source, language=None)
            if original_source_id is not None:
                st.caption("Managed Source ID (immutable)")
                st.code(str(original_source_id), language=None)
            else:
                st.info("Legacy concept — not linked to a managed Source.")

        with col2:
            titulo = st.text_input("Title", key="edit_titulo")
            tipo_titulo = st.selectbox(
                "Title Type", 
                [t.value for t in TipoTitulo],
                key="edit_tipo_titulo",
            )

        # Concept type (read-only for now to avoid complications)
        st.info(f"**Concept Type:** {selected_concept['tipo']} (cannot be changed)")

        # Categories
        # Get all available categories from database
        categorias_db = db.concepts.distinct("categorias")
        categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

        # Combine predefined and database categories
        categorias_predefinidas = ["Algebra", "Analysis", "Topology", "Geometry", "Number Theory", "Combinatorics", "Logic", "Statistics", "Calculus"]
        all_categories = sorted(set(categorias_predefinidas + categorias_db))

        categorias = st.multiselect(
            "Categories",
            all_categories,
            key="edit_categorias",
        )
        
        # LaTeX content with helper toolbar
        st.subheader("📝 LaTeX Content")
        
        # LaTeX Helper Toolbar (same as Add Concept)
        st.write("**🔧 LaTeX Helper Tools:**")
        
        # Main structures
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📝 Definition", key="edit_btn_def"):
                st.session_state.edit_latex_insert = r"\begin{definition}" + "\n" + r"% Definition content here" + "\n" + r"\end{definition}"
            
            if st.button("📋 Theorem", key="edit_btn_theorem"):
                st.session_state.edit_latex_insert = r"\begin{theorem}" + "\n" + r"% Theorem statement here" + "\n" + r"\end{theorem}"

            if st.button("📖 Proof", key="edit_btn_proof"):
                st.session_state.edit_latex_insert = r"\begin{proof}" + "\n" + r"% Proof content here" + "\n" + r"\end{proof}"

            if st.button("📊 Example", key="edit_btn_example"):
                st.session_state.edit_latex_insert = r"\begin{example}" + "\n" + r"% Example content here" + "\n" + r"\end{example}"

        with col2:
            if st.button("📋 Lemma", key="edit_btn_lemma"):
                st.session_state.edit_latex_insert = r"\begin{lemma}" + "\n" + r"% Lemma statement here" + "\n" + r"\end{lemma}"

            if st.button("📋 Proposition", key="edit_btn_prop"):
                st.session_state.edit_latex_insert = r"\begin{proposition}" + "\n" + r"% Proposition statement here" + "\n" + r"\end{proposition}"

            if st.button("📋 Corollary", key="edit_btn_corollary"):
                st.session_state.edit_latex_insert = r"\begin{corollary}" + "\n" + r"% Corollary statement here" + "\n" + r"\end{corollary}"

            if st.button("📋 Remark", key="edit_btn_remark"):
                st.session_state.edit_latex_insert = r"\begin{remark}" + "\n" + r"% Remark content here" + "\n" + r"\end{remark}"

        with col3:
            if st.button("🔢 Equation", key="edit_btn_eq"):
                st.session_state.edit_latex_insert = r"\begin{equation}" + "\n" + r"% Equation here" + "\n" + r"\end{equation}"

            if st.button("🔢 Align", key="edit_btn_align"):
                st.session_state.edit_latex_insert = r"\begin{align}" + "\n" + r"% Multiple equations here" + "\n" + r"\end{align}"

            if st.button("🔢 Matrix", key="edit_btn_matrix"):
                st.session_state.edit_latex_insert = r"\begin{pmatrix}" + "\n" + r"a & b \\" + "\n" + r"c & d" + "\n" + r"\end{pmatrix}"

            if st.button("🔢 Cases", key="edit_btn_cases"):
                st.session_state.edit_latex_insert = r"\begin{cases}" + "\n" + r"% Case 1 \\" + "\n" + r"% Case 2" + "\n" + r"\end{cases}"

        with col4:
            if st.button("📋 Itemize", key="edit_btn_itemize"):
                st.session_state.edit_latex_insert = r"\begin{itemize}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{itemize}"

            if st.button("📋 Enumerate", key="edit_btn_enumerate"):
                st.session_state.edit_latex_insert = r"\begin{enumerate}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{enumerate}"

            if st.button("📋 Description", key="edit_btn_description"):
                st.session_state.edit_latex_insert = r"\begin{description}" + "\n" + r"\item[Term 1] Description 1" + "\n" + r"\item[Term 2] Description 2" + "\n" + r"\end{description}"

            if st.button("📋 Quote", key="edit_btn_quote"):
                st.session_state.edit_latex_insert = r"\begin{quote}" + "\n" + r"% Quoted text here" + "\n" + r"\end{quote}"

            if st.button("🧩 Code", key="edit_btn_code_listing"):
                st.session_state["edit_latex_insert"] = (
                    r"\begin{lstlisting}[language=ValorLanguage, caption=NombreParaCaption]" "\n"
                    r"# Comentario" "\n"
                    r"codigo" "\n"
                    r"\end{lstlisting}")

            if st.button("🌳 Dir Tree", key="edit_btn_dir_tree"):
                st.session_state["edit_latex_insert"] = (
                    r"\dirtree{%" "\n"
                    r".1 main folder." "\n"
                    r".2 subfolder." "\n"
                    r".3 subsubfolder." "\n"
                    r".4 subsubsubfolder." "\n"
                    r"}"
                )

        # Mathematical symbols (abbreviated for edit page)
        st.write("**🔢 Common Symbols:**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("∑ Sum", key="edit_btn_sum"):
                st.session_state.edit_latex_insert = r"\sum_{i=1}^{n}"
            if st.button("∫ Integral", key="edit_btn_int"):
                st.session_state.edit_latex_insert = r"\int_{a}^{b}"
            if st.button("→ Arrow", key="edit_btn_arrow"):
                st.session_state.edit_latex_insert = r"\rightarrow"
            if st.button("∈ Belongs", key="edit_btn_in"):
                st.session_state.edit_latex_insert = r"\in"

        with col2:
            if st.button("∞ Infinity", key="edit_btn_inf"):
                st.session_state.edit_latex_insert = r"\infty"
            if st.button("∪ Union", key="edit_btn_union"):
                st.session_state.edit_latex_insert = r"\cup"
            if st.button("∩ Intersection", key="edit_btn_intersection"):
                st.session_state.edit_latex_insert = r"\cap"
            if st.button("∀ For All", key="edit_btn_forall"):
                st.session_state.edit_latex_insert = r"\forall"

        with col3:
            if st.button("α Alpha", key="edit_btn_alpha"):
                st.session_state.edit_latex_insert = r"\alpha"
            if st.button("β Beta", key="edit_btn_beta"):
                st.session_state.edit_latex_insert = r"\beta"
            if st.button("γ Gamma", key="edit_btn_gamma"):
                st.session_state.edit_latex_insert = r"\gamma"
            if st.button("δ Delta", key="edit_btn_delta"):
                st.session_state.edit_latex_insert = r"\delta"

        with col4:
            if st.button("π Pi", key="edit_btn_pi"):
                st.session_state.edit_latex_insert = r"\pi"
            if st.button("σ Sigma", key="edit_btn_sigma"):
                st.session_state.edit_latex_insert = r"\sigma"
            if st.button("λ Lambda", key="edit_btn_lambda"):
                st.session_state.edit_latex_insert = r"\lambda"
            if st.button("θ Theta", key="edit_btn_theta"):
                st.session_state.edit_latex_insert = r"\theta"
        
        # Initialize edit_latex_insert in session state if not exists
        if 'edit_latex_insert' not in st.session_state:
            st.session_state["edit_latex_insert"] = ""
        
        # Show current insertion if any
        if st.session_state["edit_latex_insert"]:
            st.info(f"**Ready to insert:** `{st.session_state['edit_latex_insert']}`")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Insert at Cursor", key="edit_insert_btn"):
                    st.session_state["edit_insert_latex"] = True
            with col2:
                if st.button("❌ Clear", key="edit_clear_insert"):
                    st.session_state["edit_latex_insert"] = ""
                    st.session_state["edit_insert_latex"] = False


        # -------------------------
        # LaTeX editor (ACE) - Edit Concept
        # -------------------------

        # Estado real del texto (NO es el key del widget)
        if "edit_latex_text" not in st.session_state:
            st.session_state["edit_latex_text"] = ""

        # Revisión para forzar re-mount del componente cuando insertas
        if "edit_latex_editor_rev" not in st.session_state:
            st.session_state["edit_latex_editor_rev"] = 0

        # Flags de inserción (asegurar existencia)
        if "edit_latex_insert" not in st.session_state:
            st.session_state["edit_latex_insert"] = ""
        if "edit_insert_latex" not in st.session_state:
            st.session_state["edit_insert_latex"] = False
        
        # Handle insertion (DEBE IR ANTES del st_ace)
        if st.session_state.get("edit_insert_latex") and st.session_state.get("edit_latex_insert"):
            current_text = st.session_state.get("edit_latex_text", "") or ""
            to_insert = st.session_state["edit_latex_insert"]
            if current_text and not current_text.endswith("\n"):
                current_text += "\n"
            st.session_state["edit_latex_text"] = current_text + to_insert + "\n"
            # limpiar flags
            st.session_state["edit_insert_latex"] = False
            st.session_state["edit_latex_insert"] = ""

            # fuerza re-mount
            st.session_state["edit_latex_editor_rev"] += 1
            st.rerun()

        editor_seed = f"{original_concept_id}@{original_source}"
        contenido_latex = st_ace(
            value=st.session_state["edit_latex_text"],
            language="latex",
            theme="monokai",
            font_size=16,
            tab_size=2,
            height=800,        # aquí súbele para edición cómoda
            wrap=True,
            show_gutter=True,
            auto_update=True,
            key=f"edit_latex_editor__{editor_seed}__{st.session_state['edit_latex_editor_rev']}",
        )

        # Sincronizar el contenido del editor con el estado
        st.session_state["edit_latex_text"] = contenido_latex or ""
        contenido_latex = st.session_state["edit_latex_text"]  # este es el que se guarda
        _render_tikz_weight_warnings(contenido_latex)
        concept_media_assets = _render_concept_media_manager(
            db,
            original_concept_id,
            original_source,
            prefix="edit_concept",
            latex_insert_key="edit_latex_insert",
            insert_flag_key="edit_insert_latex",
        )

        ##----------------------------------------
        # Algorithm section
        st.subheader("⚙️ Algorithm Information")
        col1, col2 = st.columns(2)
        with col1:
            es_algoritmo = st.checkbox("Is this an algorithm?", key="edit_algoritmo")
        with col2:
            if es_algoritmo:
                pasos_algoritmo = st.text_area("Algorithm Steps", key="edit_pasos")

        # Reference information
        st.subheader("📚 Reference Information")
        current_ref = st.session_state.edit_referencia

        with st.expander("Edit Reference", expanded=bool(current_ref)):
            col1, col2 = st.columns(2)
            with col1:
                ref_tipo = st.selectbox(
                    "Reference Type", 
                    [t.value for t in TipoReferencia],
                    key="edit_ref_tipo"
                )
                ref_autor = st.text_input("Author", key="edit_ref_autor")
                ref_fuente = st.text_input("Source/Title", key="edit_ref_fuente")
                ref_anio = st.number_input("Year", min_value=1800, max_value=2030, key="edit_ref_anio")

            with col2:
                ref_tomo = st.text_input("Volume", key="edit_ref_tomo")
                ref_edicion = st.text_input("Edition", key="edit_ref_edicion")
                ref_paginas = st.text_input("Pages", key="edit_ref_paginas")
                ref_capitulo = st.text_input("Chapter", key="edit_ref_capitulo")

            ref_seccion = st.text_input("Section", key="edit_ref_seccion")
            ref_editorial = st.text_input("Publisher", key="edit_ref_editorial")
            ref_doi = st.text_input("DOI", key="edit_ref_doi")
            ref_url = st.text_input("URL", key="edit_ref_url")
            ref_issbn = st.text_input("ISBN", key="edit_ref_issbn")
            # Optional citekey used for bibliography export (Quarto/Pandoc).
            st.text_input("Citekey (opcional)", key="edit_ref_citekey")

        # Teaching context
        st.subheader("🎓 Teaching Context")
        current_context = st.session_state.edit_contexto_docente

        with st.expander("Edit Teaching Context", expanded=bool(current_context)):
            col1, col2 = st.columns(2)
            with col1:
                nivel_contexto = st.selectbox(
                    "Context Level", 
                    [n.value for n in NivelContexto],
                    key="edit_nivel",
                )
            with col2:
                grado_formalidad = st.selectbox(
                    "Formality Degree",
                    [g.value for g in GradoFormalidad],
                    key="edit_formalidad",
                )

        # Technical metadata
        st.subheader("🔧 Technical Metadata")
        current_meta = st.session_state.edit_metadatos_tecnicos

        with st.expander("Edit Technical Metadata", expanded=bool(current_meta)):
            col1, col2 = st.columns(2)
            with col1:
                usa_notacion_formal = st.checkbox("Uses Formal Notation", key="edit_notacion")
                incluye_demostracion = st.checkbox("Includes Proof", key="edit_demostracion")
                es_definicion_operativa = st.checkbox("Is Operational Definition", key="edit_operativa")
                es_concepto_fundamental = st.checkbox("Is Fundamental Concept", key="edit_fundamental")

            with col2:
                requiere_conceptos_previos = st.text_area(
                    "Required Previous Concepts", 
                    key="edit_previos"
                )
                incluye_ejemplo = st.checkbox("Includes Example", key="edit_ejemplo")
                es_autocontenible = st.checkbox("Is Self-Contained", key="edit_autocontenible")

            tipo_presentacion = st.selectbox(
                "Presentation Type", 
                [t.value for t in TipoPresentacion],
                key="edit_presentacion"
            )
            nivel_simbolico = st.selectbox(
                "Symbolic Level", 
                [n.value for n in NivelSimbolico],
                key="edit_simbolico"
            )
            tipo_aplicacion = st.multiselect(
                "Application Type", 
                [t.value for t in TipoAplicacion],
                key="edit_aplicacion"
            )
        # Comment
        comentario = st.text_area(
            "Comment", 
            key="edit_comentario"
        )
        # Action buttons
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 Update Concept", type="primary"):
                try:
                    # Identity fields are deliberately absent from ordinary edits.
                    concept_changes = {
                        "titulo": titulo if titulo else None,
                        "tipo_titulo": tipo_titulo,
                        "categorias": categorias,
                        "es_algoritmo": es_algoritmo,
                        "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                        "comentario": comentario if comentario else None,
                        "image_ids": [asset["asset_id"] for asset in concept_media_assets],
                        # Keep concept-level citekey for backward compatibility.
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

                    # Add reference if provided
                    if ref_autor or ref_fuente:
                        concept_changes["referencia"] = {
                            "tipo_referencia": ref_tipo,
                            "autor": ref_autor if ref_autor else None,
                            "fuente": ref_fuente if ref_fuente else None,
                            "anio": ref_anio if ref_anio else None,
                            "tomo": ref_tomo if ref_tomo else None,
                            "edicion": ref_edicion if ref_edicion else None,
                            "paginas": ref_paginas if ref_paginas else None,
                            "capitulo": ref_capitulo if ref_capitulo else None,
                            "seccion": ref_seccion if ref_seccion else None,
                            "editorial": ref_editorial if ref_editorial else None,
                            "doi": ref_doi if ref_doi else None,
                            "url": ref_url if ref_url else None,
                            "issbn": ref_issbn if ref_issbn else None,
                            # NEW: Persist citekey at reference-level (preferred).
                            "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                        }

                    # Add teaching context if provided
                    if nivel_contexto or grado_formalidad:
                        concept_changes["contexto_docente"] = {
                            "nivel_contexto": nivel_contexto,
                            "grado_formalidad": grado_formalidad
                        }

                    # Add technical metadata if provided
                    if usa_notacion_formal is not None or incluye_demostracion is not None:
                        concept_changes["metadatos_tecnicos"] = {
                            "usa_notacion_formal": usa_notacion_formal,
                            "incluye_demostracion": incluye_demostracion,
                            "es_definicion_operativa": es_definicion_operativa,
                            "es_concepto_fundamental": es_concepto_fundamental,
                            "requiere_conceptos_previos": [c.strip() for c in requiere_conceptos_previos.split(',')] if requiere_conceptos_previos else None,
                            "incluye_ejemplo": incluye_ejemplo,
                            "es_autocontenible": es_autocontenible,
                            "tipo_presentacion": tipo_presentacion,
                            "nivel_simbolico": nivel_simbolico,
                            "tipo_aplicacion": tipo_aplicacion if tipo_aplicacion else None
                        }

                    update_result = update_concept_fields_preserving_identity(
                        db,
                        concept_id=original_concept_id,
                        source=original_source,
                        expected_source_id=original_source_id,
                        changes=concept_changes,
                        contenido_latex=contenido_latex,
                        now=datetime.now(),
                    )

                    if update_result.status is ConceptEditStatus.SUCCESS:
                        st.success(
                            f"✅ Concept '{original_concept_id}' updated successfully "
                            f"in {current_db} without changing identity!"
                        )
                        st.balloons()
                        st.session_state.pop(legacy_last_selected_key, None)
                        st.rerun()
                    elif update_result.status is ConceptEditStatus.CONCEPT_NOT_FOUND:
                        st.error("❌ The original concept no longer exists. Nothing was saved.")
                    elif update_result.status is ConceptEditStatus.LATEX_NOT_FOUND:
                        st.error(
                            "❌ The matching LaTeX document is missing. "
                            "The concept was not updated."
                        )
                    elif update_result.status is ConceptEditStatus.STALE_IDENTITY:
                        st.error(
                            "❌ The stored concept identity changed after this form was loaded. "
                            "Reload before retrying."
                        )
                    elif update_result.status is ConceptEditStatus.FAILED_COMPENSATED:
                        st.error(
                            "❌ The coordinated update failed. The original concept data "
                            "was restored; no complete update was reported."
                        )
                    else:
                        st.error(
                            "❌ The update may be partial and requires recovery before retrying. "
                            f"Details: {update_result.message}"
                        )

                except Exception as e:
                    st.error(f"❌ Error updating concept: {e}")

        # PDF Generation Button for Edit Concept
        st.markdown("---")
        st.subheader("📄 Generar PDF")
        edit_pdf_context = pdf_preview_context(
            "edit_concept",
            current_db,
            original_source,
            original_concept_id,
        )
        concept_pdf_root = get_exports_dir(
            configured=resolve_config().export_directory
        ) / "concepts"

        # Check if we have the minimum required data for PDF generation
        if original_concept_id and original_source and contenido_latex:
            if st.button(
                "📄 Generar vista previa PDF",
                key="edit_pdf_btn",
                type="secondary",
            ):
                # Build concept data for PDF generation
                pdf_concept_data = {
                    "id": original_concept_id,
                    "tipo": selected_concept['tipo'],
                    "titulo": titulo if titulo else original_concept_id,
                    "categorias": categorias,
                    "contenido_latex": contenido_latex,
                    "source": original_source,
                    "comentario": comentario if comentario else None
                }

                # Add reference if provided
                if ref_autor or ref_fuente:
                    pdf_concept_data["referencia"] = {
                        "tipo_referencia": ref_tipo,
                        "autor": ref_autor if ref_autor else None,
                        "fuente": ref_fuente if ref_fuente else None,
                        "anio": ref_anio if ref_anio else None,
                        "tomo": ref_tomo if ref_tomo else None,
                        "edicion": ref_edicion if ref_edicion else None,
                        "paginas": ref_paginas if ref_paginas else None,
                        "capitulo": ref_capitulo if ref_capitulo else None,
                        "seccion": ref_seccion if ref_seccion else None,
                        "editorial": ref_editorial if ref_editorial else None,
                        "doi": ref_doi if ref_doi else None,
                        "url": ref_url if ref_url else None,
                        "issbn": ref_issbn if ref_issbn else None,
                        # NEW: Persist citekey at reference-level too.
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

                _generate_concept_pdf_preview(
                    "edit_concept",
                    pdf_concept_data,
                    context_identity=edit_pdf_context,
                    allowed_root=concept_pdf_root,
                )
        else:
            clear_pdf_preview(st.session_state, "edit_concept")
            st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")

        render_pdf_preview(
            st,
            st.session_state,
            "edit_concept",
            context_identity=edit_pdf_context,
        )

        with col2:
            if st.button("🔄 Reset to Original"):
                st.rerun()

        with col3:
            # Persistent delete confirmation (Streamlit buttons are one-shot per rerun)
            if "delete_armed_edit" not in st.session_state:
                st.session_state["delete_armed_edit"] = False

            if st.button("🗑️ Delete Concept", key="delete_edit"):
                st.session_state["delete_armed_edit"] = True

            if st.session_state["delete_armed_edit"]:
                st.warning("⚠️ This will permanently delete the concept and related data.")
                col_del_1, col_del_2 = st.columns(2)

                with col_del_1:
                    if st.button("⚠️ Confirm Delete", key="confirm_delete_edit"):
                        try:
                            # Delete concept and LaTeX content
                            db.concepts.delete_one({"id": selected_concept['id'], "source": selected_concept['source']})
                            db.latex_documents.delete_one({"id": selected_concept['id'], "source": selected_concept['source']})

                            # Delete related relations
                            db.relations.delete_many({
                                "$or": [
                                    {"desde": f"{selected_concept['id']}@{selected_concept['source']}"},
                                    {"hasta": f"{selected_concept['id']}@{selected_concept['source']}"}
                                ]
                            })

                            st.session_state["delete_armed_edit"] = False
                            st.success("✅ Concept deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error deleting concept: {e}")

                with col_del_2:
                    if st.button("Cancel", key="cancel_delete_edit"):
                        st.session_state["delete_armed_edit"] = False
                        st.info("Deletion cancelled.")

# Browse Concepts page
elif page == "📚 Browse Concepts":
    st.title("📚 Browse Mathematical Concepts")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Browsing concepts in: **{current_db}**")

    # Filters
    st.subheader("🔍 Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        filter_type = st.selectbox("Type", ["All"] + list(db.concepts.distinct("tipo")))

    with col2:
        filter_source = st.selectbox("Source", ["All"] + list(db.concepts.distinct("source")))

    with col3:
        search_term = st.text_input("Search", placeholder="Search by title or ID...")

    # Build query
    query = {}
    if filter_type != "All":
        query["tipo"] = filter_type
    if filter_source != "All":
        query["source"] = filter_source
    if search_term:
        query["$or"] = [
            {"titulo": {"$regex": search_term, "$options": "i"}},
            {"id": {"$regex": search_term, "$options": "i"}}
        ]

    # Execute query
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))

    st.subheader(f"📊 Results ({len(concepts)} concepts)")

    # =========================
    # Quarto Book Export (NEW)
    # =========================
    st.markdown("---")
    st.subheader("📘 Export to Quarto Book")

    # Build list of selectable IDs
    concept_id_map = {
        f"{c.get('titulo', c['id'])} [{c['tipo']}]": c["id"]
        for c in concepts
    }

    selected_labels = st.multiselect(
        "Select concepts to export",
        options=list(concept_id_map.keys()),
    )


    build_dir = st.text_input(
        "Quarto build directory",
        value=str(get_exports_dir(configured=resolve_config().export_directory) / "quarto"),
    )


    force_build = st.checkbox(
        "Overwrite existing build directory",
        value=False,
    )

    # MVP-B: LaTeX preflight (pdflatex compile check) before export
    preflight_compile = st.checkbox(
        "Preflight LaTeX (pdflatex compile check) before export",
        value=True,
        help="Compiles each selected concept with pdflatex + miestilo.sty. Blocks export on fatal errors.",
    )

    if st.button("🚀 Export selected concepts to Quarto"):
        if not selected_labels:
            st.warning("Please select at least one concept.")
        else:
            try:
                from pathlib import Path

                from exporters_quarto.quarto_exporter import QuartoBookExporter
                from scripts.export_quarto_book import _write_book_quarto_yml
                build_path = validate_mutable_path(resolve_home_path(build_dir))
                selected_ids = {concept_id_map[l] for l in selected_labels}
                selected_concepts = []
                for c in concepts:
                    if c["id"] in selected_ids:
                        latex_doc = db.latex_documents.find_one({"id": c["id"], "source": c["source"]})
                        c2 = dict(c)  # copia para no mutar la lista base
                        c2["contenido_latex"] = (latex_doc or {}).get("contenido_latex", "")
                        selected_concepts.append(c2)

                # --- MVP-B: LaTeX preflight (pdflatex compile check) ---
                if preflight_compile:
                    import shutil
                    import tempfile

                    if not shutil.which("pdflatex"):
                        raise RuntimeError(
                            "pdflatex not found. Install TeX Live (texlive-latex-base) or disable the preflight checkbox."
                        )

                    style_dirs = [
                        build_path / "styles",
                        PROJECT_ROOT / "quarto_book" / "styles",
                        PROJECT_ROOT / "templates_latex",
                    ]

                    def _find_style_file(name: str) -> Path:
                        for style_dir in style_dirs:
                            candidate = style_dir / name
                            if candidate.exists():
                                return candidate
                        searched = ", ".join(str(path) for path in style_dirs)
                        raise FileNotFoundError(f"{name} not found in: {searched}")

                    miestilo_src = _find_style_file("miestilo.sty")
                    coloredtheorem_src = _find_style_file("coloredtheorem.sty")


                    failures: list[tuple[str, str, str]] = []
                    progress = st.progress(0, text="Preflight LaTeX: compiling selected concepts...")
                    total = max(1, len(selected_concepts))

                    for idx, c in enumerate(selected_concepts, start=1):
                        latex_body = (c.get("contenido_latex") or "").strip()
                        # Empty LaTeX content is treated as OK (non-blocking)
                        if not latex_body:
                            progress.progress(int(idx * 100 / total))
                            continue

                        latex_runtime = validate_mutable_path(get_latex_runtime_dir())
                        latex_runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with tempfile.TemporaryDirectory(prefix="mkb_preflight_", dir=latex_runtime) as td:
                            td_path = Path(td)
                            shutil.copy2(miestilo_src, td_path / "miestilo.sty")
                            (td_path / "styles").mkdir(parents=True, exist_ok=True)
                            shutil.copy2(coloredtheorem_src, td_path / "styles" / "coloredtheorem.sty")

                            tex = (
                                "\\documentclass{article}\n"
                                "\\usepackage{miestilo}\n"
                                "\\begin{document}\n"
                                + latex_body
                                + "\n\\end{document}\n"
                            )
                            (td_path / "main.tex").write_text(tex, encoding="utf-8")


                            command = [
                                "pdflatex",
                                "-interaction=nonstopmode",
                                "-halt-on-error",
                                "-file-line-error",
                                "main.tex",
                            ]
                            key = f"{c.get('id')}@{c.get('source')}"
                            try:
                                compile_info = run_latex_until_stable(
                                    command,
                                    cwd=str(td_path),
                                    tex_file=td_path / "main.tex",
                                    pdf_path=td_path / "main.pdf",
                                    log_path=td_path / "main.log",
                                    timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                                    max_passes=LATEX_MAX_PASSES,
                                )
                            except TimeoutError:
                                failures.append(
                                    (
                                        key,
                                        str(c.get("titulo") or ""),
                                        latex_timeout_message(
                                            td_path / "main.tex",
                                            command,
                                            PDF_COMPILE_TIMEOUT_SECONDS,
                                        ),
                                    )
                                )
                                progress.progress(int(idx * 100 / total))
                                continue

                            if compile_info["status"] == "failed":
                                tail = compile_info.get("log_excerpt") or output_tail(
                                    compile_info.get("stdout", ""),
                                    compile_info.get("stderr", ""),
                                    lines=80,
                                )
                                failures.append((key, str(c.get("titulo") or ""), tail))

                        progress.progress(int(idx * 100 / total))

                    progress.empty()
                    if failures:
                        st.error(
                            f"❌ LaTeX preflight failed for {len(failures)} concept(s). Export blocked."
                        )
                        for key, title, tail in failures:
                            with st.expander(f"Preflight error: {title or key}"):
                                st.code(tail)
                        st.stop()
                # --- end MVP-B ---

                template_dir = PROJECT_ROOT / "quarto_book"

                exporter = QuartoBookExporter(
                    template_dir=template_dir,
                    build_dir=build_path,
                    allowed_root=build_path.parent,
                )

                exporter.prepare_build(force=force_build)
                exporter.export_concepts(selected_concepts)

                _write_book_quarto_yml(build_path)

                st.success(f"Quarto book exported to: {build_path}")
                st.info("Next step: run `quarto render` inside that directory.")

            except Exception as e:
                st.error(f"Quarto export failed: {e}")
    if concepts:
        for concept in concepts:
            with st.expander(f"{concept.get('titulo', concept['id'])} ({concept['tipo']})"):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**ID:** {concept['id']}")
                    st.write(f"**Source:** {concept['source']}")
                    st.write(f"**Categories:** {', '.join(concept.get('categorias', []))}")

                    if concept.get('comentario'):
                        st.write(f"**Comment:** {concept['comentario']}")

                    # Show LaTeX content
                    latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": concept['source']})
                    if latex_doc:
                        st.subheader("LaTeX Content")
                        st.code(latex_doc['contenido_latex'], language="latex")
                    assets = get_concept_media_assets(db, concept["id"], concept["source"])
                    if assets:
                        st.subheader("Images")
                        for asset in assets:
                            _render_media_asset_preview(asset)

                with col2:
                    # Actions
                    if st.button("📤 Export PDF", key=f"export_{concept['id']}"):
                        try:
                            exportador = ExportadorLatex()
                            exportador.exportar_concepto(concept, latex_doc['contenido_latex'])
                            st.success("PDF exported successfully!")
                        except Exception as e:
                            st.error(f"Export failed: {e}")

                    if st.button("🔗 View Relations", key=f"relations_{concept['id']}"):
                        relations = db.get_relations(desde_id=concept['id'], desde_source=concept['source'])
                        if relations:
                            st.write("**Relations:**")
                            for rel in relations:
                                st.write(f"• {rel.tipo}: {rel.hasta_id}@{rel.hasta_source}")
                        else:
                            st.write("No relations found.")

                    if st.button("🗑️ Delete", key=f"delete_{concept['id']}"):
                        if st.button("⚠️ Confirm Delete", key=f"confirm_{concept['id']}"):
                            db.concepts.delete_one({"id": concept['id'], "source": concept['source']})
                            db.latex_documents.delete_one({"id": concept['id'], "source": concept['source']})
                            st.success("Concept deleted!")
                            st.rerun()
    else:
        st.info("No concepts found matching the criteria.")

# Manage Relations page
elif page == "🔗 Manage Relations":
    st.title("🔗 Manage Concept Relations")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Managing relations in: **{current_db}**")

    # Import interactive graph manager
    from editor.interactive_graph import InteractiveGraphManager
    graph_manager = InteractiveGraphManager(db)

    # Tab navigation for relations
    tab1, tab2, tab3 = st.tabs(["➕ Add New Relation", "✏️ Edit Relations", "📊 View Relations"])

    with tab1:
        st.subheader("➕ Add New Relation")
        # Inicializa IDs y fuentes para que siempre existan
        desde_id, desde_source = "", ""
        hasta_id, hasta_source = "", ""

        # Smart concept selection
        st.write("**Select Concepts:**")

        col_from, col_to = st.columns(2)

        with col_from:
            st.write("**From Concept:**")
            # Filter concepts for "from" selection
            desde_source_filter = st.selectbox("From Source", ["All"] + list(db.concepts.distinct("source")), key="desde_source_filter")
            desde_type_filter = st.selectbox("From Type", ["All"] + list(db.concepts.distinct("tipo")), key="desde_type_filter")

            # Build query for "from" concepts
            desde_query = {}
            if desde_source_filter != "All":
                desde_query["source"] = desde_source_filter
            if desde_type_filter != "All":
                desde_query["tipo"] = desde_type_filter

            desde_concepts = list(db.concepts.find(desde_query).sort("fecha_creacion", -1))

            if desde_concepts:
                desde_options = []
                desde_map = {}
                for concept in desde_concepts:
                    display_name = f"{concept.get('titulo', concept['id'])} ({concept['tipo']} - {concept['source']})"
                    desde_options.append(display_name)
                    desde_map[display_name] = concept

                selected_desde = st.selectbox("Choose From Concept", desde_options, key="desde_select")
                if selected_desde:
                    desde_concept = desde_map[selected_desde]
                    desde_id = desde_concept['id']
                    desde_source = desde_concept['source']
                    st.info(f"Selected: {desde_id}@{desde_source}")
            else:
                st.warning("No concepts found with selected filters")
                desde_id = ""
                desde_source = ""

        with col_to:
            st.write("**To Concept:**")
            # Filter concepts for "to" selection
            hasta_source_filter = st.selectbox("To Source", ["All"] + list(db.concepts.distinct("source")), key="hasta_source_filter")
            hasta_type_filter = st.selectbox("To Type", ["All"] + list(db.concepts.distinct("tipo")), key="hasta_type_filter")

            # Build query for "to" concepts
            hasta_query = {}
            if hasta_source_filter != "All":
                hasta_query["source"] = hasta_source_filter
            if hasta_type_filter != "All":
                hasta_query["tipo"] = hasta_type_filter

            hasta_concepts = list(db.concepts.find(hasta_query).sort("fecha_creacion", -1))

            if hasta_concepts:
                hasta_options = []
                hasta_map = {}
                for concept in hasta_concepts:
                    display_name = f"{concept.get('titulo', concept['id'])} ({concept['tipo']} - {concept['source']})"
                    hasta_options.append(display_name)
                    hasta_map[display_name] = concept

                selected_hasta = st.selectbox("Choose To Concept", hasta_options, key="hasta_select")
                if selected_hasta:
                    hasta_concept = hasta_map[selected_hasta]
                    hasta_id = hasta_concept['id']
                    hasta_source = hasta_concept['source']
                    st.info(f"Selected: {hasta_id}@{hasta_source}")
            else:
                st.warning("No concepts found with selected filters")
                hasta_id = ""
                hasta_source = ""

        # Relation details
        st.subheader("🔗 Relation Details")

        col_rel_type, col_rel_desc = st.columns(2)
        with col_rel_type:
            tipo_relacion = st.selectbox("Relation Type", [t.value for t in TipoRelacion], key="new_rel_type")
        with col_rel_desc:
            descripcion = st.text_area("Description (Optional)", placeholder="Describe the relationship...", key="new_rel_desc")

        # -----------------------
        # 🎓 Relation Tutor (educational guidance)
        # -----------------------
        if desde_id and hasta_id:
            st.markdown("---")
            st.subheader("🎓 Relation Tutor")
            # Fetch full concept docs once (for cards + heuristics)
            _from_doc = db.concepts.find_one({"id": desde_id, "source": desde_source}) or {}
            _to_doc = db.concepts.find_one({"id": hasta_id, "source": hasta_source}) or {}

            def _concept_label(doc: dict, fallback_id: str) -> str:
                return doc.get("titulo") or doc.get("title") or fallback_id

            def _node_key(cid: str, csource: str) -> str:
                return f"{cid}@{csource}"
            # A/B cards + relation notation
            a_col, mid_col, b_col = st.columns([5, 2, 5])
            with a_col:
                st.markdown("**A (From)**")
                st.markdown(
                    f"""<div class="concept-card">
                    <div style="font-size:1.05rem;font-weight:700">{_concept_label(_from_doc, desde_id)}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>Type:</b> {_from_doc.get('tipo','—')} &nbsp;&nbsp; <b>Source:</b> {desde_source}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>ID:</b> {desde_id}</div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with mid_col:
                st.markdown("**Relation**")
                rel_symbol = {
                    "equivalente": "≡",
                    "implica": "⇒",
                    "requiere_concepto": "↗",
                    "deriva_de": "↩",
                    "inspirado_en": "≈",
                    "contrasta_con": "≠",
                    "contradice": "⊥",
                    "contra_ejemplo": "→/",
                }.get(tipo_relacion, "→")
                st.markdown(
                    f"""<div class="metric-card" style="text-align:center">
                    <div style="font-size:1.6rem;font-weight:800">{rel_symbol}</div>
                    <div style="margin-top:0.25rem"><b>{tipo_relacion}</b></div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with b_col:
                st.markdown("**B (To)**")
                st.markdown(
                    f"""<div class="concept-card">
                    <div style="font-size:1.05rem;font-weight:700">{_concept_label(_to_doc, hasta_id)}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>Type:</b> {_to_doc.get('tipo','—')} &nbsp;&nbsp; <b>Source:</b> {hasta_source}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>ID:</b> {hasta_id}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

            # Heuristic warnings
            warnings = []
            a_key = _node_key(desde_id, desde_source)
            b_key = _node_key(hasta_id, hasta_source)

            _direct = db.relations.find_one({"desde": a_key, "hasta": b_key, "tipo": tipo_relacion})
            _inverse = db.relations.find_one({"desde": b_key, "hasta": a_key, "tipo": tipo_relacion})

            if _direct:
                warnings.append(f"Direct relation exists: {_direct['desde']} --[{_direct['tipo']}]--> {_direct['hasta']}")
            if _inverse:
                warnings.append(f"Inverse relation exists: {_inverse['desde']} --[{_inverse['tipo']}]--> {_inverse['hasta']}")

            if tipo_relacion == "equivalente":
                if _from_doc.get("tipo") and _to_doc.get("tipo") and _from_doc.get("tipo") != _to_doc.get("tipo"):
                    warnings.append("Equivalence across different concept types is often non-trivial. Document the bridge explicitly.")
                if desde_source != hasta_source:
                    warnings.append("Equivalence across different sources can indicate duplicates or parallel formulations. Add a short justification or reference.")

            if tipo_relacion == "implica" and (_from_doc.get("tipo") == "nota" and _to_doc.get("tipo") in {"teorema", "proposicion", "corolario", "lema"}):
                warnings.append("A 'nota' implying a formal statement can be valid, but usually requires explicit assumptions. Capture them in the proof sketch.")

            for w in warnings:
                st.warning(f"⚠️ {w}")

            # Checklist
            st.markdown("### ✅ Verification Checklist")

            RELATION_CHECKLIST = {
                "equivalente": {
                    "definition": "Two concepts are equivalent when they define the same object/statement under compatible hypotheses, typically via A⇒B and B⇒A.",
            "essential": [
                "Same mathematical object/statement (up to notation or framework).",
                "Hypotheses and scope are compatible (no hidden assumptions).",
                "You can justify both directions (A⇒B and B⇒A), or cite a reliable reference.",
            ],
            "optional": [
                "You can map notation/terminology from A to B explicitly.",
                "You can explain why equivalence is pedagogically useful (deduplication or alternate viewpoint).",
            ],},
            "implica": {
            "definition": "A implies B when, assuming A (and its hypotheses), B follows without adding extra assumptions beyond those stated.",
            "essential": [
                "You can state the implication A ⇒ B clearly.",
                "No extra hypotheses are required beyond what is already in A (or you list them explicitly).",
                "You can provide at least a short proof idea or reference.",
            ],
            "optional": [
                "You can provide a counterexample showing why the reverse does not hold (if applicable).",
            ],},
            "requiere_concepto": {
            "definition": "A requires B when understanding/using A depends on knowing B (B appears in the definition/proof/notation).",
            "essential": [
                "B appears in the definition/proof/notation of A, or is a prerequisite to parse it.",
                "You can point to where B is used (section, line, or short description).",
            ],
            "optional": [
                "You can suggest an order of study (B before A) in one sentence.",
            ],},

            "deriva_de": {
                "definition": "A derives from B when A is obtained as a specialization, reformulation, or construction based on B.",
                "essential": ["You can explain how A is obtained from B (special case, restriction, construction, or reformulation).",],
            "optional": ["You can specify what changes from B to A (hypotheses, notation, scope, or level of abstraction).",],},

            "inspirado_en": {
        "definition": "A is inspired by B when B motivated the ideas or approach of A, without strict logical dependence.",
        "essential": [
            "You can identify the idea, technique, or intuition from B that influenced A.",
        ],
        "optional": [
            "You can explain why the relation is not 'implica' or 'equivalente'.",
        ],
    },

    "contrasta_con": {
        "definition": "A contrasts with B when they address similar topics but differ in assumptions, scope, or conclusions.",
        "essential": [
            "You can state at least one concrete conceptual difference between A and B.",
        ],
        "optional": [
            "You can explain when one is preferable over the other.",
        ],
    },

    "contradice": {
    "definition": "A contradicts B when both cannot be true simultaneously under the same framework and compatible hypotheses.",
    "essential": [
        "You can state the conflicting claims precisely (what A asserts vs what B asserts).",
        "You can specify the framework/definitions under which the contradiction holds (same meanings for terms).",
        "You can point to the exact assumption(s) where the conflict arises, or cite a reliable reference.",
    ],
    "optional": [
        "You can clarify whether the contradiction is absolute or only under certain hypotheses.",
        "You can suggest how to resolve it (add a missing hypothesis, refine a definition, or restrict scope).",
    ],},
    "contra_ejemplo": {
    "definition": "A is a counterexample to B when A shows that a general claim in B fails, typically by satisfying the stated hypotheses while violating the conclusion (or revealing a missing hypothesis).",
    "essential": [
        "You can state the claim in B that is being refuted (hypotheses ⇒ conclusion).",
        "A satisfies the stated hypotheses (or you clearly explain which hypothesis is missing/incorrect in B).",
        "A violates the conclusion, and you can explain why (brief argument or reference).",
    ],
    "optional": [
        "You can indicate the minimal additional hypothesis needed to make B true.",
        "You can provide a short intuition of why the claim fails and what it teaches.",
    ], },
    }
            spec = RELATION_CHECKLIST.get(tipo_relacion, None)
            if spec:
                st.info(spec["definition"])
                tutor_key = f"rel_tutor::{a_key}::{b_key}::{tipo_relacion}"

                def _tri_state(label: str, key: str):
                    return st.selectbox(label, ["✅ Sí", "🤔 No sé", "❌ No"], index=1, key=key)

                essential_answers = []
                for idx, crit in enumerate(spec["essential"]):
                    essential_answers.append(_tri_state(f"Essential {idx+1}: {crit}", f"{tutor_key}::ess::{idx}"))

                with st.expander("Optional checks", expanded=False):
                    for idx, crit in enumerate(spec.get("optional", [])):
                        _tri_state(f"Optional {idx+1}: {crit}", f"{tutor_key}::opt::{idx}")

                # Semáforo
                if any(a == "❌ No" for a in essential_answers):
                    st.error("🔴 Quality: one or more essential criteria are not satisfied.")
                elif all(a == "✅ Sí" for a in essential_answers):
                    st.success("🟢 Quality: essential criteria satisfied.")
                else:
                    st.warning("🟡 Quality: some essential criteria are unknown. Consider adding evidence.")
                # Plantilla de prueba
                if tipo_relacion in {"equivalente", "implica"}:
                    st.markdown("### ✍️ Proof / Justification Sketch")
                    if tipo_relacion == "equivalente":
                        st.text_area("A ⇒ B (idea / key steps)", key=f"{tutor_key}::proof::a_to_b", height=90)
                        st.text_area("B ⇒ A (idea / key steps)", key=f"{tutor_key}::proof::b_to_a", height=90)
                    else:
                        st.text_area("A ⇒ B (idea / key steps)", key=f"{tutor_key}::proof::a_to_b", height=110)
                        st.text_area("Extra hypotheses (if any)", key=f"{tutor_key}::proof::extra_hyp", height=70)
                # Strict mode
                strict_mode = st.checkbox("Strict mode (block saving unless essential criteria are ✅ Sí)", value=False, key=f"{tutor_key}::strict")
                st.session_state["__rel_can_save__"] = (not strict_mode) or all(a == "✅ Sí" for a in essential_answers)
            else:
                st.caption("No tutor checklist is defined yet for this relation type. You can still add it, but consider documenting it in the description.")
                st.session_state["__rel_can_save__"] = True
        else:
            st.session_state["__rel_can_save__"] = False
        # Visual preview of selected concepts
        if desde_id and hasta_id:
            st.markdown("---")
            st.subheader("👁️ Visual Preview")

            preview_concepts = []
            preview_relations = []

            a_key = f"{desde_id}@{desde_source}"
            b_key = f"{hasta_id}@{hasta_source}"

            # Add both selected concepts
            desde_concept = db.concepts.find_one({"id": desde_id, "source": desde_source})
            hasta_concept = db.concepts.find_one({"id": hasta_id, "source": hasta_source})

            if desde_concept:
                preview_concepts.append(desde_concept)
            if hasta_concept:
                preview_concepts.append(hasta_concept)

            # Mini Camino B: 1-hop context
            col_ctx1, col_ctx2 = st.columns([2, 3])
            with col_ctx1:
                include_context = st.checkbox(
                    "Include context",
                    value=True,
                    key="rel_preview_context")
            with col_ctx2:
                preview_depth = st.slider(
                    "Preview depth (hops)",
                    min_value=1,
                    max_value=3,
                    value=1,
                    step=1,
                    disabled=not include_context,
                    help="1 = neighbors, 2 = neighbors of neighbors, 3 = deeper context",
                    key="rel_preview_depth"
                    )

            if include_context:
                ctx_relations = list(db.relations.find({
                    "$or": [
                         {"desde": a_key}, {"hasta": a_key},
                          {"desde": b_key}, {"hasta": b_key},
                    ]
                }))
                ctx_nodes = {a_key, b_key}
                for rctx in ctx_relations:
                    if rctx.get("desde"):
                        ctx_nodes.add(rctx["desde"])
                    if rctx.get("hasta"):
                        ctx_nodes.add(rctx["hasta"])
                existing_nodes = {(c.get("id"), c.get("source")) for c in preview_concepts}
                for nk in sorted(ctx_nodes):
                    try:
                        cid, csrc = nk.split("@", 1)
                    except ValueError:
                        continue
                    if (cid, csrc) in existing_nodes:
                        continue
                    doc = db.concepts.find_one({"id": cid, "source": csrc})
                    if doc:
                        preview_concepts.append(doc)
                        existing_nodes.add((cid, csrc))

                existing_triplets = {(r.get("desde"), r.get("hasta"), r.get("tipo")) for r in preview_relations}
                for rctx in ctx_relations:
                    trip = (rctx.get("desde"), rctx.get("hasta"), rctx.get("tipo"))
                    if trip not in existing_triplets:
                        preview_relations.append(rctx)
                        existing_triplets.add(trip)
            # Existing relations between A and B
            existing_relations = db.relations.find({
                "$or": [
                    {"desde": a_key, "hasta": b_key},
                    {"desde": b_key, "hasta": a_key}
                ]
            })
            for rel in existing_relations:
                preview_relations.append(rel)

            # Add new relation preview
            preview_relations.append({
                "desde": a_key,
                "hasta": b_key,
                "tipo": tipo_relacion,
                "descripcion": descripcion
            })

            # Generate mini preview graph
            if preview_concepts:
                try:
                    with st.spinner("🔄 Generating preview..."):
                        # Debug: Show the data being used for preview

                        with st.expander("🔍 Debug: Preview Data", expanded=False):
                            # 1) Toggle de display
                            display_mode = st.radio(
                                "Show nodes/relations as:",
                                ["Titles", "IDs", "Both"],
                                horizontal=True,
                                key="debug_display_mode"
                            )

                            # 2) Index para resolver id@source -> titulo
                            def _node_key(cid: str, csrc: str) -> str:
                                return f"{cid}@{csrc}"

                            def _title(doc: dict) -> str:
                                return doc.get("titulo") or doc.get("title") or doc.get("id", "—")

                            concept_by_key = {}
                            for c in preview_concepts:
                                cid = c.get("id")
                                csrc = c.get("source")
                                if cid and csrc:
                                    concept_by_key[_node_key(cid, csrc)] = c

                            def _fmt_node(node_key: str) -> str:
                                doc = concept_by_key.get(node_key, {})
                                t = _title(doc)
                                if display_mode == "Titles":
                                    return t
                                if display_mode == "IDs":
                                    return node_key
                                # Both
                                return f"{t}  ({node_key})"

                            # 3) Tabla amigable de conceptos
                            st.markdown("**Concepts**")
                            concept_rows = []
                            for c in preview_concepts:
                                node_key = _node_key(c.get("id",""), c.get("source",""))
                                concept_rows.append({
                                    "Title": _title(c),
                                    "Type": c.get("tipo", "—"),
                                    "Source": c.get("source", "—"),
                                    "ID": c.get("id", "—"),
                                    "NodeKey": node_key,})
                            st.dataframe(concept_rows, width='stretch', hide_index=True)
                            # 4) Tabla amigable de relaciones
                            st.markdown("**Relations**")
                            rel_rows = []
                            for r in preview_relations:
                                desde = r.get("desde","")
                                hasta = r.get("hasta","")
                                rel_rows.append({
                                    "From": _fmt_node(desde) if "@" in desde else desde,
                                    "Type": r.get("tipo","—"),
                                    "To": _fmt_node(hasta) if "@" in hasta else hasta,
                                    "FromKey": desde,
                                    "ToKey": hasta,
                                    })
                            st.dataframe(rel_rows, width='stretch', hide_index=True)
                            # 5) Export JSON (preview completo)
                            import json
                            export_payload = {
                                "concepts": preview_concepts,
                                "relations": preview_relations,
                                 "meta": {
                                     "from": {"id": desde_id, "source": desde_source},
                                     "to": {"id": hasta_id, "source": hasta_source},
                                     "new_relation": {"tipo": tipo_relacion, "descripcion": descripcion},
                                     "include_1hop_context": st.session_state.get("rel_preview_context", False),
                                 }
                             }
                            st.download_button(
                                "⬇️ Export preview as JSON",
                                data=json.dumps(
                                    export_payload,
                                    ensure_ascii=False,
                                    indent=2,
                                    default=str
                                ),
                                file_name="relation_preview.json",
                                mime="application/json",
                                key="download_preview_json")

                        def _sanitize_mongo(doc: dict) -> dict:
                            out = dict(doc)
                            if "_id" in out:
                                out["_id"] = str(out["_id"])
                            return out

                        concepts_clean = [_sanitize_mongo(c) for c in preview_concepts if c]
                        relations_clean = [_sanitize_mongo(r) for r in preview_relations if r]

                        grafo = GrafoConocimiento(concepts_clean, relations_clean)
                        grafo.construir_grafo(
                            tipos_relacion=list({r.get("tipo") for r in relations_clean if r.get("tipo")}),
                            tipos_concepto=list({c.get("tipo") for c in concepts_clean if c.get("tipo")}),)

                        html = grafo.exportar_html(salida=None)
                        st.download_button(
                            label="⬇️ Download map (HTML)",
                            data=html.encode("utf-8"),
                            file_name="relation_preview_map.html",
                            mime="text/html",
                            key="download_preview_map_html",
                        )
                        components.html(html, height=650, scrolling=False)

                except Exception as e:
                    st.error(f"❌ Could not generate preview: {e}")
                    st.exception(e)
        ###################################################################################################
        # Add relation button
        can_save = st.session_state.get("__rel_can_save__", True)
        if not can_save:
            st.info("ℹ️ Strict mode is enabled and essential criteria are not all satisfied. Complete the checklist to enable saving.")
        if st.button("🔗 Add Relation", type="primary", key="add_rel_btn", disabled=not can_save):
            if desde_id and desde_source and hasta_id and hasta_source:
                if desde_id == hasta_id and desde_source == hasta_source:
                    st.error("❌ Cannot create relation from a concept to itself.")
                else:
                    try:
                        relation = db.add_relation(
                            desde_id=desde_id,
                            desde_source=desde_source,
                            hasta_id=hasta_id,
                            hasta_source=hasta_source,
                            tipo=tipo_relacion,
                            descripcion=descripcion
                        )
                        if relation:
                            st.success("✅ Relation added successfully!")
                            st.balloons()

                            # Auto-refresh the interactive graph if it exists
                            if hasattr(st.session_state, 'current_graph_file'):
                                st.info("🔄 The interactive graph will be updated on next refresh.")

                        else:
                            st.error("❌ Failed to add relation. Check if both concepts exist.")
                    except Exception as e:
                        st.error(f"❌ Error adding relation: {e}")
            else:
                st.error("❌ Please select both concepts.")

        # Live Graph Viewer

    with tab2:
        st.subheader("✏️ Edit Relations")

        # Filter relations for editing
        col1, col2 = st.columns(2)
        with col1:
            edit_filter_source = st.selectbox("Filter by Source", ["All"] + list(db.concepts.distinct("source")), key="edit_source_filter")
        with col2:
            edit_filter_type = st.selectbox("Filter by Type", ["All"] + [t.value for t in TipoRelacion], key="edit_type_filter")

        # Build query for relations to edit
        edit_query = {}
        if edit_filter_source != "All":
            edit_query["$or"] = [
                {"desde": {"$regex": f"@{edit_filter_source}$"}},
                {"hasta": {"$regex": f"@{edit_filter_source}$"}}
            ]
        if edit_filter_type != "All":
            edit_query["tipo"] = edit_filter_type

        edit_relations = list(db.relations.find(edit_query))

        if edit_relations:
            st.write(f"**Found {len(edit_relations)} relations to edit:**")

            for i, rel in enumerate(edit_relations):
                with st.expander(f"Edit: {rel['desde']} --[{rel['tipo']}]--> {rel['hasta']}", expanded=False):
                    st.write(f"**Current Relation:** {rel['desde']} --[{rel['tipo']}]--> {rel['hasta']}")

                    # Get concept details for display
                    desde_parts = rel['desde'].split('@')
                    hasta_parts = rel['hasta'].split('@')

                    desde_concept = db.concepts.find_one({"id": desde_parts[0], "source": desde_parts[1]})
                    hasta_concept = db.concepts.find_one({"id": hasta_parts[0], "source": hasta_parts[1]})

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**From Concept:**")
                        if desde_concept:
                            st.write(f"• **Title:** {desde_concept.get('titulo', desde_parts[0])}")
                            st.write(f"• **Type:** {desde_concept['tipo']}")
                            st.write(f"• **Source:** {desde_parts[1]}")
                        else:
                            st.write(f"• **ID:** {desde_parts[0]}")
                            st.write(f"• **Source:** {desde_parts[1]}")
                            st.warning("⚠️ Concept not found in database")

                    with col2:
                        st.write("**To Concept:**")
                        if hasta_concept:
                            st.write(f"• **Title:** {hasta_concept.get('titulo', hasta_parts[0])}")
                            st.write(f"• **Type:** {hasta_concept['tipo']}")
                            st.write(f"• **Source:** {hasta_parts[1]}")
                        else:
                            st.write(f"• **ID:** {hasta_parts[0]}")
                            st.write(f"• **Source:** {hasta_parts[1]}")
                            st.warning("⚠️ Concept not found in database")

                    st.markdown("---")

                    # Edit relation details
                    st.write("**Edit Relation Details:**")

                    col1, col2 = st.columns(2)
                    with col1:
                        new_tipo = st.selectbox(
                            "Relation Type",
                            [t.value for t in TipoRelacion],
                            index=[t.value for t in TipoRelacion].index(rel['tipo']),
                            key=f"edit_type_{i}")
                    with col2:
                        new_desc = st.text_area(
                            "Description",
                            value=rel.get('descripcion', ''),
                            key=f"edit_desc_{i}")

                    # Action buttons
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        if st.button("💾 Update Relation", key=f"update_rel_{i}"):
                            try:
                                # Update the relation
                                db.relations.update_one(
                                    {"_id": rel["_id"]},
                                    {
                                        "$set": {
                                            "tipo": new_tipo,
                                            "descripcion": new_desc
                                        }
                                    }
                                )
                                st.success("✅ Relation updated successfully!")
                            except Exception as e:
                                st.error(f"❌ Error updating relation: {e}")

                    with col2:
                        if st.button("🔄 Reset", key=f"reset_rel_{i}"):
                            st.rerun()

                    with col3:
                        delete_btn_key = f"delete_btn_{i}"
                        confirm_state_key = f"confirm_delete_state_{i}"
                        confirm_btn_key = f"confirm_delete_btn_{i}"



                        if confirm_state_key not in st.session_state:
                            st.session_state[confirm_state_key] = False

                        if st.button("🗑️ Delete", key=delete_btn_key):
                            st.session_state[confirm_state_key] = True

                        if st.session_state[confirm_state_key]:
                            st.warning("⚠️ This action is irreversible. Confirm deletion.")
                            if st.button("❌ Confirm Delete", key=confirm_btn_key):
                                try:
                                    db.relations.delete_one({"_id": rel["_id"]})
                                    st.success("✅ Relation deleted successfully!")
                                    st.session_state.pop(confirm_state_key, None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error deleting relation: {e}")
        else:
            st.info("No relations found with the selected filters.")

    with tab3:
        st.subheader("📊 View Relations")

        # Filter relations for viewing
        col1, col2 = st.columns(2)
        with col1:
            view_filter_source = st.selectbox("Filter by Source", ["All"] + list(db.concepts.distinct("source")), key="view_source_filter")
        with col2:
            view_filter_type = st.selectbox("Filter by Type", ["All"] + [t.value for t in TipoRelacion], key="view_type_filter")

        # Build query
        view_query = {}
        if view_filter_source != "All":
            view_query["$or"] = [
                {"desde": {"$regex": f"@{view_filter_source}$"}},
                {"hasta": {"$regex": f"@{view_filter_source}$"}}
            ]
        if view_filter_type != "All":
            view_query["tipo"] = view_filter_type

        view_relations = list(db.relations.find(view_query))

        if view_relations:
            st.write(f"**Found {len(view_relations)} relations:**")

            # Create a summary table
            relation_data = []
            for rel in view_relations:
                desde_parts = rel['desde'].split('@')
                hasta_parts = rel['hasta'].split('@')

                desde_concept = db.concepts.find_one({"id": desde_parts[0], "source": desde_parts[1]})
                hasta_concept = db.concepts.find_one({"id": hasta_parts[0], "source": hasta_parts[1]})

                relation_data.append({
                    "From": desde_concept.get('titulo', desde_parts[0]) if desde_concept else desde_parts[0],
                    "From Type": desde_concept['tipo'] if desde_concept else "Unknown",
                    "From Source": desde_parts[1],
                    "Relation": rel['tipo'],
                    "To": hasta_concept.get('titulo', hasta_parts[0]) if hasta_concept else hasta_parts[0],
                    "To Type": hasta_concept['tipo'] if hasta_concept else "Unknown",
                    "To Source": hasta_parts[1],
                    "Description": rel.get('descripcion', '')
                })

            df = pd.DataFrame(relation_data)
            st.dataframe(df, width='stretch')

            # Statistics
            st.subheader("📈 Relation Statistics")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Relations", len(view_relations))

            with col2:
                relation_types = [rel['tipo'] for rel in view_relations]
                unique_types = len(set(relation_types))
                st.metric("Unique Types", unique_types)

            with col3:
                sources_involved = set()
                for rel in view_relations:
                    desde_parts = rel['desde'].split('@')
                    hasta_parts = rel['hasta'].split('@')
                    sources_involved.add(desde_parts[1])
                    sources_involved.add(hasta_parts[1])
                st.metric("Sources Involved", len(sources_involved))

            # Type distribution
            if relation_types:
                type_counts = pd.Series(relation_types).value_counts()
                st.subheader("📊 Relation Type Distribution")
                st.bar_chart(type_counts)
        else:
            st.info("No relations found with the selected filters.")

# Knowledge Graph page
elif page == "📊 Knowledge Graph":
    st.title("📊 Knowledge Graph Visualization")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Generating graph from: **{current_db}**")
    graph_message = st.session_state.pop("knowledge_graph_message", None)
    if graph_message:
        message_type, message_text = graph_message
        if message_type == "success":
            st.success(message_text)
        elif message_type == "info":
            st.info(message_text)
        else:
            st.error(message_text)

    maps_col = db.db["knowledge_graph_maps"]
    try:
        all_maps = list(maps_col.find({}).sort("updated_at", -1).limit(200))
    except Exception as exc:
        all_maps = []
        st.error(f"No se pudieron listar los mapas guardados: {exc}")

    source_options = _knowledge_graph_source_options(db, all_maps)
    default_concept_type_options = ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"]
    saved_concept_type_options = {
        concept_type
        for doc in all_maps
        for concept_type in (doc.get("filters", {}) or {}).get("concept_types", [])
        if isinstance(concept_type, str) and concept_type.strip()
    }
    graph_concept_type_options = {
        concept_type
        for doc in all_maps
        for concept_type in infer_concept_types_from_graph_state(doc.get("graph_state", {}))
        if concept_type
    }
    db_concept_type_options = {
        concept_type
        for concept_type in db.concepts.distinct("tipo")
        if isinstance(concept_type, str) and concept_type.strip()
    }
    concept_type_options = sorted(
        set(default_concept_type_options)
        | saved_concept_type_options
        | graph_concept_type_options
        | db_concept_type_options,
        key=str.lower,
    )
    saved_relation_type_options = {
        relation_type
        for doc in all_maps
        for relation_type in (doc.get("filters", {}) or {}).get("relation_types", [])
        if isinstance(relation_type, str) and relation_type.strip()
    }
    db_relation_type_options = {
        relation_type
        for relation_type in db.relations.distinct("tipo")
        if isinstance(relation_type, str) and relation_type.strip()
    }
    relation_type_options = sorted(
        {t.value for t in TipoRelacion} | saved_relation_type_options | db_relation_type_options,
        key=str.lower,
    )
    kg_sections = ["📊 Nuevo mapa", "📚 Mapas guardados", "✏️ Editar mapa", "📤 Exportar / importar"]
    requested_kg_section = st.session_state.pop("knowledge_graph_section_request", None)
    if requested_kg_section in kg_sections:
        st.session_state["knowledge_graph_section"] = requested_kg_section
    elif "knowledge_graph_section" not in st.session_state:
        if st.session_state.get("knowledge_graph_active_mode") == "edit":
            st.session_state["knowledge_graph_section"] = "✏️ Editar mapa"
        elif st.session_state.get("knowledge_graph_active_mode") == "view":
            st.session_state["knowledge_graph_section"] = "📚 Mapas guardados"
        else:
            st.session_state["knowledge_graph_section"] = "📊 Nuevo mapa"

    kg_section = st.radio(
        "Sección de mapas",
        kg_sections,
        horizontal=True,
        key="knowledge_graph_section",
        label_visibility="collapsed",
    )

    if kg_section == "📊 Nuevo mapa":
        st.subheader("📊 Nuevo mapa")
        col1, col2 = st.columns(2)
        with col1:
            selected_sources = st.multiselect(
                "Select Sources",
                source_options,
                default=source_options[:3] if source_options else [],
                key="kg_new_sources",
            )
            selected_types = st.multiselect(
                "Select Concept Types",
                concept_type_options,
                default=["definicion", "teorema", "proposicion"],
                key="kg_new_concept_types",
            )
        with col2:
            selected_relations = st.multiselect(
                "Select Relation Types",
                relation_type_options,
                default=["implica", "deriva_de", "requiere_concepto"],
                key="kg_new_relation_types",
            )
            max_depth = st.slider("Max Depth", 1, 5, 3, key="kg_new_max_depth")

        if st.button("🔍 Generate Graph", type="primary", key="kg_generate_graph"):
            if selected_sources:
                try:
                    concept_query = {"source": {"$in": selected_sources}}
                    if selected_types:
                        concept_query["tipo"] = {"$in": selected_types}
                    concepts = list(db.concepts.find(concept_query))

                    relation_query = {
                        "$or": [
                            {"desde": {"$regex": f"@({'|'.join(selected_sources)})$"}},
                            {"hasta": {"$regex": f"@({'|'.join(selected_sources)})$"}},
                        ]
                    }
                    if selected_relations:
                        relation_query["tipo"] = {"$in": selected_relations}
                    relations = list(db.relations.find(relation_query))

                    if concepts and relations:
                        grafo = GrafoConocimiento(concepts, relations)
                        grafo.construir_grafo(
                            tipos_relacion=selected_relations,
                            tipos_concepto=selected_types,
                        )
                        st.session_state["knowledge_graph_new_html"] = grafo.exportar_html(salida=None)
                        st.session_state["knowledge_graph_new_stats"] = {
                            "nodes": len(grafo.G.nodes),
                            "edges": len(grafo.G.edges),
                            "sources": len(selected_sources),
                        }
                        st.success("Grafo generado correctamente.")
                    else:
                        st.warning("⚠️ No concepts or relations found with the selected filters.")
                except Exception as e:
                    st.error(f"❌ Error generating graph: {e}")
            else:
                st.error("❌ Please select at least one source.")

        if st.session_state.get("knowledge_graph_new_html"):
            st.subheader("🎯 Interactive Knowledge Graph")
            st.components.v1.html(st.session_state["knowledge_graph_new_html"], height=800)
            st.caption(
                "Edita el grafo y usa 📋 Copiar estado JSON dentro del panel. "
                "Pega ese JSON abajo para guardar el mapa generado."
            )
            stats = st.session_state.get("knowledge_graph_new_stats", {})
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            stat_col1.metric("Nodes", stats.get("nodes", 0))
            stat_col2.metric("Edges", stats.get("edges", 0))
            stat_col3.metric("Sources", stats.get("sources", 0))

        with st.form("kg_save_new_map_form"):
            st.markdown("**Guardar mapa generado**")
            map_name = st.text_input("Nombre del mapa", key="kg_new_map_name")
            map_description = st.text_area("Descripción", height=80, key="kg_new_map_description")
            map_tags = st.text_input("Tags (separados por coma)", key="kg_new_map_tags")
            graph_state_json = st.text_area(
                "Estado JSON actual del grafo",
                height=160,
                key="kg_new_graph_state_json",
                placeholder="Pega aquí el JSON copiado con 📋 Copiar estado JSON...",
            )
            save_map = st.form_submit_button("💾 Guardar mapa generado")

        if save_map:
            if not map_name.strip():
                st.error("El nombre del mapa es obligatorio.")
            else:
                try:
                    graph_state = _parse_knowledge_graph_state_json(graph_state_json)
                    integrity_issues = graph_state_integrity_issues(graph_state)
                    if integrity_issues:
                        st.error("Se detectaron inconsistencias antes de guardar el mapa.")
                        st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                        st.stop()
                    now = datetime.utcnow()
                    inferred_sources = infer_sources_from_graph_state(graph_state)
                    inferred_types = infer_concept_types_from_graph_state(graph_state)
                    map_sources = merge_ordered_values(selected_sources, inferred_sources)
                    primary_map_source = map_sources[0] if map_sources else ""
                    document = {
                        "name": map_name.strip(),
                        "description": map_description.strip(),
                        "created_at": now,
                        "updated_at": now,
                        "filters": {
                            "sources": map_sources,
                            "relation_types": list(selected_relations or []),
                            "concept_types": merge_ordered_values(selected_types, inferred_types),
                            "max_depth": max_depth,
                        },
                        "primary_map_source": primary_map_source,
                        "map_sources": map_sources,
                        "graph_state": graph_state,
                        "tags": [tag.strip() for tag in map_tags.split(",") if tag.strip()],
                        "source": "interactive_knowledge_graph",
                        "map_uid": str(uuid4()),
                        "sync_settings": default_sync_settings(),
                    }
                    result = maps_col.insert_one(document)
                    if result.acknowledged:
                        st.success("Mapa guardado correctamente.")
                    else:
                        st.error("MongoDB no confirmó el guardado del mapa.")
                except json.JSONDecodeError as exc:
                    st.error(f"No se pudo leer el JSON del estado: {exc}")
                except Exception as exc:
                    st.error(f"No se pudo guardar el mapa: {exc}")

    elif kg_section == "📚 Mapas guardados":
        st.subheader("📚 Mapas guardados")
        if not all_maps:
            st.info("Todavía no hay mapas guardados en knowledge_graph_maps.")
        else:
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            with filter_col1:
                search_text = st.text_input("Buscar por nombre", key="kg_maps_search")
            all_tags = sorted({tag for doc in all_maps for tag in doc.get("tags", []) if isinstance(tag, str)})
            all_map_sources = sorted(
                {
                    source
                    for doc in all_maps
                    for source in (doc.get("filters", {}) or {}).get("sources", [])
                    if isinstance(source, str)
                }
            )
            all_map_types = sorted(
                {
                    concept_type
                    for doc in all_maps
                    for concept_type in (doc.get("filters", {}) or {}).get("concept_types", [])
                    if isinstance(concept_type, str)
                }
            )
            with filter_col2:
                tag_filter = st.selectbox("Filtrar por tag", [""] + all_tags, key="kg_maps_tag_filter")
            with filter_col3:
                source_filter = st.selectbox("Filtrar por fuente", [""] + all_map_sources, key="kg_maps_source_filter")
            with filter_col4:
                type_filter = st.selectbox("Filtrar por tipo", [""] + all_map_types, key="kg_maps_type_filter")

            filtered_maps = []
            for doc in all_maps:
                filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
                tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
                if search_text and search_text.lower() not in str(doc.get("name", "")).lower():
                    continue
                if tag_filter and tag_filter not in tags:
                    continue
                if source_filter and source_filter not in (filters.get("sources") or []):
                    continue
                if type_filter and type_filter not in (filters.get("concept_types") or []):
                    continue
                filtered_maps.append(doc)

            if not filtered_maps:
                st.info("No hay mapas que coincidan con los filtros.")
            else:
                st.dataframe(
                    pd.DataFrame([_knowledge_graph_map_summary(doc) for doc in filtered_maps]),
                    width="stretch",
                    hide_index=True,
                )
                map_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in filtered_maps}
                selected_label = st.selectbox("Seleccionar mapa", list(map_options), key="kg_saved_selected_map")
                selected_map_id = map_options[selected_label]
                selected_doc = next(doc for doc in filtered_maps if str(doc["_id"]) == selected_map_id)

                action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                with action_col1:
                    if st.button("Ver", key="kg_view_map"):
                        st.session_state["knowledge_graph_active_map_id"] = selected_map_id
                        st.session_state["knowledge_graph_active_mode"] = "view"
                with action_col2:
                    if st.button("Editar", key="kg_edit_map"):
                        st.session_state["knowledge_graph_active_map_id"] = selected_map_id
                        st.session_state["knowledge_graph_active_mode"] = "edit"
                        st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                        st.rerun()
                with action_col3:
                    if st.button("Duplicar", key="kg_duplicate_map"):
                        try:
                            now = datetime.utcnow()
                            duplicate = {k: v for k, v in selected_doc.items() if k != "_id"}
                            duplicate["name"] = f"Copia de {selected_doc.get('name', 'Mapa sin nombre')}"
                            duplicate["map_uid"] = str(uuid4())
                            duplicate["created_at"] = now
                            duplicate["updated_at"] = now
                            result = maps_col.insert_one(duplicate)
                            if result.acknowledged:
                                st.success("Mapa duplicado correctamente.")
                            else:
                                st.error("MongoDB no confirmó la duplicación.")
                        except Exception as exc:
                            st.error(f"No se pudo duplicar el mapa: {exc}")
                with action_col4:
                    confirm_delete = st.checkbox("Confirmar eliminación", key="kg_saved_confirm_delete")
                    if st.button("Eliminar", key="kg_delete_map"):
                        if not confirm_delete:
                            st.error("Marca la confirmación antes de eliminar el mapa.")
                        else:
                            try:
                                result = maps_col.delete_one(_knowledge_graph_map_id_query(selected_map_id))
                                if result.deleted_count:
                                    st.success("Mapa eliminado correctamente.")
                                    if st.session_state.get("knowledge_graph_active_map_id") == selected_map_id:
                                        st.session_state.pop("knowledge_graph_active_map_id", None)
                                        st.session_state.pop("knowledge_graph_active_mode", None)
                                else:
                                    st.error("No se encontró el mapa que se intentaba eliminar.")
                            except Exception as exc:
                                st.error(f"No se pudo eliminar el mapa: {exc}")

                if st.session_state.get("knowledge_graph_active_mode") == "view":
                    active_id = st.session_state.get("knowledge_graph_active_map_id")
                    active_doc = _find_knowledge_graph_map(maps_col, active_id) if active_id else None
                    if active_doc:
                        st.divider()
                        st.subheader(active_doc.get("name", "Mapa guardado"))
                        _render_knowledge_graph_map_metadata(active_doc)
                        graph_state = active_doc.get("graph_state", {})
                        nodes, edges = _knowledge_graph_state_counts(graph_state)
                        metric_col1, metric_col2 = st.columns(2)
                        metric_col1.metric("Nodos", nodes)
                        metric_col2.metric("Aristas", edges)
                        if st.button("✏️ Editar este mapa", key="kg_view_to_edit"):
                            st.session_state["knowledge_graph_active_mode"] = "edit"
                            st.session_state["knowledge_graph_active_map_id"] = active_id
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.rerun()
                        html_content = _render_knowledge_graph_map_html(graph_state, f"view_{active_id}")
                        st.components.v1.html(html_content, height=800)

    elif kg_section == "✏️ Editar mapa":
        st.subheader("✏️ Editar mapa")
        if not all_maps:
            st.info("No hay mapas guardados para editar.")
        else:
            edit_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in all_maps}
            active_id = st.session_state.get("knowledge_graph_active_map_id")
            default_index = 0
            if active_id and active_id in edit_options.values():
                default_index = list(edit_options.values()).index(active_id)
            edit_label = st.selectbox(
                "Mapa para editar",
                list(edit_options),
                index=default_index,
                key="kg_edit_selected_map",
            )
            edit_map_id = edit_options[edit_label]
            edit_doc = _find_knowledge_graph_map(maps_col, edit_map_id)
            if not edit_doc:
                st.error("No se encontró el mapa seleccionado.")
            else:
                edit_map_id_text = str(edit_map_id)
                filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
                form_state_key = _kg_edit_form_state_key(edit_map_id_text)
                widget_keys = _kg_edit_widget_keys(edit_map_id_text)
                source_widget_key = widget_keys["sources"]
                concept_type_widget_key = widget_keys["concept_types"]
                if st.session_state.get("knowledge_graph_editing_map_id") != edit_map_id_text:
                    initial_graph_state = deepcopy(edit_doc.get("graph_state", {}))
                    st.session_state["knowledge_graph_editing_map_id"] = edit_map_id_text
                    st.session_state["knowledge_graph_edit_graph_state"] = initial_graph_state
                    st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                        edit_doc.get("sync_settings")
                    )
                    form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, initial_graph_state)
                    st.session_state[form_state_key] = form_state
                    _queue_kg_edit_widget_update(edit_map_id_text, form_state)
                    st.session_state["knowledge_graph_edit_dirty"] = False
                    st.session_state["knowledge_graph_render_version"] = 0
                    st.session_state.pop("knowledge_graph_remove_pending", None)
                else:
                    form_state = st.session_state.get(form_state_key, {})
                    if not isinstance(form_state, dict):
                        form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, edit_doc.get("graph_state", {}))
                        st.session_state[form_state_key] = form_state
                st.session_state["knowledge_graph_active_map_id"] = edit_map_id_text
                st.session_state["knowledge_graph_active_mode"] = "edit"

                graph_state = st.session_state.get("knowledge_graph_edit_graph_state") or edit_doc.get("graph_state", {})
                current_node_count, current_edge_count = _knowledge_graph_state_counts(graph_state)
                _kg_debug(
                    "Loaded edit map",
                    map_id=edit_map_id_text,
                    nodes=current_node_count,
                    edges=current_edge_count,
                    dirty=st.session_state.get("knowledge_graph_edit_dirty"),
                )
                repaired_graph_state, repaired_nodes, unresolved_nodes = repair_incomplete_graph_nodes(
                    db,
                    graph_state,
                )
                if repaired_nodes:
                    repair_result = maps_col.update_one(
                        _knowledge_graph_map_id_query(edit_map_id),
                        {
                            "$set": {
                                "graph_state": repaired_graph_state,
                                "updated_at": datetime.utcnow(),
                            }
                        },
                    )
                    if repair_result.acknowledged:
                        graph_state = repaired_graph_state
                        st.session_state["knowledge_graph_edit_graph_state"] = repaired_graph_state
                        st.session_state["knowledge_graph_edit_dirty"] = False
                        st.session_state["knowledge_graph_render_version"] = (
                            st.session_state.get("knowledge_graph_render_version", 0) + 1
                        )
                        edit_doc["graph_state"] = repaired_graph_state
                        st.success(
                            f"Se repararon {repaired_nodes} nodos incompletos usando los metadatos de MongoDB."
                        )
                    else:
                        st.warning("Se detectaron nodos incompletos, pero MongoDB no confirmó la reparación.")
                elif unresolved_nodes:
                    st.warning(
                        f"Hay {unresolved_nodes} nodos incompletos que no pudieron repararse porque no se encontró "
                        "su concepto en MongoDB."
                    )
                current_node_count, current_edge_count = _knowledge_graph_state_counts(graph_state)
                form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, graph_state)
                map_source_options = merge_ordered_values(
                    source_options,
                    filters.get("sources", []),
                    form_state.get("sources", []),
                )
                map_concept_type_options = merge_ordered_values(
                    concept_type_options,
                    filters.get("concept_types", []),
                    form_state.get("concept_types", []),
                )
                st.markdown(f"**Editando:** {edit_doc.get('name', 'Mapa guardado')}")
                st.caption(
                    "Los cambios hechos con controles de Streamlit se guardan directamente. "
                    "Para conservar posiciones movidas dentro del grafo, copia el JSON desde el panel del grafo "
                    "y pégalo abajo."
                )
                st.caption(
                    f"Nodos actuales: {current_node_count} · Enlaces actuales: {current_edge_count} · "
                    f"Cambios no guardados: {'sí' if st.session_state.get('knowledge_graph_edit_dirty') else 'no'}"
                )
                if st.session_state.get("knowledge_graph_edit_dirty"):
                    st.warning("Hay cambios no guardados en este mapa.")
                render_version = st.session_state.get("knowledge_graph_render_version", 0)
                html_content = _render_knowledge_graph_map_html(graph_state, f"edit_{edit_map_id}_{render_version}")
                st.components.v1.html(html_content, height=800)

                sync_settings = default_sync_settings(
                    st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                )
                manual_sync_key = f"kg_sync_manual_{edit_map_id}"
                ignore_sync_key = f"kg_sync_ignore_once_{edit_map_id}"

                def _save_graph_sync_update(
                    selected_concepts: list[dict],
                    include_relations: bool,
                    sync_origin: str,
                ) -> None:
                    if not selected_concepts:
                        if sync_origin == "external_source":
                            st.session_state[f"kg_import_nodes_expander_open_{edit_map_id}"] = True
                        st.error("Selecciona al menos un concepto para agregar.")
                        return
                    invalid_concepts = []
                    warning_concepts = []
                    for concept in selected_concepts:
                        errors = concept_graph_node_errors(concept)
                        warnings = concept_graph_node_warnings(concept)
                        concept_name = concept_key(concept) or str(concept.get("titulo") or concept.get("title") or "")
                        if errors:
                            invalid_concepts.append(f"{concept_name or '<sin id>'}: {', '.join(errors)}")
                        elif warnings:
                            warning_concepts.append(concept_name or "<sin id>")
                    if invalid_concepts:
                        st.error(
                            "No se pudieron agregar algunos conceptos porque faltan metadatos mínimos:\n"
                            + "\n".join(f"- {item}" for item in invalid_concepts[:8])
                        )
                        return
                    new_graph_state, added_nodes, added_edges = add_concepts_to_graph_state(
                        db,
                        graph_state,
                        selected_concepts,
                        include_relations=include_relations,
                        sync_origin=sync_origin,
                    )
                    before_nodes, before_edges = _knowledge_graph_state_counts(graph_state)
                    after_nodes, after_edges = _knowledge_graph_state_counts(new_graph_state)
                    _kg_debug(
                        "Added concepts to edit map",
                        map_id=edit_map_id_text,
                        selected=len(selected_concepts),
                        before_nodes=before_nodes,
                        after_nodes=after_nodes,
                        before_edges=before_edges,
                        after_edges=after_edges,
                        added_nodes=added_nodes,
                        added_edges=added_edges,
                    )
                    skipped_duplicates = max(0, len(selected_concepts) - added_nodes)
                    selected_keys = {concept_key(concept) for concept in selected_concepts}
                    updated_sync_settings = default_sync_settings(
                        st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                    )
                    updated_sync_settings["last_sync_check_at"] = utc_timestamp()
                    for field in ("removed_node_ids", "manually_removed_node_ids"):
                        updated_sync_settings[field] = [
                            node_id for node_id in updated_sync_settings.get(field, []) if node_id not in selected_keys
                        ]
                    updated_form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, new_graph_state)
                    updated_form_state["sources"] = merge_ordered_values(
                        updated_form_state.get("sources", []),
                        [concept.get("source") for concept in selected_concepts if isinstance(concept, dict)],
                        infer_sources_from_graph_state(new_graph_state),
                    )
                    updated_form_state["concept_types"] = merge_ordered_values(
                        updated_form_state.get("concept_types", []),
                        [
                            concept.get("tipo") or concept.get("type") or concept.get("conceptType")
                            for concept in selected_concepts
                            if isinstance(concept, dict)
                        ],
                        infer_concept_types_from_graph_state(new_graph_state),
                    )
                    st.session_state[form_state_key] = updated_form_state
                    _queue_kg_edit_widget_update(
                        edit_map_id_text,
                        {
                            "sources": updated_form_state["sources"],
                            "concept_types": updated_form_state["concept_types"],
                        },
                    )
                    st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                    st.session_state["knowledge_graph_edit_sync_settings"] = updated_sync_settings
                    st.session_state["knowledge_graph_edit_dirty"] = True
                    st.session_state["knowledge_graph_render_version"] = (
                        st.session_state.get("knowledge_graph_render_version", 0) + 1
                    )
                    st.session_state[manual_sync_key] = False
                    st.session_state.pop(ignore_sync_key, None)
                    st.session_state["knowledge_graph_active_map_id"] = edit_map_id
                    st.session_state["knowledge_graph_active_mode"] = "edit"
                    st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                    if sync_origin == "external_source":
                        st.session_state[f"kg_import_nodes_expander_open_{edit_map_id}"] = True
                    duplicate_text = (
                        f" {skipped_duplicates} conceptos ya estaban en el mapa y se omitieron."
                        if skipped_duplicates
                        else ""
                    )
                    warning_text = (
                        f" {len(warning_concepts)} conceptos no tenían tipo explícito y se agregaron como `otro`."
                        if warning_concepts
                        else ""
                    )
                    st.session_state["knowledge_graph_message"] = (
                        "success" if added_nodes or added_edges else "info",
                        (
                            f"Se agregaron {added_nodes} nodos y {added_edges} relaciones al mapa actual. "
                            f"{duplicate_text}{warning_text} Guarda los cambios para persistirlos."
                        ),
                    )
                    st.rerun()

                sync_col1, sync_col2, sync_col3 = st.columns([1, 1, 2])
                with sync_col1:
                    if st.button("🔎 Revisar nuevos nodos del source", key=f"kg_sync_manual_button_{edit_map_id}"):
                        st.session_state[manual_sync_key] = True
                        st.session_state.pop(ignore_sync_key, None)
                        st.rerun()
                with sync_col2:
                    if st.button("🧩 Reparar nodos incompletos", key=f"kg_repair_nodes_button_{edit_map_id}"):
                        repaired_graph_state, repaired_nodes, unresolved_nodes = repair_incomplete_graph_nodes(
                            db,
                            graph_state,
                        )
                        if repaired_nodes:
                            repair_result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "graph_state": repaired_graph_state,
                                        "updated_at": datetime.utcnow(),
                                    }
                                },
                            )
                            if repair_result.acknowledged:
                                st.session_state["knowledge_graph_edit_graph_state"] = repaired_graph_state
                                st.session_state["knowledge_graph_render_version"] = (
                                    st.session_state.get("knowledge_graph_render_version", 0) + 1
                                )
                                st.session_state["knowledge_graph_message"] = (
                                    "success",
                                    f"Se repararon {repaired_nodes} nodos incompletos.",
                                )
                                st.rerun()
                            else:
                                st.error("MongoDB no confirmó la reparación.")
                        elif unresolved_nodes:
                            st.warning(
                                f"No se reparó ningún nodo; {unresolved_nodes} nodos no tienen concepto local "
                                "para reconstruirse."
                            )
                        else:
                            st.info("No se encontraron nodos incompletos.")
                with sync_col3:
                    primary_source_values = primary_sources(edit_doc)
                    primary_source_text = primary_source_values[0] if primary_source_values else ""
                    if primary_source_text:
                        st.caption(f"Source principal del mapa: {primary_source_text}")
                    else:
                        st.caption("Este mapa no tiene source principal declarado en sus filtros.")
                    map_sources_text = ", ".join(form_state.get("sources", []))
                    if map_sources_text:
                        st.caption(f"Fuentes presentes en el mapa: {map_sources_text}")
                    if sync_settings.get("suppress_new_nodes_prompt"):
                        st.caption("El aviso automático de nodos nuevos está desactivado para este mapa.")

                include_removed_sync_key = f"kg_sync_include_removed_{edit_map_id}"
                edit_doc_for_sync = dict(edit_doc)
                edit_doc_for_sync["sync_settings"] = sync_settings
                missing_concepts = detect_missing_source_concepts(
                    db,
                    edit_doc_for_sync,
                    graph_state,
                    include_removed=bool(st.session_state.get(include_removed_sync_key, False)),
                )
                show_manual_sync = bool(st.session_state.get(manual_sync_key))
                show_auto_sync = (
                    bool(missing_concepts)
                    and not show_manual_sync
                    and not sync_settings.get("suppress_new_nodes_prompt")
                    and not st.session_state.get(ignore_sync_key)
                )

                if show_manual_sync and not missing_concepts:
                    st.info("No hay conceptos nuevos pendientes para el source principal del mapa.")

                if missing_concepts and (show_auto_sync or show_manual_sync):
                    st.warning(
                        "Se detectaron nuevos conceptos en el source de este mapa que todavía no están incluidos "
                        "como nodos."
                    )
                    st.caption(
                        f"Conceptos faltantes detectados: {len(missing_concepts)}. "
                        "Puedes agregarlos todos o seleccionar una lista parcial."
                    )
                    include_sync_relations = st.checkbox(
                        "También agregar relaciones disponibles entre los nodos presentes y seleccionados",
                        value=True,
                        key=f"kg_sync_include_relations_{edit_map_id}",
                    )
                    st.checkbox(
                        "Mostrar también nodos removidos manualmente",
                        value=False,
                        key=include_removed_sync_key,
                    )
                    action_col1, action_col2, action_col3 = st.columns(3)
                    with action_col1:
                        if st.button("Agregar todos", key=f"kg_sync_add_all_{edit_map_id}"):
                            _save_graph_sync_update(
                                missing_concepts,
                                include_sync_relations,
                                sync_origin="source_sync",
                            )
                    with action_col2:
                        if st.button("Ignorar por ahora", key=f"kg_sync_ignore_now_{edit_map_id}"):
                            st.session_state[ignore_sync_key] = True
                            st.session_state[manual_sync_key] = False
                            st.session_state["knowledge_graph_message"] = (
                                "info",
                                "Sincronización omitida por ahora. El aviso volverá a aparecer en otra edición.",
                            )
                            st.rerun()
                    with action_col3:
                        if st.button("No volver a mostrar para este mapa", key=f"kg_sync_suppress_{edit_map_id}"):
                            updated_sync_settings = default_sync_settings(edit_doc.get("sync_settings"))
                            updated_sync_settings["suppress_new_nodes_prompt"] = True
                            updated_sync_settings["last_sync_check_at"] = utc_timestamp()
                            result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "sync_settings": updated_sync_settings,
                                        "updated_at": datetime.utcnow(),
                                    }
                                },
                            )
                            if result.acknowledged:
                                st.session_state[manual_sync_key] = False
                                st.session_state["knowledge_graph_message"] = (
                                    "info",
                                    "Aviso automático desactivado para este mapa. La revisión manual seguirá disponible.",
                                )
                                st.rerun()
                            else:
                                st.error("MongoDB no confirmó el cambio de preferencia.")

                    with st.expander("Seleccionar de una lista", expanded=show_manual_sync):
                        selected_missing_concepts = _knowledge_graph_concept_selector(
                            missing_concepts,
                            key=f"kg_sync_missing_selector_{edit_map_id}",
                        )
                        if st.button("Agregar seleccionados", key=f"kg_sync_add_selected_{edit_map_id}"):
                            _save_graph_sync_update(
                                selected_missing_concepts,
                                include_sync_relations,
                                sync_origin="source_sync",
                            )

                external_expander_key = f"kg_import_nodes_expander_open_{edit_map_id}"
                with st.expander(
                    "Agregar nodos desde otros sources",
                    expanded=st.session_state.get(external_expander_key, False),
                ):
                    current_sources = set(form_state.get("sources", []))
                    external_source_options = [source for source in source_options if source not in current_sources]
                    if not external_source_options:
                        external_source_options = list(source_options)
                    if not external_source_options:
                        st.info("No hay sources disponibles para agregar nodos externos.")
                    else:
                        external_col1, external_col2 = st.columns(2)
                        with external_col1:
                            external_source = st.selectbox(
                                "Source",
                                external_source_options,
                                key=f"kg_external_source_{edit_map_id}",
                                on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                            )
                        with external_col2:
                            external_types = st.multiselect(
                                "Tipos de concepto",
                                concept_type_options,
                                key=f"kg_external_types_{edit_map_id}",
                                on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                            )
                        external_search = st.text_input(
                            "Buscar por texto",
                            key=f"kg_external_search_{edit_map_id}",
                            on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                        )
                        include_external_relations = st.checkbox(
                            "También agregar relaciones disponibles",
                            value=True,
                            key=f"kg_external_include_relations_{edit_map_id}",
                            on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                        )
                        external_concepts = find_available_concepts(
                            db,
                            external_source,
                            graph_state,
                            concept_types=list(external_types or []),
                            search_text=external_search,
                        )
                        if not external_concepts:
                            st.info("No hay conceptos disponibles con esos filtros o todos ya están en el mapa.")
                        else:
                            st.caption(
                                f"Conceptos disponibles para agregar desde `{external_source}`: "
                                f"{len(external_concepts)}"
                            )
                            selected_external_concepts = _knowledge_graph_concept_selector(
                                external_concepts,
                                key=f"kg_external_selector_{edit_map_id}",
                            )
                            if st.button("Agregar seleccionados al mapa", key=f"kg_external_add_selected_{edit_map_id}"):
                                _save_graph_sync_update(
                                    selected_external_concepts,
                                    include_external_relations,
                                    sync_origin="external_source",
                                )

                node_rows = map_node_rows(db, graph_state)

                def _queue_node_removal(node_ids: list[str], reason: str) -> None:
                    clean_ids = [node_id for node_id in node_ids if node_id]
                    if not clean_ids:
                        st.error("Selecciona al menos un nodo para quitar del mapa.")
                        return
                    st.session_state["knowledge_graph_remove_pending"] = {
                        "map_id": edit_map_id_text,
                        "node_ids": clean_ids,
                        "reason": reason,
                    }
                    st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                    st.rerun()

                pending_removal = st.session_state.get("knowledge_graph_remove_pending")
                if isinstance(pending_removal, dict) and pending_removal.get("map_id") == edit_map_id_text:
                    pending_ids = pending_removal.get("node_ids", [])
                    pending_rows = [row for row in node_rows if row.get("ID interno") in pending_ids]
                    st.warning(
                        f"Vas a quitar {len(pending_ids)} nodo(s) del mapa actual. "
                        "También se quitarán las aristas asociadas. Esto NO borrará los conceptos de MongoDB."
                    )
                    if pending_rows:
                        st.dataframe(
                            pd.DataFrame(pending_rows).drop(columns=["Quitar"], errors="ignore"),
                            width="stretch",
                            hide_index=True,
                        )
                    confirm_col1, confirm_col2 = st.columns(2)
                    with confirm_col1:
                        if st.button("Sí, quitar del mapa", key=f"kg_confirm_remove_nodes_{edit_map_id}"):
                            new_graph_state, removed_nodes, removed_edges = remove_nodes_from_graph_state(
                                graph_state,
                                pending_ids,
                            )
                            before_nodes, before_edges = _knowledge_graph_state_counts(graph_state)
                            after_nodes, after_edges = _knowledge_graph_state_counts(new_graph_state)
                            _kg_debug(
                                "Removed nodes from edit map",
                                map_id=edit_map_id_text,
                                requested=len(pending_ids),
                                removed_nodes=removed_nodes,
                                removed_edges=removed_edges,
                                before_nodes=before_nodes,
                                after_nodes=after_nodes,
                                before_edges=before_edges,
                                after_edges=after_edges,
                            )
                            updated_sync_settings = default_sync_settings(
                                st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                            )
                            for field in ("removed_node_ids", "manually_removed_node_ids"):
                                existing_removed = set(updated_sync_settings.get(field, []))
                                existing_removed.update(pending_ids)
                                updated_sync_settings[field] = sorted(existing_removed)
                            updated_form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, new_graph_state)
                            updated_form_state["sources"] = infer_sources_from_graph_state(new_graph_state)
                            updated_form_state["concept_types"] = infer_concept_types_from_graph_state(new_graph_state)
                            st.session_state[form_state_key] = updated_form_state
                            _queue_kg_edit_widget_update(
                                edit_map_id_text,
                                {
                                    "sources": updated_form_state["sources"],
                                    "concept_types": updated_form_state["concept_types"],
                                },
                            )
                            st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                            st.session_state["knowledge_graph_edit_sync_settings"] = updated_sync_settings
                            st.session_state["knowledge_graph_edit_dirty"] = True
                            st.session_state["knowledge_graph_render_version"] = (
                                st.session_state.get("knowledge_graph_render_version", 0) + 1
                            )
                            st.session_state.pop("knowledge_graph_remove_pending", None)
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.session_state["knowledge_graph_message"] = (
                                "info",
                                (
                                    f"Se quitaron {removed_nodes} nodos y {removed_edges} aristas del mapa actual. "
                                    "Guarda los cambios para persistirlos."
                                ),
                            )
                            st.rerun()
                    with confirm_col2:
                        if st.button("Cancelar", key=f"kg_cancel_remove_nodes_{edit_map_id}"):
                            st.session_state.pop("knowledge_graph_remove_pending", None)
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.rerun()

                with st.expander("Administrar nodos del mapa", expanded=False):
                    if not node_rows:
                        st.info("Este mapa no tiene nodos administrables.")
                    else:
                        node_options = {
                            f"{row.get('Título') or row.get('ID interno')} · {row.get('Tipo') or 'sin tipo'} · {row.get('ID interno')}": row.get("ID interno")
                            for row in node_rows
                        }
                        selected_node_label = st.selectbox(
                            "Nodo para quitar",
                            list(node_options),
                            key=f"kg_remove_single_node_selector_{edit_map_id}",
                        )
                        if st.button("🗑️ Quitar nodo seleccionado del mapa", key=f"kg_remove_single_node_{edit_map_id}"):
                            _queue_node_removal([node_options[selected_node_label]], "single")

                        st.divider()
                        selected_node_ids = _knowledge_graph_node_id_selector(
                            node_rows,
                            key=f"kg_manage_nodes_selector_{edit_map_id}",
                        )
                        if st.button("🗑️ Quitar nodos seleccionados del mapa", key=f"kg_remove_selected_nodes_{edit_map_id}"):
                            _queue_node_removal(selected_node_ids, "selected")

                        incomplete_ids = incomplete_node_ids(db, graph_state)
                        if incomplete_ids:
                            st.divider()
                            st.caption(f"Nodos incompletos detectados: {len(incomplete_ids)}")
                            incomplete_rows = [row for row in node_rows if row.get("ID interno") in incomplete_ids]
                            st.dataframe(
                                pd.DataFrame(incomplete_rows).drop(columns=["Quitar"], errors="ignore"),
                                width="stretch",
                                hide_index=True,
                            )
                            if st.button("🧹 Eliminar nodos incompletos", key=f"kg_remove_incomplete_nodes_{edit_map_id}"):
                                _queue_node_removal(incomplete_ids, "incomplete")

                        isolated_ids = isolated_node_ids(graph_state)
                        if isolated_ids:
                            st.divider()
                            st.caption(f"Nodos aislados detectados: {len(isolated_ids)}")
                            isolated_rows = [row for row in node_rows if row.get("ID interno") in isolated_ids]
                            st.dataframe(
                                pd.DataFrame(isolated_rows).drop(columns=["Quitar"], errors="ignore"),
                                width="stretch",
                                hide_index=True,
                            )
                            if st.button("🧹 Quitar nodos aislados", key=f"kg_remove_isolated_nodes_{edit_map_id}"):
                                _queue_node_removal(isolated_ids, "isolated")

                filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
                state_col1, state_col2, state_col3 = st.columns(3)
                with state_col1:
                    st.download_button(
                        "📥 Descargar estado JSON",
                        data=json.dumps(graph_state, ensure_ascii=False, indent=2, default=str),
                        file_name=f"{edit_doc.get('name', 'knowledge_graph_map')}_state.json",
                        mime="application/json",
                        key=f"kg_edit_download_state_{edit_map_id}",
                    )
                with state_col2:
                    if st.button("📋 Mostrar estado JSON", key=f"kg_edit_show_state_json_{edit_map_id}"):
                        st.session_state[f"kg_show_edit_state_json_{edit_map_id}"] = not st.session_state.get(
                            f"kg_show_edit_state_json_{edit_map_id}",
                            False,
                        )
                with state_col3:
                    if st.button("↩️ Deshacer cambios no guardados", key=f"kg_discard_unsaved_{edit_map_id}"):
                        reset_graph_state = deepcopy(edit_doc.get("graph_state", {}))
                        st.session_state["knowledge_graph_edit_graph_state"] = reset_graph_state
                        st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                            edit_doc.get("sync_settings")
                        )
                        reset_form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, reset_graph_state)
                        st.session_state[form_state_key] = reset_form_state
                        _queue_kg_edit_widget_update(edit_map_id_text, reset_form_state)
                        st.session_state["knowledge_graph_edit_dirty"] = False
                        st.session_state.pop("knowledge_graph_remove_pending", None)
                        st.session_state["knowledge_graph_render_version"] = (
                            st.session_state.get("knowledge_graph_render_version", 0) + 1
                        )
                        st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                        st.rerun()

                if st.session_state.get(f"kg_show_edit_state_json_{edit_map_id}"):
                    st.code(json.dumps(graph_state, ensure_ascii=False, indent=2, default=str), language="json")

                widget_keys = _apply_kg_edit_widget_updates_before_creation(
                    edit_map_id_text,
                    form_state,
                    graph_state,
                )
                source_widget_key = widget_keys["sources"]
                concept_type_widget_key = widget_keys["concept_types"]
                relation_type_widget_key = widget_keys["relation_types"]
                max_depth_widget_key = widget_keys["max_depth"]
                map_relation_type_options = merge_ordered_values(
                    relation_type_options,
                    filters.get("relation_types", []),
                    form_state.get("relation_types", []),
                )

                with st.form("kg_update_map_form"):
                    updated_name = st.text_input(
                        "Nombre del mapa",
                        key=widget_keys["name"],
                    )
                    updated_description = st.text_area(
                        "Descripción",
                        height=80,
                        key=widget_keys["description"],
                    )
                    updated_tags = st.text_input(
                        "Tags (separados por coma)",
                        key=widget_keys["tags"],
                    )
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        updated_sources = st.multiselect(
                            "Fuentes",
                            map_source_options,
                            key=source_widget_key,
                        )
                        updated_types = st.multiselect(
                            "Tipos de concepto",
                            map_concept_type_options,
                            key=concept_type_widget_key,
                        )
                    with edit_col2:
                        updated_relations = st.multiselect(
                            "Tipos de relación",
                            map_relation_type_options,
                            key=relation_type_widget_key,
                        )
                        updated_max_depth = st.slider(
                            "Max depth",
                            1,
                            5,
                            key=max_depth_widget_key,
                        )
                    st.info(
                        "Guardar mapa usa el estado server-side del editor. "
                        "Para guardar posiciones o física cambiadas dentro del grafo, copia el estado JSON desde el panel "
                        "del grafo, pégalo aquí y activa la casilla."
                    )
                    use_pasted_state_json = st.checkbox(
                        "Guardar con el JSON visual pegado abajo",
                        key=widget_keys["use_pasted_state_json"],
                    )
                    updated_state_json = st.text_area(
                        "Estado JSON actual del grafo",
                        height=180,
                        key=widget_keys["graph_state_json"],
                        placeholder=(
                            "Pega aquí el JSON copiado desde 📋 Copiar estado JSON. "
                            "Sólo se usará si activas la casilla anterior."
                        ),
                    )
                    update_map = st.form_submit_button("💾 Guardar mapa")

                if update_map:
                    if not updated_name.strip():
                        st.error("El nombre del mapa es obligatorio.")
                    else:
                        try:
                            current_filter_payload = {
                                "sources": list(filters.get("sources") or []),
                                "relation_types": list(filters.get("relation_types") or []),
                                "concept_types": list(filters.get("concept_types") or []),
                                "max_depth": min(5, max(1, int(filters.get("max_depth", 3) or 3))),
                            }
                            base_graph_state = (
                                _parse_knowledge_graph_state_json(updated_state_json)
                                if use_pasted_state_json and updated_state_json.strip()
                                else graph_state
                            )
                            baseline_sources = merge_ordered_values(
                                current_filter_payload["sources"],
                                infer_sources_from_graph_state(base_graph_state),
                            )
                            baseline_types = merge_ordered_values(
                                current_filter_payload["concept_types"],
                                infer_concept_types_from_graph_state(base_graph_state),
                            )
                            source_filter_changed = set(updated_sources or []) != set(baseline_sources)
                            concept_type_filter_changed = set(updated_types or []) != set(baseline_types)
                            filter_changed = (
                                source_filter_changed
                                or concept_type_filter_changed
                                or list(updated_relations or []) != current_filter_payload["relation_types"]
                                or updated_max_depth != current_filter_payload["max_depth"]
                            )
                            if filter_changed:
                                new_graph_state = _build_knowledge_graph_state_from_filters(
                                    db,
                                    updated_sources,
                                    updated_relations,
                                    updated_types,
                                    previous_state=base_graph_state,
                                )
                                new_graph_state = merge_preserved_graph_items(new_graph_state, base_graph_state)
                            else:
                                new_graph_state = base_graph_state
                            inferred_sources = infer_sources_from_graph_state(new_graph_state)
                            inferred_types = infer_concept_types_from_graph_state(new_graph_state)
                            updated_filter_payload = {
                                "sources": merge_ordered_values(updated_sources, inferred_sources),
                                "relation_types": list(updated_relations or []),
                                "concept_types": merge_ordered_values(updated_types, inferred_types),
                                "max_depth": updated_max_depth,
                            }
                            primary_source_values = primary_sources(edit_doc)
                            primary_map_source = (
                                primary_source_values[0]
                                if primary_source_values
                                else (updated_filter_payload["sources"][0] if updated_filter_payload["sources"] else "")
                            )
                            integrity_issues = graph_state_integrity_issues(new_graph_state)
                            if integrity_issues:
                                st.error("Se detectaron inconsistencias antes de guardar; no se guardó el mapa.")
                                st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                                st.info("Usa Reparar nodos incompletos, elimina los nodos inválidos o pega un JSON reparado.")
                                st.stop()
                            result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "name": updated_name.strip(),
                                        "description": updated_description.strip(),
                                        "tags": [tag.strip() for tag in updated_tags.split(",") if tag.strip()],
                                        "filters": updated_filter_payload,
                                        "primary_map_source": primary_map_source,
                                        "map_sources": updated_filter_payload["sources"],
                                        "graph_state": new_graph_state,
                                        "sync_settings": default_sync_settings(
                                            st.session_state.get(
                                                "knowledge_graph_edit_sync_settings",
                                                edit_doc.get("sync_settings"),
                                            )
                                        ),
                                        "map_uid": edit_doc.get("map_uid") or str(uuid4()),
                                        "updated_at": datetime.utcnow(),
                                    }
                                },
                            )
                            saved_nodes, saved_edges = _knowledge_graph_state_counts(new_graph_state)
                            _kg_debug(
                                "Saving edit map",
                                map_id=edit_map_id_text,
                                nodes=saved_nodes,
                                edges=saved_edges,
                                filter_changed=filter_changed,
                                using_pasted_json=bool(use_pasted_state_json and updated_state_json.strip()),
                            )
                            saved_form_state = {
                                "name": updated_name.strip(),
                                "description": updated_description.strip(),
                                "tags": updated_tags,
                                "sources": updated_filter_payload["sources"],
                                "concept_types": updated_filter_payload["concept_types"],
                                "relation_types": updated_filter_payload["relation_types"],
                                "max_depth": updated_filter_payload["max_depth"],
                                "use_pasted_state_json": False,
                                "graph_state_json": "",
                            }
                            if not result.acknowledged:
                                st.error("MongoDB no confirmó la actualización del mapa.")
                            elif result.matched_count == 0:
                                st.error("No se encontró el mapa que se intentaba actualizar.")
                            elif result.modified_count == 0:
                                st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                                st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                                    st.session_state.get(
                                        "knowledge_graph_edit_sync_settings",
                                        edit_doc.get("sync_settings"),
                                    )
                                )
                                st.session_state[form_state_key] = saved_form_state
                                _queue_kg_edit_widget_update(edit_map_id_text, saved_form_state)
                                st.session_state["knowledge_graph_edit_dirty"] = False
                                st.info("No hubo cambios nuevos que guardar.")
                            else:
                                st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                                st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                                    st.session_state.get(
                                        "knowledge_graph_edit_sync_settings",
                                        edit_doc.get("sync_settings"),
                                    )
                                )
                                st.session_state[form_state_key] = saved_form_state
                                _queue_kg_edit_widget_update(edit_map_id_text, saved_form_state)
                                st.session_state["knowledge_graph_edit_dirty"] = False
                                st.session_state["knowledge_graph_active_map_id"] = edit_map_id
                                st.session_state["knowledge_graph_active_mode"] = "edit"
                                st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                                st.session_state["knowledge_graph_message"] = (
                                    "success",
                                    "Mapa actualizado correctamente.",
                                )
                                st.rerun()
                        except json.JSONDecodeError as exc:
                            st.error(f"No se pudo leer el JSON del estado: {exc}")
                        except Exception as exc:
                            st.error(f"No se pudo actualizar el mapa: {exc}")

    elif kg_section == "📤 Exportar / importar":
        st.subheader("📤 Exportar / importar")
        st.info(
            "El estado visual real vive en JavaScript. Usa 📋 Copiar estado JSON dentro del grafo "
            "para traer el estado actual a Streamlit y guardarlo o importarlo."
        )
        if all_maps:
            export_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in all_maps}
            export_label = st.selectbox("Mapa para exportar", list(export_options), key="kg_export_selected_map")
            export_doc = _find_knowledge_graph_map(maps_col, export_options[export_label])
            if export_doc:
                export_state = export_doc.get("graph_state", {})
                export_sources = infer_sources_from_graph_state(export_state)
                export_types = infer_concept_types_from_graph_state(export_state)
                if export_sources:
                    st.caption(f"Fuentes inferidas del estado exportado: {', '.join(export_sources)}")
                if export_types:
                    st.caption(f"Tipos inferidos del estado exportado: {', '.join(export_types)}")
                st.download_button(
                    "📥 Descargar JSON guardado",
                    data=json.dumps(export_state, ensure_ascii=False, indent=2, default=str),
                    file_name=f"{export_doc.get('name', 'knowledge_graph_map')}.json",
                    mime="application/json",
                )
                html_content = _render_knowledge_graph_map_html(export_state, f"export_{export_doc['_id']}")
                st.download_button(
                    "📥 Descargar HTML restaurado",
                    data=html_content,
                    file_name=f"{export_doc.get('name', 'knowledge_graph_map')}.html",
                    mime="text/html",
                )
        else:
            st.info("No hay mapas guardados para exportar.")

        with st.form("kg_import_state_form"):
            st.markdown("**Importar estado JSON como mapa nuevo**")
            import_name = st.text_input("Nombre del mapa importado", key="kg_import_name")
            import_description = st.text_area("Descripción", height=80, key="kg_import_description")
            import_tags = st.text_input("Tags (separados por coma)", key="kg_import_tags")
            import_state_json = st.text_area("Estado JSON", height=180, key="kg_import_state_json")
            import_map = st.form_submit_button("📥 Importar estado JSON")

        if import_map:
            if not import_name.strip():
                st.error("El nombre del mapa es obligatorio.")
            else:
                try:
                    graph_state = _parse_knowledge_graph_state_json(import_state_json)
                    integrity_issues = graph_state_integrity_issues(graph_state)
                    if integrity_issues:
                        st.error("Se detectaron inconsistencias antes de importar el mapa.")
                        st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                        st.stop()
                    inferred_sources = infer_sources_from_graph_state(graph_state)
                    inferred_types = infer_concept_types_from_graph_state(graph_state)
                    primary_map_source = inferred_sources[0] if inferred_sources else ""
                    now = datetime.utcnow()
                    result = maps_col.insert_one(
                        {
                            "name": import_name.strip(),
                            "description": import_description.strip(),
                            "created_at": now,
                            "updated_at": now,
                            "filters": {
                                "sources": inferred_sources,
                                "relation_types": [],
                                "concept_types": inferred_types,
                                "max_depth": 3,
                            },
                            "primary_map_source": primary_map_source,
                            "map_sources": inferred_sources,
                            "graph_state": graph_state,
                            "tags": [tag.strip() for tag in import_tags.split(",") if tag.strip()],
                            "source": "interactive_knowledge_graph",
                            "map_uid": str(uuid4()),
                            "sync_settings": default_sync_settings(),
                        }
                    )
                    if result.acknowledged:
                        st.success("Mapa importado correctamente.")
                    else:
                        st.error("MongoDB no confirmó la importación.")
                except json.JSONDecodeError as exc:
                    st.error(f"No se pudo leer el JSON del estado: {exc}")
                except Exception as exc:
                    st.error(f"No se pudo importar el mapa: {exc}")

# Document Builder page
elif page == "📄 Document Builder":
    render_document_builder_page(db, current_db)

# Export page
elif page == "📤 Export":
    st.title("📤 Export Concepts")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Exporting from: **{current_db}**")

    st.subheader("📄 LaTeX/PDF Export")
    st.info("Para construir un unico PDF modular con varios conceptos, usa la pagina 📄 Document Builder.")

    # Export options
    col1, col2 = st.columns(2)

    with col1:
        export_source = st.selectbox("Select Source", [""] + list(db.concepts.distinct("source")))
        export_type = st.selectbox("Export Type", ["All", "definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"])

    with col2:
        export_format = st.selectbox("Export Format", ["PDF", "LaTeX"])
        output_dir = st.text_input(
            "Output Directory",
            value=str(get_exports_dir(configured=resolve_config().export_directory) / "concepts"),
        )

    val_exp_col1, val_exp_col2, val_exp_col3 = st.columns(3)
    with val_exp_col1:
        validate_latex_before_export = st.checkbox(
            "Validar LaTeX antes de exportar",
            value=True,
            key="export_validate_latex_before_export",
        )
    with val_exp_col2:
        apply_safe_fixes_export = st.checkbox(
            "Aplicar fixes seguros solo al export",
            value=False,
            key="export_apply_safe_fixes",
        )
    with val_exp_col3:
        export_even_with_errors = st.checkbox(
            "Exportar aunque haya errores",
            value=False,
            key="export_even_with_errors",
        )

    if st.button("📤 Export", type="primary"):
        if export_source:
            try:
                exportador = ExportadorLatex()
                resolved_output_dir = validate_mutable_path(resolve_home_path(output_dir))

                # Build query
                query = {"source": export_source}
                if export_type != "All":
                    query["tipo"] = export_type

                concepts = list(db.concepts.find(query))

                if concepts:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, concept in enumerate(concepts):
                        status_text.text(f"Exporting {concept['id']}...")

                        latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": export_source})
                        if latex_doc:
                            contenido_latex = latex_doc['contenido_latex']
                            if validate_latex_before_export:
                                validation = validate_latex_fragment(
                                    contenido_latex,
                                    concept=concept,
                                    apply_fixes=apply_safe_fixes_export,
                                )
                                if validation.status == "error" and not export_even_with_errors:
                                    st.error(
                                        f"Skipping {concept['id']} due to LaTeX errors. "
                                        "Enable 'Exportar aunque haya errores' to force export."
                                    )
                                    if validation.unknown_commands:
                                        st.write(validation.unknown_commands)
                                    if validation.log_excerpt:
                                        with st.expander(f"LaTeX log: {concept['id']}"):
                                            st.code(validation.log_excerpt)
                                    progress_bar.progress((i + 1) / len(concepts))
                                    continue
                                if validation.status == "warning":
                                    st.warning(f"LaTeX warnings for {concept['id']}")
                                if apply_safe_fixes_export and validation.safe_fixes:
                                    contenido_latex = validation.corrected_latex_preview
                                    st.warning(
                                        f"Applied safe fixes only to exported file for {concept['id']}; "
                                        "MongoDB was not modified."
                                    )
                            exportador.exportar_concepto(
                                concept,
                                contenido_latex,
                                salida=str(resolved_output_dir),
                            )

                        progress_bar.progress((i + 1) / len(concepts))

                    status_text.text("✅ Export completed!")
                    st.success(f"✅ Exported {len(concepts)} concepts to {resolved_output_dir}")

                    # Show exported files
                    if resolved_output_dir.exists():
                        st.subheader("📁 Exported Files")
                        files = list(
                            resolved_output_dir.glob(
                                "*.pdf" if export_format == "PDF" else "*.tex"
                            )
                        )
                        for file in files:
                            st.write(f"• {file.name}")

                else:
                    st.warning("⚠️ No concepts found for the selected source and type.")

            except Exception as e:
                st.error(f"❌ Export failed: {e}")
        else:
            st.error("❌ Please select a source to export.")

    st.markdown("---")

    # Bulk operations
    st.subheader("🔄 Bulk Operations")

    if st.button("🔄 Export All Sources"):
        try:
            sources = db.concepts.distinct("source")
            exportador = ExportadorLatex()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, source in enumerate(sources):
                status_text.text(f"Exporting source: {source}")
                concepts_root = get_exports_dir(
                    configured=resolve_config().export_directory
                ) / "concepts"
                bulk_dir = validate_mutable_path(
                    concepts_root / source,
                    allowed_root=concepts_root,
                )
                exportador.exportar_todos_de_source(db.client, source, salida=str(bulk_dir))
                progress_bar.progress((i + 1) / len(sources))

            status_text.text("✅ Bulk export completed!")
            st.success(f"✅ Exported all {len(sources)} sources")

        except Exception as e:
            st.error(f"❌ Bulk export failed: {e}")

# Maintenance page
elif page == "🧹 Maintenance":
    _render_cleanup_maintenance_page()

# Settings page
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")

    st.subheader("🔧 Database Configuration")

    # Database status
    if db is None:
        st.error("❌ No database connection.")
        st.stop()
    else:
        st.success(f"✅ Connected to: **{current_db}**")

    # Database statistics
    st.subheader("📊 Database Statistics")

    col1, col2 = st.columns(2)

    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("Total Concepts", concept_count)

        relation_count = db.relations.count_documents({})
        st.metric("Total Relations", relation_count)

    with col2:
        source_count = len(db.concepts.distinct("source"))
        st.metric("Sources", source_count)

        category_count = len(db.concepts.distinct("categorias"))
        st.metric("Categories", category_count)

    # Database operations
    st.subheader("🗄️ Database Operations")

    if "confirm_clear_all" not in st.session_state:
        st.session_state.confirm_clear_all = False

    col1, col2 = st.columns(2)

    with col1:
        if not st.session_state.confirm_clear_all:
            if st.button("🧹 Clear All Data", type="secondary", key="clear_all_data_btn"):
                st.session_state.confirm_clear_all = True
                st.rerun()
        else:
            st.warning("⚠️ This will permanently delete all concepts, relations, and LaTeX documents from the current database.")

            c1, c2 = st.columns(2)

            with c1:
                 if st.button("⚠️ Confirm Clear All", type="primary", key="confirm_clear_all_btn"):
                    try:
                        for collection_name in EXPORT_COLLECTIONS:
                            db.db[collection_name].delete_many({})
                        st.session_state.confirm_clear_all = False
                        st.success("✅ All data cleared!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error clearing data: {e}")
            with c2:
                if st.button("Cancel", key="cancel_clear_all_btn"):
                    st.session_state.confirm_clear_all = False
                    st.rerun()

    with col2:
        if st.button("📊 Rebuild Indexes", key="rebuild_indexes_btn"):
            try:
                db.ensure_indexes()
                st.success("✅ Indexes rebuilt successfully!")
            except MongoIndexInitializationError as e:
                st.error(f"❌ MongoDB está conectado, pero falló la inicialización de índices: {e}")
            except Exception as e:
                st.error(f"❌ Error rebuilding indexes: {e}")

    # Application information
    st.subheader("ℹ️ Application Information")

    st.write("**Math Knowledge Base** - Version 0.1.0b1")
    st.write("A platform for managing mathematical knowledge with LaTeX support and MongoDB storage.")
    st.write("**Author:** Enrique Díaz Ocampo")
    st.write("**License:** MIT")

elif page == "📦 Database Export":
    st.header("📦 Database Export")
    st.markdown(
        """
        Export the full Math Knowledge Base database as a ZIP archive.
        This operation is **read-only** and does not modify the database.
        """
    )
    st.caption(
        f"Timeout: {EXPORT_TIMEOUT_SECONDS}s · Expected collections: "
        + ", ".join(EXPORT_COLLECTIONS)
    )
    if st.button("📦 Export database"):
        with st.spinner("Exporting database..."):
            try:
                out_dir = validate_mutable_path(get_backups_dir())
                out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                zip_path = export_database_to_zip(db, out_dir)
                st.success(f"Export completed successfully: {zip_path}")
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Download ZIP",
                        data=f,
                        file_name=zip_path.name,
                        mime="application/zip",
                    )
            except Exception as e:
                st.error(f"Export failed: {e}")


elif page == "📥 Database Import":
    render_database_import_page(st, db)


# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Math Knowledge Base - Built with Streamlit and MongoDB
    </div>
    """,
    unsafe_allow_html=True)
