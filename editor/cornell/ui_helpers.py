"""Shared UI helpers for Cornell and Diario LaTeX note editing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from datetime import date
from typing import Any

NO_PROJECT_LABEL = "(sin proyecto)"
NEW_PROJECT_LABEL = "Escribir proyecto nuevo"
ALL_LABEL = "(all)"
DEFAULT_NOTE_CONTEXTS = ("estudio", "debug", "lectura", "idea", "reflexion", "capacitación")


def normalize_project_name(project: str) -> str:
    """Normalize project names the same way Diario LaTeX does."""
    return re.sub(r"\s+", " ", (project or "").strip())


def normalize_tags(raw: str) -> list[str]:
    """Parse comma-separated tags without changing the current Cornell storage format."""
    tags = []
    seen = set()
    for part in (raw or "").split(","):
        tag = " ".join(part.split())
        key = tag.lower()
        if tag and key not in seen:
            tags.append(tag)
            seen.add(key)
    return tags


def existing_note_projects_from_values(values: Iterable[Any]) -> list[str]:
    """Return distinct normalized project names from note history values."""
    normalized: dict[str, str] = {}
    for project in values:
        if not isinstance(project, str):
            continue
        clean = normalize_project_name(project)
        if clean:
            normalized.setdefault(clean.lower(), clean)
    return sorted(normalized.values(), key=str.lower)


def existing_note_contexts_from_values(values: Iterable[Any]) -> list[str]:
    """Merge Diario context defaults with values found in note history."""
    found = [value for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys([*DEFAULT_NOTE_CONTEXTS, *sorted(found, key=str.lower)]))


def get_existing_note_projects(source: Any) -> list[str]:
    """Read project history from MathMongo or a latex_notes collection."""
    try:
        if hasattr(source, "get_notebook_projects"):
            return existing_note_projects_from_values(source.get_notebook_projects())
        return existing_note_projects_from_values(source.distinct("project"))
    except Exception:
        return []


def get_existing_note_contexts(source: Any) -> list[str]:
    """Read contexts from MathMongo or a latex_notes collection with Diario defaults."""
    try:
        if hasattr(source, "get_notebook_contexts"):
            values = source.get_notebook_contexts()
        else:
            values = source.distinct("context")
    except Exception:
        values = []
    return existing_note_contexts_from_values(values)


def project_selector_choices(projects: Iterable[str], current_project: str = "") -> tuple[list[str], int]:
    """Build Diario-compatible project choices and default index."""
    clean_current = normalize_project_name(current_project)
    history = existing_note_projects_from_values(projects)
    choices = [NO_PROJECT_LABEL, NEW_PROJECT_LABEL, *history]
    if not clean_current:
        return choices, 0
    matches = [project for project in history if project.lower() == clean_current.lower()]
    if matches:
        return choices, choices.index(matches[0])
    return choices, 1


def resolve_project_choice(choice: str, new_project: str = "") -> str:
    """Resolve the final project value saved by the UI."""
    if choice == NO_PROJECT_LABEL:
        return ""
    if choice == NEW_PROJECT_LABEL:
        return normalize_project_name(new_project)
    return normalize_project_name(choice)


def note_page_count(note: Mapping[str, Any]) -> int:
    """Return the page count for a persisted Cornell note dict."""
    pages = ((note.get("cornell") or {}).get("pages") or []) if isinstance(note, Mapping) else []
    return len(pages)


def filter_cornell_notes_for_explorer(
    notes: Iterable[Mapping[str, Any]],
    *,
    text: str = "",
    project: str = ALL_LABEL,
    context: str = ALL_LABEL,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Mapping[str, Any]]:
    """Filter Cornell notes for the local Streamlit explorer."""
    text_q = (text or "").strip().lower()
    filtered = []
    for note in notes:
        if note.get("note_format") != "cornell_math_v1":
            continue
        note_project = normalize_project_name(str(note.get("project") or ""))
        if project not in (ALL_LABEL, None):
            if project == NO_PROJECT_LABEL and note_project:
                continue
            if project != NO_PROJECT_LABEL and note_project != normalize_project_name(project):
                continue
        if context != ALL_LABEL and (note.get("context") or "") != context:
            continue
        note_date = str(note.get("date") or "")
        if start_date and note_date < start_date.strftime("%Y-%m-%d"):
            continue
        if end_date and note_date > end_date.strftime("%Y-%m-%d"):
            continue
        if text_q:
            haystack = "\n".join(
                [
                    str(note.get("title") or ""),
                    str(note.get("latex_body") or ""),
                    str(note.get("project") or ""),
                    str(note.get("context") or ""),
                ]
            ).lower()
            if text_q not in haystack:
                continue
        filtered.append(note)
    return filtered
