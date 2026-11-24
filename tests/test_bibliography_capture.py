"""Canonical save/cite, manual correction and export regression tests on owned Mongo."""

# ruff: noqa: D103
from __future__ import annotations

from uuid import uuid4

import pytest

from editor.pdf_export import _generar_latex_content
from editor.source_catalog.lookup_ui import reference_update_options
from editor.source_catalog.lookup_ui import selected_reference_updates
from editor.source_catalog.reference_form import authors_to_text
from editor.source_catalog.reference_form import build_reference_from_form
from mathmongo.bibliography_lookup.capture import ReferenceCapture
from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.source_catalog.citations import CitationLocator
from mathmongo.source_catalog.citations import legacy_citation
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import RepositoryConflictError
from mathmongo.source_catalog.repository import reference_revision
from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import edit
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def request(action, **values):
    return {"request_id": str(uuid4()), "action": action, **values}


def test_reference_save_retry_reuse_and_concept_locator_export(service):
    capture = ReferenceCapture(service.db, MetadataLookup())
    original = Reference(
        reference_type="article",
        title="Artículo & texto",
        year=1977,
        authors=[{"family": "Nyaga", "given": "V. I."}],
        doi="10.1007/BF01106749",
        journal="Revista",
        language="en",
        bibtex={"key": "Nyaga_1977", "extra": {"pages": "228-231"}},
    )
    payload = request(
        "save", source_id=service.test_source_id, reference_data=original.model_dump(mode="json")
    )
    first = capture.execute(payload)
    assert first["status"] == "saved"
    assert capture.execute(payload)["reference_data"]["reference_id"] == original.reference_id
    assert service.db.references.count_documents({}) == 1
    ref = ReferenceRepository(service.db).get_by_id(original.reference_id)
    assert ref.bibtex.key == "Nyaga_1977"
    # A new provider proposal is a duplicate candidate, never an update.
    proposed = original.model_copy(
        update={"reference_id": "ref_" + str(uuid4()), "title": "Título proveedor"}
    )
    duplicate = capture.execute(
        request(
            "save",
            source_id=service.test_source_id,
            reference_data=proposed.model_dump(mode="json"),
        )
    )
    assert duplicate["status"] == "duplicates"
    reused = capture.execute(
        request(
            "save", source_id=service.test_source_id, existing_reference_id=original.reference_id
        )
    )
    assert reused["reference_data"]["title"] == original.title
    locator = CitationLocator(
        printed_page="229", pdf_page=3, theorem="2", passage="Pasaje & aclaración"
    )
    saved = service.execute(
        create(service, reference_id=original.reference_id, reference_locator=locator.model_dump())
    )
    assert saved["status"] == "saved"
    concept = service.find(saved["key"])
    assert concept["reference_id"] == original.reference_id
    assert concept["reference_locator"] == locator.model_dump()
    assert concept["referencia"]["publication_pages"] == "228-231"
    assert concept["referencia"]["paginas"] == "229"
    assert concept["referencia"]["pdf_page"] == "3"
    assert concept["referencia"]["tipo_referencia"] == "articulo"
    assert concept["referencia"]["citekey"] == "Nyaga_1977"
    assert ReferenceRepository(service.db).get_by_id(original.reference_id) == ref
    exported = _generar_latex_content({**concept, "contenido_latex": "Contenido seguro"})
    assert r"Artículo \& texto" in exported
    assert "Pág. 229" in exported and "Páginas de la publicación: 228-231" in exported
    assert "Página física del PDF: 3" in exported and "Teorema citado: 2" in exported
    assert r"Pasaje \& aclaración" in exported
    # Existing edit routes preserve the citation even if an old client omits it.
    changed = service.execute(edit(service, saved["key"]))
    assert changed["status"] == "saved"
    assert service.find(saved["key"])["reference_locator"] == locator.model_dump()


def test_stale_reference_update_and_race_do_not_overwrite_corrections(service, monkeypatch):
    repo = ReferenceRepository(service.db)
    ref = repo.insert(Reference(title="Inicial"))
    repo.update(
        ref.reference_id, {"title": "Corrección de otra ventana", "updated_at": ref.updated_at}
    )
    with pytest.raises(RepositoryConflictError):
        repo.update(
            ref.reference_id,
            {"title": "Edición antigua"},
            expected_revision=reference_revision(ref),
        )
    observed = repo.get_by_id(ref.reference_id)
    collection = repo._collection
    monkeypatch.setattr(ReferenceRepository, "_collection", property(lambda self: collection))
    real_update = collection.update_one

    def raced(query, patch):
        # Simulate another tool preserving updated_at; full-document CAS still wins.
        real_update({"reference_id": ref.reference_id}, {"$set": {"notes": "Trabajo ajeno"}})
        return real_update(query, patch)

    monkeypatch.setattr(collection, "update_one", raced)
    with pytest.raises(RepositoryConflictError):
        repo.update(
            ref.reference_id,
            {"title": "No debe imponerse"},
            expected_updated_at=observed.updated_at,
        )
    current = repo.get_by_id(ref.reference_id)
    assert (current.title, current.notes) == ("Corrección de otra ventana", "Trabajo ajeno")


def test_selective_refresh_and_form_preserve_identity_key_raw_orcid_and_translation():
    old = Reference(
        title="Corrección manual",
        year=2006,
        edition="Traducción española",
        authors=[{"family": "Autora", "given": "A.", "orcid": "0000-0002-1825-0097"}],
        bibtex={
            "key": "ClaveFija",
            "raw": "@book{ClaveFija,title={Texto}}",
            "extra": {"pages": "10-20", "translator": "Traductora"},
        },
    )
    proposed = Reference(
        title="Título proveedor",
        year=1901,
        publisher="Editorial recuperada",
        bibtex={"key": "ClaveAjena", "extra": {"pages": "200-300"}},
    )
    options = reference_update_options(old, proposed)
    assert "reference_id" not in options and "bibtex" not in options
    changes = selected_reference_updates(old, proposed, ["publisher", "extra.pages"])
    assert set(changes) == {"publisher", "bibtex"}
    assert changes["bibtex"]["key"] == "ClaveFija"
    assert changes["bibtex"]["raw"] == old.bibtex.raw
    assert changes["bibtex"]["extra"] == {"pages": "200-300", "translator": "Traductora"}
    assert old.year == 2006 and old.edition == "Traducción española"
    edited = build_reference_from_form(
        {"authors_text": authors_to_text(old.authors), "title": "Otro"}, initial=old
    )
    assert edited.authors == old.authors and edited.reference_id == old.reference_id
    assert legacy_citation(old, CitationLocator())["reference_id"] == old.reference_id


@pytest.mark.parametrize(
    "collection",
    [
        "concepts",
        "source_documents",
        "reading_notes",
        "reading_annotations",
        "concept_evidence_links",
    ],
)
def test_referenced_record_cannot_be_deleted_after_source_disassociation(service, collection):
    repo = ReferenceRepository(service.db)
    ref = repo.insert(Reference(title="En uso"))
    service.db[collection].insert_one({"reference_id": ref.reference_id})
    assert collection + ":reference_id" in repo.deletion_blockers(ref.reference_id)
    with pytest.raises(Exception, match="blocked"):
        repo.physical_delete_if_unused(ref.reference_id)
    assert repo.get_by_id(ref.reference_id) is not None


def test_capture_dispatch_validates_before_provider_and_searches_local(service):
    class Offline:
        def identifier(self, _query):
            raise AssertionError("unexpected network")

    capture = ReferenceCapture(service.db, Offline())
    assert (
        capture.execute({"request_id": "not-a-uuid", "action": "identifier"})["status"] == "invalid"
    )
    assert capture.execute(request("edition", query="../etc/passwd"))["status"] == "unavailable"
    invalid = service.execute(create(service, reference_id="bad-reference-id"))
    assert invalid["status"] == "invalid"
    assert service.db.concepts.count_documents({}) == 0
    assert service.db["_knowledge_map_operations"].count_documents({}) == 0
    ref = ReferenceRepository(service.db).insert(Reference(title="Hallazgo local"))
    found = capture.execute(request("local", query="Hallazgo"))
    assert found["candidates"][0]["reference_data"]["reference_id"] == ref.reference_id
    assert found["candidates"][0]["existing"] is True
    assert capture.execute(request("local", query="Inexistente"))["status"] == "not_found"
    assert capture.execute(request("local", query=""))["status"] == "invalid"


def test_source_only_note_can_cite_without_pdf_and_publish_same_reference(service):
    from exporters_latex.unified_document import render_concept_fragment
    from mathmongo.knowledge_map.service import digest
    from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
    from mathmongo.reading_annotations.service import ReadingAnnotationService

    ReadingAnnotationIndexManager(service.db).apply()
    ref = ReferenceRepository(service.db).insert(
        Reference(
            title="Edición de papel",
            year=2006,
            edition="Traducción",
            source_ids=[service.test_source_id],
        )
    )
    locator = CitationLocator(printed_page="xii", theorem="1.2")
    operation = {
        "operation_id": str(uuid4()),
        "action": "save_note",
        "source_id": service.test_source_id,
        "titulo": "Lectura de papel",
        "contenido_latex": "Borrador guardado sin adjuntar un PDF.",
        "reference_id": ref.reference_id,
        "reference_locator": locator.model_dump(),
    }
    result = service.execute(operation)
    assert result["status"] == "saved"
    assert service.db.concepts.count_documents({}) == 0
    notes = ReadingAnnotationService(service.db)
    note = notes.get_note(result["note_id"]).value
    assert note.document_id is None and note.reference_id == ref.reference_id
    assert note.reference_locator == locator
    assert note.page_start is None and note.reference_locator.pdf_page is None
    updated = service.execute(
        {
            **operation,
            "operation_id": str(uuid4()),
            "note_id": note.note_id,
            "revision": digest(note.model_dump()),
            "contenido_latex": "Versión completada.",
        }
    )
    assert updated["status"] == "saved"
    note = notes.get_note(note.note_id).value
    concept = service.execute(
        create(
            service,
            action="publish_note",
            titulo="Concepto explícito",
            note_id=note.note_id,
            note_revision=digest(note.model_dump()),
            contenido_latex=note.body,
        )
    )
    assert concept["status"] == "saved"
    document = service.find(concept["key"])
    assert document["reference_id"] == ref.reference_id
    assert document["reference_locator"] == locator.model_dump()
    assert notes.get_note(note.note_id).value == note
    latex = render_concept_fragment(document, note.body)
    assert "xii" in latex and "Teorema citado: 1.2" in latex


@pytest.mark.parametrize("identifier", ["10.1007/BF01106749", "9780140328721"])
def test_lookup_provenance_survives_real_bson_and_manual_correction(service, identifier):
    from tests.test_bibliography_lookup import CROSSREF
    from tests.test_bibliography_lookup import EDITION
    from tests.test_bibliography_lookup import lookup

    api, _, _ = (
        lookup(CROSSREF)
        if identifier.startswith("10.")
        else lookup(EDITION, {"name": "Autora temporal"})
    )
    capture = ReferenceCapture(service.db, api)
    response = capture.execute(request("identifier", query=identifier))
    assert response["status"] == "found"
    proposal = response["candidates"][0]["reference_data"]
    proposal["title"] = "Corrección explícita antes de guardar"
    result = capture.execute(
        request("save", source_id=service.test_source_id, reference_data=proposal)
    )
    assert result["status"] == "saved"
    saved = ReferenceRepository(service.db).get_by_id(proposal["reference_id"])
    stamp = saved.provenance.external_lookup
    assert stamp.original_query == identifier and stamp.retrieved_at.tzinfo is not None
    assert stamp.provider == ("crossref" if identifier.startswith("10.") else "openlibrary")
    assert saved.title == proposal["title"]
    assert result["reference_data"]["reference_id"] == proposal["reference_id"]
    archived = saved.archived()
    service.db.references.replace_one(
        {"reference_id": saved.reference_id}, archived.model_dump(mode="python")
    )
    assert (
        capture.execute(
            request(
                "save", source_id=service.test_source_id, existing_reference_id=saved.reference_id
            )
        )["status"]
        == "invalid"
    )


@pytest.mark.parametrize("change", [{"reference_type": "thesis"}, {"year_raw": "aprox. 1919"}])
def test_reference_replay_never_confirms_a_different_type_or_raw_year(service, change):
    capture = ReferenceCapture(service.db, MetadataLookup())
    original = Reference(reference_type="book", title="Ficha conservada", year_raw="aprox. 1918")
    data = original.model_dump(mode="json")
    saved = capture.execute(request("save", source_id=service.test_source_id, reference_data=data))
    assert saved["status"] == "saved"
    before = ReferenceRepository(service.db).get_by_id(original.reference_id)
    result = capture.execute(
        request("save", source_id=service.test_source_id, reference_data={**data, **change})
    )
    assert result["status"] == "conflict"
    assert ReferenceRepository(service.db).get_by_id(original.reference_id) == before
    assert service.db.references.count_documents({}) == 1
