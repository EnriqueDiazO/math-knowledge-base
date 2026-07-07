"""Editable LaTeX project exporter for Cornell notes."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from editor.cornell.identity import cornell_attribution_latex
from editor.cornell.identity import cornell_watermark_latex
from editor.cornell.latex_compat import cornell_latex_compat_preamble
from editor.cornell.media import _assets_by_id_from_db
from editor.cornell.media import _normalize_assets_by_id
from editor.cornell.media import _safe_asset_source_path
from editor.cornell.media import cornell_document_image_ids
from editor.cornell.media import latex_uses_svg_paths
from editor.cornell.media import render_cornell_region_latex
from editor.cornell.media import safe_cornell_asset_filename
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from mathkb_config import PROJECT_ROOT

REGION_EXPORTS = {
    "cue": {
        "master": "Izquierda.tex",
        "template": "A.tex",
        "content": "izquierda.tex",
        "pdf": "Izquierda.pdf",
        "paper_width": "2.4in",
        "paper_height": "9in",
    },
    "main": {
        "master": "Derecha.tex",
        "template": "B.tex",
        "content": "derecha.tex",
        "pdf": "Derecha.pdf",
        "paper_width": "6.1in",
        "paper_height": "9in",
    },
    "summary": {
        "master": "Abajo.tex",
        "template": "C.tex",
        "content": "abajo.tex",
        "pdf": "Abajo.pdf",
        "paper_width": "8.5in",
        "paper_height": "2in",
    },
}
HISTORICAL_CORNELL_DIR = PROJECT_ROOT / "CornellFormats" / "1 Notas matemáticas tipo cornel"
HISTORICAL_LINES_IMAGE = HISTORICAL_CORNELL_DIR / "lineas.png"
LINES_IMAGE_FILENAME = "lineas.png"
LINES_IMAGE_EXPORT_PATH = f"images/{LINES_IMAGE_FILENAME}"


@dataclass(frozen=True, slots=True)
class CornellProjectExportResult:
    """Filesystem paths for an exported editable Cornell LaTeX project."""

    project_dir: Path
    zip_path: Path
    metadata_path: Path


def safe_project_slug(value: object, fallback: str = "cornell_project") -> str:
    """Return a portable folder name derived from a note title."""
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_text).strip("._")
    return slug or fallback


def _escape_latex_text(value: str) -> str:
    replacements = {
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
    return "".join(replacements.get(character, character) for character in value)


def _resolve_project_images(
    document: CornellDocument,
    project_dir: Path,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    if not HISTORICAL_LINES_IMAGE.exists():
        raise FileNotFoundError(f"Historical Cornell lines image not found: {HISTORICAL_LINES_IMAGE}")
    shutil.copyfile(HISTORICAL_LINES_IMAGE, images_dir / LINES_IMAGE_FILENAME)

    image_ids = cornell_document_image_ids(document)
    if not image_ids:
        return {}

    resolved_assets = _normalize_assets_by_id(assets_by_id)
    if db is not None:
        resolved_assets.update(_assets_by_id_from_db(db, image_ids))
    missing = [asset_id for asset_id in image_ids if asset_id not in resolved_assets]
    if missing:
        raise ValueError(f"Cornell image asset not found: {', '.join(missing)}")

    latex_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for asset_id in image_ids:
        asset = resolved_assets[asset_id]
        source = _safe_asset_source_path(asset)
        safe_name = safe_cornell_asset_filename(asset)
        if safe_name in used_names:
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            safe_name = f"{stem}_{asset_id[:8]}{suffix}"
        used_names.add(safe_name)
        destination = images_dir / safe_name
        shutil.copyfile(source, destination)
        latex_paths[asset_id] = destination.relative_to(project_dir).as_posix()
    return latex_paths


def _common_preamble(*, paper_width: str, paper_height: str, include_svg: bool = False) -> str:
    svg_package = "\n\\usepackage{svg}" if include_svg else ""
    return dedent(
        rf"""
        \documentclass[12pt]{{article}}
        \usepackage[utf8]{{inputenc}}
        \usepackage[T1]{{fontenc}}
        \usepackage[paperwidth={paper_width},paperheight={paper_height},margin=0in]{{geometry}}
        \usepackage{{amsmath,amssymb,amsfonts}}
        \usepackage{{graphicx}}
        \usepackage{{adjustbox}}
        \usepackage[dvipsnames,svgnames]{{xcolor}}
        \usepackage{{tikz}}
        \usetikzlibrary{{calc}}
        """
        + svg_package
        + "\n"
        + cornell_latex_compat_preamble()
        + "\n"
        + r"""
        \pagestyle{empty}
        \setlength{\parindent}{0pt}
        \setlength{\parskip}{4pt}
        \newcommand{\CornellMainText}{\normalfont\color{black}\fontsize{10}{18.9}\selectfont}
        \newcommand{\CornellCueHeading}[1]{\begin{center}{\Huge\color{OliveGreen} #1}\end{center}}
        \newcommand{\cornellimage}[1]{\textbf{[Imagen Cornell: \detokenize{#1}]}}
        \newcommand{\CornellMainHeading}[1]{%
          \begin{minipage}{1mm}\rule{0pt}{2.1cm}\end{minipage}%
          \begin{minipage}{5.45in}{\Huge\color{RubineRed} #1}\end{minipage}\par%
        }
        \newcommand{\CornellSummaryHeading}[1]{{\color{blue}\bfseries\large #1}\par}
        """
    ).strip() + "\n"


def _main_background_preamble() -> str:
    return dedent(
        rf"""
        \AddToHook{{shipout/background}}{{%
          \begin{{tikzpicture}}[remember picture,overlay]
            \node[anchor=north west, inner sep=0pt, opacity=0.2]
              at ($(current page.north west)+(.1in,-1.11in)$)
              {{\includegraphics[width=6in]{{{LINES_IMAGE_EXPORT_PATH}}}}};
          \end{{tikzpicture}}%
        }}
        """
    ).strip() + "\n"


def _write_region_templates(project_dir: Path, *, asset_paths_by_id: Mapping[str, str]) -> None:
    include_svg = latex_uses_svg_paths(dict(asset_paths_by_id))
    for region_name, region in REGION_EXPORTS.items():
        preamble = _common_preamble(
            paper_width=region["paper_width"],
            paper_height=region["paper_height"],
            include_svg=include_svg,
        )
        if region_name == "main":
            preamble += "\n" + _main_background_preamble()
        (project_dir / region["template"]).write_text(
            preamble,
            encoding="utf-8",
        )


def _cue_content(page: CornellPage, body: str) -> str:
    heading = _escape_latex_text(page.cue.heading)
    return dedent(
        rf"""
        \thispagestyle{{empty}}
        \null
        \begin{{tikzpicture}}[remember picture,overlay]
          \node[anchor=north west, inner sep=0pt] at (current page.north west) {{%
            \begin{{minipage}}[t]{{2.4in}}
              \vspace*{{5mm}}
              \hspace*{{4mm}}\begin{{minipage}}[t]{{2.05in}}
                {{\setlength{{\fboxrule}}{{1pt}}\setlength{{\fboxsep}}{{3pt}}%
                \fcolorbox{{gray}}{{white}}{{%
                  \begin{{minipage}}{{1.93in}}
                    \CornellCueHeading{{{heading}}}
                  \end{{minipage}}%
                }}}}
                \par\vspace{{4mm}}
                \CornellMainText
                {body}
              \end{{minipage}}
            \end{{minipage}}%
          }};
        \end{{tikzpicture}}
        """
    ).strip() + "\n"


def _main_content(page: CornellPage, body: str) -> str:
    heading = _escape_latex_text(page.main.heading)
    return dedent(
        rf"""
        \thispagestyle{{empty}}
        \null
        \begin{{tikzpicture}}[remember picture,overlay]
          \node[anchor=north west, inner sep=0pt]
            at ($(current page.north west)+(.1in,0)$) {{%
            \begin{{minipage}}[t]{{6in}}
              \vspace*{{.2cm}}
              \hspace*{{4mm}}\begin{{minipage}}[t]{{5.52in}}
                \CornellMainHeading{{{heading}}}
                \CornellMainText
                {body}
              \end{{minipage}}
            \end{{minipage}}
          }};
        \end{{tikzpicture}}
        """
    ).strip() + "\n"


def _summary_content(page: CornellPage, body: str) -> str:
    heading = _escape_latex_text(page.summary.heading)
    return dedent(
        rf"""
        \thispagestyle{{empty}}
        \null
        \begin{{tikzpicture}}[remember picture,overlay]
          \node[anchor=north west, inner sep=0pt] at (current page.north west) {{%
            \begin{{minipage}}[t]{{8.5in}}
              \vspace*{{4mm}}
              \hspace*{{18mm}}\begin{{minipage}}[t]{{7.43in}}
                \CornellSummaryHeading{{{heading}}}
              \end{{minipage}}
              \par\vspace{{1mm}}
              \hspace*{{18mm}}\begin{{minipage}}[t]{{7.55in}}
                \raggedright
                \CornellMainText
                {body}
              \end{{minipage}}
            \end{{minipage}}%
          }};
        \end{{tikzpicture}}
        """
    ).strip() + "\n"


def _region_content(page: CornellPage, region_name: str, body: str) -> str:
    if region_name == "cue":
        return _cue_content(page, body)
    if region_name == "main":
        return _main_content(page, body)
    if region_name == "summary":
        return _summary_content(page, body)
    raise ValueError(f"Unknown Cornell region: {region_name!r}")


def _write_page_content(
    project_dir: Path,
    pages: tuple[CornellPage, ...],
    *,
    asset_paths_by_id: Mapping[str, str],
) -> None:
    content_dir = project_dir / "contenido"
    for index, page in enumerate(pages, start=1):
        page_dir = content_dir / f"pagina_{index:03d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        for region_name, region_info in REGION_EXPORTS.items():
            region = getattr(page, region_name)
            body = render_cornell_region_latex(
                region,
                region_name=region_name,
                asset_paths_by_id=asset_paths_by_id,
            )
            (page_dir / region_info["content"]).write_text(
                _region_content(page, region_name, body),
                encoding="utf-8",
            )


def _region_inputs(pages: tuple[CornellPage, ...], content_filename: str) -> str:
    inputs = []
    for index, _page in enumerate(pages, start=1):
        inputs.append(rf"\input{{contenido/pagina_{index:03d}/{content_filename}}}")
    return "\n\\newpage\n".join(inputs)


def _write_region_masters(project_dir: Path, pages: tuple[CornellPage, ...]) -> None:
    for region in REGION_EXPORTS.values():
        source = (
            rf"\input{{{region['template']}}}"
            "\n\\begin{document}\n"
            + _region_inputs(pages, region["content"])
            + "\n\\end{document}\n"
        )
        (project_dir / region["master"]).write_text(source, encoding="utf-8")


def _notas_page(
    document: CornellDocument,
    page_number: int,
    *,
    asset_paths_by_id: Mapping[str, str],
) -> str:
    return dedent(
        rf"""
        \null
        \begin{{tikzpicture}}[remember picture,overlay]
          \coordinate (SW) at (current page.south west);
          \coordinate (SE) at (current page.south east);
          \coordinate (NW) at (current page.north west);
          \coordinate (NE) at (current page.north east);

          {cornell_watermark_latex(document, asset_paths_by_id=asset_paths_by_id)}

          \node[anchor=north west, inner sep=0pt] at (NW)
            {{\includegraphics[page={page_number},width=2.4in,height=9in]{{Izquierda.pdf}}}};
          \node[anchor=north west, inner sep=0pt] at ($(NW)+(2.4in,0)$)
            {{\includegraphics[page={page_number},width=6.1in,height=9in]{{Derecha.pdf}}}};
          \node[anchor=south west, inner sep=0pt] at (SW)
            {{\includegraphics[page={page_number},width=8.5in,height=2in]{{Abajo.pdf}}}};
          \draw[line width=.4pt] ($(SW)+(0,2in)$) -- ($(SE)+(0,2in)$);
          \draw[line width=.4pt] ($(SW)+(2.4in,2in)$) -- ($(NW)+(2.4in,0)$);

          {cornell_attribution_latex(document)}
        \end{{tikzpicture}}
        """
    ).strip()


def _write_notas(
    project_dir: Path,
    document: CornellDocument,
    *,
    asset_paths_by_id: Mapping[str, str],
) -> None:
    pages = document.ordered_pages()
    page_bodies = [
        _notas_page(document, index, asset_paths_by_id=asset_paths_by_id)
        for index, _page in enumerate(pages, start=1)
    ]
    svg_package = "\n\\usepackage{svg}" if latex_uses_svg_paths(dict(asset_paths_by_id)) else ""
    source = (
        dedent(
            r"""
            \documentclass[12pt,letterpaper]{article}
            \usepackage[paperwidth=8.5in,paperheight=11in,margin=0in]{geometry}
            \usepackage{graphicx}
            \usepackage[dvipsnames,svgnames]{xcolor}
            \usepackage{tikz}
            \usetikzlibrary{calc}
            \pagestyle{empty}
            """
        ).strip()
        + svg_package
        + "\n\\begin{document}\n"
        + "\n\\newpage\n".join(page_bodies)
        + "\n\\end{document}\n"
    )
    (project_dir / "Notas.tex").write_text(source, encoding="utf-8")


def _metadata_payload(metadata: Mapping[str, Any], document: CornellDocument) -> dict[str, Any]:
    pages = document.ordered_pages()
    return {
        "title": str(metadata.get("title") or "Nueva nota Cornell"),
        "date": str(metadata.get("date") or ""),
        "project": str(metadata.get("project") or ""),
        "context": str(metadata.get("context") or ""),
        "tags": list(metadata.get("tags") or []),
        "note_format": CORNELL_NOTE_FORMAT,
        "schema_version": document.schema_version,
        "page_ids": [page.page_id for page in pages],
        "order": [{"page_id": page.page_id, "order": page.order} for page in pages],
        "attribution": document.attribution.to_dict(),
        "watermark": document.watermark.to_dict(),
    }


def _write_metadata(project_dir: Path, metadata: Mapping[str, Any], document: CornellDocument) -> Path:
    metadata_path = project_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(_metadata_payload(metadata, document), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _write_readme(project_dir: Path) -> None:
    (project_dir / "README.md").write_text(
        dedent(
            """
            # Proyecto Cornell LaTeX editable

            Compila los documentos regionales y despues el documento final:

            ```bash
            pdflatex Izquierda.tex
            pdflatex Derecha.tex
            pdflatex Abajo.tex
            pdflatex Notas.tex
            ```

            Edita los archivos en `contenido/pagina_NNN/` para modificar cada region.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _zip_project(project_dir: Path) -> Path:
    zip_path = project_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(project_dir.parent).as_posix())
    return zip_path


def export_cornell_project(
    document: CornellDocument,
    metadata: Mapping[str, Any],
    output_root: str | Path,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> CornellProjectExportResult:
    """Export a Cornell document as a standalone editable LaTeX project."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")

    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)
    project_dir = output_path / safe_project_slug(metadata.get("title") or "cornell_project")
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)

    asset_paths = _resolve_project_images(
        document,
        project_dir,
        db=db,
        assets_by_id=assets_by_id,
    )
    _write_region_templates(project_dir, asset_paths_by_id=asset_paths)
    _write_page_content(project_dir, pages, asset_paths_by_id=asset_paths)
    _write_region_masters(project_dir, pages)
    _write_notas(project_dir, document, asset_paths_by_id=asset_paths)
    metadata_path = _write_metadata(project_dir, metadata, document)
    _write_readme(project_dir)
    zip_path = _zip_project(project_dir)
    return CornellProjectExportResult(
        project_dir=project_dir,
        zip_path=zip_path,
        metadata_path=metadata_path,
    )
