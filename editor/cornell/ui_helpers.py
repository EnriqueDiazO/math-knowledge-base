"""Shared UI helpers for Cornell and Diario LaTeX note editing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

NO_PROJECT_LABEL = "(sin proyecto)"
NEW_PROJECT_LABEL = "Escribir proyecto nuevo"
ALL_LABEL = "(all)"
DEFAULT_NOTE_CONTEXTS = ("estudio", "debug", "lectura", "idea", "reflexion")


@dataclass(frozen=True, slots=True)
class LatexSnippet:
    """One insertable LaTeX snippet from the shared Diario toolbar."""

    key: str
    label: str
    snippet: str


@dataclass(frozen=True, slots=True)
class LatexSnippetGroup:
    """A visual group of insertable LaTeX snippets."""

    title: str
    snippets: tuple[LatexSnippet, ...]


LATEX_SNIPPET_GROUPS = (
    LatexSnippetGroup(
        title="Estructura",
        snippets=(
            LatexSnippet("def", "📝 Definición", "\\begin{definition}\n% ...\n\\end{definition}\n"),
            LatexSnippet("theorem", "📋 Teorema", "\\begin{theorem}{Titulo}\n% ...\n\\end{theorem}\n"),
            LatexSnippet("lemma", "📌 Lema", "\\begin{lemma}\n% ...\n\\end{lemma}\n"),
            LatexSnippet("prop", "📌 Proposición", "\\begin{proposition}\n% ...\n\\end{proposition}\n"),
            LatexSnippet("cor", "📋 Corolario", "\\begin{corollary}\n% ...\n\\end{corollary}\n"),
            LatexSnippet("proof", "📖 Prueba", "\\begin{proof}\n% ...\n\\end{proof}\n"),
        ),
    ),
    LatexSnippetGroup(
        title="Matemática",
        snippets=(
            LatexSnippet("ex", "🧪 Ejemplo", "\\begin{example}\n% ...\n\\end{example}\n"),
            LatexSnippet("remark", "🗒️ Nota / Remark", "\\begin{remark}\n% ...\n\\end{remark}\n"),
            LatexSnippet("eq", "🔢 Ecuación", "\\begin{equation}\n% ...\n\\end{equation}\n"),
            LatexSnippet("align", "🔢 Align", "\\begin{align}\n% ...\n\\end{align}\n"),
            LatexSnippet("matrix", "🔢 Matrix", "\\[\n\\begin{pmatrix}\na & b \\\\\nc & d\n\\end{pmatrix}\n\\]\n"),
            LatexSnippet("cases", "🔢 Cases", "\\[\n\\begin{cases}\n% ...\n\\end{cases}\n\\]\n"),
        ),
    ),
    LatexSnippetGroup(
        title="Listas",
        snippets=(
            LatexSnippet("itemize", "• Itemize", "\\begin{itemize}\n  \\item ...\n\\end{itemize}\n"),
            LatexSnippet("enum", "1) Enumerate", "\\begin{enumerate}\n  \\item ...\n\\end{enumerate}\n"),
            LatexSnippet("desc", "≡ Description", "\\begin{description}\n  \\item[Item] ...\n\\end{description}\n"),
            LatexSnippet("code", "💻 Código (lstlisting)", "\\begin{lstlisting}\ncodigo ...\n\\end{lstlisting}\n"),
            LatexSnippet("dirtree", "📁 DirTree", "\\begin{dirtree}\n.1 /ruta.\n.2 archivo.txt.\n\\end{dirtree}\n"),
        ),
    ),
    LatexSnippetGroup(
        title="Símbolos",
        snippets=(
            LatexSnippet("sum", "∑", "\\(\\sum_{i=1}^{n}\\)"),
            LatexSnippet("int", "∫", "\\(\\int_{a}^{b}\\)"),
            LatexSnippet("in", "∈", "\\(\\in\\)"),
            LatexSnippet("forall", "∀", "\\(\\forall\\)"),
            LatexSnippet("R", "ℝ", "\\(\\mathbb{R}\\)"),
            LatexSnippet("exists", "∃", "\\(\\exists\\)"),
            LatexSnippet("to", "→", "\\(\\rightarrow\\)"),
            LatexSnippet("inf", "∞", "\\(\\infty\\)"),
            LatexSnippet("eps", "ε", "\\(\\varepsilon\\)"),
            LatexSnippet("delta", "δ", "\\(\\delta\\)"),
        ),
    ),
    LatexSnippetGroup(
        title="Bloques semánticos del cuaderno",
        snippets=(
            LatexSnippet("context", "context", "\\begin{context}\n...\n\\end{context}\n"),
            LatexSnippet("reading", "reading", "\\begin{reading}\n...\n\\end{reading}\n"),
            LatexSnippet("exploration", "exploration", "\\begin{exploration}\n...\n\\end{exploration}\n"),
            LatexSnippet("hypothesis", "hypothesis", "\\begin{hypothesis}\n...\n\\end{hypothesis}\n"),
            LatexSnippet("connections", "connections", "\\begin{connections}\n...\n\\end{connections}\n"),
            LatexSnippet("reflection", "reflection", "\\begin{reflection}\n...\n\\end{reflection}\n"),
            LatexSnippet("decision", "decision", "\\begin{decision}\n...\n\\end{decision}\n"),
            LatexSnippet("openquestions", "openquestions", "\\begin{openquestions}\n...\n\\end{openquestions}\n"),
            LatexSnippet("technical", "technical", "\\begin{technical}\n...\n\\end{technical}\n"),
            LatexSnippet("nextsteps", "nextsteps", "\\begin{nextsteps}\n...\n\\end{nextsteps}\n"),
        ),
    ),
)


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


def append_latex_snippet(existing: str, snippet: str) -> str:
    """Append a snippet without erasing existing LaTeX content."""
    current = existing or ""
    insert = snippet or ""
    if not insert:
        return current
    if current and not current.endswith("\n"):
        current += "\n"
    return current + insert + ("\n" if not insert.endswith("\n") else "")


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
