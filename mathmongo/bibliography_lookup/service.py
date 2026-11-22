"""Interactive public metadata queries with cache, rate limits and explicit states."""

from __future__ import annotations

import copy
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import quote
from urllib.parse import urlencode

from pydantic import ValidationError

from mathmongo.bibliography_lookup import adapters
from mathmongo.bibliography_lookup.identifiers import parse_identifier
from mathmongo.bibliography_lookup.transport import MetadataLookupError
from mathmongo.bibliography_lookup.transport import PublicMetadataHTTP
from mathmongo.source_catalog.normalization import isbn_equivalents
from mathmongo.source_catalog.normalization import normalize_doi


@dataclass(frozen=True)
class LookupResult:
    """Absence in a provider is not a claim that an identifier does not exist."""

    status: str
    query: str
    normalized: str = ""
    candidates: tuple[adapters.Proposal, ...] = ()
    providers: tuple[str, ...] = ()
    retry_after: float | None = None

    def public(self, request_id: str) -> dict:
        """Associate a response with the exact client request, including stale replies."""
        return {
            "request_id": request_id,
            "status": self.status,
            "query": self.query,
            "normalized": self.normalized,
            "providers": list(self.providers),
            "candidates": [candidate.public() for candidate in self.candidates],
            "retry_after": self.retry_after,
        }


class MetadataLookup:
    """Read-only lookup facade; callers must confirm through SourceCatalogService."""

    def __init__(self, *, http=None, contact: str = "", clock=time.monotonic, sleep=time.sleep):
        """Inject transport/clock for deterministic tests without Internet dependency."""
        self.http = http or PublicMetadataHTTP(contact=contact, clock=clock)
        self.clock, self.sleep = clock, sleep
        self.cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.cache_lock = threading.Lock()
        self.provider_locks = {
            provider: threading.Lock() for provider in ("crossref", "datacite", "openlibrary")
        }
        self.next_request = dict.fromkeys(self.provider_locks, 0.0)

    def _get(self, provider: str, url: str, deadline: float) -> dict:
        with self.cache_lock:
            cached = self.cache.get(url)
            if cached and self.clock() - cached[0] < 3600:
                self.cache.move_to_end(url)
                return copy.deepcopy(cached[1])
        lock = self.provider_locks[provider]
        if not lock.acquire(timeout=max(0.0, deadline - self.clock())):
            raise MetadataLookupError("unavailable")
        try:
            for attempt in range(2):
                wait = max(0.0, self.next_request[provider] - self.clock())
                if wait > 2 or self.clock() + wait >= deadline:
                    raise MetadataLookupError("rate_limited", retry_after=wait)
                if wait:
                    self.sleep(wait)
                try:
                    self.next_request[provider] = self.clock() + 1.0
                    result = self.http.get(url, deadline=deadline)
                    with self.cache_lock:
                        self.cache[url] = (self.clock(), copy.deepcopy(result))
                        self.cache.move_to_end(url)
                        while len(self.cache) > 64:
                            self.cache.popitem(last=False)
                    return result
                except MetadataLookupError as exc:
                    if exc.status == "rate_limited":
                        delay = exc.retry_after if exc.retry_after is not None else 1.0
                        self.next_request[provider] = self.clock() + delay
                        if attempt or delay > 2 or self.clock() + delay >= deadline:
                            raise
                    elif attempt or exc.status == "not_found":
                        raise
                    else:
                        self.next_request[provider] = self.clock() + 0.25
            raise MetadataLookupError("unavailable")
        finally:
            lock.release()

    @staticmethod
    def _result(
        proposal: adapters.Proposal, original: str, normalized: str, providers: tuple[str, ...]
    ) -> LookupResult:
        value = proposal.reference
        partial = (
            not value.title
            or not value.authors
            or value.year is None
            or bool(value.provenance.warnings)
        )
        return LookupResult(
            "partial" if partial else "found", original, normalized, (proposal,), providers
        )

    def identifier(self, query: str) -> LookupResult:
        """Query only after the user's explicit action; no note/PDF content is sent."""
        try:
            parsed = parse_identifier(query)
        except ValueError:
            return LookupResult("invalid", query if isinstance(query, str) else "")
        deadline = self.clock() + 20.0
        if parsed.kind == "isbn":
            return self.edition(parsed.value, original=query, deadline=deadline)
        outcomes = []
        for provider, host, adapter in [
            ("crossref", "https://api.crossref.org/works/", adapters.crossref),
            ("datacite", "https://api.datacite.org/dois/", adapters.datacite),
        ]:
            url = host + quote(parsed.value, safe="")
            try:
                raw = self._get(provider, url, deadline)
                supplied = (
                    (raw.get("message") or {}).get("DOI")
                    if provider == "crossref"
                    else (raw.get("data") or {}).get("id")
                )
                if supplied and normalize_doi(supplied) != parsed.value:
                    raise MetadataLookupError("unavailable")
                proposal = adapter(raw, doi=parsed.value, original=query, url=url)
                return self._result(
                    proposal, query, parsed.value, tuple(item[0] for item in outcomes) + (provider,)
                )
            except MetadataLookupError as exc:
                outcomes.append((provider, exc))
            except (ValueError, TypeError, AttributeError, ValidationError):
                outcomes.append((provider, MetadataLookupError("unavailable")))
        failure = next(
            (failure for _, failure in outcomes if failure.status != "not_found"), outcomes[-1][1]
        )
        return LookupResult(
            failure.status,
            query,
            parsed.value,
            providers=tuple(provider for provider, _ in outcomes),
            retry_after=failure.retry_after,
        )

    def edition(
        self, identifier: str, *, original: str | None = None, deadline: float | None = None
    ) -> LookupResult:
        """Resolve a checked ISBN or an explicitly selected Open Library edition ID."""
        original = original if original is not None else identifier
        deadline = deadline if deadline is not None else self.clock() + 20.0
        isbn = isbn_equivalents(identifier)
        if not isbn and not re.fullmatch(r"OL[0-9]+M", identifier):
            return LookupResult("invalid", original)
        url = (
            "https://openlibrary.org/"
            + ("isbn/" if isbn else "books/")
            + quote(identifier, safe="")
            + ".json"
        )
        try:
            raw = self._get("openlibrary", url, deadline)
            recorded = [*(raw.get("isbn_10") or []), *(raw.get("isbn_13") or [])]
            if (
                isbn
                and recorded
                and not isbn.intersection(
                    equivalent for item in recorded for equivalent in isbn_equivalents(item)
                )
            ):
                raise MetadataLookupError("unavailable")
            warnings, authors = [], []
            for person in (raw.get("authors") or [])[:8]:
                key = person.get("key") if isinstance(person, dict) else None
                if not isinstance(key, str) or not re.fullmatch(r"/authors/OL[0-9]+A", key):
                    warnings.append("Identidad de autor incompleta; revisa el registro original.")
                    continue
                try:
                    author = self._get(
                        "openlibrary", "https://openlibrary.org" + key + ".json", deadline
                    )
                    if name := adapters.text(author.get("name")):
                        authors.append(name)
                    else:
                        warnings.append("Autor sin nombre; revisa el registro original.")
                except MetadataLookupError:
                    warnings.append(
                        "No se pudo recuperar un nombre de autor; la edición se conserva como propuesta parcial."
                    )
            if len(raw.get("authors") or []) > 8:
                warnings.append(
                    "La consulta está limitada a ocho autores; revisa los demás en el registro original."
                )
            proposal = adapters.openlibrary_edition(
                raw,
                identifier=identifier,
                original=original,
                url=url,
                authors=authors,
                warnings=warnings,
            )
            return self._result(proposal, original, identifier, ("openlibrary",))
        except MetadataLookupError as exc:
            return LookupResult(
                exc.status,
                original,
                identifier,
                providers=("openlibrary",),
                retry_after=exc.retry_after,
            )
        except (ValueError, TypeError, AttributeError, ValidationError):
            return LookupResult("unavailable", original, identifier, providers=("openlibrary",))

    def search(self, title: str, author: str = "") -> LookupResult:
        """Search a few works; an edition must still be consulted to cite its ISBN/date."""
        if (
            not isinstance(title, str)
            or not isinstance(author, str)
            or not title.strip()
            or len(title) > 200
            or len(author) > 200
        ):
            return LookupResult("invalid", str(title)[:200])
        url = "https://openlibrary.org/search.json?" + urlencode(
            {
                "title": title.strip(),
                "author": author.strip(),
                "limit": 5,
                "fields": "key,title,author_name,first_publish_year,edition_key",
            }
        )
        try:
            raw = self._get("openlibrary", url, self.clock() + 20.0)
            proposals = []
            for item in (raw.get("docs") or [])[:5]:
                key = item.get("key")
                if not isinstance(key, str) or not re.fullmatch(r"/works/OL[0-9]+W", key):
                    continue
                proposal = adapters.reference(
                    {
                        "reference_type": "book",
                        "title": adapters.text(item.get("title")),
                        "authors": adapters.names(item.get("author_name") or []),
                        "url": "https://openlibrary.org" + key,
                        "bibtex": {"entry_type": "book"},
                    },
                    provider="openlibrary",
                    identifier=key,
                    original=title,
                    record_url=url,
                    record_kind="work",
                    raw=item,
                    warnings=[
                        "Resultado de obra: consulta una edición para obtener su ISBN y fecha, sin asumir la primera publicación."
                    ],
                )
                editions = tuple(
                    value
                    for value in (item.get("edition_key") or [])[:5]
                    if isinstance(value, str) and re.fullmatch(r"OL[0-9]+M", value)
                )
                proposals.append(adapters.Proposal(proposal.reference, editions))
            return LookupResult(
                "candidates" if proposals else "not_found",
                title,
                candidates=tuple(proposals),
                providers=("openlibrary",),
            )
        except MetadataLookupError as exc:
            return LookupResult(
                exc.status, title, providers=("openlibrary",), retry_after=exc.retry_after
            )
        except (ValueError, TypeError, AttributeError, ValidationError):
            return LookupResult("unavailable", title, providers=("openlibrary",))
