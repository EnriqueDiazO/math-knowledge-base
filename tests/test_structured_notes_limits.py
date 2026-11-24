"""Document page limits protect the isolated compiler without changing canonical schemas."""

from copy import deepcopy

import pytest

from mathmongo.study.structured_notes import structured_format
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_library_management_http import http as _http
from tests.test_structured_notes_http import BASE
from tests.test_structured_notes_http import payload

owned_client = _owned_client
service = _service
http = _http


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_thirty_pages_are_accepted_but_thirty_one_never_writes_a_note(http, service, family):
    """Use unique identities so this exercises the HTTP budget, not duplicate-page rejection."""
    client, _ = http
    body = payload(family)
    first = body["document"]["pages"][0]
    pages = []
    for index in range(31):
        page = deepcopy(first)
        page["order" if family == "cornell" else "page_number"] = index + 1
        if family == "cornell":
            page["page_id"] = "page-" + str(index)
        pages.append(page)
    body["document"]["pages"] = pages
    assert len(structured_format(family).document_type.from_dict(body["document"]).pages) == 31
    rejected = client.post(BASE + family, json=body)
    assert (
        rejected.status_code == 422
        and rejected.json()["error"]["code"] == "invalid_structured_document"
    )
    assert service.db.latex_notes.count_documents({}) == 0
    body["document"]["pages"] = pages[:30]
    saved = client.post(BASE + family, json=body)
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["document"]["pages"]) == 30
    assert service.db.latex_notes.count_documents({}) == 1
