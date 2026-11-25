"""Real isolated MongoDB regressions for migrated task activities, not line-execution tests."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from mathmongo.study.activities import COLLECTIONS
from mathmongo.study.activities import NotebookActivities
from tests.test_notebook_http import http as _http
from tests.test_notebook_http import owned_client as _owned_client
from tests.test_notebook_http import service as _service

http = _http
owned_client = _owned_client
service = _service
BASE = "/api/study/v1/activities/"


def fields(kind):
    """Minimum real records accepted by the historical forms."""
    return {
        "worklog": {"date": "2026-11-24", "project": "Migración", "task": "Comparar", "hours": 1.5},
        "backlog": {"project": "Migración", "task": "Comprobar", "owner": "Persona"},
        "deliverables": {
            "date": "2026-11-24",
            "project": "Migración",
            "deliverable": "Informe",
            "url_or_path": "/no-server-read/report.pdf",
        },
        "weekly": {
            "iso_year": 2026,
            "iso_week": 48,
            "weekly_objectives": ["Conservar capacidades"],
        },
    }[kind]


@pytest.mark.parametrize("kind", list(COLLECTIONS))
def test_create_reload_edit_and_explicit_csv_keep_historical_links(http, service, kind):
    """Replays neither duplicate nor replace, CAS edits keep unknown fields and linked entities."""
    client, _ = http
    request = {"request_id": str(uuid4()), "fields": fields(kind)}
    first = client.post(BASE + kind, json=request)
    assert first.status_code == 200, first.text
    note = first.json()
    assert client.post(BASE + kind, json=request).json() == note
    assert client.get(BASE + kind + "/" + note["id"]).json() == note
    collection = service.db[COLLECTIONS[kind]]
    collection.update_one(
        {"_id": note["id"]},
        {"$set": {"historical": {"macro": r"\unknown{x}"}, "linked_note_ids": ["original"]}},
    )
    note = client.get(BASE + kind + "/" + note["id"]).json()
    changes = {
        **note["fields"],
        **({"wins": ["Guardado"]} if kind == "weekly" else {"project": "=formula"}),
    }
    edited = client.post(
        BASE + kind + "/" + note["id"],
        json={"request_id": str(uuid4()), "revision": note["revision"], "fields": changes},
    )
    assert edited.status_code == 200, edited.text
    after = collection.find_one({"_id": note["id"]})
    assert after["historical"] == {"macro": r"\unknown{x}"} and after["linked_note_ids"] == [
        "original"
    ]
    assert collection.count_documents({}) == 1
    exported = client.post(BASE + kind + "/export", json={"ids": [note["id"], note["id"]]})
    assert exported.status_code == 200 and note["id"] in exported.text
    if kind != "weekly":
        assert "'=formula" in exported.text
    assert client.get(BASE + kind, params={"project": "=formula"}).json()["total"] == (
        0 if kind == "weekly" else 1
    )
    stale = client.post(
        BASE + kind + "/" + note["id"],
        json={
            "request_id": str(uuid4()),
            "revision": note["revision"],
            "fields": {**changes, "wins": ["stale"]}
            if kind == "weekly"
            else {**changes, "project": "stale"},
        },
    )
    assert stale.status_code == 409 and collection.find_one({"_id": note["id"]}) == after
    assert (
        client.post(
            BASE + kind, json={**request, "fields": {**request["fields"], "extra": "not allowed"}}
        ).status_code
        == 422
    )
    assert client.get(BASE + kind, headers={"X-MathMongo-Library": "other"}).status_code == 409


def test_kanban_done_timestamp_and_weekly_derived_metrics_are_stable(http, service):
    """Changing a Done task title cannot move its completion into another weekly review."""
    client, _ = http
    work = client.post(
        BASE + "worklog", json={"request_id": str(uuid4()), "fields": fields("worklog")}
    )
    assert work.status_code == 200
    created = client.post(
        BASE + "backlog", json={"request_id": str(uuid4()), "fields": fields("backlog")}
    ).json()

    def update(note, **changes):
        result = client.post(
            BASE + "backlog/" + note["id"],
            json={
                "request_id": str(uuid4()),
                "revision": note["revision"],
                "fields": {**note["fields"], **changes},
            },
        )
        assert result.status_code == 200, result.text
        return result.json()

    done = update(created, status="Done")
    completed_at = service.db.backlog_items.find_one({})["done_at"]
    changed = update(done, task="Completada y documentada")
    assert service.db.backlog_items.find_one({})["done_at"] == completed_at
    snapshot = service.db.backlog_items.find_one({})
    assert update(changed) == changed and service.db.backlog_items.find_one({}) == snapshot
    metric = NotebookActivities(service.db, "weekly").metrics(2026, 48)
    assert metric["real_hours"] == 1.5 and metric["worklog_n"] == 1
    reopened = update(changed, status="Doing")
    assert service.db.backlog_items.find_one({})["done_at"] is None
    assert reopened["fields"]["status"] == "Doing"
    assert (
        client.post(
            BASE + "weekly",
            json={"request_id": str(uuid4()), "fields": {"iso_year": 2026, "iso_week": 53}},
        ).status_code
        == 200
    )
    assert (
        client.post(
            BASE + "weekly",
            json={"request_id": str(uuid4()), "fields": {"iso_year": 2025, "iso_week": 53}},
        ).status_code
        == 422
    )


def test_concurrent_review_creation_uses_one_week_identity(service):
    """Different windows cannot insert two new reviews for the same ISO week without transactions."""

    def create(_):
        return NotebookActivities(service.db, "weekly").create(uuid4(), fields("weekly"))

    with ThreadPoolExecutor(2) as pool:
        records = list(pool.map(create, range(2)))
    assert records[0] == records[1]
    assert service.db.weekly_reviews.count_documents({}) == 1


def test_weekly_refreshes_derived_metrics_and_deliverable_edit_preserves_other_commits(
    http, service
):
    """Saving a review recomputes totals; editing notes cannot silently unlink another commit."""
    client, _ = http
    review = client.post(
        BASE + "weekly", json={"request_id": str(uuid4()), "fields": fields("weekly")}
    ).json()
    assert review["metrics_at_save"]["real_hours"] == 0
    work = client.post(
        BASE + "worklog", json={"request_id": str(uuid4()), "fields": fields("worklog")}
    )
    assert work.status_code == 200
    updated = client.post(
        BASE + "weekly/" + review["id"],
        json={
            "request_id": str(uuid4()),
            "revision": review["revision"],
            "fields": review["fields"],
        },
    )
    assert updated.status_code == 200 and updated.json()["metrics_at_save"]["real_hours"] == 1.5
    deliverable = client.post(
        BASE + "deliverables",
        json={
            "request_id": str(uuid4()),
            "fields": {**fields("deliverables"), "commit_ref": "primary"},
        },
    ).json()
    service.db.deliverables.update_one(
        {"_id": deliverable["id"]}, {"$set": {"linked_commits": ["primary", "separate-consumer"]}}
    )
    deliverable = client.get(BASE + "deliverables/" + deliverable["id"]).json()
    result = client.post(
        BASE + "deliverables/" + deliverable["id"],
        json={
            "request_id": str(uuid4()),
            "revision": deliverable["revision"],
            "fields": {**deliverable["fields"], "notes": "Reviewed"},
        },
    )
    assert result.status_code == 200
    assert service.db.deliverables.find_one({"_id": deliverable["id"]})["linked_commits"] == [
        "primary",
        "separate-consumer",
    ]
