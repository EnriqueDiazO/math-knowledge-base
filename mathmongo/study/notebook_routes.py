"""Bounded Diario HTTP adapters; no Streamlit session or arbitrary database/path input."""

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
from mathmongo.study.notebook import Notebook
from mathmongo.study.routes import scoped

Text = Annotated[str, Field(max_length=500)]
ReferenceId = Annotated[str, Field(min_length=1, max_length=100)]


class DiaryChanges(BaseModel):
    """Only explicit, validated fields participate in an existing note's minimal edit."""

    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    latex_body: Annotated[str, Field(min_length=1, max_length=200000)] | None = None
    date: calendar_date | None = None
    project: Text | None = None
    context: Text | None = None
    tags: list[Text] | None = Field(default=None, max_length=100)
    catalog_reference_ids: list[ReferenceId] | None = Field(default=None, max_length=100)

    @field_validator("*", mode="before")
    @classmethod
    def explicit_value(cls, value):
        """Omitting a field preserves it; an explicit null is not a silent successful edit."""
        if value is None:
            raise ValueError(
                "Proporciona un valor explícito; usa una lista vacía para desvincular referencias."
            )
        return value

    @field_validator("title", "latex_body")
    @classmethod
    def nonempty(cls, value):
        """Check emptiness without normalizing canonical LaTeX."""
        if value is not None and not value.strip():
            raise ValueError("El título y el cuerpo deben tener contenido.")
        return value


class DiaryCreate(DiaryChanges):
    """A persisted request UUID identifies this one creation across retries."""

    request_id: UUID
    title: Annotated[str, Field(min_length=1, max_length=500)]
    latex_body: Annotated[str, Field(min_length=1, max_length=200000)]
    date: calendar_date
    project: Text = ""
    context: Text = "estudio"
    tags: list[Text] = Field(default_factory=list, max_length=100)
    catalog_reference_ids: list[ReferenceId] = Field(default_factory=list, max_length=100)


class DiaryEdit(BaseModel):
    """Bind the edit to the complete observed note rather than a second revision read."""

    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    changes: DiaryChanges


class DiaryExport(BaseModel):
    """Export the saved source with the canonical builder and isolated TeX runner."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["tex", "pdf"] = "tex"


def build_notebook_router():
    """Register user activities, with the same backend library/origin guards."""
    router = APIRouter(prefix="/api/study/v1/notebook")

    @router.get("")
    def listing(
        request: Request,
        q: str = Query("", max_length=200),
        project: str = Query("", max_length=500),
        source_id: str = Query("", max_length=100),
        page: int = Query(1, ge=1, le=1000000),
    ):
        return Notebook(scoped(request).db).summaries(
            q=q, project=project, source_id=source_id, page=page
        )

    @router.post("")
    def create(payload: DiaryCreate, request: Request):
        fields = payload.model_dump(mode="json", exclude={"request_id", "catalog_reference_ids"})
        return Notebook(scoped(request).db).create(
            payload.request_id, fields, payload.catalog_reference_ids
        )

    @router.get("/{identity}")
    def opened(identity: str, request: Request):
        return Notebook(scoped(request).db).detail(identity)

    @router.post("/{identity}")
    def update(identity: str, payload: DiaryEdit, request: Request):
        return Notebook(scoped(request).db).update(
            identity,
            payload.revision,
            payload.changes.model_dump(mode="json", exclude_unset=True, exclude_none=True),
        )

    @router.post("/{identity}/export")
    def export(identity: str, payload: DiaryExport, request: Request):
        bundle = Notebook(scoped(request).db).project(identity)
        if payload.format == "tex":
            return Response(
                bundle.zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": 'attachment; filename="mathmongo-cuaderno-tex.zip"'
                },
            )
        result = compile_project(bundle)
        if result.status != "ready":
            raise AdvancedReaderError(
                "notebook_export_failed",
                result.message
                + " Descarga el proyecto TEX para revisar las dependencias. La entrada se conserva.",
                status_code=422,
            )
        return Response(
            result.pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="mathmongo-cuaderno.pdf"'},
        )

    @router.post("/{identity}/actions")
    def action(identity: str, payload: NoteActionRequest, request: Request):
        return NoteActions(Notebook(scoped(request).db), "diary").execute(identity, payload.action, payload.request_id, payload.revision, payload.title)

    return router
