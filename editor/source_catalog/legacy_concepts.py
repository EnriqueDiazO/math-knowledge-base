"""Read-only Streamlit presentation for exactly associated legacy concepts."""

from __future__ import annotations

from typing import Any

from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.state import queue_legacy_concept_open
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.legacy_repository import LegacyConceptPage
from mathmongo.source_catalog.legacy_repository import LegacyConceptRepository
from mathmongo.source_catalog.models import Source

REFERENCE_FILTERS = {
    "All": None,
    "With reference": True,
    "Without reference": False,
}


def legacy_table_rows(page: LegacyConceptPage) -> list[dict[str, Any]]:
    """Convert projected summaries to bounded table rows without raw bodies."""
    return [
        {
            "id": item.id,
            "title": item.title,
            "type": item.type,
            "categories": ", ".join(item.categories),
            "reference": "yes" if item.has_reference else "no",
            "pages": item.pages or "",
            "chapter": item.chapter or "",
            "section": item.section or "",
            "updated_at": item.updated_at,
            "source": item.source,
        }
        for item in page.items
    ]


def render_legacy_concepts(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
) -> LegacyConceptPage | None:
    """Render exact, paginated legacy metadata and never mutate concepts."""
    ui.subheader("Concepts — Legacy Read Only")
    ui.info(
        "Sólo lectura. Se consultan coincidencias exactas con Source.name y "
        "legacy.source_strings; no se usa similitud ni se modifica id@source."
    )
    repository = LegacyConceptRepository(context.database)
    prefix = source.source_id
    try:
        type_options = ["All", *repository.list_types(source)]
        columns = ui.columns(3)
        with columns[0]:
            concept_type = ui.selectbox(
                "Type",
                type_options,
                key=state_key("legacy_type", prefix),
            )
        with columns[1]:
            reference_label = ui.selectbox(
                "Reference",
                list(REFERENCE_FILTERS),
                key=state_key("legacy_reference_filter", prefix),
            )
        with columns[2]:
            search = ui.text_input(
                "Search legacy metadata",
                key=state_key("legacy_search", prefix),
            )
        page_number = int(
            ui.number_input(
                "Legacy page",
                min_value=1,
                value=1,
                step=1,
                key=state_key("legacy_page", prefix),
            )
        )
        page = repository.list(
            source,
            page=page_number,
            page_size=25,
            concept_type=None if concept_type == "All" else concept_type,
            has_reference=REFERENCE_FILTERS[reference_label],
            search=search,
        )
    except Exception as exc:
        ui.error(f"Database error reading legacy concepts: {safe_error_message(exc)}")
        return None

    ui.caption(
        f"{page.total} conceptos exactos · página {page.page} de {max(page.pages, 1)} · "
        f"valores: {', '.join(page.exact_source_values)}"
    )
    ui.dataframe(legacy_table_rows(page), use_container_width=True, hide_index=True)
    for item in page.items:
        if ui.button(
            f"Open concept {item.id}",
            key=state_key("legacy_open", source.source_id, item.source, item.id),
        ):
            queue_legacy_concept_open(
                ui.session_state,
                concept_id=item.id,
                source=item.source,
            )
            ui.rerun()
    return page


__all__ = [
    "REFERENCE_FILTERS",
    "legacy_table_rows",
    "render_legacy_concepts",
]
