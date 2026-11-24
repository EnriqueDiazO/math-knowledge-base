"""Document exports and explicit isolated previews, within the authorized library."""

from __future__ import annotations

from typing import Annotated
from typing import Literal

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.study.document_export import StudyDocumentExport
from mathmongo.study.document_export import compile_project
from mathmongo.study.preview import DocumentPreviews
from mathmongo.study.preview import valid_cached_output
from mathmongo.study.routes import scoped


class ExportRequest(BaseModel):
    """Select canonical identities, never client-supplied database/file paths."""

    model_config = ConfigDict(extra="forbid")
    concept_keys: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=100
    )
    note_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100
    )
    format: Literal["pdf", "tex"] = "tex"
    include_technical_ids: bool = False


class PreviewRequest(BaseModel):
    """A fragment plus explicit macros; both contribute to the cache identity."""

    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=200000)
    macros: str = Field(default="", max_length=100000)
    refresh: bool = False
    kind: Literal["figure", "document"] = "figure"
    title: str = Field(default="Documento", max_length=500)

    @model_validator(mode="after")
    def document_owns_preamble(self):
        """Full drafts own their macros; never silently ignore a second preamble."""
        if self.kind == "document" and self.macros:
            raise ValueError("Incluye las macros en la fuente completa del documento.")
        return self


def build_document_router():
    """Use the same scope/origin/body guards as the other study activities."""
    router = APIRouter(prefix="/api/study/v1")

    @router.post("/export")
    def export(payload: ExportRequest, request: Request):
        bundle = StudyDocumentExport(scoped(request)).project(
            payload.concept_keys,
            payload.note_ids,
            include_technical_ids=payload.include_technical_ids,
        )
        if payload.format == "tex":
            return Response(
                bundle.zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="mathmongo-documentos-tex.zip"'
                },
            )
        result = compile_project(bundle)
        if result.status != "ready":
            raise AdvancedReaderError(
                "export_failed",
                result.message
                + " Puedes descargar el proyecto TEX para revisar macros y recursos.",
                status_code=422,
            )
        return Response(
            result.pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="mathmongo-documentos.pdf"'},
        )

    @router.post("/document-previews")
    def preview(payload: PreviewRequest, request: Request):
        app = scoped(request)
        return DocumentPreviews(app.library_id).create(
            payload.source,
            payload.macros,
            refresh=payload.refresh,
            kind=payload.kind,
            title=payload.title,
        )

    @router.get("/document-previews/{identifier}/{extension}")
    def image(identifier: str, extension: str, request: Request):
        app = scoped(request)
        try:
            path = DocumentPreviews(app.library_id).output(identifier, extension)
            if not valid_cached_output(
                path, b"\x89PNG\r\n\x1a\n" if extension == "png" else b"%PDF-"
            ):
                raise ValueError("Incomplete preview output")
            content = path.read_bytes()
        except (ValueError, OSError):
            raise AdvancedReaderError(
                "preview_missing",
                "La vista previa no está disponible. Vuelve a generarla; el código original se conserva.",
                status_code=404,
            ) from None
        return Response(
            content, media_type="image/png" if extension == "png" else "application/pdf"
        )

    return router
