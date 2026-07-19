"""Read-only helpers for selecting managed Sources in Add Concept."""

from __future__ import annotations

from collections import Counter

from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.repository import SourceRepository

PAGE_SIZE = 100


def load_active_sources(repository: SourceRepository) -> tuple[Source, ...]:
    """Load every active Source through the bounded catalog repository API."""
    page_number = 1
    sources: list[Source] = []
    while True:
        page = repository.list(
            page=page_number,
            page_size=PAGE_SIZE,
            status=SourceStatus.ACTIVE.value,
        )
        sources.extend(
            source for source in page.items if source.status == SourceStatus.ACTIVE
        )
        if page_number >= page.pages:
            break
        page_number += 1
    return tuple(sorted(sources, key=lambda source: (source.name.casefold(), source.source_id)))


def _short_source_id(source_id: str) -> str:
    value = source_id.removeprefix("src_")
    return f"{value[:8]}…{value[-8:]}"


def source_labels(sources: tuple[Source, ...]) -> dict[str, str]:
    """Build labels keyed by stable ID and disambiguate duplicate names."""
    name_counts = Counter(source.name.casefold() for source in sources)
    labels: dict[str, str] = {}
    for source in sources:
        label = source.name
        if name_counts[source.name.casefold()] > 1:
            label = (
                f"{source.name} · {source.source_type.value} · "
                f"{_short_source_id(source.source_id)}"
            )
        labels[source.source_id] = label
    return labels


def resolve_active_source(
    repository: SourceRepository,
    source_id: str | None,
) -> Source | None:
    """Rehydrate a selected ID and reject missing or archived Sources."""
    if not source_id:
        return None
    source = repository.get_by_id(source_id)
    if source is None or source.status != SourceStatus.ACTIVE:
        return None
    return source


def can_save_with_managed_source(source: Source | None) -> bool:
    """Return whether a valid active Source can back a new concept."""
    return bool(
        source is not None
        and source.status == SourceStatus.ACTIVE
        and source.source_id
        and source.name
    )
