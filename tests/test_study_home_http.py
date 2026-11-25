"""Home is a read-only metadata summary, not a full-document prefetch or automatic maintenance."""

from pymongo.errors import OperationFailure

from mathmongo.study.home import StudyHome
from tests.test_notebook_http import http as _http
from tests.test_notebook_http import owned_client as _owned_client
from tests.test_notebook_http import service as _service

http = _http
owned_client = _owned_client
service = _service


def test_home_counts_and_summaries_preserve_bodies_on_demand(http, service):
    """Real scoped collections retain identities without exposing note bodies or hidden metadata."""
    client, _ = http
    service.db.latex_notes.insert_one({"_id": "kept", "title": "CPI", "note_format": "cpi_v1", "latex_body": r"\unknown{not a summary}", "private": "hidden"})
    before = set(service.db.list_collection_names())
    response = client.get("/api/study/v1/home")
    assert response.status_code == 200
    result = response.json()
    assert result["counts"]["notes"] == 1
    assert result["notes"][0]["family"] == "cpi" and result["notes"][0]["note_id"] == "kept"
    assert "unknown" not in response.text and "private" not in response.text
    assert set(service.db.list_collection_names()) == before
    assert client.get("/api/study/v1/home", headers={"X-MathMongo-Library": "different"}).status_code == 409


def test_home_inspection_failure_is_not_successful_zero_counts(service, monkeypatch):
    """An unavailable count remains an actionable error, without initializing storage."""
    import pytest
    from pymongo.collection import Collection

    from mathmongo.advanced_reader.document_access import AdvancedReaderError

    def denied(*_args, **_kwargs):
        raise OperationFailure("permission denied", code=13)
    monkeypatch.setattr(Collection, "count_documents", denied)
    with pytest.raises(AdvancedReaderError) as error:
        StudyHome(service.db).snapshot()
    assert error.value.status_code == 503 and "permisos" in error.value.public_message
