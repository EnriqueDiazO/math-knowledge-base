"""Native Streamlit cards and summaries for Source Catalog workflows."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any


def _card(ui: Any):
    container = getattr(ui, "container", None)
    if callable(container):
        return container(border=True)
    return nullcontext(ui)


def _write(ui: Any, value: object) -> None:
    writer = getattr(ui, "write", None)
    if callable(writer):
        writer(value)


def _caption(ui: Any, value: object) -> None:
    caption = getattr(ui, "caption", None)
    if callable(caption):
        caption(value)
    else:
        _write(ui, value)


def _label(ui: Any, value: str) -> None:
    markdown = getattr(ui, "markdown", None)
    if callable(markdown):
        markdown(f"**{value}**")
    else:
        _write(ui, value)


def _value(value: object, *, empty: str = "—") -> str:
    if value is None:
        return empty
    if isinstance(value, list | tuple | set):
        return ", ".join(str(item) for item in value) or empty
    text = str(value).strip()
    return text or empty


def render_section_header(ui: Any, title: str, caption: str | None = None) -> None:
    """Render a compact, accessible section heading without injected markup."""
    subheader = getattr(ui, "subheader", None)
    if callable(subheader):
        subheader(title)
    else:
        _label(ui, title)
    if caption:
        _caption(ui, caption)


def render_key_value_card(
    ui: Any,
    title: str,
    values: Iterable[tuple[str, object]],
    *,
    caption: str | None = None,
) -> None:
    """Render a short vertical summary; never a one-row pseudo-table."""
    with _card(ui):
        _label(ui, title)
        if caption:
            _caption(ui, caption)
        for label, value in values:
            _label(ui, label)
            _write(ui, _value(value))


def render_source_summary_card(ui: Any, source: Any, *, title: str) -> None:
    """Render the meaningful Source fields as a readable vertical card."""
    aliases = [getattr(alias, "value", alias) for alias in getattr(source, "aliases", ())]
    rights = getattr(source, "rights_default", None)
    rights_text = " · ".join(
        item
        for item in (
            _value(getattr(rights, "copyright_status", None), empty=""),
            _value(getattr(rights, "redistribution", None), empty=""),
        )
        if item
    )
    render_key_value_card(
        ui,
        title,
        (
            ("Nombre", getattr(source, "name", None)),
            ("Tipo", getattr(getattr(source, "source_type", None), "value", None)),
            ("Descripción", getattr(source, "description", None)),
            ("Idioma", getattr(source, "language", None)),
            ("Etiquetas", getattr(source, "tags", ())),
            ("Aliases", aliases),
            ("Estado", getattr(getattr(source, "status", None), "value", None)),
            ("Derechos", rights_text),
            ("Última actualización", getattr(source, "updated_at", None)),
        ),
        caption=f"ID: {getattr(source, 'source_id', 'pendiente de validar')}",
    )


def render_reference_summary_card(ui: Any, reference: Any, *, title: str) -> None:
    """Render bibliographic metadata as a compact card instead of a dataframe."""
    render_key_value_card(
        ui,
        title,
        (
            ("Título", getattr(reference, "title", None)),
            ("Tipo", getattr(getattr(reference, "reference_type", None), "value", None)),
            ("Enlace", getattr(reference, "url", None)),
            ("DOI", getattr(reference, "doi", None)),
            ("Año", getattr(reference, "year", None) or getattr(reference, "year_raw", None)),
            ("Estado", getattr(getattr(reference, "status", None), "value", None)),
            ("Última actualización", getattr(reference, "updated_at", None)),
        ),
        caption=f"ID: {getattr(reference, 'reference_id', 'pendiente de validar')}",
    )


def render_duplicate_cards(ui: Any, matches: Iterable[Any]) -> bool:
    """Present duplicate evidence as small review cards and return whether any exist."""
    values = tuple(matches)
    if not values:
        success = getattr(ui, "success", None)
        if callable(success):
            success("No se encontraron candidatos duplicados en la base activa.")
        return False

    labels = {
        "exact": "Coincidencia exacta",
        "strong": "Coincidencia fuerte",
        "possible": "Posible coincidencia",
        "weak": "Sugerencia débil",
    }
    for match in values:
        classification = getattr(getattr(match, "classification", None), "value", "possible")
        evidence = ", ".join(
            getattr(getattr(item, "evidence_type", None), "value", "evidencia")
            for item in getattr(match, "evidence", ())
        )
        warnings = "; ".join(str(item) for item in getattr(match, "warnings", ()))
        render_key_value_card(
            ui,
            labels.get(classification, "Coincidencia a revisar"),
            (
                ("Registro", getattr(match, "entity_id", None)),
                ("Razón del match", evidence or classification),
                ("Notas", warnings),
            ),
        )
    return True


def render_change_cards(
    ui: Any,
    changes: Mapping[str, tuple[object, object]],
    *,
    title: str = "Cambios propuestos",
) -> None:
    """Show only changed fields, with a before/after value in a small card."""
    if not changes:
        _caption(ui, "No hay cambios pendientes.")
        return
    render_section_header(ui, title, "Revisa los valores antes de confirmar el guardado.")
    for label, (before, after) in changes.items():
        render_key_value_card(ui, label, (("Anterior", before), ("Nuevo", after)))


def render_association_cards(ui: Any, associations: Iterable[Mapping[str, object]]) -> None:
    """Show associated Sources as small cards, preserving missing-record evidence."""
    for association in associations:
        render_key_value_card(
            ui,
            "Source asociada",
            (
                ("Nombre", association.get("name")),
                ("Estado", association.get("status")),
            ),
            caption=f"ID: {_value(association.get('source_id'))}",
        )


__all__ = [
    "render_association_cards",
    "render_change_cards",
    "render_duplicate_cards",
    "render_key_value_card",
    "render_reference_summary_card",
    "render_section_header",
    "render_source_summary_card",
]
