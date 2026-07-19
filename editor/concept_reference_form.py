"""Persistence-free bibliography import and form state for Add Concept."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from editor.helpers.bibliographic_reference import NormalizedBibliographicEntry
from editor.helpers.bibliographic_reference import normalize_bibliographic_entry
from editor.helpers.tipo_referencia import TipoReferencia
from editor.source_catalog.bibtex_ui import uploaded_bibtex_bytes
from mathmongo.source_catalog.bibtex import BibTeXParseResult
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_paste
from mathmongo.source_catalog.normalization import normalize_doi

STATE_PREFIX = "add_concept_reference_"
_REFERENCE_FIELDS = (
    "tipo_referencia",
    "autor",
    "fuente",
    "anio",
    "tomo",
    "edicion",
    "paginas",
    "capitulo",
    "seccion",
    "editorial",
    "doi",
    "url",
    "issbn",
    "citekey",
)
_TEXT_FIELDS = tuple(
    field_name
    for field_name in _REFERENCE_FIELDS
    if field_name not in {"tipo_referencia", "anio"}
)
_VALID_REFERENCE_TYPES = frozenset(item.value for item in TipoReferencia)


def state_key(name: str) -> str:
    """Return one key private to the Add Concept reference workflow."""
    return f"{STATE_PREFIX}{name}"


def _scope_identity(
    database_scope: str | None,
    source_id: str | None,
    concept_id: str | None,
) -> str:
    return "\x1f".join(
        "" if value is None else str(value)
        for value in (database_scope, source_id, concept_id)
    )


def clear_reference_state(
    state: Any,
    *,
    preserve_scope: bool = True,
) -> None:
    """Clear only the namespaced Add Concept bibliography workflow."""
    scope = state.get(state_key("scope")) if preserve_scope else None
    for key in tuple(state):
        if str(key).startswith(STATE_PREFIX):
            state.pop(key, None)
    if preserve_scope and scope is not None:
        state[state_key("scope")] = scope


def sync_reference_scope(
    state: Any,
    *,
    database_scope: str | None,
    source_id: str | None,
    concept_id: str | None,
) -> bool:
    """Clear bibliography state when its database, Source, or concept changes."""
    identity = _scope_identity(database_scope, source_id, concept_id)
    scope_key = state_key("scope")
    previous = state.get(scope_key)
    if previous == identity:
        return False
    clear_reference_state(state, preserve_scope=False)
    state[scope_key] = identity
    return previous is not None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("Year must be an integer.")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError("Year must contain digits only.")
    return int(text)


def _reference_updates(reference: Mapping[str, Any]) -> dict[str, Any]:
    type_value = getattr(reference.get("tipo_referencia"), "value", None) or reference.get(
        "tipo_referencia"
    )
    type_text = _optional_text(type_value) or "libro"
    if type_text not in _VALID_REFERENCE_TYPES:
        raise ValueError(f"Reference type {type_text!r} is not valid for Add Concept.")
    updates: dict[str, Any] = {
        state_key("tipo_referencia"): type_text,
        state_key("anio"): _year(reference.get("anio")),
    }
    updates.update(
        {
            state_key(field_name): _optional_text(reference.get(field_name)) or ""
            for field_name in _TEXT_FIELDS
        }
    )
    return updates


def apply_reference_to_state(state: Any, reference: Mapping[str, Any]) -> None:
    """Atomically replace form fields after a successful parse or explicit load."""
    if not isinstance(reference, Mapping):
        raise TypeError("Concept reference must be a mapping.")
    updates = _reference_updates(reference)
    state.update(updates)


def reference_from_state(state: Any) -> dict[str, Any]:
    """Read the normalized concept Reference contract from namespaced state."""
    return {
        "tipo_referencia": _optional_text(state.get(state_key("tipo_referencia")))
        or "libro",
        "autor": _optional_text(state.get(state_key("autor"))),
        "fuente": _optional_text(state.get(state_key("fuente"))),
        "anio": _year(state.get(state_key("anio"))),
        "tomo": _optional_text(state.get(state_key("tomo"))),
        "edicion": _optional_text(state.get(state_key("edicion"))),
        "paginas": _optional_text(state.get(state_key("paginas"))),
        "capitulo": _optional_text(state.get(state_key("capitulo"))),
        "seccion": _optional_text(state.get(state_key("seccion"))),
        "editorial": _optional_text(state.get(state_key("editorial"))),
        "doi": normalize_doi(state.get(state_key("doi"))),
        "url": _optional_text(state.get(state_key("url"))),
        "issbn": _optional_text(state.get(state_key("issbn"))),
        "citekey": _optional_text(state.get(state_key("citekey"))),
    }


def concept_reference_has_content(reference: Mapping[str, Any] | None) -> bool:
    """Return whether a Reference has content beyond its default type."""
    if not isinstance(reference, Mapping):
        return False
    return any(reference.get(field_name) not in (None, "") for field_name in _TEXT_FIELDS) or (
        reference.get("anio") is not None
    )


def _candidate_by_index(
    preview: BibTeXParseResult,
    entry_index: int,
) -> Mapping[str, Any] | None:
    return next(
        (
            candidate
            for candidate in preview.candidates
            if int(candidate.get("entry_index", -1)) == entry_index
        ),
        None,
    )


def _candidate_label(candidate: Mapping[str, Any]) -> str:
    reference_data = candidate.get("reference_data")
    reference_data = reference_data if isinstance(reference_data, Mapping) else {}
    citekey = _optional_text(candidate.get("citekey")) or "(sin key)"
    title = _optional_text(reference_data.get("title")) or "(sin título)"
    return f"{citekey} — {title[:80]}"


def _parse_error_message(error: Mapping[str, Any], *, from_file: bool) -> str:
    prefix = "No se pudo leer el .bib" if from_file else "No se pudo analizar la referencia"
    code = _optional_text(error.get("code")) or "parse_error"
    message = _optional_text(error.get("message")) or "Entrada bibliográfica inválida."
    entry = error.get("entry_index")
    entry_text = f" Entrada {entry}." if entry is not None else ""
    return f"{prefix}: [{code}]{entry_text} {message}"


def _render_parse_errors(
    ui: Any,
    preview: BibTeXParseResult,
    *,
    from_file: bool,
) -> None:
    for error in preview.errors:
        ui.error(_parse_error_message(error, from_file=from_file))


def _input_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _apply_candidate(
    ui: Any,
    candidate: Mapping[str, Any],
    *,
    success_message: str,
) -> None:
    try:
        normalized: NormalizedBibliographicEntry = normalize_bibliographic_entry(candidate)
    except RuntimeError as exc:
        raise ValueError(f"Unexpected bibliography contract: {exc}") from exc
    warnings = list(normalized.warnings)
    if not (normalized.reference.get("autor") or normalized.reference.get("fuente")):
        warnings.append(
            "Entrada incompleta: no contiene autor ni título; revisa los campos antes de guardar."
        )
    apply_reference_to_state(ui.session_state, normalized.reference)
    ui.session_state[state_key("last_preview")] = dict(normalized.reference)
    ui.session_state[state_key("last_warnings")] = tuple(dict.fromkeys(warnings))
    ui.session_state[state_key("notice")] = success_message
    ui.rerun()


def _render_notice_and_preview(ui: Any) -> None:
    notice = ui.session_state.pop(state_key("notice"), None)
    if notice:
        ui.success(str(notice))
    preview = ui.session_state.get(state_key("last_preview"))
    if isinstance(preview, Mapping):
        ui.markdown("##### Resultado normalizado")
        ui.json(dict(preview))
    warnings = ui.session_state.get(state_key("last_warnings"))
    if isinstance(warnings, list | tuple):
        for warning in warnings:
            ui.warning(str(warning))


def _render_file_import(ui: Any) -> None:
    ui.markdown("##### Importar .bib")
    uploaded = ui.file_uploader(
        "Cargar .bib",
        type=["bib"],
        key=state_key("upload"),
    )
    if uploaded is None:
        return
    try:
        content = uploaded_bibtex_bytes(uploaded)
        preview = parse_bibtex_file_content(content)
    except (TypeError, ValueError) as exc:
        ui.error(f"No se pudo leer el .bib: {exc}")
        return
    _render_parse_errors(ui, preview, from_file=True)
    if not preview.candidates:
        return
    indices = [int(candidate["entry_index"]) for candidate in preview.candidates]
    labels = {
        int(candidate["entry_index"]): _candidate_label(candidate)
        for candidate in preview.candidates
    }
    selected = ui.selectbox(
        "Selecciona entrada",
        indices,
        format_func=lambda value: labels.get(int(value), str(value)),
        key=state_key("file_entry"),
    )
    if ui.button("Usar esta entrada", key=state_key("use_file_entry")):
        candidate = _candidate_by_index(preview, int(selected))
        if candidate is None:
            ui.error("Error interno: la entrada seleccionada ya no está disponible.")
            return
        try:
            _apply_candidate(
                ui,
                candidate,
                success_message="Entrada cargada. Revisa los campos antes de guardar.",
            )
        except (TypeError, ValueError) as exc:
            ui.error(f"Error interno al normalizar la entrada: {exc}")


def _stored_paste_preview(ui: Any, content: str) -> BibTeXParseResult | None:
    preview = ui.session_state.get(state_key("paste_preview"))
    digest = ui.session_state.get(state_key("paste_digest"))
    if isinstance(preview, BibTeXParseResult) and digest == _input_digest(content):
        return preview
    return None


def _render_paste_import(ui: Any) -> None:
    ui.markdown("##### Pegar referencia o entrada BibTeX")
    content = ui.text_area(
        "Pegar referencia o entrada BibTeX",
        height=200,
        key=state_key("paste"),
    )
    analyzed = ui.button(
        "Analizar referencia",
        key=state_key("analyze_paste"),
        disabled=not bool(content.strip()),
    )
    if analyzed and content.strip():
        preview = parse_bibtex_paste(content)
        ui.session_state[state_key("paste_preview")] = preview
        ui.session_state[state_key("paste_digest")] = _input_digest(content)
        if len(preview.candidates) == 1 and not preview.errors:
            try:
                _apply_candidate(
                    ui,
                    preview.candidates[0],
                    success_message=(
                        "Referencia analizada. Revisa los campos antes de guardar."
                    ),
                )
            except (TypeError, ValueError) as exc:
                ui.error(f"Error interno al normalizar la referencia: {exc}")

    preview = _stored_paste_preview(ui, content)
    if preview is None:
        return
    _render_parse_errors(ui, preview, from_file=False)
    if not preview.candidates:
        return
    if len(preview.candidates) == 1 and not preview.errors:
        return

    indices = [int(candidate["entry_index"]) for candidate in preview.candidates]
    labels = {
        int(candidate["entry_index"]): _candidate_label(candidate)
        for candidate in preview.candidates
    }
    selected = ui.selectbox(
        "Selecciona entrada pegada",
        indices,
        format_func=lambda value: labels.get(int(value), str(value)),
        key=state_key("paste_entry"),
    )
    if ui.button("Usar entrada pegada", key=state_key("use_paste_entry")):
        candidate = _candidate_by_index(preview, int(selected))
        if candidate is None:
            ui.error("Error interno: la entrada pegada seleccionada ya no está disponible.")
            return
        try:
            _apply_candidate(
                ui,
                candidate,
                success_message="Entrada cargada. Revisa los campos antes de guardar.",
            )
        except (TypeError, ValueError) as exc:
            ui.error(f"Error interno al normalizar la referencia: {exc}")


def _render_manual_form(ui: Any) -> dict[str, Any]:
    ui.markdown("##### Editar manualmente")
    type_options = [item.value for item in TipoReferencia]
    current_type = ui.session_state.get(state_key("tipo_referencia"), "libro")
    type_index = type_options.index(current_type) if current_type in type_options else 0
    col1, col2 = ui.columns(2)
    with col1:
        ref_type = ui.selectbox(
            "Reference Type",
            type_options,
            index=type_index,
            key=state_key("tipo_referencia"),
        )
        author = ui.text_input("Author", key=state_key("autor"))
        source_title = ui.text_input("Source/Title", key=state_key("fuente"))
        year = ui.number_input(
            "Year",
            min_value=1800,
            max_value=3000,
            value=None,
            key=state_key("anio"),
        )
    with col2:
        volume = ui.text_input("Volume", key=state_key("tomo"))
        edition = ui.text_input("Edition", key=state_key("edicion"))
        pages = ui.text_input("Pages", key=state_key("paginas"))
        chapter = ui.text_input("Chapter", key=state_key("capitulo"))
    section = ui.text_input("Section", key=state_key("seccion"))
    publisher = ui.text_input("Publisher", key=state_key("editorial"))
    doi = ui.text_input("DOI", key=state_key("doi"))
    url = ui.text_input("URL", key=state_key("url"))
    issbn = ui.text_input("ISBN", key=state_key("issbn"))
    citekey = ui.text_input("Citekey (opcional)", key=state_key("citekey"))
    return {
        "tipo_referencia": ref_type,
        "autor": _optional_text(author),
        "fuente": _optional_text(source_title),
        "anio": _year(year),
        "tomo": _optional_text(volume),
        "edicion": _optional_text(edition),
        "paginas": _optional_text(pages),
        "capitulo": _optional_text(chapter),
        "seccion": _optional_text(section),
        "editorial": _optional_text(publisher),
        "doi": normalize_doi(doi),
        "url": _optional_text(url),
        "issbn": _optional_text(issbn),
        "citekey": _optional_text(citekey),
    }


def render_concept_reference_form(
    ui: Any,
    *,
    database_scope: str | None,
    source_id: str | None,
    concept_id: str | None,
) -> dict[str, Any]:
    """Render all Add Concept input methods into one editable form contract."""
    sync_reference_scope(
        ui.session_state,
        database_scope=database_scope,
        source_id=source_id,
        concept_id=concept_id,
    )
    with ui.expander("Add / Edit Reference", expanded=False):
        if ui.button(
            "Limpiar formulario de referencia",
            key=state_key("clear"),
        ):
            clear_reference_state(ui.session_state)
            ui.session_state[state_key("notice")] = "Formulario de referencia limpiado."
            ui.rerun()
        _render_notice_and_preview(ui)
        _render_file_import(ui)
        _render_paste_import(ui)
        return _render_manual_form(ui)


__all__ = [
    "STATE_PREFIX",
    "apply_reference_to_state",
    "clear_reference_state",
    "concept_reference_has_content",
    "reference_from_state",
    "render_concept_reference_form",
    "state_key",
    "sync_reference_scope",
]
