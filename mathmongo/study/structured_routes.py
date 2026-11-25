"""Explicit Cornell/CPI HTTP activities with existing library/origin and resource guards."""

from datetime import date as calendar_date
from typing import Annotated
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.study.document_export import compile_project
from mathmongo.study.note_action_models import NoteActionRequest
from mathmongo.study.note_actions import NoteActions
from mathmongo.study.note_images import NoteImages
from mathmongo.study.routes import scoped
from mathmongo.study.structured_layout import fit_response
from mathmongo.study.structured_layout import measured_project
from mathmongo.study.structured_notes import StructuredNotes

Family = Literal["cornell", "cpi"]
Text = Annotated[str, Field(max_length=500)]


class StructuredMetadata(BaseModel):
    """The activity edits academic metadata deliberately, never arbitrary Mongo fields."""

    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=500)]
    date: calendar_date
    project: Text = ""
    context: Text = "estudio"
    tags: list[Text] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def title_has_content(cls, value):
        """Validate without normalizing a historical title."""
        if not value.strip():
            raise ValueError("Escribe un título para la nota.")
        return value


class StructuredCreate(BaseModel):
    """Bounded source structures are validated by their canonical dataclass models."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    metadata: StructuredMetadata
    document: dict = Field(max_length=20)


class StructuredMetadataEdit(StructuredMetadata):
    """Omitted historical metadata stays absent instead of materializing defaults."""

    title: Annotated[str, Field(min_length=1, max_length=500)] = ""
    date: calendar_date | None = None


class StructuredEdit(BaseModel):
    """A full document projection is tied to one exact observed note revision."""

    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    metadata: StructuredMetadataEdit
    document: dict = Field(max_length=20)
    page_origins: list[str | int | None] | None = Field(default=None, max_length=30)


class StructuredExport(BaseModel):
    """Only saved content is exported; user-supplied filesystem paths are not accepted."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["tex", "pdf"] = "tex"


def build_structured_router():
    """Expose the two academic activities separately from the free-form Diario endpoint."""
    router = APIRouter(prefix="/api/study/v1/structured")

    @router.get("/{family}")
    def listing(
        family: Family,
        request: Request,
        q: str = Query("", max_length=200),
        page: int = Query(1, ge=1, le=1000000),
        project: str = Query("", max_length=500),
        context: str = Query("", max_length=500),
        date_from: calendar_date | None = None,
        date_to: calendar_date | None = None,
    ):
        notes = StructuredNotes(scoped(request).db, family)
        if date_from and date_to and date_from > date_to:
            raise AdvancedReaderError("invalid_note_filter", "La fecha inicial debe ser anterior o igual a la final. Corrige el intervalo y vuelve a buscar.", status_code=422)
        return notes.listing(q, page, project=project, context=context, date_from=date_from, date_to=date_to)

    @router.post("/{family}")
    def create(family: Family, payload: StructuredCreate, request: Request):
        return StructuredNotes(scoped(request).db, family).create(
            payload.request_id, payload.metadata.model_dump(mode="json"), payload.document
        )

    @router.get("/{family}/references/{reference_id}")
    def reference(family: Family, reference_id: str, request: Request):
        return StructuredNotes(scoped(request).db, family).reference(reference_id)

    @router.get("/{family}/{identity}")
    def detail(family: Family, identity: str, request: Request):
        return StructuredNotes(scoped(request).db, family).detail(identity)

    @router.post("/{family}/{identity}")
    def update(family: Family, identity: str, payload: StructuredEdit, request: Request):
        return StructuredNotes(scoped(request).db, family).update(
            identity,
            payload.revision,
            payload.metadata.model_dump(mode="json", exclude_unset=True),
            payload.document,
            payload.page_origins,
        )

    @router.post("/{family}/{identity}/export")
    def export(family: Family, identity: str, payload: StructuredExport, request: Request):
        notes = StructuredNotes(scoped(request).db, family)
        if payload.format == "tex":
            bundle = notes.project(identity)
            return Response(
                bundle.zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="mathmongo-{family}-tex.zip"'
                },
            )
        note = notes.opened(identity)
        fit, bundle = measured_project(note, notes.db, notes.spec, notes.parse(note[family]))
        if fit.has_overflow:
            raise AdvancedReaderError(
                "structured_overflow", fit_response(fit)["message"], status_code=422
            )
        result = compile_project(bundle)
        if result.status != "ready":
            raise AdvancedReaderError(
                "structured_export_failed",
                result.message + " Descarga TEX para revisar los recursos; la nota se conserva.",
                status_code=422,
            )
        return Response(
            result.pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="mathmongo-{family}.pdf"'},
        )

    @router.get("/{family}/{identity}/images")
    def images(family: Family, identity: str, request: Request):
        return NoteImages(StructuredNotes(scoped(request).db, family), identity).listing()

    @router.get("/{family}/{identity}/images/{asset_id}")
    def image(family: Family, identity: str, asset_id: str, request: Request):
        from mathmongo.study.note_images import MIME_TYPES

        path = NoteImages(StructuredNotes(scoped(request).db, family), identity).path(asset_id)
        return Response(path.read_bytes(), media_type=MIME_TYPES[path.suffix.lower()], headers={"Cache-Control": "no-store"})

    @router.post("/{family}/{identity}/actions")
    def action(family: Family, identity: str, payload: NoteActionRequest, request: Request):
        notes = StructuredNotes(scoped(request).db, family)
        return NoteActions(notes, family).execute(identity, payload.action, payload.request_id, payload.revision, payload.title)

    @router.post("/{family}/{identity}/fit")
    def fit(family: Family, identity: str, request: Request):
        notes = StructuredNotes(scoped(request).db, family)
        note = notes.opened(identity)
        report, _ = measured_project(note, notes.db, notes.spec, notes.parse(note[family]))
        return fit_response(report)

    return router
