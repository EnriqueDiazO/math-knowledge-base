"""Explicit online lookup feeding the existing editable catalog form and save plans."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any
from uuid import uuid4

from editor.source_catalog.reference_actions import render_reference_save_plan
from editor.source_catalog.reference_form import render_reference_form
from editor.source_catalog.shared import render_duplicate_preview
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import request_navigation
from editor.source_catalog.state import state_key
from editor.source_catalog.workflows import ReferenceSavePlan
from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.repository import reference_revision

STATUS_TEXT = {
    "found": "Referencia recuperada. Revisa la propuesta antes de guardar.",
    "partial": "Resultado parcial: faltan datos. Puedes completar la ficha manualmente.",
    "candidates": "Varias obras candidatas. Consulta una edición antes de asignarle ISBN o fecha.",
    "invalid": "DOI o ISBN inválido. Revisa el formato y el dígito de control.",
    "not_found": "No se pudo recuperar la referencia. Esto no demuestra que el identificador no exista.",
    "unavailable": "Proveedor no disponible. Conservamos la consulta y las correcciones; puedes reintentar o usar captura manual.",
    "rate_limited": "El proveedor limita las solicitudes. Espera antes de volver a consultar.",
}


def metadata_lookup() -> MetadataLookup:
    """Share bounded cache/rate limits across sessions; transmit explicit contact only."""
    import streamlit as st

    @st.cache_resource
    def resource(contact: str) -> MetadataLookup:
        return MetadataLookup(contact=contact)

    return resource(os.environ.get("MATHMONGO_METADATA_CONTACT", ""))


def render_lookup(
    ui: Any, *, key_prefix: str, api: MetadataLookup | None = None
) -> Reference | None:
    """Keep each explicitly chosen proposal's widget keys, never overwrite its corrections."""
    api = api or metadata_lookup()
    result_key = state_key(key_prefix, "lookup_result")
    ui.caption(
        "Se envía sólo el identificador o el título/autor a los catálogos públicos. No se envían notas ni PDF; recuperar metadatos no descarga el texto completo."
    )
    query = ui.text_input("Pegar DOI o ISBN", key=state_key(key_prefix, "identifier"))
    if ui.button("Buscar referencia", key=state_key(key_prefix, "search_identifier")):
        with ui.spinner("Buscando referencia…"):
            result = api.identifier(query).public(str(uuid4()))
        ui.session_state[result_key] = result
    with ui.expander("Buscar por título y autor"):
        title = ui.text_input("Título del libro", key=state_key(key_prefix, "title_query"))
        author = ui.text_input("Autor del libro", key=state_key(key_prefix, "author_query"))
        if ui.button("Buscar libros", key=state_key(key_prefix, "search_books")):
            with ui.spinner("Buscando libros…"):
                ui.session_state[result_key] = api.search(title, author).public(str(uuid4()))
    result = ui.session_state.get(result_key)
    if not isinstance(result, dict):
        return None
    ui.info(STATUS_TEXT.get(result["status"], "Revisa el resultado de la consulta."))
    ui.caption(f"Consulta: {result['query']} · Proveedores: {', '.join(result['providers'])}")
    if result.get("retry_after"):
        ui.caption(f"Espera indicada por el proveedor: {result['retry_after']:g} s.")
    candidates = result.get("candidates") or []
    if not candidates:
        candidate = ui.session_state.get(state_key(key_prefix, "active_proposal"))
        if not candidate:
            return None
        ui.caption(
            "Se conserva la propuesta anterior y sus correcciones; no es un resultado de la consulta fallida."
        )
    else:
        index = ui.selectbox(
            "Propuesta recuperada",
            list(range(len(candidates))),
            format_func=lambda i: candidates[i]["reference_data"].get("title") or "Sin título",
            key=state_key(key_prefix, "candidate", result["request_id"]),
        )
        candidate = candidates[index]
        ui.session_state[state_key(key_prefix, "active_proposal")] = candidate
    if candidate.get("edition_ids"):
        edition = ui.selectbox(
            "Edición candidata",
            candidate["edition_ids"],
            key=state_key(key_prefix, "edition", result["request_id"], str(index)),
        )
        if ui.button(
            "Consultar esta edición",
            key=state_key(key_prefix, "load_edition", result["request_id"]),
        ):
            with ui.spinner("Consultando la edición…"):
                ui.session_state[result_key] = api.edition(edition).public(str(uuid4()))
            ui.rerun()
    initial = Reference.model_validate(candidate["reference_data"])
    for warning in initial.provenance.warnings:
        ui.warning(warning)
    stamp = initial.provenance.external_lookup
    if stamp:
        ui.caption(f"{stamp.provider} · {stamp.record_kind} · {stamp.retrieved_at.isoformat()}")
    # New searches have separate drafts; the old proposal's corrections remain in
    # Streamlit state. Selecting a result never writes an existing Reference.
    draft = render_reference_form(
        ui, key_prefix=f"{key_prefix}_{initial.reference_id}", initial=initial, compact=True
    )
    for error in draft.errors:
        ui.error(error)
    if draft.reference is not None:
        saved_candidate = deepcopy(candidate)
        saved_candidate["reference_data"] = draft.reference.model_dump(mode="json")
        ui.session_state[state_key(key_prefix, "active_proposal")] = saved_candidate
    return draft.reference


def render_lookup_reference_plan(
    ui: Any, context, *, key_prefix: str, source_ids=()
) -> tuple[list[ReferenceSavePlan], bool]:
    """Apply the same duplicate decisions as manual/BibTeX input, including reuse."""
    reference = render_lookup(ui, key_prefix=key_prefix)
    if reference is None:
        return [], False
    matches = tuple(context.service.detect_reference_duplicates(reference))
    render_duplicate_preview(ui, matches)
    for match in matches:
        existing = context.reference_repository.get_by_id(match.entity_id)
        if existing is None:
            continue
        for source_id in existing.source_ids:
            if ui.button(
                "Usar Source existente: " + source_id,
                key=state_key(key_prefix, "reuse_source", source_id, existing.reference_id),
            ):
                request_navigation(ui.session_state, EDIT_SOURCE_NAV_LABEL, source_id=source_id)
                ui.rerun()
    plan, ready = render_reference_save_plan(
        ui,
        key_prefix=key_prefix,
        label="Referencia en línea",
        reference=reference,
        duplicates=matches,
    )
    return ([plan] if plan else []), ready


def reference_update_options(current: Reference, proposal: Reference) -> dict[str, tuple[Any, Any]]:
    """Metadata differences never offer identity, Source memberships or citation keys."""
    fields = (
        "reference_type",
        "authors",
        "title",
        "year",
        "year_raw",
        "journal",
        "publisher",
        "volume",
        "number",
        "edition",
        "isbn",
        "doi",
        "url",
        "language",
        "notes",
    )
    before, after = current.model_dump(mode="json"), proposal.model_dump(mode="json")
    result = {key: (before[key], after[key]) for key in fields if before[key] != after[key]}
    for key in set(current.bibtex.extra) | set(proposal.bibtex.extra):
        old, new = current.bibtex.extra.get(key), proposal.bibtex.extra.get(key)
        if old != new:
            result["extra." + key] = (old, new)
    return result


def selected_reference_updates(
    current: Reference, proposal: Reference, selected: list[str]
) -> dict:
    """Preserve every unselected/manual field and the stable BibTeX key/raw source."""
    options = reference_update_options(current, proposal)
    changes, extra = {}, dict(current.bibtex.extra)
    values = proposal.model_dump(mode="python")
    for key in selected:
        if key not in options:
            raise ValueError("Unknown metadata difference")
        if key.startswith("extra."):
            name = key.removeprefix("extra.")
            value = proposal.bibtex.extra.get(name)
            if value is None:
                extra.pop(name, None)
            else:
                extra[name] = value
        else:
            changes[key] = values[key]
    if extra != current.bibtex.extra:
        changes["bibtex"] = {**current.bibtex.model_dump(mode="python"), "extra": extra}
    if changes and proposal.provenance.external_lookup:
        changes["provenance"] = proposal.provenance.model_dump(mode="python")
    return changes


def render_reference_refresh(ui: Any, context, current: Reference, *, writes_enabled: bool) -> None:
    """An update is a reviewed field selection, with no automatic overwrite/merge."""
    from editor.source_catalog.shared import render_catalog_result
    from editor.source_catalog.state import draft_fingerprint

    with ui.expander("Consultar DOI/ISBN para actualizar esta ficha"):
        proposal = render_lookup(ui, key_prefix="refresh_" + current.reference_id)
        if proposal is None:
            return
        selected = []
        for key, (old, new) in reference_update_options(current, proposal).items():
            ui.write({"campo": key, "actual": old, "propuesta": new})
            if ui.checkbox(
                "Actualizar sólo " + key,
                key=state_key(
                    "refresh_field",
                    current.reference_id,
                    draft_fingerprint({"field": key, "old": old, "new": new}),
                ),
            ):
                selected.append(key)
        if ui.button(
            "Aplicar campos seleccionados",
            key=state_key("refresh_apply", current.reference_id),
            disabled=not writes_enabled or not selected,
        ):
            result = context.service.update_reference(
                current.reference_id,
                selected_reference_updates(current, proposal, selected),
                expected_updated_at=current.updated_at,
                expected_revision=reference_revision(current),
            )
            render_catalog_result(
                ui,
                result,
                success="Campos seleccionados actualizados; identidad y clave de cita conservadas.",
            )
