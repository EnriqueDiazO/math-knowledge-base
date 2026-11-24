"""Compose canonical portable projects; compilation never gains host filesystem access."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from editor.latex_bundle import build_latex_project_bundle
from exporters_latex.sandbox import TEMPLATES
from exporters_latex.sandbox import compile_document
from exporters_latex.unified_document import build_master_tex
from exporters_latex.unified_document import render_concept_fragment
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.source_catalog.citations import CitationLocator
from mathmongo.source_catalog.citations import legacy_citation
from mathmongo.source_catalog.repository import ReferenceRepository

BLOCKS = json.loads((TEMPLATES.parent / "editor/ui/document_blocks.json").read_text())


def compose_project(concepts: list[dict], title="Documentos de estudio"):
    """Use existing fragment/master/bundle rules, with one authored body per item."""
    styles = {
        path.name: path.read_bytes()
        for path in TEMPLATES.iterdir()
        if not path.is_symlink() and path.suffix in {".sty", ".cls"}
    }
    full = []
    for concept in concepts:
        leading = concept["contenido_latex"].lstrip()
        while leading.startswith("%"):
            leading = leading.partition("\n")[2].lstrip()
        full.append(leading.startswith((r"\documentclass{", r"\documentclass[")))
    if any(full):
        if len(concepts) != 1:
            raise AdvancedReaderError(
                "export_preamble",
                "Exporta el documento completo por separado para conservar su preámbulo. No se combinaron ni eliminaron sus estructuras.",
                status_code=422,
            )
        body = concepts[0]["contenido_latex"]
        return build_latex_project_bundle(
            main_tex=body,
            raw_body=body,
            project_styles=styles,
            title=title,
            source_type="study_document",
        )
    fragments = {}
    records = []
    for index, concept in enumerate(concepts):
        path = f"concepts/document-{index + 1}.tex"
        fragments[path] = render_concept_fragment(concept, concept["contenido_latex"])
        records.append({"concept": concept, "input_path": path})
    master = build_master_tex(title, records, include_toc=False)
    if any(r"\begin{" + name + "}" in body for name in BLOCKS for body in fragments.values()):
        master = master.replace(
            r"\usepackage{coloredtheorem}",
            r"\usepackage{coloredtheorem}" + "\n" + r"\usepackage{notes}",
        )
    return build_latex_project_bundle(
        main_tex=master,
        raw_body="\n".join(c["contenido_latex"] for c in concepts),
        metadata={"title": title},
        project_styles=styles,
        additional_assets=fragments,
        title=title,
        source_type="study_selection",
    )


def compile_project(bundle):
    """Stage only files produced by the canonical in-memory bundle, then isolate TeX."""
    with zipfile.ZipFile(io.BytesIO(bundle.zip_bytes)) as archive:
        files = {
            str(Path(name).relative_to(Path(name).parts[0])): archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    main = files.pop("main.tex").decode("utf-8")
    return compile_document(main, files)


class StudyDocumentExport:
    """Resolve content on demand from the same configured library as the editor."""

    def __init__(self, application):
        """Bind without preparing indexes, copying files or altering records."""
        self.app = application

    def project(self, concept_keys, note_ids):
        """Each selected identity contributes its full body exactly once."""
        documents = []
        for key in dict.fromkeys(concept_keys):
            concept = self.app.maps.find(key)
            if concept is None:
                raise AdvancedReaderError(
                    "export_missing",
                    "Un concepto de la selección ya no está disponible. Actualiza la selección antes de exportar.",
                    status_code=409,
                )
            content = self.app.maps.latex(concept)
            if content is None:
                raise AdvancedReaderError(
                    "export_missing",
                    "El contenido de un concepto no está disponible. Revisa su ficha antes de exportar.",
                    status_code=409,
                )
            documents.append({**concept, "contenido_latex": content.get("contenido_latex", "")})
        for note_id in dict.fromkeys(note_ids):
            result = ReadingAnnotationService(self.app.db).get_note(note_id)
            if not result.completed or result.value is None:
                raise AdvancedReaderError(
                    "export_missing",
                    "Una nota ya no está disponible. Conserva el borrador y actualiza la selección.",
                    status_code=409,
                )
            note = result.value
            reference = (
                ReferenceRepository(self.app.db).get_by_id(note.reference_id)
                if note.reference_id
                else None
            )
            documents.append(
                {
                    "id": note.note_id,
                    "source": note.source_id,
                    "titulo": note.title,
                    "tipo": "nota",
                    "contenido_latex": note.body,
                    "referencia": legacy_citation(
                        reference, note.reference_locator or CitationLocator()
                    )
                    if reference
                    else {},
                }
            )
        if not documents:
            raise AdvancedReaderError(
                "export_empty",
                "Selecciona al menos un concepto o una nota guardada para exportar.",
                status_code=422,
            )
        return compose_project(documents)
