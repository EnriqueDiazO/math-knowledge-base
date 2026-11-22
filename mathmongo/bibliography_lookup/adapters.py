"""Provider schemas become editable canonical References, never PDF downloads."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone

from mathmongo.source_catalog.models import Reference

TYPE_MAP = {
    "journal-article": "article",
    "book-chapter": "chapter",
    "book-section": "chapter",
    "monograph": "book",
    "book": "book",
    "edited-book": "book",
    "dissertation": "thesis",
    "proceedings-article": "proceedings",
    "report": "report",
    "journalarticle": "article",
    "bookchapter": "chapter",
    "text": "other",
}
TYPE_MAP.update(
    {
        "article": "article",
        "chapter": "chapter",
        "incollection": "chapter",
        "proceedings": "proceedings",
        "phdthesis": "thesis",
        "techreport": "report",
    }
)
ENTRY_MAP = {
    "article": "article",
    "chapter": "incollection",
    "book": "book",
    "thesis": "phdthesis",
    "proceedings": "inproceedings",
    "report": "techreport",
}


def text(value) -> str | None:
    """Only declared text is text; never stringify unrecognized JSON objects."""
    if isinstance(value, list):
        value = value[0] if value else None
    return value.strip() or None if isinstance(value, str) else None


def names(items: list, *, given="given", family="family", literal="name") -> list[dict]:
    """Keep the catalog's structured/literal names without guessing name order."""
    result = []
    if not isinstance(items, list):
        return result
    for item in items[:100]:
        if isinstance(item, str):
            result.append({"literal": item})
        elif isinstance(item, dict):
            name = {
                "given": text(item.get(given)),
                "family": text(item.get(family)),
                "literal": text(item.get(literal)),
                "orcid": text(item.get("ORCID")),
            }
            if any(name[key] for key in ("given", "family", "literal")):
                result.append(name)
    return result


def display_names(authors: list[dict]) -> str:
    """Format only names explicitly supplied by the provider."""
    return " and ".join(
        author.get("literal") or " ".join(filter(None, [author.get("given"), author.get("family")]))
        for author in authors
    )


@dataclass(frozen=True)
class Proposal:
    """A lookup result is a proposal; it has not been persisted or merged."""

    reference: Reference
    edition_ids: tuple[str, ...] = ()

    def public(self) -> dict:
        """Expose editable metadata and safe catalog IDs, without provider raw blobs."""
        return {
            "reference_data": self.reference.model_dump(mode="json"),
            "edition_ids": list(self.edition_ids),
        }


def reference(
    values: dict,
    *,
    provider: str,
    identifier: str,
    original: str,
    record_url: str,
    record_kind: str,
    raw: dict,
    warnings: list[str] | None = None,
) -> Proposal:
    """Attach explicit query provenance; publication and retrieval dates differ."""
    now = datetime.now(timezone.utc)
    return Proposal(
        Reference(
            **values,
            provenance={
                "import_method": "online_lookup",
                "imported_at": now,
                "warnings": warnings or [],
                "external_lookup": {
                    "provider": provider,
                    "identifier": identifier,
                    "original_query": original,
                    "record_url": record_url,
                    "record_kind": record_kind,
                    "retrieved_at": now,
                    "response_sha256": hashlib.sha256(
                        json.dumps(
                            raw, sort_keys=True, ensure_ascii=False, allow_nan=False
                        ).encode()
                    ).hexdigest(),
                },
            },
        )
    )


def crossref(raw: dict, *, doi: str, original: str, url: str) -> Proposal:
    """Keep article/chapter identity and that DOI's publication/container data."""
    message = raw.get("message")
    if not isinstance(message, dict) or not message:
        raise ValueError("Crossref singleton missing")
    kind = TYPE_MAP.get(str(message.get("type", "")).casefold(), "other")
    extra = {}
    for source, target in [("page", "pages"), ("edition-number", "edition"), ("ISSN", "issn")]:
        if value := text(message.get(source)):
            extra[target] = value
    container = text(message.get("container-title"))
    if kind == "chapter" and container:
        extra["booktitle"] = container
    for role in ("editor", "translator"):
        if people := names(message.get(role) or []):
            extra[role] = display_names(people)
    year, date = None, None
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (message.get(key) or {}).get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            if isinstance(parts[0][0], int) and not isinstance(parts[0][0], bool):
                year = parts[0][0]
                date = "-".join(str(part) for part in parts[0])
                extra["date"] = date
                break
    return reference(
        {
            "reference_type": kind,
            "title": text(message.get("title")),
            "authors": names(message.get("author") or []),
            "year": year,
            "year_raw": date,
            "journal": container if kind == "article" else None,
            "volume": text(message.get("volume")),
            "number": text(message.get("issue")),
            "publisher": text(message.get("publisher")),
            "edition": text(message.get("edition-number")),
            "language": text(message.get("language")),
            "doi": doi,
            "url": "https://doi.org/" + doi,
            "isbn": message.get("ISBN") or [],
            "bibtex": {"entry_type": ENTRY_MAP.get(kind, "misc"), "extra": extra},
        },
        provider="crossref",
        identifier=doi,
        original=original,
        record_url=url,
        record_kind=kind,
        raw=raw,
    )


def datacite(raw: dict, *, doi: str, original: str, url: str) -> Proposal:
    """Retrieve findable DataCite metadata without an account or enrichment service."""
    values = (raw.get("data") or {}).get("attributes")
    if not isinstance(values, dict) or not values:
        raise ValueError("DataCite singleton missing")
    types = values.get("types") or {}
    kind = TYPE_MAP.get(
        str(
            types.get("citeproc") or types.get("bibtex") or types.get("resourceTypeGeneral") or ""
        ).casefold(),
        "other",
    )
    title = next(
        (
            text(item.get("title"))
            for item in values.get("titles", [])
            if isinstance(item, dict) and item.get("titleType") in (None, "")
        ),
        None,
    )
    extra = {}
    for role, label in [("Editor", "editor"), ("Translator", "translator")]:
        people = [
            person
            for person in values.get("contributors", [])
            if isinstance(person, dict) and person.get("contributorType") == role
        ]
        if people:
            extra[label] = display_names(names(people, given="givenName", family="familyName"))
    publisher = values.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    return reference(
        {
            "reference_type": kind,
            "title": title,
            "authors": names(values.get("creators") or [], given="givenName", family="familyName"),
            "year": values.get("publicationYear"),
            "publisher": text(publisher),
            "language": text(values.get("language")),
            "doi": doi,
            "url": "https://doi.org/" + doi,
            "bibtex": {"entry_type": ENTRY_MAP.get(kind, "misc"), "extra": extra},
        },
        provider="datacite",
        identifier=doi,
        original=original,
        record_url=url,
        record_kind=kind,
        raw=raw,
    )


def openlibrary_edition(
    raw: dict, *, identifier: str, original: str, url: str, authors: list[str], warnings: list[str]
) -> Proposal:
    """An ISBN resolves an edition: never substitute the work's first publication."""
    key = raw.get("key")
    if not isinstance(key, str) or not re.fullmatch(r"/books/OL[0-9]+M", key):
        raise ValueError("Open Library edition identity missing")
    date = text(raw.get("publish_date"))
    match = re.search(r"\b([12][0-9]{3})\b", date or "")
    extra = {
        key: str(value)
        for key, value in {
            "date": date,
            "pagination": text(raw.get("pagination")),
            "pagetotal": raw.get("number_of_pages"),
            "by_statement": text(raw.get("by_statement")),
            "contributions": "; ".join(
                item for item in (raw.get("contributions") or []) if isinstance(item, str)
            ),
        }.items()
        if value
    }
    languages = raw.get("languages") or []
    return reference(
        {
            "reference_type": "book",
            "title": text(raw.get("title")),
            "authors": names(authors),
            "year": int(match.group(1)) if match else None,
            "year_raw": date,
            "publisher": "; ".join(
                item for item in raw.get("publishers", []) if isinstance(item, str)
            )
            or None,
            "edition": text(raw.get("edition_name")),
            "isbn": list(dict.fromkeys([*(raw.get("isbn_10") or []), *(raw.get("isbn_13") or [])])),
            "language": str(languages[0].get("key", "")).removeprefix("/languages/")
            if languages and isinstance(languages[0], dict)
            else None,
            "url": "https://openlibrary.org" + key,
            "bibtex": {"entry_type": "book", "extra": extra},
        },
        provider="openlibrary",
        identifier=identifier,
        original=original,
        record_url=url,
        record_kind="edition",
        raw=raw,
        warnings=warnings,
    )
