"""Scoped HTTP adapters for the historical Cuaderno activities."""

from typing import Annotated

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.study.activities import NotebookActivities
from mathmongo.study.activity_models import ActivityWrite
from mathmongo.study.activity_models import Kind
from mathmongo.study.routes import scoped


class ActivitySelection(BaseModel):
    """Explicit bounded selection, never a client-provided query or collection."""

    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=200
    )


def build_activity_router():
    """Keep list/open read-only and all writes behind the existing origin/library guards."""
    router = APIRouter(prefix="/api/study/v1/activities")

    @router.get("/{kind}")
    def listing(
        kind: Kind,
        request: Request,
        q: str = Query("", max_length=200),
        project: str = Query("", max_length=500),
        status: str = Query("", max_length=40),
        page: int = Query(1, ge=1, le=1000000),
    ):
        return NotebookActivities(scoped(request).db, kind).listing(q, project, status, page)

    @router.get("/{kind}/{identity}")
    def opened(kind: Kind, identity: str, request: Request):
        service = NotebookActivities(scoped(request).db, kind)
        return service.describe(service.opened(identity))

    @router.post("/{kind}/export")
    def export(kind: Kind, payload: ActivitySelection, request: Request):
        content = NotebookActivities(scoped(request).db, kind).export(payload.ids)
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="mathmongo-{kind}.csv"'},
        )

    def save(kind, identity, payload, request):
        service = NotebookActivities(scoped(request).db, kind)
        try:
            if identity:
                if payload.revision is None:
                    raise AdvancedReaderError(
                        "activity_revision",
                        "Vuelve a abrir el registro antes de editarlo. El borrador se conserva.",
                        status_code=409,
                    )
                return service.update(identity, payload.revision, payload.fields)
            return service.create(payload.request_id, payload.fields)
        except ValidationError as error:
            messages = "; ".join(
                ".".join(str(part) for part in item["loc"]) + ": " + item["msg"]
                for item in error.errors()
            )
            raise AdvancedReaderError(
                "activity_fields", "Revisa los campos del registro: " + messages, status_code=422
            ) from None

    @router.post("/{kind}")
    def create(kind: Kind, payload: ActivityWrite, request: Request):
        return save(kind, None, payload, request)

    @router.post("/{kind}/{identity}")
    def update(kind: Kind, identity: str, payload: ActivityWrite, request: Request):
        return save(kind, identity, payload, request)

    return router
