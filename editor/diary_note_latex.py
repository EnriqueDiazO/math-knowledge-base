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
_DIARY_TIKZ_LIBRARIES = (
    "arrows.meta",
    "positioning",
    "calc",
    "fit",
    "backgrounds",
    "shapes.geometric",
    "shapes.multipart",
    "matrix",
    "shadows",
)
_DIARY_COMPATIBILITY_BOXES = {
    "learningobjectives": r"""\ProvideTColorBox{learningobjectives}{}{
  notesbase,
  title=Objetivos de aprendizaje,
  colback=DIlightgreen,
  colframe=DIgreen
}""",
    "precisionbox": r"""\ProvideTColorBox{precisionbox}{O{}}{
  notesbase,
  title=Precisión técnica,
  colback=DIlightorange,
  colframe=DIorange,
  #1
}""",
    "commonerror": r"""\ProvideTColorBox{commonerror}{O{}}{
  notesbase,
  title=Error frecuente,
  colback=DIlightred,
  colframe=DIred,
  #1
}""",
    "designchoice": r"""\ProvideTColorBox{designchoice}{O{}}{
  notesbase,
  title=Decisión de diseño,
  colback=teal!5,
  colframe=DIteal,
  #1
}""",
    "answerbox": r"""\ProvideTColorBox{answerbox}{O{}}{
  notesbase,
  title=Respuesta integradora,
  colback=blue!3,
  colframe=DIblue,
  #1
}""",
    "checkpoint": r"""\ProvideTColorBox{checkpoint}{O{}}{
  notesbase,
  title=Punto de comprobación,
  colback=DIlightpurple,
  colframe=DIpurple,
  #1
}""",
}


@dataclass(frozen=True, slots=True)
class DiaryLatexFragments:
    """All generated fragments consumed by the existing Diario TEX builder."""

    preamble: str
    metadata_lines: tuple[str, ...]
    toc_after_title: str
    toc_after_metadata: str
    lists_after_metadata: str
    first_page_style: str
    bibliography: str
    warnings: tuple[str, ...]


def latex_escape_text(value: object) -> str:
    """Escape an ordinary text value while preserving Unicode for pdfLaTeX."""
    return "".join(_LATEX_TEXT_ESCAPES.get(character, character) for character in str(value or ""))


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _latex_command_defined(body: str, name: str) -> bool:
    escaped_name = re.escape(name)
    return bool(
        re.search(
            rf"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*"
            rf"(?:\{{\\{escaped_name}\}}|\\{escaped_name}(?![A-Za-z@]))",
            body,
        )
    )


def _latex_environment_defined(body: str, name: str) -> bool:
    commands = (
        "newtcolorbox",
        "renewtcolorbox",
        "NewTColorBox",
        "RenewTColorBox",
        "ProvideTColorBox",
        "DeclareTColorBox",
        "newenvironment",
        "renewenvironment",
        "provideenvironment",
    )
    return bool(
        re.search(
            rf"\\(?:{'|'.join(commands)})\s*\{{{re.escape(name)}\}}",
            body,
        )
    )


def _diary_body_compatibility_preamble(body: str) -> str:
    """Supply known, inert preamble features only when the note body needs them."""
    if not body:
        return ""

    fragments: list[str] = []
    if r"\setlist" in body or re.search(
        r"\\begin\s*\{(?:enumerate|itemize|description)\}\s*\[",
        body,
    ):
        fragments.append(r"\usepackage{enumitem}")
    if re.search(r"\\begin\s*\{(?:table|figure)\}\s*\[[^]]*H", body):
        fragments.append(r"\usepackage{float}")
    if re.search(r"\\begin\s*\{tikzpicture\}", body):
        fragments.append(
            r"\usetikzlibrary{" + ",".join(_DIARY_TIKZ_LIBRARIES) + "}"
        )
        # Spanish babel activates ``"``, ``<`` and ``>``. TikZ usually protects
        # its own parser, but a picture captured first by commands such as
        # ``\resizebox`` still sees the active shorthand tokens. Literal quotes
        # are also common in JSON, R and Python fragments embedded in nodes.
        fragments.append(r'\AtBeginDocument{\shorthandoff{"<>}}')

    for name, definition in (
        ("code", r"\providecommand{\code}[1]{\texttt{#1}}"),
        ("concept", r"\providecommand{\concept}[1]{\textbf{\textcolor{DIblue}{#1}}}"),
    ):
        if re.search(rf"\\{name}(?![A-Za-z@])", body) and not _latex_command_defined(
            body, name
        ):
            fragments.append(definition)

    for name, definition in _DIARY_COMPATIBILITY_BOXES.items():
        if re.search(
            rf"\\begin\s*\{{{re.escape(name)}\}}",
            body,
        ) and not _latex_environment_defined(body, name):
            fragments.append(definition)

    return "\n".join(fragments)


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


def _native_list(
    *,
    show: bool,
    title: str,
    title_command: str,
    list_command: str,
    page_layout_enabled: bool,
) -> str:
    """Render one native LaTeX auxiliary list on clean page boundaries."""
    if not show:
        return ""
    lines = [
        r"\clearpage",
        rf"\renewcommand{{\{title_command}}}{{{latex_escape_text(title)}}}",
        rf"\{list_command}",
    ]
    if page_layout_enabled:
        lines.append(r"\thispagestyle{mathmongonote}")
    lines.append(r"\clearpage")
    return "\n".join(lines)


def _native_lists(settings: DiaryNoteSettings) -> str:
    """Render enabled figure/table lists independently in document order."""
    figures = settings.list_of_figures
    tables = settings.list_of_tables
    return "\n".join(
        fragment
        for fragment in (
            _native_list(
                show=figures.show_list_of_figures,
                title=figures.title,
                title_command="listfigurename",
                list_command="listoffigures",
                page_layout_enabled=settings.page_layout.enabled,
            ),
            _native_list(
                show=tables.show_list_of_tables,
                title=tables.title,
                title_command="listtablename",
                list_command="listoftables",
                page_layout_enabled=settings.page_layout.enabled,
            ),
        )
        if fragment
    )


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
    compatibility_preamble = _diary_body_compatibility_preamble(
        str(note.get("latex_body") or "")
    )
    preamble = "\n".join(
        item
        for item in (_pdf_metadata(note, settings), compatibility_preamble, page_preamble)
        if item
    )
    warnings = tuple(dict.fromkeys((*settings_warnings(settings), *page_warnings)))
    toc = _toc(settings, report_class=report_class)
    toc_after_title = toc if settings.table_of_contents.position == TocPosition.AFTER_TITLE else ""
    toc_after_metadata = (
        toc if settings.table_of_contents.position == TocPosition.AFTER_METADATA else ""
    )
    lists_after_metadata = _native_lists(settings)
    return DiaryLatexFragments(
        preamble=preamble,
        metadata_lines=_metadata_lines(note, settings),
        toc_after_title=toc_after_title,
        toc_after_metadata=toc_after_metadata,
        lists_after_metadata=lists_after_metadata,
        first_page_style=_first_page_command(settings),
        bibliography=_bibliography(settings, report_class=report_class),
        warnings=warnings,
    )


__all__ = ["DiaryLatexFragments", "build_diary_latex_fragments", "latex_escape_text"]
