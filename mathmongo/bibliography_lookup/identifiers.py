"""Strict new-query validation, separate from tolerant legacy normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote
from urllib.parse import urlsplit

from mathmongo.source_catalog.normalization import isbn_equivalents
from mathmongo.source_catalog.normalization import normalize_doi
from mathmongo.source_catalog.normalization import normalize_isbn


@dataclass(frozen=True)
class Identifier:
    """Retain the input alongside the lookup/comparison identity."""

    kind: Literal["doi", "isbn"]
    value: str
    original: str


def parse_identifier(value: str) -> Identifier:
    """Accept DOI names/recognized DOI links or checksum-valid ISBN editions."""
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Pega un DOI o ISBN de hasta 2000 caracteres.")
    original, text = value, value.strip()
    if "://" in text:
        parsed = urlsplit(text)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"doi.org", "dx.doi.org", "www.doi.org"}
            or parsed.username
            or parsed.password
            or parsed.port
        ):
            raise ValueError(
                "Sólo se admiten enlaces DOI reconocidos; no se descargan URLs arbitrarias."
            )
        text = unquote(parsed.path.lstrip("/"))
    doi = normalize_doi(text)
    if doi and re.fullmatch(r"10\.[0-9]{4,9}/[^\s<>\x00-\x1f]+", doi):
        return Identifier("doi", doi, original)
    isbn = normalize_isbn(text)
    if isbn and isbn_equivalents(isbn):
        return Identifier("isbn", isbn, original)
    raise ValueError(
        "DOI inválido o ISBN con formato/dígito de control inválido. Revisa el identificador."
    )
