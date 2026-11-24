"""Preview and selective import using canonical BibTeX parsing and duplicate decisions."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import UUID

from fastapi import APIRouter
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from mathmongo.bibliography_lookup.capture import ReferenceCapture
from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.study.library_management import rejected
from mathmongo.study.preparation import AuthoringPreparation
from mathmongo.study.routes import scoped


class BibtexRequest(BaseModel):
    """The same operation identity and paste survive partial success or a lost reply."""

    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    content: str = Field(min_length=1, max_length=200000)
    selected: list[int] = Field(default_factory=list, max_length=100)


def preview_for(catalog, payload):
    """Derive stable reference IDs from the reviewed operation and entry content."""
    preview = catalog.preview_bibtex(payload.content)
    candidates = []
    for candidate in preview.candidates:
        data = dict(candidate["reference_data"])
        identity = ":".join(
            [str(payload.operation_id), str(candidate["entry_index"]), candidate["raw_sha256"]]
        )
        data["reference_id"] = "ref_" + str(
            UUID(bytes=hashlib.sha256(identity.encode()).digest()[:16], version=4)
        )
        candidates.append({**candidate, "reference_data": data})
    return replace(preview, candidates=tuple(candidates))


def build_bibtex_router():
    """No remote fetch, implicit merge, path upload or unselected entry insertion."""
    router = APIRouter(prefix="/api/study/v1")

    @router.post("/sources/{source_id}/bibtex/preview")
    def preview(source_id: str, payload: BibtexRequest, request: Request):
        catalog = SourceCatalogService(scoped(request).db)
        if catalog.sources.get_by_id(source_id) is None:
            raise rejected()
        return preview_for(catalog, payload).to_dict()

    @router.post("/sources/{source_id}/bibtex/import")
    def import_selected(source_id: str, payload: BibtexRequest, request: Request):
        app = scoped(request)
        if AuthoringPreparation(app.db).inspect()["state"] != "ready":
            raise rejected(
                "Prepara la biblioteca antes de importar referencias. El texto BibTeX se conserva."
            )
        catalog = SourceCatalogService(app.db)
        source = catalog.sources.get_by_id(source_id)
        if source is None or source.status.value != "active":
            raise rejected("Elige una fuente activa antes de importar referencias.")
        preview = preview_for(catalog, payload)
        candidates = {item["entry_index"]: item for item in preview.candidates}
        if not payload.selected or any(index not in candidates for index in payload.selected):
            raise rejected(
                "Selecciona entradas válidas de la vista previa. No se importaron las otras."
            )
        results = []
        capture = ReferenceCapture(app.db, MetadataLookup())
        for index in dict.fromkeys(payload.selected):
            data = candidates[index]["reference_data"]
            if catalog.references.get_by_id(data["reference_id"]) is not None:
                item = capture.execute(
                    {
                        "request_id": str(payload.operation_id),
                        "action": "save",
                        "source_id": source_id,
                        "reference_data": data,
                    }
                )
                results.append(
                    {
                        "entry_index": index,
                        "status": item["status"],
                        "reference_id": data["reference_id"],
                    }
                )
            else:
                result = catalog.import_selected_bibtex_candidates(
                    preview, [index], source_ids=[source_id]
                )
                imported = (
                    result.value.items[0].result if result.value and result.value.items else result
                )
                results.append(
                    {
                        "entry_index": index,
                        "status": "saved"
                        if imported.persisted
                        else "duplicates"
                        if imported.duplicates
                        else "conflict",
                        "reference_id": data["reference_id"],
                    }
                )
        return {
            "items": results,
            "saved": sum(item["status"] == "saved" for item in results),
            "message": "Revisa el resultado por entrada. Sólo se procesó la selección; no se fusionaron coincidencias.",
        }

    return router
