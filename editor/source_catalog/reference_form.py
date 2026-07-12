"""Reusable, persistence-free Reference form helpers for S1B."""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timezone
from typing import Any

from pydantic import ValidationError

from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceAuthor
from mathmongo.source_catalog.models import ReferenceType

_YEAR_RE = re.compile(r"^[+-]?\d{1,4}$")


@dataclass(frozen=True, slots=True)
class ReferenceFormDraft:
    """A validated, non-persisted Reference produced by visible form values."""

    values: Mapping[str, Any]
    reference: Reference | None
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        """Return whether the draft can be handed to the service layer."""
        return self.reference is not None and not self.errors


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def split_list_text(value: Any) -> list[str]:
    """Split a comma, semicolon, or newline-delimited UI value."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\n]", value)
    else:
        parts = list(value)
    return [str(item).strip() for item in parts if str(item).strip()]


def authors_to_text(authors: Iterable[ReferenceAuthor | Mapping[str, Any]]) -> str:
    """Serialize structured and literal authors into an editable line format.

    Literal authors use ``literal: Name``. Structured authors use
    ``Family | Given``. A plain line is deliberately interpreted as literal so
    organizations and historical author strings are not destructively split.
    """
    lines: list[str] = []
    for value in authors:
        author = (
            value if isinstance(value, ReferenceAuthor) else ReferenceAuthor.model_validate(value)
        )
        if author.literal:
            lines.append(f"literal: {author.literal}")
        else:
            lines.append(f"{author.family or ''} | {author.given or ''}".rstrip())
    return "\n".join(lines)


def parse_authors_text(value: Any) -> list[dict[str, str | None]]:
    """Parse the form's explicit structured/literal author syntax."""
    if value is None:
        return []
    if not isinstance(value, str):
        return [ReferenceAuthor.model_validate(item).model_dump(mode="python") for item in value]

    authors: list[dict[str, str | None]] = []
    for line_number, raw_line in enumerate(value.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.casefold().startswith("literal:"):
            literal = line.split(":", 1)[1].strip()
            if not literal:
                raise ValueError(f"Author line {line_number} has an empty literal name.")
            authors.append({"family": None, "given": None, "literal": literal})
            continue
        if "|" in line:
            family, given = (part.strip() for part in line.split("|", 1))
            if not (family or given):
                raise ValueError(f"Author line {line_number} is empty.")
            authors.append(
                {
                    "family": family or None,
                    "given": given or None,
                    "literal": None,
                }
            )
            continue
        authors.append({"family": None, "given": None, "literal": line})
    return authors


def parse_accessed_at(value: Any) -> datetime | None:
    """Parse date/ISO form input and return an aware UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
    else:
        text_value = str(value).strip()
        if not text_value:
            return None
        if text_value.endswith(("Z", "z")):
            text_value = text_value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text_value)
        except ValueError as exc:
            raise ValueError(
                "Accessed at must be an ISO date or datetime, for example 2026-07-12."
            ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("Year must be an integer, not a boolean value.")
    if isinstance(value, int):
        return value
    text_value = str(value).strip()
    if not _YEAR_RE.fullmatch(text_value):
        raise ValueError("Year must contain one to four digits; use year_raw otherwise.")
    return int(text_value)


def _validation_messages(error: ValidationError) -> tuple[str, ...]:
    messages: list[str] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "reference"
        messages.append(f"{location}: {item.get('msg', 'invalid value')}")
    return tuple(messages)


def _initial_reference(initial: Reference | Mapping[str, Any] | None) -> Reference | None:
    if initial is None:
        return None
    return initial if isinstance(initial, Reference) else Reference.model_validate(initial)


def build_reference_from_form(
    values: Mapping[str, Any],
    *,
    initial: Reference | Mapping[str, Any] | None = None,
    source_ids: Iterable[str] = (),
    reference_id: str | None = None,
) -> Reference:
    """Build and validate a Reference without persistence or database access."""
    current = _initial_reference(initial)
    if current is not None:
        data = current.model_dump(mode="python")
        if reference_id is not None and reference_id != current.reference_id:
            raise ValueError("reference_id cannot change while editing a Reference.")
    else:
        data = {}

    def form_value(name: str, default: Any = None) -> Any:
        return values[name] if name in values else default

    effective_reference_id = reference_id or (current.reference_id if current is not None else None)
    requested_sources = list(dict.fromkeys(str(item) for item in source_ids))
    if not requested_sources and current is not None:
        requested_sources = list(current.source_ids)

    current_authors: Any = current.authors if current is not None else ""
    current_isbn: Any = current.isbn if current is not None else ""
    authors_value = form_value(
        "authors",
        form_value("authors_text", current_authors),
    )
    isbn_value = form_value("isbn", form_value("isbn_text", current_isbn))
    bibtex_data = (
        current.bibtex.model_dump(mode="python")
        if current is not None
        else {"key": None, "entry_type": None, "raw": None, "extra": {}}
    )
    bibtex_data["key"] = _optional_text(
        form_value(
            "bibtex_key",
            current.bibtex.key if current is not None else None,
        )
    )

    replace_raw = bool(values.get("replace_bibtex_raw", False))
    if replace_raw or current is None:
        raw = _optional_text(form_value("bibtex_raw"))
        bibtex_data.update(
            {
                "entry_type": _optional_text(form_value("bibtex_entry_type")),
                "raw": raw,
                "raw_sha256": None,
                "extra": dict(form_value("bibtex_extra", {}) or {}),
            }
        )

    data.update(
        {
            "source_ids": requested_sources,
            "reference_type": form_value(
                "reference_type",
                current.reference_type if current is not None else ReferenceType.MISC.value,
            ),
            "bibtex": bibtex_data,
            "authors": parse_authors_text(authors_value),
            "title": _optional_text(
                form_value("title", current.title if current is not None else None)
            ),
            "year": _parse_year(form_value("year", current.year if current is not None else None)),
            "year_raw": _optional_text(
                form_value("year_raw", current.year_raw if current is not None else None)
            ),
            "journal": _optional_text(
                form_value("journal", current.journal if current is not None else None)
            ),
            "publisher": _optional_text(
                form_value("publisher", current.publisher if current is not None else None)
            ),
            "volume": _optional_text(
                form_value("volume", current.volume if current is not None else None)
            ),
            "number": _optional_text(
                form_value("number", current.number if current is not None else None)
            ),
            "edition": _optional_text(
                form_value("edition", current.edition if current is not None else None)
            ),
            "isbn": split_list_text(isbn_value),
            "doi": _optional_text(form_value("doi", current.doi if current is not None else None)),
            "url": _optional_text(form_value("url", current.url if current is not None else None)),
            "accessed_at": parse_accessed_at(
                form_value(
                    "accessed_at",
                    current.accessed_at if current is not None else None,
                )
            ),
            "language": _optional_text(
                form_value("language", current.language if current is not None else None)
            ),
            "notes": _optional_text(
                form_value("notes", current.notes if current is not None else None)
            ),
        }
    )
    if effective_reference_id is not None:
        data["reference_id"] = effective_reference_id
    return Reference.model_validate(data)


def _initial_values(initial: Reference | None) -> dict[str, Any]:
    if initial is None:
        return {
            "reference_type": ReferenceType.MISC.value,
            "authors_text": "",
            "title": "",
            "year": "",
            "year_raw": "",
            "journal": "",
            "publisher": "",
            "volume": "",
            "number": "",
            "edition": "",
            "isbn_text": "",
            "doi": "",
            "url": "",
            "accessed_at": "",
            "language": "",
            "notes": "",
            "bibtex_key": "",
            "bibtex_entry_type": "",
            "bibtex_raw": "",
            "replace_bibtex_raw": False,
        }
    accessed = initial.accessed_at.isoformat() if initial.accessed_at else ""
    return {
        "reference_type": initial.reference_type.value,
        "authors_text": authors_to_text(initial.authors),
        "title": initial.title or "",
        "year": "" if initial.year is None else str(initial.year),
        "year_raw": initial.year_raw or "",
        "journal": initial.journal or "",
        "publisher": initial.publisher or "",
        "volume": initial.volume or "",
        "number": initial.number or "",
        "edition": initial.edition or "",
        "isbn_text": "\n".join(initial.isbn),
        "doi": initial.doi or "",
        "url": initial.url or "",
        "accessed_at": accessed,
        "language": initial.language or "",
        "notes": initial.notes or "",
        "bibtex_key": initial.bibtex.key or "",
        "bibtex_entry_type": initial.bibtex.entry_type or "",
        "bibtex_raw": initial.bibtex.raw or "",
        "replace_bibtex_raw": False,
    }


def _text_input(ui: Any, label: str, *, key: str, value: Any = "", **kwargs: Any) -> Any:
    return ui.text_input(label, key=key, value=value, **kwargs)


def render_reference_form(
    ui: Any,
    *,
    key_prefix: str,
    initial: Reference | Mapping[str, Any] | None = None,
    source_ids: Iterable[str] = (),
    reference_id: str | None = None,
) -> ReferenceFormDraft:
    """Render Reference fields and return a typed, non-persisted draft."""
    current: Reference | None = None
    initial_error: tuple[str, ...] = ()
    try:
        current = _initial_reference(initial)
    except ValidationError as exc:
        initial_error = _validation_messages(exc)
    defaults = _initial_values(current)

    shown_id = reference_id or (current.reference_id if current is not None else None)
    ui.caption(
        f"Reference ID: {shown_id} (stable, read-only)"
        if shown_id
        else "Reference ID: generated by the system when this draft is validated."
    )
    type_options = [item.value for item in ReferenceType]
    type_default = defaults["reference_type"]
    reference_type = ui.selectbox(
        "Reference type",
        type_options,
        index=type_options.index(type_default) if type_default in type_options else 0,
        key=state_key(key_prefix, "reference_type"),
    )
    authors_text = ui.text_area(
        "Authors",
        value=defaults["authors_text"],
        key=state_key(key_prefix, "authors"),
        help=(
            "One author per line. Use 'Family | Given' for a structured name or "
            "'literal: Organization Name' for a literal author."
        ),
    )
    title = _text_input(
        ui,
        "Title",
        key=state_key(key_prefix, "title"),
        value=defaults["title"],
    )
    year = _text_input(
        ui,
        "Year",
        key=state_key(key_prefix, "year"),
        value=defaults["year"],
    )
    year_raw = _text_input(
        ui,
        "Year (raw/historical)",
        key=state_key(key_prefix, "year_raw"),
        value=defaults["year_raw"],
    )
    journal = _text_input(
        ui,
        "Journal",
        key=state_key(key_prefix, "journal"),
        value=defaults["journal"],
    )
    publisher = _text_input(
        ui,
        "Publisher",
        key=state_key(key_prefix, "publisher"),
        value=defaults["publisher"],
    )
    volume = _text_input(
        ui,
        "Volume",
        key=state_key(key_prefix, "volume"),
        value=defaults["volume"],
    )
    number = _text_input(
        ui,
        "Number",
        key=state_key(key_prefix, "number"),
        value=defaults["number"],
    )
    edition = _text_input(
        ui,
        "Edition",
        key=state_key(key_prefix, "edition"),
        value=defaults["edition"],
    )
    isbn_text = ui.text_area(
        "ISBN values",
        value=defaults["isbn_text"],
        key=state_key(key_prefix, "isbn"),
        help="One ISBN per line, or separate values with commas or semicolons.",
    )
    doi = _text_input(
        ui,
        "DOI",
        key=state_key(key_prefix, "doi"),
        value=defaults["doi"],
    )
    url = _text_input(
        ui,
        "URL",
        key=state_key(key_prefix, "url"),
        value=defaults["url"],
    )
    accessed_at = _text_input(
        ui,
        "Accessed at (ISO date/datetime)",
        key=state_key(key_prefix, "accessed_at"),
        value=defaults["accessed_at"],
    )
    language = _text_input(
        ui,
        "Language",
        key=state_key(key_prefix, "language"),
        value=defaults["language"],
    )
    notes = ui.text_area(
        "Notes",
        value=defaults["notes"],
        key=state_key(key_prefix, "notes"),
    )
    bibtex_key = _text_input(
        ui,
        "BibTeX key",
        key=state_key(key_prefix, "bibtex_key"),
        value=defaults["bibtex_key"],
    )

    replace_raw = False
    bibtex_entry_type = defaults["bibtex_entry_type"]
    bibtex_raw = defaults["bibtex_raw"]
    if current is not None and current.bibtex.raw:
        ui.caption(
            f"Preserved BibTeX raw SHA-256: {current.bibtex.raw_sha256}. "
            "It is retained unless replacement is explicitly enabled."
        )
        replace_raw = ui.checkbox(
            "Replace preserved BibTeX raw explicitly",
            value=False,
            key=state_key(key_prefix, "replace_bibtex_raw"),
        )
        if replace_raw:
            bibtex_entry_type = _text_input(
                ui,
                "Replacement ENTRYTYPE",
                key=state_key(key_prefix, "bibtex_entry_type"),
                value=defaults["bibtex_entry_type"],
            )
            bibtex_raw = ui.text_area(
                "Replacement BibTeX raw",
                value=defaults["bibtex_raw"],
                key=state_key(key_prefix, "bibtex_raw"),
            )

    values = {
        "reference_type": reference_type,
        "authors_text": authors_text,
        "title": title,
        "year": year,
        "year_raw": year_raw,
        "journal": journal,
        "publisher": publisher,
        "volume": volume,
        "number": number,
        "edition": edition,
        "isbn_text": isbn_text,
        "doi": doi,
        "url": url,
        "accessed_at": accessed_at,
        "language": language,
        "notes": notes,
        "bibtex_key": bibtex_key,
        "bibtex_entry_type": bibtex_entry_type,
        "bibtex_raw": bibtex_raw,
        "replace_bibtex_raw": replace_raw,
    }
    if initial_error:
        return ReferenceFormDraft(values=values, reference=None, errors=initial_error)
    try:
        reference = build_reference_from_form(
            values,
            initial=current,
            source_ids=source_ids,
            reference_id=reference_id,
        )
    except ValidationError as exc:
        return ReferenceFormDraft(
            values=values,
            reference=None,
            errors=_validation_messages(exc),
        )
    except (TypeError, ValueError) as exc:
        return ReferenceFormDraft(values=values, reference=None, errors=(str(exc),))

    for warning in reference.provenance.warnings:
        ui.warning(safe_error_message(warning))
    return ReferenceFormDraft(values=values, reference=reference)


__all__ = [
    "ReferenceFormDraft",
    "authors_to_text",
    "build_reference_from_form",
    "parse_accessed_at",
    "parse_authors_text",
    "render_reference_form",
    "split_list_text",
]
