from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

import yaml


# -----------------------------
# Helpers
# -----------------------------
def _slug(s: str) -> str:
    """
    Normalize a string into a filesystem-friendly slug.
    """
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s, flags=re.UNICODE)
    return s.strip("-") or "concepto"


def _safe_title(concept: Dict[str, Any]) -> str:
    """
    Prefer titulo; fallback to Tipo (ID).
    """
    t = (concept.get("titulo") or "").strip()
    if t:
        return t

    tipo = (concept.get("tipo") or "concepto")
    cid = (concept.get("id") or "sin-id")
    return f"{str(tipo).title()} ({cid})"


def _route(concept: Dict[str, Any]) -> Path:
    """
    Map concept types into your Quarto Book folder structure.
    Normalizes unknown types to avoid weird folder names.
    """
    tipo = (concept.get("tipo") or "").strip().lower()

    if tipo == "nota":
        return Path("atlas/notas")
    if tipo == "ejemplo":
        return Path("atlas/ejemplos")

    # Default to chapters/<tipo>
    return Path("chapters") / _slug(tipo or "otros")


def _file_stem(concept: Dict[str, Any]) -> str:
    """
    File name stem that avoids collisions:
    <slug(title)>-<slug(id)>
    """
    title = _safe_title(concept)
    cid = str(concept.get("id") or "").strip()
    return f"{_slug(title)}-{_slug(cid) if cid else 'noid'}"

def _bib_escape(s: str) -> str:
    s = str(s or "")
    # escapes mínimos para LaTeX/BibTeX
    s = s.replace("\\", "\\textbackslash{}")
    s = s.replace("{", "\\{").replace("}", "\\}")
    s = s.replace("&", "\\&")
    s = s.replace("%", "\\%")
    s = s.replace("_", "\\_")
    s = s.replace("#", "\\#")
    s = s.replace("$", "\\$")
    s = s.replace("~", "\\textasciitilde{}")
    s = s.replace("^", "\\textasciicircum{}")
    return s

def _bib_key_for_ref(ref: Dict[str, Any], fallback: str) -> str:
    base = (
        f"{ref.get('autor','')}_{ref.get('anio','')}_"
        f"{ref.get('titulo','') or ref.get('fuente','')}_{fallback}"
    )
    key = _slug(base)
    if not key or key == "concepto":
        key = _slug(fallback) or "ref"
    return key[:80]





def concept_to_qmd(concept: Dict[str, Any], bibfile: str) -> str:
    front = {
        "title": _safe_title(concept),
        "bibliography": bibfile,
    }

    parts = [
        "---",
        yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip(),
        "---",
        "",
        "## Contenido",
        "",
        "```{=latex}",
        concept.get("contenido_latex", ""),
        "```",
        "",
    ]

    cite = concept.get("_cite_key")
    if cite:
        parts += [
            "## Referencias",
            "",
            f"[@{cite}]",
            ""
        ]

    return "\n".join(parts)



def referencia_to_bibtex(concept: Dict[str, Any]) -> tuple[str, str] | None:
    ref = concept.get("referencia")
    if not isinstance(ref, dict):
        return None

    fallback = f"{concept.get('id','')}_{concept.get('source','')}"
    key = _bib_key_for_ref(ref, fallback=fallback)

    tipo = (ref.get("tipo_referencia") or "").strip().lower()

    # Si hay "titulo" y además "fuente" (libro), esto se parece a una parte de un libro
    has_part = bool((ref.get("titulo") or "").strip())
    has_book = bool((ref.get("fuente") or "").strip())

    if tipo == "libro" and has_part and has_book:
        entry_type = "inbook"
    elif tipo == "libro":
        entry_type = "book"
    else:
        entry_type = "misc"

    lines = [f"@{entry_type}{{{key},"]

    autor = (ref.get("autor") or "").strip()
    if autor:
        lines.append(f"  author = {{{_bib_escape(autor)}}},")

    # Para book: title=fuente o titulo
    if entry_type == "book":
        title = (ref.get("fuente") or ref.get("titulo") or "").strip()
        if title:
            lines.append(f"  title = {{{_bib_escape(title)}}},")
    else:
        # inbook: title=parte, booktitle/título del libro no es estándar; se usa "booktitle" a veces, pero mejor:
        part_title = (ref.get("titulo") or "").strip()
        book_title = (ref.get("fuente") or "").strip()
        if part_title:
            lines.append(f"  title = {{{_bib_escape(part_title)}}},")
        if book_title:
            lines.append(f"  booktitle = {{{_bib_escape(book_title)}}},")

    editorial = (ref.get("editorial") or "").strip()
    if editorial:
        lines.append(f"  publisher = {{{_bib_escape(editorial)}}},")

    anio = ref.get("anio")
    if anio:
        lines.append(f"  year = {{{_bib_escape(anio)}}},")

    paginas = (ref.get("paginas") or "").strip()
    if paginas:
        lines.append(f"  pages = {{{_bib_escape(paginas)}}},")

    # Campos extra no estándar pero útiles como note
    extra = []
    if ref.get("capitulo"):
        extra.append(f"capitulo: {ref['capitulo']}")
    if ref.get("seccion"):
        extra.append(f"seccion: {ref['seccion']}")
    if extra:
        lines.append(f"  note = {{{_bib_escape('; '.join(extra))}}},")

    lines.append("}")
    return "\n".join(lines), key



# -----------------------------
# Public API
# -----------------------------
@dataclass(frozen=True)
class QuartoExportResult:
    build_dir: Path
    written_files: List[Path]


class QuartoBookExporter:
    """
    Copies a Quarto Book template into a build directory and writes QMD files
    for the provided concepts.

    Important: Concepts must already include 'contenido_latex' (e.g., enriched from latex_documents).
    """

    def __init__(self, template_dir: Path, build_dir: Path):
        self.template_dir = Path(template_dir)
        self.build_dir = Path(build_dir)

    def prepare_build(self, force: bool = False) -> None:
        if not self.template_dir.exists():
            raise FileNotFoundError(f"Template dir not found: {self.template_dir}")

        if self.build_dir.exists():
            if not force:
                raise FileExistsError(
                    f"Build dir exists: {self.build_dir} (use force=True)"
                )
            shutil.rmtree(self.build_dir)

        shutil.copytree(self.template_dir, self.build_dir)

    def export_concepts(self, concepts: Iterable[Dict[str, Any]]) -> QuartoExportResult:
        written: List[Path] = []
        concepts = list(concepts)

        bib_entries: list[str] = []
        seen: set[str] = set()

        # 1) construir bibliografía global
        for c in concepts:
            res = referencia_to_bibtex(c)
            if res:
                bibtex, key = res
                if key not in seen:
                    bib_entries.append(bibtex)
                    bib_entries.append("")
                    seen.add(key)
                c["_cite_key"] = key
        # escribir references.bib
        bib_path = self.build_dir / "references.bib"
        bib_path.write_text("\n".join(bib_entries), encoding="utf-8")

        # 2) generar QMDs
        for c in concepts:
            title = _safe_title(c)
            stem = _file_stem(c)
            out_dir = self.build_dir / _route(c)
            out_dir.mkdir(parents=True, exist_ok=True)
            bib_path = Path("references.bib")
            rel_bib = os.path.relpath(
                self.build_dir / bib_path,
                out_dir)
            qmd = concept_to_qmd(c, bibfile=rel_bib)
            out = out_dir / f"{stem}.qmd"
            out.write_text(qmd, encoding="utf-8")
            written.append(out)
        return QuartoExportResult(self.build_dir, written)
