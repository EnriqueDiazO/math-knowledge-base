"""A passage locator belongs to its citation, separately from edition metadata/PDF."""

from __future__ import annotations

from urllib.parse import quote

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from mathmongo.source_catalog.models import Reference


class CitationLocator(BaseModel):
    """Printed pagination and physical PDF index never imply each other."""

    model_config = ConfigDict(extra="forbid", strict=True)
    printed_page: str = Field(default="", max_length=200)
    pdf_page: int | None = Field(default=None, ge=1, le=1_000_000)
    chapter: str = Field(default="", max_length=200)
    section: str = Field(default="", max_length=200)
    theorem: str = Field(default="", max_length=200)
    passage: str = Field(default="", max_length=2000)


def legacy_citation(reference: Reference, locator: CitationLocator) -> dict[str, str]:
    """Feed established reference export fields without changing the catalog record."""
    authors = "; ".join(
        person.literal or " ".join(filter(None, [person.given, person.family]))
        for person in reference.authors
    )
    result = {
        "reference_id": reference.reference_id,
        "autor": authors,
        "fuente": reference.title or "",
        "anio": str(reference.year) if reference.year is not None else "",
        "tipo_referencia": {
            "book": "libro",
            "article": "articulo",
            "thesis": "tesis",
            "web": "pagina_web",
        }.get(reference.reference_type.value, "miscelanea"),
        "reference_type": reference.reference_type.value,
        "citekey": reference.bibtex.key or "",
        "editorial": reference.publisher or "",
        "edicion": reference.edition or "",
        "tomo": reference.volume or "",
        "doi": reference.doi or "",
        "issbn": "; ".join(reference.isbn),
        "url": reference.url or "",
        "paginas": locator.printed_page,
        "capitulo": locator.chapter,
        "seccion": locator.section,
        "teorema": locator.theorem,
        "pasaje": locator.passage,
        "pdf_page": str(locator.pdf_page) if locator.pdf_page is not None else "",
        "journal": reference.journal or "",
        "number": reference.number or "",
        "publication_pages": reference.bibtex.extra.get("pages", ""),
        "booktitle": reference.bibtex.extra.get("booktitle", ""),
        "translator": reference.bibtex.extra.get("translator", ""),
        "language": reference.language or "",
    }
    return {
        key: value
        if key in {"reference_id", "citekey"}
        else quote(value, safe=":/?&=;@+,.~_-#%")
        if key == "url"
        else escape_tex(value)
        for key, value in result.items()
        if value
    }


def escape_tex(value: str) -> str:
    """Catalog metadata is text, not executable TeX; legacy authored TeX stays separate."""
    escaped = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "%": r"\%",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    return "".join(escaped.get(char, char) for char in value)


def extra_citation_latex(reference: dict) -> str:
    """Add explicit edition/passage distinctions to both established LaTeX exports."""
    if not reference.get("reference_id"):
        return ""
    fields = [
        ("journal", "Revista"),
        ("booktitle", "Libro contenedor"),
        ("number", "Número"),
        ("publication_pages", "Páginas de la publicación"),
        ("translator", "Traducción"),
        ("language", "Idioma"),
        ("teorema", "Teorema citado"),
        ("pdf_page", "Página física del PDF"),
        ("pasaje", "Pasaje citado"),
    ]
    return "".join(
        escape_tex(label) + ": " + str(reference[key]) + r"\\" + "\n"
        for key, label in fields
        if reference.get(key)
    )
