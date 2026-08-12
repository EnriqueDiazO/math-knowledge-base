"""Safe LaTeX fragments for structured free-form Diario note settings."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import FirstPageStyle
from editor.diary_note_models import NoteReference
from editor.diary_note_models import NoteReferenceKind
from editor.diary_note_models import TocPosition
from editor.diary_note_models import resolve_tokens
from editor.diary_note_models import settings_from_note
from editor.diary_note_models import settings_warnings
from editor.diary_note_models import token_values

_LATEX_TEXT_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_PAGE_SENTINEL = "\ue000"
_SLOTS = (
    "header_left",
    "header_center",
    "header_right",
    "footer_left",
    "footer_center",
    "footer_right",
)
_FANCY_COMMANDS = {
    "header_left": "fancyhead[L]",
    "header_center": "fancyhead[C]",
    "header_right": "fancyhead[R]",
    "footer_left": "fancyfoot[L]",
    "footer_center": "fancyfoot[C]",
    "footer_right": "fancyfoot[R]",
}


@dataclass(frozen=True, slots=True)
class DiaryLatexFragments:
    """All generated fragments consumed by the existing Diario TEX builder."""

    preamble: str
    metadata_lines: tuple[str, ...]
    toc_after_title: str
    toc_after_metadata: str
    first_page_style: str
    bibliography: str
    warnings: tuple[str, ...]


def latex_escape_text(value: object) -> str:
    """Escape an ordinary text value while preserving Unicode for pdfLaTeX."""
    return "".join(_LATEX_TEXT_ESCAPES.get(character, character) for character in str(value or ""))


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _pdf_metadata(note: Mapping[str, Any], settings: DiaryNoteSettings) -> str:
    metadata = settings.academic_metadata
    tags = note.get("tags") or []
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",") if item.strip()]
    keywords = metadata.pdf_keywords or [str(item) for item in tags if str(item).strip()]
    subject = (
        metadata.pdf_subject or metadata.topic or metadata.course_name or note.get("context") or ""
    )
    values = {
        "pdftitle": note.get("title") or "Nota sin título",
        "pdfauthor": metadata.author,
        "pdfsubject": subject,
        "pdfkeywords": ", ".join(keywords),
    }
    lines = [r"\hypersetup{unicode=true,"]
    for index, (key, value) in enumerate(values.items()):
        suffix = "," if index < len(values) - 1 else ""
        lines.append(f"  {key}={{{latex_escape_text(value)}}}{suffix}")
    lines.append("}")
    return "\n".join(lines)


def _page_box(text: str, *, alignment: str) -> str:
    alignment_command = {
        "left": r"\raggedright",
        "center": r"\centering",
        "right": r"\raggedleft",
    }[alignment]
    return r"\parbox[b]{0.30\headwidth}{" + alignment_command + r"\scriptsize\sloppy " + text + "}"


def _resolved_page_slots(
    note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> tuple[dict[str, str], tuple[str, ...]]:
    layout = settings.page_layout
    values = token_values(note, settings)
    resolved: dict[str, str] = {}
    warnings: list[str] = []
    page_emitted = False
    for slot in _SLOTS:
        template = getattr(layout, slot)
        includes_page = "{page}" in template
        allow_page = layout.show_page_number and includes_page and not page_emitted
        if allow_page:
            template = template.replace("{page}", _PAGE_SENTINEL, 1)
        text, token_warnings = resolve_tokens(template, values, page_value="")
        escaped = latex_escape_text(text).replace(_PAGE_SENTINEL, r"\thepage")
        resolved[slot] = escaped
        warnings.extend(token_warnings)
        page_emitted = page_emitted or allow_page
    if layout.show_page_number and not page_emitted:
        target = layout.page_number_position.value
        resolved[target] = r"\enspace ".join(
            item for item in (resolved[target], r"\thepage") if item
        )
    return resolved, tuple(dict.fromkeys(warnings))


def _fancy_style_body(slots: Mapping[str, str]) -> list[str]:
    lines = [r"\fancyhf{}"]
    for slot in _SLOTS:
        text = slots.get(slot) or ""
        if not text:
            continue
        alignment = (
            "left" if slot.endswith("left") else "right" if slot.endswith("right") else "center"
        )
        lines.append(rf"\{_FANCY_COMMANDS[slot]}{{{_page_box(text, alignment=alignment)}}}")
    lines.extend(
        (
            r"\renewcommand{\headrulewidth}{0.4pt}",
            r"\renewcommand{\footrulewidth}{0pt}",
        )
    )
    return lines


def _page_layout_preamble(
    note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> tuple[str, tuple[str, ...]]:
    if not settings.page_layout.enabled:
        return "", ()
    slots, warnings = _resolved_page_slots(note, settings)
    style_body = _fancy_style_body(slots)
    first_plain: list[str] = [r"\fancyhf{}"]
    if settings.page_layout.show_page_number:
        first_plain.append(r"\fancyfoot[C]{\thepage}")
    first_plain.extend(
        (
            r"\renewcommand{\headrulewidth}{0pt}",
            r"\renewcommand{\footrulewidth}{0pt}",
        )
    )
    lines = [
        r"\usepackage{fancyhdr}",
        r"\setlength{\headheight}{36pt}",
        r"\fancypagestyle{mathmongonote}{%",
        *(f"  {line}" for line in style_body),
        "}",
        # Chapter openings must retain configured furniture.  The title page is
        # overridden separately according to first_page_style.
        r"\fancypagestyle{plain}{%",
        *(f"  {line}" for line in style_body),
        "}",
        r"\fancypagestyle{mathmongofirstplain}{%",
        *(f"  {line}" for line in first_plain),
        "}",
        r"\pagestyle{mathmongonote}",
    ]
    return "\n".join(lines), warnings


def _first_page_command(settings: DiaryNoteSettings) -> str:
    if not settings.page_layout.enabled:
        return ""
    style = settings.page_layout.first_page_style
    if style == FirstPageStyle.EMPTY:
        return r"\thispagestyle{empty}"
    if style == FirstPageStyle.PLAIN:
        return r"\thispagestyle{mathmongofirstplain}"
    return r"\thispagestyle{mathmongonote}"


def _metadata_lines(note: Mapping[str, Any], settings: DiaryNoteSettings) -> tuple[str, ...]:
    metadata = settings.academic_metadata
    course = " · ".join(item for item in (metadata.course_code, metadata.course_name) if item)
    tags = note.get("tags") or []
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",") if item.strip()]
    fields = (
        ("Institución", metadata.institution),
        ("Programa", metadata.program),
        ("Asignatura", course),
        ("Semana", metadata.week),
        ("Sesión", metadata.session),
        ("Tema", metadata.topic),
        ("Objetivo", metadata.objective),
        ("Actividad", metadata.linked_activity),
        ("Fecha", note.get("date")),
        ("Autoría", metadata.author),
        ("Versión", metadata.version),
        ("Idioma", metadata.language),
        ("Proyecto", note.get("project")),
        ("Contexto", note.get("context")),
        ("Tags", ", ".join(str(item) for item in tags)),
    )
    return tuple(
        rf"\noindent\textbf{{{latex_escape_text(label)}:}} {latex_escape_text(_clean(value))}\par"
        for label, value in fields
        if _clean(value)
    )


def _toc(settings: DiaryNoteSettings, *, report_class: bool) -> str:
    toc = settings.table_of_contents
    if not toc.show_table_of_contents:
        return ""
    depth = toc.toc_depth if report_class else min(toc.toc_depth + 1, 3)
    lines = [
        r"\clearpage",
        rf"\setcounter{{tocdepth}}{{{depth}}}",
        rf"\renewcommand{{\contentsname}}{{{latex_escape_text(toc.toc_title)}}}",
        r"\tableofcontents",
    ]
    if settings.page_layout.enabled:
        lines.append(r"\thispagestyle{mathmongonote}")
    lines.append(r"\clearpage")
    return "\n".join(lines)


def _citation_key(reference: NoteReference, used: set[str]) -> str:
    source = reference.citation_key or reference.reference_id
    ascii_value = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9:._-]+", "_", ascii_value).strip("._-") or "reference"
    candidate = base
    suffix = 2
    while candidate.casefold() in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _safe_url(value: str) -> str:
    compact = re.sub(r"[\x00-\x20\x7f]+", "", value)
    return quote(compact, safe=":/?&=#%._~+-")


def _reference_text(reference: NoteReference) -> str:
    parts: list[str] = []
    if reference.authors:
        parts.append(latex_escape_text(reference.authors) + ".")
    title = r"\emph{" + latex_escape_text(reference.title) + "}."
    if reference.kind == NoteReferenceKind.CHAPTER:
        title = "«" + latex_escape_text(reference.title) + "»."
    elif reference.kind == NoteReferenceKind.ARTICLE:
        title = "«" + latex_escape_text(reference.title) + "»."
    elif reference.kind == NoteReferenceKind.THESIS:
        title += " [Tesis]."
    elif reference.kind == NoteReferenceKind.DATASET:
        title += " [Conjunto de datos]."
    elif reference.kind == NoteReferenceKind.SOFTWARE:
        title += " [Software]."
    elif reference.kind == NoteReferenceKind.DOCUMENTATION:
        title += " [Documentación]."
    elif reference.kind == NoteReferenceKind.INSTITUTIONAL:
        title += " [Material institucional]."
    parts.append(title)
    if reference.container_title:
        prefix = "En: " if reference.kind == NoteReferenceKind.CHAPTER else ""
        parts.append(prefix + latex_escape_text(reference.container_title) + ".")
    publication = ", ".join(item for item in (reference.publisher, reference.year_or_date) if item)
    if publication:
        parts.append(latex_escape_text(publication) + ".")
    detail_parts = []
    if reference.edition:
        detail_parts.append(f"edición {reference.edition}")
    if reference.volume:
        detail_parts.append(f"vol. {reference.volume}")
    if reference.number:
        detail_parts.append(f"núm. {reference.number}")
    if reference.pages:
        detail_parts.append(f"pp. {reference.pages}")
    if detail_parts:
        parts.append(latex_escape_text(", ".join(detail_parts)) + ".")
    if reference.doi:
        doi = re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
            "",
            reference.doi,
            flags=re.IGNORECASE,
        )
        parts.append(r"DOI: \url{" + _safe_url(f"https://doi.org/{doi}") + "}.")
    if reference.url:
        parts.append(r"URL: \url{" + _safe_url(reference.url) + "}.")
    if reference.accessed_date:
        parts.append("Consultado: " + latex_escape_text(reference.accessed_date) + ".")
    return " ".join(parts)


def _bibliography(settings: DiaryNoteSettings, *, report_class: bool) -> str:
    references = [reference for reference in settings.references if reference.exportable]
    if not references:
        return ""
    heading_command = "bibname" if report_class else "refname"
    toc_level = "chapter" if report_class else "section"
    lines = [
        r"\clearpage",
        rf"\renewcommand{{\{heading_command}}}{{Referencias}}",
        r"\phantomsection",
        rf"\addcontentsline{{toc}}{{{toc_level}}}{{Referencias}}",
        r"\begin{thebibliography}{99}",
    ]
    if settings.page_layout.enabled:
        lines.append(r"\thispagestyle{mathmongonote}")
    used: set[str] = set()
    for reference in references:
        lines.extend(
            (
                rf"\bibitem{{{_citation_key(reference, used)}}}",
                _reference_text(reference),
            )
        )
    lines.append(r"\end{thebibliography}")
    return "\n".join(lines)


def build_diary_latex_fragments(
    note: Mapping[str, Any],
    *,
    report_class: bool,
) -> DiaryLatexFragments:
    """Build all structured additions without mutating or persisting the note."""
    settings = settings_from_note(note)
    page_preamble, page_warnings = _page_layout_preamble(note, settings)
    preamble = "\n".join(item for item in (_pdf_metadata(note, settings), page_preamble) if item)
    warnings = tuple(dict.fromkeys((*settings_warnings(settings), *page_warnings)))
    toc = _toc(settings, report_class=report_class)
    toc_after_title = toc if settings.table_of_contents.position == TocPosition.AFTER_TITLE else ""
    toc_after_metadata = (
        toc if settings.table_of_contents.position == TocPosition.AFTER_METADATA else ""
    )
    return DiaryLatexFragments(
        preamble=preamble,
        metadata_lines=_metadata_lines(note, settings),
        toc_after_title=toc_after_title,
        toc_after_metadata=toc_after_metadata,
        first_page_style=_first_page_command(settings),
        bibliography=_bibliography(settings, report_class=report_class),
        warnings=warnings,
    )


__all__ = ["DiaryLatexFragments", "build_diary_latex_fragments", "latex_escape_text"]
