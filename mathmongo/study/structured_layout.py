"""Measure canonical Cornell/CPI geometry inside the existing restricted TeX runner."""

from importlib import import_module

from editor.note_export import build_note_latex_bundle
from editor.structured_note_resources import prepare_structured_note_images
from editor.structured_note_resources import structured_image_paths
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.study.document_export import compile_project


def measured_project(note, database, spec, document):
    """Return a real geometry report and its scaled portable project, without writes."""
    layout = import_module("editor." + spec.family + ".layout")
    renderer = import_module("editor." + spec.family + ".renderer")
    generate = getattr(renderer, "generate_" + spec.family + "_document_tex")
    # Unknown historical source stays recoverable; regenerating a divergent body is unsafe.
    canonical_body = import_module("editor." + spec.family + ".models").generate_latex_body
    if note.get("latex_body", "") != canonical_body(document):
        raise AdvancedReaderError(
            "structured_source_conflict",
            "La fuente histórica difiere de sus regiones. Descarga TEX y conserva el original antes de regenerar un PDF.",
            status_code=409,
        )
    images = prepare_structured_note_images(note, db=database)
    paths = structured_image_paths(images)
    generated = generate(document, asset_paths_by_id=paths)
    preamble = generated.split(r"\begin{document}", 1)[0]
    pages = []
    for index, page in enumerate(document.ordered_pages(), start=1):
        # One bounded job per page keeps all three measurements in the diagnostic tail.
        arguments = (document, (page,)) if spec.family == "cpi" else ((page,),)
        source = layout._measurement_source(
            *arguments, latex_preamble=preamble, asset_paths_by_id=paths
        )
        source = source.replace(r"\end{document}", r"\null\end{document}")
        bundle = build_note_latex_bundle(note, db=database, source_tex=source, image_assets=images)
        measured = compile_project(bundle)
        values = layout._parse_measurements(measured.diagnostic)
        if measured.status != "ready" or any((1, key) not in values for key in layout.REGION_ORDER):
            raise AdvancedReaderError(
                "structured_fit_failed",
                "No se pudo comprobar el ajuste de la página. Revisa sus macros y recursos o descarga TEX. La nota se conserva.",
                status_code=422,
            )
        compute = (
            layout._cpi_region_fit_from_cornell
            if spec.family == "cpi"
            else layout.compute_region_fit
        )
        regions = tuple(
            compute(region=key, min_region_scale=layout.MIN_REGION_SCALE, **values[(1, key)])
            for key in layout.REGION_ORDER
        )
        report = (
            layout.CpiPageFitReport(page_number=index, regions=regions)
            if spec.family == "cpi"
            else layout.PageFitReport(page_id=page.page_id, page_number=index, regions=regions)
        )
        pages.append(report)
    report_type = layout.CpiFitReport if spec.family == "cpi" else layout.CornellFitReport
    fit = report_type(pages=tuple(pages), min_region_scale=layout.MIN_REGION_SCALE)
    return fit, build_note_latex_bundle(
        note,
        db=database,
        source_tex=generate(document, fit_report=fit, asset_paths_by_id=paths),
        image_assets=images,
    )


def fit_response(fit):
    """Translate measured results into an activity-level, actionable status."""
    return {
        **fit.to_dict(),
        "has_overflow": fit.has_overflow,
        "message": (
            "Una región no cabe con una escala legible. Distribuye su contenido en otra página y vuelve a comprobar."
            if fit.has_overflow
            else "Las regiones caben en la plantilla. El contenido guardado permanece intacto."
        ),
    }
