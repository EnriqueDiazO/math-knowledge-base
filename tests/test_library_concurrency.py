"""Standalone MongoDB races in the canonical catalog and document repositories."""

import pytest

from mathmongo.source_catalog.repository import RepositoryConflictError
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.repository import SourceDocumentRepositoryConflictError
from tests.advanced_reader_test_support import synthetic_text_pdf
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_study_http import http as _http

owned_client = _owned_client
service = _service
http = _http


def test_source_write_rejects_a_race_after_its_snapshot(service, monkeypatch):
    """A second writer's name must survive the first writer's late update."""
    repository = SourceRepository(service.db)
    collection = service.db.sources
    update = collection.update_one

    def interleave(query, values, **options):
        update(
            {"source_id": service.test_source_id},
            {"$set": {"name": "Otra ventana", "name_normalized": "otra ventana"}},
        )
        return update(query, values, **options)

    monkeypatch.setattr(collection, "update_one", interleave)
    monkeypatch.setattr(SourceRepository, "_collection", property(lambda self: collection))
    with pytest.raises(RepositoryConflictError):
        repository.update(service.test_source_id, {"name": "Nombre desactualizado"})
    assert (
        service.db.sources.find_one({"source_id": service.test_source_id})["name"] == "Otra ventana"
    )


def test_document_metadata_does_not_replace_concurrent_content(http, service, monkeypatch):
    """Editing a title may not roll back another writer's metadata or PDF descriptor."""
    client, _ = http
    import tempfile
    from pathlib import Path

    from mathmongo.source_documents.repository import SourceDocumentRepository
    from mathmongo.source_documents.service import SourceDocumentService
    from mathmongo.source_documents.storage import SourceDocumentBlobStore

    with tempfile.TemporaryDirectory(prefix="library-race-") as directory:
        documents = SourceDocumentService(
            service.db, storage=SourceDocumentBlobStore(Path(directory))
        )
        created = documents.create_pdf_document(
            source_id=service.test_source_id,
            title="Documento",
            original_filename="owned.pdf",
            pdf_bytes=synthetic_text_pdf(padding_bytes=0),
        )
        assert created.completed
        collection = service.db.source_documents
        replace = collection.replace_one
        update = collection.update_one

        def interleave(query, values, **options):
            update(
                {"document_id": created.value.document_id},
                {"$set": {"description": "Cambio de otra ventana"}},
            )
            return replace(query, values, **options)

        monkeypatch.setattr(collection, "replace_one", interleave)
        monkeypatch.setattr(
            SourceDocumentRepository, "_collection", property(lambda self: collection)
        )
        with pytest.raises(SourceDocumentRepositoryConflictError):
            documents.documents.update_metadata(
                created.value.document_id, {"title": "Título desactualizado"}
            )
        assert (
            collection.find_one({"document_id": created.value.document_id})["description"]
            == "Cambio de otra ventana"
        )
