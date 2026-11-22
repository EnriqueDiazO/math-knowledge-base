"""Canonical catalog capture shared by the in-document bibliographic picker."""

from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError

from mathmongo.bibliography_lookup.service import MetadataLookup
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.service import SourceCatalogService


class ReferenceCapture:
    """Lookups propose, explicit saves create/associate; existing metadata is immutable here."""

    def __init__(self, database, lookup: MetadataLookup):
        """Bind every local operation to the already selected database."""
        self.catalog = SourceCatalogService(database)
        self.lookup = lookup

    def execute(self, payload: dict) -> dict:
        """Return bounded public states with a request ID for stale-response rejection."""
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        try:
            UUID(request_id)
        except (ValueError, TypeError, AttributeError):
            return {"request_id": None, "status": "invalid"}
        action = payload.get("action")
        try:
            if action == "identifier":
                return self.lookup.identifier(payload.get("query")).public(request_id)
            if action == "edition":
                identifier = payload.get("query")
                if not isinstance(identifier, str) or len(identifier) > 100:
                    return {"request_id": request_id, "status": "invalid"}
                return self.lookup.edition(identifier).public(request_id)
            if action == "title":
                return self.lookup.search(payload.get("query"), payload.get("author", "")).public(
                    request_id
                )
            if action == "local":
                query = payload.get("query")
                if not isinstance(query, str) or not query.strip() or len(query) > 200:
                    return {"request_id": request_id, "status": "invalid"}
                values = self.catalog.references.search(query, page_size=20).items
                return {
                    "request_id": request_id,
                    "status": "candidates" if values else "not_found",
                    "candidates": [
                        {"reference_data": item.model_dump(mode="json"), "existing": True}
                        for item in values
                    ],
                }
            if action == "save":
                return {**self._save(payload), "request_id": request_id}
        except (ValueError, TypeError, ValidationError):
            return {"request_id": request_id, "status": "invalid"}
        except Exception:
            # Database/provider diagnostics may include credentials; drafts remain client-side.
            return {"request_id": request_id, "status": "unavailable"}
        return {"request_id": request_id, "status": "invalid"}

    def _save(self, payload: dict) -> dict:
        source_id = payload.get("source_id")
        source = self.catalog.sources.get_by_id(source_id)
        if source is None or source.status.value != "active":
            return {"status": "invalid", "message": "Elige una Source administrada activa."}
        existing_id = payload.get("existing_reference_id")
        if existing_id:
            # Reuse preserves manual corrections, citation key and all associated Sources.
            existing = self.catalog.references.get_by_id(existing_id)
            if existing is None or existing.status.value == "archived":
                return {
                    "status": "invalid",
                    "message": "La referencia no está activa; revísala en Edit Source.",
                }
            result = self.catalog.associate_reference(existing_id, source_id)
        else:
            candidate = Reference.model_validate(payload.get("reference_data"))
            if candidate.status.value == "archived":
                return {"status": "invalid"}
            present = self.catalog.references.get_by_id(candidate.reference_id)
            if present is not None:
                fields = (
                    "title",
                    "authors",
                    "year",
                    "journal",
                    "publisher",
                    "volume",
                    "number",
                    "edition",
                    "isbn",
                    "doi",
                    "url",
                    "accessed_at",
                    "language",
                    "bibtex",
                    "notes",
                )
                if any(getattr(present, field) != getattr(candidate, field) for field in fields):
                    return {
                        "status": "conflict",
                        "message": "La ficha cambió. Revisa la referencia existente; tus correcciones están conservadas.",
                    }
                result = self.catalog.associate_reference(present.reference_id, source_id)
            else:
                data = candidate.model_dump(mode="python")
                data["source_ids"] = [source_id]
                result = self.catalog.create_reference(data)
        if not result.persisted or result.value is None:
            candidates = []
            for match in result.duplicates:
                ref = self.catalog.references.get_by_id(match.entity_id)
                if ref is not None:
                    candidates.append(
                        {
                            "reference_data": ref.model_dump(mode="json"),
                            "existing": True,
                            "match": match.classification.value,
                        }
                    )
            return {
                "status": "duplicates" if candidates else "conflict",
                "candidates": candidates,
                "message": "Revisa las coincidencias locales. No se fusionaron ni sobrescribieron registros.",
            }
        return {"status": "saved", "reference_data": result.value.model_dump(mode="json")}
