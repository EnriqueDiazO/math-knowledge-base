"""Pure, bounded BibTeX parsing for Source catalog previews.

This module deliberately knows nothing about MongoDB, Streamlit, or the
catalog's Pydantic models.  It turns pasted text or already-read ``.bib``
content into candidate dictionaries that can subsequently be passed to
``Reference.model_validate``.  Parsing never persists a candidate.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser

MAX_BIBTEX_TEXT_CHARS = 4_000_000
MAX_BIBTEX_ENTRIES = 1_000
MAX_BIBTEX_ENTRY_CHARS = 500_000
MAX_BIBTEX_FIELD_CHARS = 100_000
MAX_BIBTEX_EXTRA_FIELDS = 32
MAX_BIBTEX_EXTRA_VALUE_CHARS = 4_096
MAX_BIBTEX_EXTRA_TOTAL_CHARS = 16_384

_CONTROL_DIRECTIVES = frozenset({"comment", "preamble", "string"})
_IMPORT_METHODS = frozenset({"manual", "bibtex_paste", "bib_file", "legacy"})
_ENTRY_TYPE_TO_REFERENCE_TYPE = {
    "article": "article",
    "book": "book",
    "booklet": "book",
    "conference": "proceedings",
    "course": "course",
    "electronic": "web",
    "inbook": "chapter",
    "incollection": "chapter",
    "inproceedings": "proceedings",
    "manual": "book",
    "mastersthesis": "thesis",
    "misc": "misc",
    "online": "web",
    "phdthesis": "thesis",
    "proceedings": "proceedings",
    "report": "report",
    "techreport": "report",
    "thesis": "thesis",
    "unpublished": "other",
    "web": "web",
    "www": "web",
}
_YEAR_RE = re.compile(r"^[+-]?\d{1,4}$")


@dataclass(frozen=True, slots=True)
class BibTeXParseResult:
    """Immutable top-level result for a paste or already-read file."""

    candidates: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    ignored_directives: tuple[str, ...] = ()

    @property
    def has_errors(self) -> bool:
        """Return whether any document-level or per-entry error occurred."""
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        """Return a detached, JSON-friendly representation for a UI preview."""
        return {
            "candidates": copy.deepcopy(list(self.candidates)),
            "errors": copy.deepcopy(list(self.errors)),
            "ignored_directives": list(self.ignored_directives),
        }


@dataclass(frozen=True, slots=True)
class _ScannedBlock:
    directive: str
    raw: str
    error_code: str | None = None
    error_message: str | None = None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _entry_error(
    *,
    entry_index: int | None,
    code: str,
    message: str,
    raw: str | None = None,
    entry_type: str | None = None,
    citekey: str | None = None,
) -> dict[str, Any]:
    return {
        "entry_index": entry_index,
        "code": code,
        "message": message,
        "entry_type": entry_type,
        "citekey": citekey,
        "raw": raw,
        "raw_sha256": _sha256_text(raw) if raw is not None else None,
    }


def _next_line_end(text: str, start: int) -> int:
    end = text.find("\n", start)
    return len(text) if end < 0 else end


def _scan_bibtex_blocks(text: str) -> tuple[list[_ScannedBlock], list[dict[str, Any]]]:
    """Delimit top-level ``@type{...}``/``@type(...)`` blocks without I/O."""
    blocks: list[_ScannedBlock] = []
    errors: list[dict[str, Any]] = []
    length = len(text)
    cursor = 0

    while cursor < length:
        character = text[cursor]
        if character.isspace() or (cursor == 0 and character == "\ufeff"):
            cursor += 1
            continue
        if character == "%":
            cursor = _next_line_end(text, cursor) + 1
            continue
        if character != "@":
            start = cursor
            while cursor < length and text[cursor] not in "@\n":
                cursor += 1
            unexpected = text[start:cursor].strip()
            if unexpected:
                errors.append(
                    _entry_error(
                        entry_index=None,
                        code="unexpected_text",
                        message="Unexpected text outside a BibTeX entry.",
                        raw=text[start:cursor],
                    )
                )
            continue

        start = cursor
        cursor += 1
        while cursor < length and text[cursor].isspace():
            cursor += 1
        directive_start = cursor
        while cursor < length and (text[cursor].isalnum() or text[cursor] in "_:-"):
            cursor += 1
        directive = text[directive_start:cursor]
        if not directive:
            end = _next_line_end(text, start)
            blocks.append(
                _ScannedBlock(
                    directive="",
                    raw=text[start:end],
                    error_code="missing_entry_type",
                    error_message="BibTeX entry type is missing after '@'.",
                )
            )
            cursor = end
            continue

        while cursor < length and text[cursor].isspace():
            cursor += 1
        if cursor >= length or text[cursor] not in "{(":
            end = _next_line_end(text, start)
            if directive.casefold() == "comment":
                blocks.append(_ScannedBlock(directive=directive, raw=text[start:end]))
            else:
                blocks.append(
                    _ScannedBlock(
                        directive=directive,
                        raw=text[start:end],
                        error_code="missing_opening_delimiter",
                        error_message=(
                            "BibTeX entry must use an opening '{' or '(' delimiter."
                        ),
                    )
                )
            cursor = end
            continue

        opening = text[cursor]
        stack = ["}" if opening == "{" else ")"]
        cursor += 1
        quoted = False
        escaped = False
        line_comment = False
        end: int | None = None

        while cursor < length:
            character = text[cursor]
            if line_comment:
                if character in "\r\n":
                    line_comment = False
                cursor += 1
                continue
            if escaped:
                escaped = False
                cursor += 1
                continue
            if character == "\\":
                escaped = True
                cursor += 1
                continue
            if character == '"':
                quoted = not quoted
                cursor += 1
                continue
            if quoted:
                cursor += 1
                continue
            if character == "%":
                line_comment = True
                cursor += 1
                continue
            if character == "{":
                stack.append("}")
                cursor += 1
                continue
            if character == "(" and stack[-1] == ")":
                stack.append(")")
                cursor += 1
                continue
            if character == stack[-1]:
                stack.pop()
                cursor += 1
                if not stack:
                    end = cursor
                    break
                continue
            cursor += 1

        if end is None:
            blocks.append(
                _ScannedBlock(
                    directive=directive,
                    raw=text[start:],
                    error_code="unclosed_entry",
                    error_message=(
                        f"BibTeX entry @{directive} has no matching closing delimiter."
                    ),
                )
            )
            break
        blocks.append(_ScannedBlock(directive=directive, raw=text[start:end]))

    return blocks, errors


def _new_parser() -> BibTexParser:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    parser.homogenize_fields = False
    return parser


def _parse_one_entry(raw: str, string_definitions: list[str]) -> dict[str, Any]:
    context = "\n".join((*string_definitions, raw))
    database = bibtexparser.loads(context, parser=_new_parser())
    if len(database.entries) != 1:
        raise ValueError(
            "The delimited BibTeX block did not produce exactly one bibliographic entry."
        )
    return dict(database.entries[0])


def _outer_brace_group(value: str) -> str | None:
    """Return one complete outer brace group's contents, otherwise ``None``."""
    if len(value) < 2 or value[0] != "{" or value[-1] != "}":
        return None
    depth = 0
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and index != len(value) - 1:
                return None
            if depth < 0:
                return None
    return value[1:-1].strip() if depth == 0 else None


def _split_top_level_authors(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    cursor = 0
    depth = 0
    quoted = False
    escaped = False
    while cursor < len(value):
        character = value[cursor]
        if escaped:
            escaped = False
            cursor += 1
            continue
        if character == "\\":
            escaped = True
            cursor += 1
            continue
        if character == '"':
            quoted = not quoted
            cursor += 1
            continue
        if not quoted:
            if character == "{":
                depth += 1
            elif character == "}" and depth:
                depth -= 1
            elif (
                depth == 0
                and value[cursor : cursor + 3].casefold() == "and"
                and (cursor == 0 or value[cursor - 1].isspace())
                and (cursor + 3 == len(value) or value[cursor + 3].isspace())
            ):
                part = value[start:cursor].strip()
                if part:
                    parts.append(part)
                cursor += 3
                start = cursor
                continue
        cursor += 1
    final = value[start:].strip()
    if final:
        parts.append(final)
    return parts


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def _clean_name_part(value: str) -> str:
    value = value.strip()
    outer = _outer_brace_group(value)
    return outer if outer is not None else value


def parse_bibtex_authors(value: str | None) -> list[dict[str, str | None]]:
    """Convert BibTeX authors while retaining explicitly literal names."""
    if not value or not value.strip():
        return []
    authors: list[dict[str, str | None]] = []
    for raw_author in _split_top_level_authors(value.strip()):
        literal = _outer_brace_group(raw_author)
        if literal is not None or raw_author.casefold() == "others":
            authors.append(
                {
                    "family": None,
                    "given": None,
                    "literal": literal if literal is not None else raw_author,
                    "orcid": None,
                }
            )
            continue

        comma_parts = _split_top_level_commas(raw_author)
        if len(comma_parts) == 2 and all(comma_parts):
            family = _clean_name_part(comma_parts[0])
            given = _clean_name_part(comma_parts[1])
        elif len(comma_parts) > 2:
            authors.append(
                {
                    "family": None,
                    "given": None,
                    "literal": raw_author,
                    "orcid": None,
                }
            )
            continue
        else:
            tokens = raw_author.split()
            if len(tokens) < 2:
                authors.append(
                    {
                        "family": None,
                        "given": None,
                        "literal": raw_author,
                        "orcid": None,
                    }
                )
                continue
            particle_index = next(
                (
                    index
                    for index, token in enumerate(tokens[1:-1], start=1)
                    if token[:1].islower()
                ),
                len(tokens) - 1,
            )
            family = " ".join(tokens[particle_index:])
            given = " ".join(tokens[:particle_index])

        authors.append(
            {
                "family": family or None,
                "given": given or None,
                "literal": None,
                "orcid": None,
            }
        )
    return authors


def _selected_text_field(
    entry: dict[str, Any],
    consumed_fields: set[str],
    *names: str,
) -> str | None:
    """Select the first populated alias and preserve unused aliases in extra."""
    for name in names:
        value = entry.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            consumed_fields.add(name)
            return text
    return None


def _extract_citekey(raw: str, fallback: Any) -> str | None:
    opening_positions = [position for position in (raw.find("{"), raw.find("(")) if position >= 0]
    if opening_positions:
        start = min(opening_positions) + 1
        comma = raw.find(",", start)
        if comma >= 0:
            key = raw[start:comma].strip()
            if key:
                return key
    fallback_text = "" if fallback is None else str(fallback).strip()
    return fallback_text or None


def _bounded_extra(
    entry: dict[str, Any],
    warnings: list[str],
    consumed_fields: set[str],
) -> dict[str, str]:
    extra: dict[str, str] = {}
    total_chars = 0
    for field_name in sorted(entry, key=lambda value: str(value).casefold()):
        if field_name in consumed_fields:
            continue
        if len(extra) >= MAX_BIBTEX_EXTRA_FIELDS:
            warnings.append(
                f"Additional BibTeX fields beyond {MAX_BIBTEX_EXTRA_FIELDS} were omitted."
            )
            break
        safe_name = str(field_name)[:128]
        raw_value = "" if entry[field_name] is None else str(entry[field_name])
        remaining = MAX_BIBTEX_EXTRA_TOTAL_CHARS - total_chars
        if remaining <= 0:
            warnings.append(
                "Additional BibTeX fields exceeded the total preview limit and were omitted."
            )
            break
        limit = min(MAX_BIBTEX_EXTRA_VALUE_CHARS, remaining)
        value = raw_value[:limit]
        if len(value) < len(raw_value):
            warnings.append(f"BibTeX extra field {safe_name!r} was truncated for preview.")
        extra[safe_name] = value
        total_chars += len(value)
    return extra


def _reference_type(entry_type: str) -> str:
    return _ENTRY_TYPE_TO_REFERENCE_TYPE.get(entry_type.casefold(), "other")


def _reference_data(
    entry: dict[str, Any],
    *,
    raw: str,
    entry_type: str,
    citekey: str | None,
    import_method: str,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    for field_name, value in entry.items():
        if value is not None and len(str(value)) > MAX_BIBTEX_FIELD_CHARS:
            raise ValueError(
                f"BibTeX field {field_name!r} exceeds the per-field preview limit."
            )

    consumed_fields = {"ID", "ENTRYTYPE"}
    authors_raw = _selected_text_field(entry, consumed_fields, "author")
    title = _selected_text_field(entry, consumed_fields, "title")
    year_raw = _selected_text_field(entry, consumed_fields, "year")
    year = int(year_raw) if year_raw and _YEAR_RE.fullmatch(year_raw) else None
    journal = _selected_text_field(
        entry,
        consumed_fields,
        "journal",
        "journaltitle",
    )
    publisher = _selected_text_field(entry, consumed_fields, "publisher")
    volume = _selected_text_field(entry, consumed_fields, "volume")
    number = _selected_text_field(entry, consumed_fields, "number", "issue")
    edition = _selected_text_field(entry, consumed_fields, "edition")
    isbn = _selected_text_field(entry, consumed_fields, "isbn")
    doi = _selected_text_field(entry, consumed_fields, "doi")
    url = _selected_text_field(entry, consumed_fields, "url")
    language = _selected_text_field(
        entry,
        consumed_fields,
        "language",
        "langid",
    )
    note = _selected_text_field(entry, consumed_fields, "note", "annote")
    reference_data: dict[str, Any] = {
        "reference_type": _reference_type(entry_type),
        "bibtex": {
            "key": citekey,
            "entry_type": entry_type,
            "raw": raw,
            "raw_sha256": _sha256_text(raw),
            "extra": _bounded_extra(entry, warnings, consumed_fields),
        },
        "authors": parse_bibtex_authors(authors_raw),
        "title": title,
        "year": year,
        "year_raw": year_raw,
        "journal": journal,
        "publisher": publisher,
        "volume": volume,
        "number": number,
        "edition": edition,
        "isbn": [isbn] if isbn else [],
        "doi": doi,
        "url": url,
        "language": language,
        "notes": note,
        "provenance": {
            "import_method": import_method,
            "warnings": warnings,
        },
    }
    return reference_data, warnings


def parse_bibtex_text(
    content: str,
    *,
    import_method: str = "bibtex_paste",
) -> BibTeXParseResult:
    """Parse one or many BibTeX entries without writing or validating MongoDB."""
    if not isinstance(content, str):
        raise TypeError("BibTeX content must be text; use parse_bibtex_file_content for bytes.")
    if import_method not in _IMPORT_METHODS:
        raise ValueError(f"Unsupported BibTeX import method: {import_method!r}")
    if not content.strip("\ufeff\r\n\t "):
        return BibTeXParseResult(
            errors=(
                _entry_error(
                    entry_index=None,
                    code="empty_input",
                    message="BibTeX input is empty.",
                ),
            )
        )
    if len(content) > MAX_BIBTEX_TEXT_CHARS:
        return BibTeXParseResult(
            errors=(
                _entry_error(
                    entry_index=None,
                    code="input_too_large",
                    message=(
                        f"BibTeX input exceeds the {MAX_BIBTEX_TEXT_CHARS} character limit."
                    ),
                ),
            )
        )

    blocks, scan_errors = _scan_bibtex_blocks(content)
    string_definitions = [
        block.raw
        for block in blocks
        if block.directive.casefold() == "string" and block.error_code is None
    ]
    candidates: list[dict[str, Any]] = []
    errors = list(scan_errors)
    ignored: list[str] = []
    entry_index = 0

    for block in blocks:
        directive_normalized = block.directive.casefold()
        if directive_normalized in _CONTROL_DIRECTIVES and block.error_code is None:
            ignored.append(directive_normalized)
            continue

        entry_index += 1
        if entry_index > MAX_BIBTEX_ENTRIES:
            errors.append(
                _entry_error(
                    entry_index=entry_index,
                    code="too_many_entries",
                    message=f"BibTeX preview is limited to {MAX_BIBTEX_ENTRIES} entries.",
                    raw=block.raw,
                    entry_type=block.directive or None,
                )
            )
            break
        if block.error_code:
            errors.append(
                _entry_error(
                    entry_index=entry_index,
                    code=block.error_code,
                    message=block.error_message or "Malformed BibTeX entry.",
                    raw=block.raw,
                    entry_type=block.directive or None,
                )
            )
            continue
        if len(block.raw) > MAX_BIBTEX_ENTRY_CHARS:
            errors.append(
                _entry_error(
                    entry_index=entry_index,
                    code="entry_too_large",
                    message=(
                        f"BibTeX entry exceeds the {MAX_BIBTEX_ENTRY_CHARS} character limit."
                    ),
                    raw=block.raw,
                    entry_type=block.directive,
                )
            )
            continue

        citekey = _extract_citekey(block.raw, None)
        try:
            parsed = _parse_one_entry(block.raw, string_definitions)
            citekey = _extract_citekey(block.raw, parsed.get("ID"))
            if not citekey:
                raise ValueError("BibTeX entry has no citation key.")
            entry_type = str(parsed.get("ENTRYTYPE") or block.directive).strip()
            if not entry_type:
                raise ValueError("BibTeX entry has no ENTRYTYPE.")
            reference_data, warnings = _reference_data(
                parsed,
                raw=block.raw,
                entry_type=entry_type,
                citekey=citekey,
                import_method=import_method,
            )
        except Exception as exc:
            errors.append(
                _entry_error(
                    entry_index=entry_index,
                    code="parse_error",
                    message=f"Could not parse BibTeX entry: {exc}",
                    raw=block.raw,
                    entry_type=block.directive or None,
                    citekey=citekey,
                )
            )
            continue

        candidates.append(
            {
                "entry_index": entry_index,
                "entry_type": entry_type,
                "citekey": citekey,
                "raw": block.raw,
                "raw_sha256": _sha256_text(block.raw),
                "reference_data": reference_data,
                "warnings": list(warnings),
            }
        )

    if not candidates and not errors:
        errors.append(
            _entry_error(
                entry_index=None,
                code="no_entries",
                message="BibTeX input contains no bibliographic entries.",
            )
        )
    return BibTeXParseResult(
        candidates=tuple(candidates),
        errors=tuple(errors),
        ignored_directives=tuple(ignored),
    )


def parse_bibtex_paste(content: str) -> BibTeXParseResult:
    """Parse pasted BibTeX content for preview."""
    return parse_bibtex_text(content, import_method="bibtex_paste")


def parse_bibtex_file_content(
    content: str | bytes,
    *,
    encoding: str = "utf-8-sig",
) -> BibTeXParseResult:
    """Parse content already read from a ``.bib`` file; this function opens no file."""
    if isinstance(content, bytes):
        try:
            text = content.decode(encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            return BibTeXParseResult(
                errors=(
                    {
                        **_entry_error(
                            entry_index=None,
                            code="decode_error",
                            message=f"Could not decode BibTeX file content: {exc}",
                        ),
                        "content_sha256": hashlib.sha256(content).hexdigest(),
                    },
                )
            )
    elif isinstance(content, str):
        text = content.lstrip("\ufeff")
    else:
        raise TypeError("BibTeX file content must be str or bytes.")
    return parse_bibtex_text(text, import_method="bib_file")


def parse_bibtex(content: str) -> BibTeXParseResult:
    """Backward-friendly short name for pasted BibTeX parsing."""
    return parse_bibtex_paste(content)


def preview_bibtex(content: str, *, import_method: str = "bibtex_paste") -> BibTeXParseResult:
    """Explicit preview alias used by service-layer callers."""
    return parse_bibtex_text(content, import_method=import_method)


__all__ = [
    "BibTeXParseResult",
    "MAX_BIBTEX_ENTRIES",
    "MAX_BIBTEX_ENTRY_CHARS",
    "MAX_BIBTEX_EXTRA_FIELDS",
    "MAX_BIBTEX_EXTRA_TOTAL_CHARS",
    "MAX_BIBTEX_EXTRA_VALUE_CHARS",
    "MAX_BIBTEX_FIELD_CHARS",
    "MAX_BIBTEX_TEXT_CHARS",
    "parse_bibtex",
    "parse_bibtex_authors",
    "parse_bibtex_file_content",
    "parse_bibtex_paste",
    "parse_bibtex_text",
    "preview_bibtex",
]
