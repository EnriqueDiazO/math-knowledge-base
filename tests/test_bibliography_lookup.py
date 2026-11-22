"""Offline provider contracts: editions, failures and bounded public transport."""

# ruff: noqa: D103
from __future__ import annotations

import copy
import io
import json
from datetime import datetime
from datetime import timezone
from email.message import Message
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request

import pytest

from mathmongo.bibliography_lookup.identifiers import parse_identifier
from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.bibliography_lookup.transport import MAX_RESPONSE_BYTES
from mathmongo.bibliography_lookup.transport import MetadataLookupError
from mathmongo.bibliography_lookup.transport import ProviderRedirects
from mathmongo.bibliography_lookup.transport import PublicMetadataHTTP
from mathmongo.bibliography_lookup.transport import allowed_url
from mathmongo.bibliography_lookup.transport import retry_delay
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.normalization import isbn_equivalents
from tests.test_source_catalog_service import _service

DOI = "10.1007/bf01106749"
CROSSREF = {
    "message": {
        "DOI": DOI,
        "type": "journal-article",
        "title": ["Singular integral operators along a complex contour"],
        "author": [{"family": "Nyaga", "given": "V. I."}],
        "published-print": {"date-parts": [[1977, 3]]},
        "created": {"date-parts": [[2005]]},
        "container-title": ["Mathematical Notes"],
        "page": "228-231",
        "volume": "21",
        "issue": "3",
        "language": "en",
    }
}
EDITION = {
    "key": "/books/OL123M",
    "title": "Edición traducida",
    "publish_date": "2006",
    "edition_name": "Segunda edición española",
    "isbn_10": ["0140328726"],
    "isbn_13": ["9780140328721"],
    "authors": [{"key": "/authors/OL42A"}],
    "languages": [{"key": "/languages/spa"}],
    "publishers": ["Editorial de prueba"],
    "pagination": "xii, 231 p.",
    "contributions": ["Traductora declarada (Translator)"],
    "works": [{"key": "/works/OL999W", "first_publish_year": 1901}],
}


class Clock:
    """Deterministic time and observable waits for rate-limit checks."""

    def __init__(self):
        """Start from a positive monotonic timestamp."""
        self.now = 10.0
        self.sleeps = []

    def __call__(self):
        """Read simulated time without advancing it."""
        return self.now

    def sleep(self, seconds):
        """Advance time while retaining the actual requested delay."""
        self.sleeps.append(seconds)
        self.now += seconds


class HTTP:
    """Ordered provider replies and exact requested URLs, without a network."""

    def __init__(self, replies):
        """Retain independent replies, including provider failures."""
        self.replies = list(replies)
        self.urls = []

    def get(self, url, *, deadline):
        """Record the fixed provider endpoint and serve exactly one reply."""
        self.urls.append(url)
        assert allowed_url(url)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)


def lookup(*replies):
    clock, http = Clock(), HTTP(replies)
    return MetadataLookup(http=http, clock=clock, sleep=clock.sleep), http, clock


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("10.1007/BF01106749", DOI),
        ("https://doi.org/10.1007%2FBF01106749?x=1", DOI),
        (" DOI:10.1007/BF01106749 ", DOI),
        ("0-14-032872-6", "0140328726"),
        ("978 0 14 032872 1", "9780140328721"),
    ],
)
def test_strict_identifier_retains_original(query, expected):
    result = parse_identifier(query)
    assert result.original == query
    assert result.value == expected


@pytest.mark.parametrize(
    "query",
    [
        "",
        "9780140328722",
        "0-14-032872-7",
        "https://evil.test/10.1007/BF01106749",
        "https://doi.org:bad/10.1007/abc",
        "https://name:secret@doi.org/10.1007/abc",
        "10.12/abc",
        "١٤٠٣٢٨٧٢٦",
    ],
)
def test_invalid_identifier_never_makes_request(query):
    api, http, _ = lookup()
    assert api.identifier(query).status == "invalid"
    assert http.urls == []


def test_crossref_article_date_container_and_cached_independent_proposals():
    api, http, _ = lookup(CROSSREF)
    first = api.identifier("https://doi.org/" + DOI)
    assert first.status == "found"
    ref = first.candidates[0].reference
    assert (ref.title, ref.year, ref.language) == (CROSSREF["message"]["title"][0], 1977, "en")
    assert (ref.reference_type.value, ref.bibtex.extra["pages"]) == ("article", "228-231")
    assert ref.provenance.external_lookup.provider == "crossref"
    assert ref.provenance.external_lookup.original_query == "https://doi.org/" + DOI
    assert ref.provenance.external_lookup.retrieved_at.tzinfo is not None
    ref.title = "corrección local"
    second = api.identifier(DOI)
    assert second.candidates[0].reference.title != ref.title
    assert len(http.urls) == 1
    assert second.public("B")["request_id"] == "B"


def test_datacite_fallback_keeps_chapter_and_declared_editor():
    raw = {
        "data": {
            "id": DOI,
            "attributes": {
                "types": {"bibtex": "incollection", "resourceTypeGeneral": "BookChapter"},
                "titles": [{"title": "Capítulo", "titleType": None}],
                "publicationYear": 2020,
                "creators": [{"familyName": "Apellido", "givenName": "Nombre"}],
                "contributors": [{"name": "Editora", "contributorType": "Editor"}],
                "publisher": {"name": "Editorial"},
                "language": "es",
            },
        }
    }
    api, http, _ = lookup(MetadataLookupError("not_found"), raw)
    result = api.identifier(DOI)
    assert result.providers == ("crossref", "datacite")
    assert result.candidates[0].reference.provenance.external_lookup.provider == "datacite"
    assert result.candidates[0].reference.publisher == "Editorial"
    assert result.candidates[0].reference.bibtex.extra["editor"] == "Editora"
    assert len(http.urls) == 2


def test_no_match_is_distinct_from_outage_and_partial():
    api, _, _ = lookup(MetadataLookupError("not_found"), MetadataLookupError("not_found"))
    assert api.identifier(DOI).status == "not_found"
    api, http, _ = lookup(
        MetadataLookupError("unavailable"),
        MetadataLookupError("unavailable"),
        MetadataLookupError("not_found"),
    )
    assert api.identifier(DOI).status == "unavailable"
    assert len(http.urls) == 3
    api, _, _ = lookup({"message": {"DOI": DOI, "title": ["Sólo título"]}})
    result = api.identifier(DOI)
    assert result.status == "partial"
    assert result.candidates[0].reference.year is None
    assert result.candidates[0].reference.authors == []


def test_rate_limit_retry_after_prevents_repeat_and_long_sleep():
    api, http, clock = lookup(
        MetadataLookupError("rate_limited", retry_after=120),
        MetadataLookupError("not_found"),
        MetadataLookupError("not_found"),
    )
    result = api.identifier(DOI)
    assert (result.status, result.retry_after) == ("rate_limited", 120)
    assert not clock.sleeps
    api.identifier(DOI)
    assert sum("crossref" in url for url in http.urls) == 1
    api, http, clock = lookup(MetadataLookupError("rate_limited", retry_after=1), CROSSREF)
    assert api.identifier(DOI).status == "found"
    assert clock.sleeps == [1]
    assert len(http.urls) == 2


def test_isbn_resolves_edition_authors_and_never_uses_work_date():
    api, http, clock = lookup(EDITION, {"name": "Autora canónica"})
    result = api.identifier("0-14-032872-6")
    ref = result.candidates[0].reference
    assert result.status == "found"
    assert (ref.year, ref.edition, ref.language) == (2006, "Segunda edición española", "spa")
    assert ref.authors[0].literal == "Autora canónica"
    assert ref.bibtex.extra["pagination"] == "xii, 231 p."
    assert "Translator" in ref.bibtex.extra["contributions"]
    assert http.urls == [
        "https://openlibrary.org/isbn/0140328726.json",
        "https://openlibrary.org/authors/OL42A.json",
    ]
    assert clock.sleeps == [1]
    assert ref.provenance.external_lookup.record_kind == "edition"


def test_missing_author_keeps_partial_edition_and_mismatched_isbn_is_rejected():
    api, _, _ = lookup(EDITION, MetadataLookupError("not_found"))
    result = api.identifier("9780140328721")
    assert result.status == "partial"
    assert result.candidates[0].reference.edition == EDITION["edition_name"]
    wrong = {**EDITION, "isbn_10": [], "isbn_13": ["9780306406157"]}
    api, http, _ = lookup(wrong)
    assert api.identifier("9780140328721").status == "unavailable"
    assert len(http.urls) == 1


def test_title_search_requires_explicit_edition_and_does_not_infer_year():
    api, http, _ = lookup(
        {
            "docs": [
                {
                    "key": "/works/OL123W",
                    "title": "Obra",
                    "author_name": ["Autora"],
                    "first_publish_year": 1901,
                    "edition_key": ["OL123M", "../evil"],
                }
            ]
        },
        EDITION,
        {"name": "Autora"},
    )
    result = api.search("Obra", "Autora")
    assert result.status == "candidates"
    proposal = result.candidates[0]
    assert proposal.reference.year is None and proposal.reference.isbn == []
    assert proposal.edition_ids == ("OL123M",)
    edition = api.edition(proposal.edition_ids[0])
    assert edition.candidates[0].reference.year == 2006
    assert "search.json?" in http.urls[0] and "title=Obra" in http.urls[0]
    assert api.edition("../secret").status == "invalid"


def test_equivalent_isbn_and_doi_offer_existing_without_mutating_manual_fields():
    service, sources, refs = _service()
    existing = Reference(
        title="Título corregido",
        isbn=["0140328726"],
        doi=DOI,
        bibtex={"key": "ClaveEstable"},
        notes="Corrección manual",
    )
    refs.insert(existing)
    proposal = Reference(title="Otro título del proveedor", isbn=["9780140328721"])
    matches = service.detect_reference_duplicates(proposal)
    assert any(match.entity_id == existing.reference_id for match in matches)
    outcome = service.create_reference(proposal)
    assert not outcome.persisted
    assert len(refs.records) == 1 and sources.records == {}
    assert refs.get_by_id(existing.reference_id).model_dump() == existing.model_dump()
    assert isbn_equivalents("0140328726") == isbn_equivalents("9780140328721")
    assert len(isbn_equivalents("9791090636071")) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://api.crossref.org/works/a",
        "https://api.crossref.org:bad/works/a",
        "https://evil.test/isbn/123.json",
        "https://openlibrary.org/api/books",
        "https://openlibrary.org/books/../secret.json",
        "https://openlibrary.org/books/%2e%2e/secret.json",
        "https://api.crossref.org/works/a#b",
    ],
)
def test_transport_rejects_arbitrary_endpoints(url):
    assert not allowed_url(url)


def test_redirects_allow_only_same_provider_edition_and_retry_dates():
    redirects = ProviderRedirects()
    request = Request("https://openlibrary.org/isbn/9780140328721.json")
    assert redirects.redirect_request(
        request, None, 302, "", {}, "https://openlibrary.org/books/OL123M.json"
    ).full_url.endswith("/OL123M.json")
    for target in (
        "https://evil.test/steal",
        "https://api.crossref.org/works/secret",
        "https://openlibrary.org/secret.pdf",
    ):
        with pytest.raises(MetadataLookupError):
            redirects.redirect_request(request, None, 302, "", {}, target)
    assert (
        retry_delay("Sun, 22 Nov 2026 00:01:00 GMT", datetime(2026, 11, 22, tzinfo=timezone.utc))
        == 60
    )
    assert retry_delay("nan") is None and retry_delay("bad") is None


class Response(io.BytesIO):
    """HTTP response double that exercises bounded reads and resource closure."""

    headers = {"Content-Type": "application/json"}
    read1 = io.BytesIO.read


class Opener:
    """Record request identity/timeout and return a controlled response."""

    def __init__(self, reply):
        """Keep the response/error and a request ledger."""
        self.reply, self.requests = reply, []

    def open(self, request, *, timeout):
        """Capture the request headers and effective timeout."""
        self.requests.append((request, timeout))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_public_http_identity_deadline_bounded_body_and_failure_status():
    http = PublicMetadataHTTP(contact="mailto:configured@example.test", clock=lambda: 10.0)
    http.opener = Opener(Response(json.dumps(CROSSREF).encode()))
    assert http.get("https://api.crossref.org/works/x", deadline=12.0) == CROSSREF
    req, timeout = http.opener.requests[0]
    assert timeout == 2 and "configured@example.test" in req.get_header("User-agent")
    for body in (b"x" * (MAX_RESPONSE_BYTES + 1), b"[]", b"bad"):
        http.opener = Opener(Response(body))
        with pytest.raises(MetadataLookupError, match="unavailable"):
            http.get("https://api.crossref.org/works/x", deadline=12.0)
    headers = Message()
    headers["Retry-After"] = "120"
    error = HTTPError("https://api.crossref.org/works/x", 429, "limited", headers, io.BytesIO())
    http.opener = Opener(error)
    with pytest.raises(MetadataLookupError) as caught:
        http.get("https://api.crossref.org/works/x", deadline=12.0)
    assert caught.value.status == "rate_limited" and caught.value.retry_after == 120
    assert error.closed
    http.opener = Opener(URLError("proxy credential must not be rendered"))
    with pytest.raises(MetadataLookupError, match="^unavailable$"):
        http.get("https://api.crossref.org/works/x", deadline=12.0)
    with pytest.raises(ValueError):
        PublicMetadataHTTP(contact="bad\r\nInjected: value")
