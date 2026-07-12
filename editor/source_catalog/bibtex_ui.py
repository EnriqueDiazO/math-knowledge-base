"""Persistence-free BibTeX preview and selection UI for Source Catalog pages."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from editor.source_catalog.reference_form import ReferenceFormDraft
from editor.source_catalog.reference_form import render_reference_form
from editor.source_catalog.shared import render_duplicate_preview
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.bibtex import MAX_BIBTEX_TEXT_CHARS
from mathmongo.source_catalog.bibtex import BibTeXParseResult
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import Reference

MAX_BIBTEX_UPLOAD_BYTES = MAX_BIBTEX_TEXT_CHARS * 4
MAX_RAW_PREVIEW_CHARS = 800
MAX_BIBTEX_UI_ENTRIES = 25
_MONGO_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s'\"<>]+", re.IGNORECASE)
_URI_USERINFO_RE = re.compile(
    r"(?P<scheme>https?|ftp)://[^/\s:@]+:[^@\s/]+@",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)(?P<name>password|passwd|pwd|token|secret|api[_-]?key|"
    r"access[_-]?token|authorization)\s*=\s*"
    r"(?:[{'\"])?[^,}\n'\"]+"
)
_LOCAL_PATH_RE = re.compile(
    r"(?i)(?:file:///)?(?:"
    r"/(?:home|Users|root|tmp|var|opt|srv|mnt|workspace|private|usr|etc|Library)"
    r"(?:/[^\s,;:'\"<>\])]+)+"
    r"|[a-z]:\\(?:[^\\\s,;:'\"<>\])]+\\?)+)"
)


@dataclass(frozen=True, slots=True)
class BibTeXCandidateDraft:
    """One selected, editable candidate and its non-persisted decision state."""

    entry_index: int
    form: ReferenceFormDraft
    duplicates: tuple[DuplicateMatch, ...] = ()
    allow_duplicate: bool = False

    @property
    def reference(self) -> Reference | None:
        """Return the validated edited Reference, if any."""
        return self.form.reference

    @property
    def ready(self) -> bool:
        """Return whether validation and any required duplicate decision pass."""
        return self.reference is not None and (
            not _requires_duplicate_confirmation(self.duplicates) or self.allow_duplicate
        )


@dataclass(frozen=True, slots=True)
class BibTeXSelection:
    """Typed output for a caller that may later choose to persist drafts."""

    preview: BibTeXParseResult | None = None
    selected_entry_indices: tuple[int, ...] = ()
    drafts: tuple[BibTeXCandidateDraft, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        """Return whether every selected candidate validates."""
        return bool(self.drafts) and all(item.ready for item in self.drafts)


def uploaded_bibtex_bytes(uploaded_file: Any) -> bytes:
    """Return bounded bytes from an already-uploaded `.bib` object.

    The helper never opens a path. It accepts Streamlit's UploadedFile or a
    faithful fake exposing ``getvalue()``/``read()``.
    """
    if uploaded_file is None:
        return b""
    name = getattr(uploaded_file, "name", None)
    if isinstance(name, str) and name and not name.casefold().endswith(".bib"):
        raise ValueError("The uploaded bibliography must use the .bib extension.")
    declared_size = getattr(uploaded_file, "size", None)
    if (
        isinstance(declared_size, int)
        and not isinstance(declared_size, bool)
        and declared_size > MAX_BIBTEX_UPLOAD_BYTES
    ):
        raise ValueError(f"The uploaded bibliography exceeds {MAX_BIBTEX_UPLOAD_BYTES} bytes.")

    if hasattr(uploaded_file, "read"):
        position = None
        if hasattr(uploaded_file, "tell"):
            try:
                position = uploaded_file.tell()
            except (OSError, ValueError):
                position = None
        value = uploaded_file.read(MAX_BIBTEX_UPLOAD_BYTES + 1)
        if position is not None and hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(position)
            except (OSError, ValueError):
                pass
    elif hasattr(uploaded_file, "getvalue"):
        value = uploaded_file.getvalue()
    else:
        raise TypeError("Uploaded BibTeX content must expose getvalue() or read().")

    if isinstance(value, str):
        data = value.encode("utf-8")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
    else:
        raise TypeError("Uploaded BibTeX content must be bytes or text.")
    if len(data) > MAX_BIBTEX_UPLOAD_BYTES:
        raise ValueError(f"The uploaded bibliography exceeds {MAX_BIBTEX_UPLOAD_BYTES} bytes.")
    return data


def _redacted_raw_preview(raw: Any) -> str:
    text = "" if raw is None else str(raw)
    text = _MONGO_URI_RE.sub("<redacted MongoDB URI>", text)
    text = _URI_USERINFO_RE.sub(
        lambda match: f"{match.group('scheme')}://<redacted>@",
        text,
    )
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('name')}={{<redacted>}}",
        text,
    )
    text = _LOCAL_PATH_RE.sub("<redacted local path>", text)
    if len(text) > MAX_RAW_PREVIEW_CHARS:
        return text[:MAX_RAW_PREVIEW_CHARS].rstrip() + "\n… [truncated]"
    return text


def _input_digest(content: str | bytes, *, from_file: bool) -> str:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    prefix = b"file\0" if from_file else b"paste\0"
    return hashlib.sha256(prefix + data).hexdigest()


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    reference = candidate.get("reference_data") or {}
    authors: list[str] = []
    for author in reference.get("authors") or []:
        if not isinstance(author, dict):
            continue
        literal = author.get("literal")
        if literal:
            authors.append(str(literal))
        else:
            authors.append(
                " ".join(
                    str(value) for value in (author.get("given"), author.get("family")) if value
                )
            )
    return {
        "entry": candidate.get("entry_index"),
        "ENTRYTYPE": candidate.get("entry_type"),
        "citekey": candidate.get("citekey"),
        "authors": "; ".join(authors),
        "title": reference.get("title"),
        "year": reference.get("year_raw") or reference.get("year"),
        "DOI": reference.get("doi"),
        "ISBN": "; ".join(reference.get("isbn") or []),
        "raw_sha256": candidate.get("raw_sha256"),
    }


def _parse_error_text(error: dict[str, Any]) -> str:
    entry = error.get("entry_index")
    prefix = f"Entry {entry}" if entry is not None else "BibTeX input"
    code = str(error.get("code") or "error")
    message = safe_error_message(error.get("message") or "Could not parse this entry.")
    raw_hash = error.get("raw_sha256") or error.get("content_sha256")
    suffix = f" · SHA-256 {raw_hash}" if raw_hash else ""
    return f"{prefix} · {code}: {message}{suffix}"


def _candidate_by_index(
    preview: BibTeXParseResult,
    entry_index: int,
) -> dict[str, Any] | None:
    return next(
        (
            candidate
            for candidate in preview.candidates
            if int(candidate.get("entry_index", -1)) == entry_index
        ),
        None,
    )


def _requires_duplicate_confirmation(matches: Iterable[DuplicateMatch]) -> bool:
    return any(
        match.classification
        in {
            DuplicateClassification.EXACT,
            DuplicateClassification.STRONG,
            DuplicateClassification.POSSIBLE,
        }
        for match in matches
    )


def selected_bibtex_references(
    selection: BibTeXSelection,
    *,
    source_ids: Iterable[str] = (),
) -> tuple[Reference, ...]:
    """Return selected edited References scoped to caller-supplied Sources."""
    requested_sources = list(dict.fromkeys(str(item) for item in source_ids))
    references: list[Reference] = []
    for draft in selection.drafts:
        if draft.reference is None:
            raise ValueError(f"Selected BibTeX entry {draft.entry_index} has validation errors.")
        if not draft.ready:
            raise ValueError(
                f"Selected BibTeX entry {draft.entry_index} requires a duplicate decision."
            )
        data = draft.reference.model_dump(mode="python")
        data["source_ids"] = requested_sources
        references.append(Reference.model_validate(data))
    return tuple(references)


def render_bibtex_input(
    ui: Any,
    service: Any,
    *,
    key_prefix: str,
) -> BibTeXSelection:
    """Render paste/upload preview and return edited candidates without writes."""
    preview_key = state_key(key_prefix, "bibtex_preview")
    preview_digest_key = state_key(key_prefix, "bibtex_preview_digest")
    mode = ui.selectbox(
        "BibTeX input",
        ("Paste BibTeX", "Upload .bib"),
        key=state_key(key_prefix, "bibtex_mode"),
    )
    content: str | bytes = ""
    from_file = mode == "Upload .bib"
    if from_file:
        uploaded = ui.file_uploader(
            "Upload a .bib file",
            type=["bib"],
            key=state_key(key_prefix, "bibtex_upload"),
        )
        try:
            content = uploaded_bibtex_bytes(uploaded)
        except (TypeError, ValueError) as exc:
            ui.error(safe_error_message(exc))
    else:
        content = ui.text_area(
            "Paste one or more BibTeX entries",
            height=220,
            key=state_key(key_prefix, "bibtex_paste"),
        )
        if len(content) > MAX_BIBTEX_TEXT_CHARS:
            ui.error(f"BibTeX input exceeds the {MAX_BIBTEX_TEXT_CHARS}-character limit.")
            content = ""

    preview_clicked = ui.button(
        "Preview BibTeX",
        key=state_key(key_prefix, "bibtex_preview_button"),
        disabled=not bool(content),
    )
    current_digest = _input_digest(content, from_file=from_file)
    errors: list[str] = []
    if preview_clicked and content:
        try:
            preview = service.preview_bibtex(content, from_file=from_file)
            if not isinstance(preview, BibTeXParseResult):
                raise TypeError("BibTeX preview returned an unexpected result type.")
            ui.session_state[preview_key] = preview
            ui.session_state[preview_digest_key] = current_digest
            selected_key = state_key(key_prefix, "bibtex_selected_entries")
            ui.session_state[selected_key] = [
                int(candidate["entry_index"])
                for candidate in preview.candidates[:MAX_BIBTEX_UI_ENTRIES]
            ]
        except Exception as exc:
            safe = safe_error_message(exc)
            errors.append(safe)
            ui.error(f"BibTeX preview failed: {safe}")

    stored_preview = ui.session_state.get(preview_key)
    preview = (
        stored_preview
        if isinstance(stored_preview, BibTeXParseResult)
        and ui.session_state.get(preview_digest_key) == current_digest
        else None
    )
    if stored_preview is not None and preview is None:
        ui.caption("BibTeX input changed; run Preview BibTeX again.")
    if preview is None:
        return BibTeXSelection(errors=tuple(errors))

    for error in preview.errors:
        message = _parse_error_text(error)
        errors.append(message)
        ui.error(message)
    if preview.ignored_directives:
        ui.caption("Ignored BibTeX directives: " + ", ".join(preview.ignored_directives))
    if not preview.candidates:
        return BibTeXSelection(preview=preview, errors=tuple(errors))

    visible_candidates = preview.candidates[:MAX_BIBTEX_UI_ENTRIES]
    if len(preview.candidates) > len(visible_candidates):
        ui.warning(
            f"This preview contains {len(preview.candidates)} valid entries. "
            f"Only the first {MAX_BIBTEX_UI_ENTRIES} are available in one UI batch; "
            "split the bibliography to process the remainder."
        )
    summaries = [_candidate_summary(candidate) for candidate in visible_candidates]
    ui.dataframe(summaries, use_container_width=True, hide_index=True)
    indices = [int(candidate["entry_index"]) for candidate in visible_candidates]
    labels = {
        int(candidate["entry_index"]): (
            f"{candidate.get('entry_index')} · {candidate.get('entry_type')} · "
            f"{candidate.get('citekey')}"
        )
        for candidate in visible_candidates
    }
    selected = ui.multiselect(
        "Select entries to keep",
        options=indices,
        default=indices,
        format_func=lambda value: labels.get(int(value), str(value)),
        key=state_key(key_prefix, "bibtex_selected_entries"),
    )
    selected_indices = tuple(dict.fromkeys(int(value) for value in selected))
    drafts: list[BibTeXCandidateDraft] = []

    for entry_index in selected_indices:
        candidate = _candidate_by_index(preview, entry_index)
        if candidate is None:
            errors.append(f"Selected BibTeX entry {entry_index} is no longer available.")
            continue
        reference_data = candidate.get("reference_data") or {}
        raw_hash = (
            candidate.get("raw_sha256")
            or hashlib.sha256(str(candidate.get("raw") or "").encode("utf-8")).hexdigest()
        )
        with ui.expander(
            f"Edit entry {entry_index}: {candidate.get('citekey')}",
            expanded=len(selected_indices) == 1,
        ):
            ui.caption(f"Original raw SHA-256: {raw_hash}")
            show_raw = ui.checkbox(
                "Show bounded raw snippet",
                key=state_key(
                    key_prefix,
                    "bibtex_show_raw",
                    entry_index,
                    str(raw_hash)[:12],
                ),
            )
            if show_raw:
                ui.code(_redacted_raw_preview(candidate.get("raw")), language="bibtex")
            try:
                initial = Reference.model_validate(reference_data)
                form = render_reference_form(
                    ui,
                    key_prefix=(f"{key_prefix}_bibtex_{entry_index}_{str(raw_hash)[:12]}"),
                    initial=initial,
                )
            except ValidationError as exc:
                messages = tuple(
                    f"{'.'.join(str(part) for part in item.get('loc', ()))}: "
                    f"{item.get('msg', 'invalid value')}"
                    for item in exc.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    )
                )
                form = ReferenceFormDraft(reference=None, values={}, errors=messages)

            for message in form.errors:
                ui.error(f"Entry {entry_index}: {safe_error_message(message)}")
            duplicates: tuple[DuplicateMatch, ...] = ()
            if form.reference is not None:
                try:
                    duplicates = tuple(
                        service.detect_reference_duplicates(
                            form.reference,
                            import_context=f"bibtex-entry:{entry_index}",
                        )
                    )
                    render_duplicate_preview(ui, duplicates)
                except Exception as exc:
                    safe = safe_error_message(exc)
                    errors.append(safe)
                    ui.error(f"Duplicate preview failed: {safe}")
            allow_duplicate = False
            if _requires_duplicate_confirmation(duplicates):
                candidate_fingerprint = (
                    draft_fingerprint(form.reference)
                    if form.reference is not None
                    else str(raw_hash)[:16]
                )
                allow_duplicate = ui.checkbox(
                    "I reviewed the duplicate evidence and want to keep this draft",
                    key=state_key(
                        key_prefix,
                        "bibtex_allow_duplicate",
                        entry_index,
                        str(raw_hash)[:12],
                        candidate_fingerprint,
                    ),
                )
            drafts.append(
                BibTeXCandidateDraft(
                    entry_index=entry_index,
                    form=form,
                    duplicates=duplicates,
                    allow_duplicate=allow_duplicate,
                )
            )

    return BibTeXSelection(
        preview=preview,
        selected_entry_indices=selected_indices,
        drafts=tuple(drafts),
        errors=tuple(errors),
    )


__all__ = [
    "BibTeXCandidateDraft",
    "BibTeXSelection",
    "MAX_BIBTEX_UPLOAD_BYTES",
    "MAX_BIBTEX_UI_ENTRIES",
    "MAX_RAW_PREVIEW_CHARS",
    "render_bibtex_input",
    "selected_bibtex_references",
    "uploaded_bibtex_bytes",
]
