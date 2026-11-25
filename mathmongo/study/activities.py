"""Cuaderno application operations over its unchanged historical MongoDB collections."""

import csv
import io
import re
from datetime import date
from datetime import datetime
from datetime import timedelta

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.concurrency import digest
from mathmongo.concurrency import exact_document
from mathmongo.study.activity_models import MODELS
from mathmongo.study.library_management import rejected
from mathmongo.time import naive_utc_now

COLLECTIONS = {
    "worklog": "worklog_entries",
    "backlog": "backlog_items",
    "deliverables": "deliverables",
    "weekly": "weekly_reviews",
}


class NotebookActivities:
    """Explicit field contracts, bounded queries, replay-safe creation and atomic snapshot edits."""

    def __init__(self, db, kind):
        """Bind a whitelisted collection in the already scoped active library."""
        self.db, self.kind = db, kind
        self.collection = db[COLLECTIONS[kind]]
        self.model = MODELS[kind]

    def describe(self, record):
        """Return editable metadata; never serialize unknown historical fields or paths as files."""
        result = {
            "id": str(record["_id"]),
            "revision": digest(record),
            "fields": {
                name: record.get(
                    name,
                    field.get_default(call_default_factory=True)
                    if not field.is_required()
                    else None,
                )
                for name, field in self.model.model_fields.items()
            },
        }
        if self.kind == "weekly":
            result["metrics_at_save"] = {
                "real_hours": record.get("agg_real_hours"),
                "tasks_done": record.get("agg_tasks_done"),
            }
        return result

    def opened(self, identity):
        """Prefer exact string identities and then historical ObjectIds, without identity conversion."""
        record = self.collection.find_one({"_id": identity})
        if record is None and ObjectId.is_valid(identity):
            record = self.collection.find_one({"_id": ObjectId(identity)})
        if record is None:
            raise AdvancedReaderError(
                "activity_missing",
                "El registro ya no está disponible. Conserva el borrador y vuelve a la lista.",
                status_code=404,
            )
        return record

    def listing(self, q="", project="", status="", page=1):
        """Keep the same filters for the list and Kanban; no document bodies are requested."""
        query = {}
        if q:
            query["$or"] = [
                {field: {"$regex": re.escape(q), "$options": "i"}}
                for field in ("task", "deliverable", "project")
            ]
        if project:
            query["project"] = project
        if status:
            query["status"] = status
        # Revisions require the exact snapshot; bounded 20 records retain unknown-field CAS protection.
        items = (
            self.collection.find(query)
            .sort([("updated_at", -1), ("_id", -1)])
            .skip((page - 1) * 20)
            .limit(20)
        )
        return {
            "items": [self.describe(row) for row in items],
            "total": self.collection.count_documents(query),
            "page": page,
        }

    def metrics(self, year, week):
        """Use the historical ISO bounds and legacy Done timestamp fallback; errors propagate."""
        start = datetime.combine(date.fromisocalendar(year, week, 1), datetime.min.time())
        end = start + timedelta(days=7)
        aggregate = list(
            self.db.worklog_entries.aggregate(
                [
                    {"$match": {"iso_year": year, "iso_week": week}},
                    {"$group": {"_id": None, "hours": {"$sum": "$hours"}, "count": {"$sum": 1}}},
                ]
            )
        )
        done = self.db.backlog_items.count_documents(
            {
                "status": "Done",
                "$or": [
                    {"done_at": {"$gte": start, "$lt": end}},
                    {"done_at": None, "updated_at": {"$gte": start, "$lt": end}},
                ],
            }
        )
        return {
            "real_hours": float(aggregate[0]["hours"]) if aggregate else 0,
            "worklog_n": aggregate[0]["count"] if aggregate else 0,
            "tasks_done": done,
        }

    def normalized(self, fields, original=None):
        """Compute derived fields once; preserve links and unknown metadata in every update."""
        value = self.model.model_validate(fields).model_dump(mode="json")
        now = naive_utc_now()
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        if self.kind == "worklog":
            iso = date.fromisoformat(value["date"]).isocalendar()
            value.update(iso_year=iso.year, iso_week=iso.week)
        elif self.kind == "backlog":
            previous = (original or {}).get("status")
            if value["status"] == "Done" and previous != "Done":
                value["done_at"] = now
            elif value["status"] != "Done" and previous == "Done":
                value["done_at"] = None
            if not value["estimate_hours"]:
                value["estimate_hours"] = None
        elif self.kind == "deliverables":
            if original is None or value["commit_ref"] != original.get("commit_ref"):
                previous = (original or {}).get("linked_commits") or []
                links = [link for link in previous if link != (original or {}).get("commit_ref")]
                value["linked_commits"] = list(
                    dict.fromkeys([*links, *([value["commit_ref"]] if value["commit_ref"] else [])])
                )
        else:
            metrics = self.metrics(value["iso_year"], value["iso_week"])
            value.update(agg_real_hours=metrics["real_hours"], agg_tasks_done=metrics["tasks_done"])
            if not value["manual_override_metrics"]:
                value.update(manual_real_hours=None, manual_tasks_done=None)
        return value

    def create(self, request_id, fields):
        """One UUID identifies retries; a week cannot overwrite an existing review implicitly."""
        validated = self.model.model_validate(fields).model_dump(mode="json")
        fingerprint = digest(validated)
        identity = (
            f"study_week_{validated["iso_year"]}_{validated["iso_week"]}"
            if self.kind == "weekly"
            else "study_" + str(request_id)
        )
        record = self.collection.find_one({"_id": identity})
        if record is None:
            normalized = self.normalized(validated)
            if self.kind == "weekly" and self.collection.find_one(
                {
                    "iso_year": normalized["iso_year"],
                    "iso_week": normalized["iso_week"],
                    "_id": {"$ne": identity},
                }
            ):
                raise rejected(
                    "Ya existe una revisión de esa semana. Ábrela para editarla; no se reemplazó su contenido."
                )
            now = naive_utc_now()
            defaults = {
                "worklog": {"start_time": None, "end_time": None, "deliverable_id": None},
                "deliverables": {"linked_worklog_ids": [], "linked_note_ids": []},
            }.get(self.kind, {})
            try:
                self.collection.insert_one(
                    {
                        "_id": identity,
                        **defaults,
                        **normalized,
                        "created_at": now,
                        "updated_at": now,
                        "study_create_fingerprint": fingerprint,
                    }
                )
            except DuplicateKeyError:
                pass
            record = self.opened(identity)
        if record.get("study_create_fingerprint") != fingerprint:
            raise rejected(
                "El intento ya corresponde a otro contenido. El borrador se conserva; inicia otro registro."
            )
        return self.describe(record)

    def update(self, identity, revision, fields):
        """The same read supplies revision, transitions and the exact atomic update predicate."""
        original = self.opened(identity)
        validated = self.model.model_validate(fields).model_dump(mode="json")
        changes = self.normalized(validated, original) if self.kind == "weekly" else None
        comparison = changes if changes is not None else validated
        if all(original.get(key) == value for key, value in comparison.items()):
            return self.describe(original)
        if digest(original) != revision:
            raise rejected(
                "Otra ventana cambió el registro. El borrador se conserva; vuelve a abrir la versión guardada."
            )
        if self.kind == "weekly" and any(
            validated[key] != original.get(key) for key in ("iso_year", "iso_week")
        ):
            raise rejected(
                "La semana identifica esta revisión. Crea otra revisión para una semana distinta."
            )
        changes = changes if changes is not None else self.normalized(validated, original)
        result = self.collection.update_one(
            exact_document(original), {"$set": {**changes, "updated_at": naive_utc_now()}}
        )
        if not result.acknowledged or result.matched_count != 1:
            raise rejected()
        confirmed = self.opened(identity)
        if any(confirmed.get(key) != value for key, value in changes.items()):
            raise rejected()
        return self.describe(confirmed)

    def export(self, identities):
        """Export an explicit selection; formula-looking cells stay spreadsheet text."""
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["id", *self.model.model_fields])
        writer.writeheader()
        for identity in dict.fromkeys(identities):
            item = self.describe(self.opened(identity))
            row = {"id": item["id"], **item["fields"]}
            writer.writerow(
                {
                    key: "'" + str(value)
                    if str(value).lstrip().startswith(("=", "+", "-", "@"))
                    else value
                    for key, value in row.items()
                }
            )
        return buffer.getvalue().encode("utf-8-sig")
