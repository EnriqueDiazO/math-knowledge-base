"""Same-origin activity API delegating writes to canonical, recoverable services."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.knowledge_map.service import CONCEPT_TYPES
from mathmongo.knowledge_map.service import Intent
from mathmongo.study.application import StudyApplication
from schemas.schemas import TipoRelacion


class PreparationRequest(BaseModel):
    """Only an inspected contract version can authorize compatible preparation."""

    model_config = ConfigDict(extra="forbid")
    version: str


def application(request: Request) -> StudyApplication:
    """Resolve the configured library lazily; never accept database names or URIs."""
    if not hasattr(request.app.state, "study_application"):
        database = getattr(
            request.app.state.advanced_reader_dependencies.document_service, "database", None
        )
        if database is None:
            raise AdvancedReaderError(
                "study_unavailable", "La biblioteca no está disponible.", status_code=503
            )
        request.app.state.study_application = StudyApplication(database)
    return request.app.state.study_application


def scoped(request: Request) -> StudyApplication:
    """Reject requests that were prepared for another library before any write."""
    app = application(request)
    if request.headers.get("X-MathMongo-Library") != app.library_id:
        raise AdvancedReaderError(
            "library_changed",
            "La biblioteca cambió. Conserva el borrador y vuelve a abrirla.",
            status_code=409,
        )
    return app


def optional_reader_scope(request: Request) -> None:
    """Keep old reader clients compatible; bind independent clients to their library."""
    if request.headers.get("X-MathMongo-Library"):
        scoped(request)


def build_study_router() -> APIRouter:
    """Register bounded activity queries separately from reading media contracts."""
    router = APIRouter(prefix="/api/study/v1")

    @router.get("/context")
    def context(request: Request):
        return application(request).context()

    @router.post("/prepare")
    def prepare(payload: PreparationRequest, request: Request):
        app = scoped(request)
        status = app.preparation.inspect()
        if payload.version != status.version:
            raise AdvancedReaderError(
                "preparation_changed",
                "La función cambió. Vuelve a comprobar su estado.",
                status_code=409,
            )
        app.preparation.prepare(status)
        return app.context()  # always a new backend read-back, never a guessed success

    @router.get("/library")
    def library(request: Request, q: str = Query("", max_length=200), page: int = Query(1, ge=1), status: str = Query("active", pattern="^(active|archived)$"), source_type: str = Query("", max_length=40)):
        return scoped(request).library(q, page, status=status, source_type=source_type)

    @router.get("/sources/{source_id}")
    def source(source_id: str, request: Request, document_page: int = Query(1,ge=1), reference_page: int = Query(1,ge=1), document_status: str = Query("active",pattern="^(active|archived)$")):
        deps = request.app.state.advanced_reader_dependencies
        return scoped(request).source(source_id, deps.document_service.documents, document_page=document_page, reference_page=reference_page, document_status=document_status)

    @router.get("/notes")
    def notes(request: Request, page: int = Query(1, ge=1), q: str = Query("", max_length=200), source_id: str = Query("", max_length=100), document_id: str = Query("", max_length=100)):
        return scoped(request).notes(page, q, source_id, document_id)

    @router.get("/notes/{note_id}")
    def note(note_id: str, request: Request):
        deps = request.app.state.advanced_reader_dependencies
        return scoped(request).note(note_id, deps.annotation_service)

    @router.get("/concepts/detail")
    def concept(request: Request, key: str = Query(..., max_length=1000)):
        return scoped(request).concept(key)

    @router.get("/choices")
    def choices(request: Request):
        app = scoped(request)
        return {"sources": [{"id": source.source_id, "name": source.name} for source in app.sources.list(page_size=100, status="active").items], "concept_types": list(CONCEPT_TYPES), "relation_types": [kind.value for kind in TipoRelacion]}

    @router.get("/concepts")
    def concepts(request: Request, q: str = Query("", max_length=200), tipo: str = Query("", max_length=40), source_id: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1000000), document_id: str = Query("", max_length=100)):
        return scoped(request).concepts(q, tipo, source_id, page, document_id=document_id)

    @router.get("/overview")
    def overview(request: Request):
        app = scoped(request)
        return {**app.maps.graph(include_content=False), "scope": app.library_id}

    @router.get("/home")
    def home(request: Request):
        from mathmongo.study.home import StudyHome

        return StudyHome(scoped(request).db).snapshot()

    @router.post("/operations")
    def operation(payload: Intent, request: Request):
        app = scoped(request)
        if payload.action in {"create","create_connected","edit","connect","publish_note"}:
            from mathmongo.study.preparation import AuthoringPreparation
            if AuthoringPreparation(app.db).inspect(core_only=True)["state"] != "ready":
                raise AdvancedReaderError("authoring_preparation", "Prepara las restricciones de la biblioteca antes de guardar conceptos o relaciones. El borrador se conserva.", status_code=409)
        return app.maps.execute(payload.model_dump(mode="json"))

    return router
