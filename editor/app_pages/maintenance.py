"""Maintenance; extracted without import-time rendering."""

from __future__ import annotations

from editor.maintenance_page import _render_cleanup_maintenance_page


def render(context):
    """Render only the selected page using its explicit application context."""
    _render_cleanup_maintenance_page()

# Settings page
