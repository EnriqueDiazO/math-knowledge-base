"""Explicit management HTTP adapters for Library; all writes use canonical services."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from mathmongo.study.library_management import LibraryManagement
from mathmongo.study.library_management import rejected
from mathmongo.study.preparation import AuthoringPreparation
from mathmongo.study.routes import scoped


class EditRecord(BaseModel):
    """A bounded metadata change tied to the version opened by the user."""

    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=64, max_length=64)
    changes: dict = Field(max_length=30)
    acknowledge_shared: bool = False


class ChangeState(BaseModel):
    """Archiving retains both the object and physical document bytes."""

    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=64, max_length=64)
    status: Literal["active", "archived"]


def management(request, *, write=False):
    """Resolve one immutable backend library, not a client database name."""
    app = scoped(request)
    if write and AuthoringPreparation(app.db).inspect()["state"] != "ready":
        raise rejected(
            "Prepara la biblioteca antes de guardar estos datos. El borrador se conserva."
        )
    return LibraryManagement(app, request.app.state.advanced_reader_dependencies.document_service)


def build_library_router():
    """Keep maintenance and arbitrary MongoDB queries out of user routes."""
    router = APIRouter(prefix="/api/study/v1")

    @router.get("/sources/{source_id}/profile")
    def source(source_id: str, request: Request):
        return management(request).source(source_id)

    @router.post("/sources/{source_id}/profile")
    def edit_source(source_id: str, payload: EditRecord, request: Request):
        return management(request, write=True).edit_source(
            source_id, payload.changes, payload.revision
        )

    @router.post("/sources/{source_id}/state")
    def source_state(source_id: str, payload: ChangeState, request: Request):
        return management(request, write=True).state(
            "source", source_id, source_id, payload.status, payload.revision
        )

    @router.get("/sources/{source_id}/references")
    def references(
        source_id: str,
        request: Request,
        q: str = Query("", max_length=200),
        page: int = Query(1, ge=1),
    ):
        service = management(request)
        service.source(source_id)
        repository = service.catalog.references
        result = (
            repository.search(q, source_id=source_id, page=page, page_size=20)
            if q.strip()
            else repository.list(source_id=source_id, page=page, page_size=20)
        )
        return {
            "items": [
                {
                    "reference_id": item.reference_id,
                    "title": item.title,
                    "status": item.status.value,
                }
                for item in result.items
            ],
            "total": result.total,
            "page": page,
        }

    @router.get("/sources/{source_id}/references/{identity}")
    def reference(source_id: str, identity: str, request: Request):
        return management(request).reference(identity, source_id)

    @router.post("/sources/{source_id}/references/{identity}")
    def edit_reference(source_id: str, identity: str, payload: EditRecord, request: Request):
        service = management(request, write=True)
        current = service.reference(identity, source_id)
        if len(current["source_ids"]) > 1 and not payload.acknowledge_shared:
            raise rejected(
                "Esta referencia está compartida. Confirma que sus cambios se aplicarán a todas las fuentes vinculadas."
            )
        return service.edit_reference(identity, source_id, payload.changes, payload.revision)

    @router.post("/sources/{source_id}/references/{identity}/detach")
    def detach(source_id: str, identity: str, payload: EditRecord, request: Request):
        return management(request, write=True).detach_reference(
            identity, source_id, payload.revision
        )

    @router.get("/sources/{source_id}/documents/{identity}")
    def document(source_id: str, identity: str, request: Request):
        return management(request).document(identity, source_id)

    @router.post("/sources/{source_id}/documents/{identity}")
    def edit_document(source_id: str, identity: str, payload: EditRecord, request: Request):
        return management(request, write=True).edit_document(
            identity, source_id, payload.changes, payload.revision
        )

    @router.post("/sources/{source_id}/documents/{identity}/state")
    def document_state(source_id: str, identity: str, payload: ChangeState, request: Request):
        return management(request, write=True).state(
            "document", identity, source_id, payload.status, payload.revision
        )

    return router
