"""Explicit session context passed to page composition, without UI side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PageContext:
    """One active connection and its validated catalog and presentation scope."""

    db: Any
    current_db: str | None
    current_database_label: str | None
    catalog_context: Any = None
    catalog_context_error: str | None = None
    active_database_scope: str | None = None
    active_database_name: str | None = None
    active_theme: str = 'light'
    page: str = ''
