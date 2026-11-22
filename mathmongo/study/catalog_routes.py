"""Explicit catalog activities; canonical services own validation and persistence."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.bibliography_lookup.capture import ReferenceCapture
from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.study.preparation import AuthoringPreparation
from mathmongo.study.routes import PreparationRequest
from mathmongo.study.routes import scoped


class NewSource(BaseModel):
    """A source identity is stable across lost acknowledgements."""

    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    name: str = Field(min_length=1, max_length=500)
    source_type: SourceType = SourceType.OTHER
    description: str = Field(default="", max_length=10000)


class BibliographyRequest(BaseModel):
    """Only proposal and explicit capture actions accepted by ReferenceCapture."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    action: str = Field(pattern="^(identifier|edition|title|save)$")
    query: str = Field(default="", max_length=500)
    author: str = Field(default="", max_length=300)
    source_id: str = Field(default="", max_length=100)
    existing_reference_id: str = Field(default="", max_length=100)
    reference_data: dict | None = None


class WebDocumentRequest(BaseModel):
    """Store an explicit URL without fetching the remote page."""

    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    reference_id: str | None = None


def document_response(result):
    """Expose only a confirmed document identity; sanitize internal diagnostics."""
    if not result.completed or result.value is None:
        raise AdvancedReaderError(
            "document_rejected",
            "No se pudo asociar el documento. Revisa su formato, la fuente y la referencia; el archivo original se conserva.",
            status_code=409,
        )
    return {
        "document_id": result.value.document_id,
        "title": result.value.title,
        "kind": result.value.kind.value,
    }


def build_catalog_router():
    """Bind writes to the active library and existing same-origin middleware."""
    router = APIRouter(prefix="/api/study/v1")

    @router.get("/catalog/preparation")
    def preparation(request: Request):
        return AuthoringPreparation(scoped(request).db).inspect()

    @router.post("/catalog/prepare")
    def prepare(payload: PreparationRequest, request: Request):
        service = AuthoringPreparation(scoped(request).db)
        if payload.version != service.inspect()["version"]:
            raise AdvancedReaderError(
                "preparation_changed",
                "La preparación cambió. Vuelve a comprobarla antes de continuar.",
                status_code=409,
            )
        return service.prepare(payload.version)

    @router.post("/sources")
    def create_source(payload: NewSource, request: Request):
        app = scoped(request)
        if AuthoringPreparation(app.db).inspect()["state"] != "ready":
            raise AdvancedReaderError(
                "authoring_preparation",
                "Prepara la biblioteca antes de crear una fuente. El borrador se conserva.",
                status_code=409,
            )
        catalog = SourceCatalogService(app.db)
        try:
            candidate = Source(
                source_id="src_" + str(payload.operation_id),
                name=payload.name,
                source_type=payload.source_type,
                description=payload.description,
            )
        except ValidationError:
            raise AdvancedReaderError(
                "invalid_source", "Escribe un nombre válido para la fuente.", status_code=422
            ) from None
        present = catalog.sources.get_by_id(candidate.source_id)
        if present is not None:
            if present.status.value != "active":
                raise AdvancedReaderError(
                    "source_conflict",
                    "La fuente del intento está archivada. Revisa su ficha; no se reactivó automáticamente.",
                    status_code=409,
                )
            if any(
                getattr(present, field) != getattr(candidate, field)
                for field in ("name", "source_type", "description")
            ):
                raise AdvancedReaderError(
                    "source_conflict",
                    "El intento pertenece a otra ficha. Conserva el borrador y revisa la fuente existente.",
                    status_code=409,
                )
            stored = present
        else:
            result = catalog.create_source(candidate)
            if not result.persisted or result.value is None:
                raise AdvancedReaderError(
                    "source_duplicate",
                    "La fuente no se creó. Revisa las coincidencias en Biblioteca o corrige su nombre; el borrador se conserva.",
                    status_code=409,
                )
            stored = result.value
        confirmed = catalog.sources.get_by_id(stored.source_id)
        if confirmed is None:
            raise AdvancedReaderError(
                "source_unconfirmed",
                "No se confirmó la fuente. Reintenta el mismo envío.",
                status_code=503,
            )
        return {
            "source_id": confirmed.source_id,
            "name": confirmed.name,
            "source_type": confirmed.source_type.value,
        }

    @router.post("/bibliography")
    def bibliography(payload: BibliographyRequest, request: Request):
        app = scoped(request)
        if payload.action == "save" and AuthoringPreparation(app.db).inspect()["state"] != "ready":
            raise AdvancedReaderError(
                "authoring_preparation",
                "Prepara la biblioteca antes de guardar referencias. No se modificó la ficha.",
                status_code=409,
            )
        return ReferenceCapture(app.db, MetadataLookup()).execute(
            payload.model_dump(mode="json", exclude_none=True)
        )

    @router.post("/sources/{source_id}/documents/web")
    def web(source_id: str, payload: WebDocumentRequest, request: Request):
        scoped(request)
        service = request.app.state.advanced_reader_dependencies.document_service
        return document_response(
            service.create_web_document(
                source_id=source_id,
                title=payload.title,
                url_raw=payload.url,
                reference_id=payload.reference_id,
                document_id="doc_" + str(payload.operation_id),
            )
        )

    @router.post("/sources/{source_id}/documents/pdf")
    async def pdf(
        source_id: str,
        request: Request,
        operation_id: UUID,
        title: str = Query(..., min_length=1, max_length=500),
        filename: str = Query(..., min_length=1, max_length=255),
        reference_id: str | None = None,
    ):
        scoped(request)
        service = request.app.state.advanced_reader_dependencies.document_service
        return document_response(
            service.create_pdf_document(
                source_id=source_id,
                title=title,
                original_filename=filename,
                pdf_bytes=await request.body(),
                reference_id=reference_id,
                document_id="doc_" + str(operation_id),
            )
        )

    return router
