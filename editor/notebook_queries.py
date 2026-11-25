"""Shared read-only Diario filters, preserving the historical query contract."""

import re
from datetime import date
from datetime import timedelta
from typing import Any

from mathmongo.time import naive_utc_now


def build_notes_query(
    text_q: str = "",
    project: str = "(all)",
    context: str = "(all)",
    tags: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    year: str = "(all)",
    month: str = "(all)",
    updated_recently: bool = False,
) -> dict[str, Any]:
    """Keep combined historical filters literal, bounded by callers, and read-only."""
    q: dict[str, Any] = {}
    and_terms = []
    if project not in ("(all)", None):
        if project == "(sin proyecto)":
            q["$or"] = [{"project": ""}, {"project": {"$exists": False}}, {"project": None}]
        else:
            q["project"] = project
    if context != "(all)":
        q["context"] = context
    if tags:
        q["tags"] = {"$all": tags}
    if start_date and end_date:
        q["date"] = {"$gte": start_date.strftime("%Y-%m-%d"), "$lte": end_date.strftime("%Y-%m-%d")}
    if year != "(all)":
        and_terms.append({"date": {"$regex": f"^{re.escape(str(year))}-"}})
    if month != "(all)" and year != "(all)":
        and_terms.append({"date": {"$regex": f"^{re.escape(str(year))}-{int(month):02d}-"}})
    if text_q.strip():
        rx = {"$regex": re.escape(text_q.strip()), "$options": "i"}
        and_terms.append({"$or": [{"title": rx}, {"latex_body": rx}]})
    if updated_recently:
        cutoff = naive_utc_now() - timedelta(days=7)
        q["updated_at"] = {"$gte": cutoff}
    if and_terms:
        q["$and"] = and_terms
    return q
