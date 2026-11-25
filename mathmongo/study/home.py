"""Bounded activity summaries for the study home; canonical content stays on demand."""

from pymongo.errors import PyMongoError

from mathmongo.advanced_reader.document_access import AdvancedReaderError


class StudyHome:
    """Read existing academic entities without preparing collections or writing history."""

    def __init__(self, database):
        """Bind the already configured library, never a client-provided database name."""
        self.db = database

    def _recent(self, collection, query, projection):
        """Only six navigation summaries per activity; never load LaTeX or note bodies."""
        return list(
            self.db[collection]
            .find(query, projection)
            .sort([("updated_at", -1), ("_id", -1)])
            .limit(6)
        )

    def snapshot(self):
        """Unavailable permissions/connections are errors, not invented zero counts."""
        try:
            return self._snapshot()
        except PyMongoError:
            raise AdvancedReaderError(
                "home_unavailable",
                "No se pudo consultar la actividad de esta biblioteca. Puedes seguir navegando; reintenta la consulta cuando vuelva la conexión o revisa sus permisos en Ajustes.",
                status_code=503,
            ) from None

    def _snapshot(self):
        """Keep format-specific identities and source associations intact in navigation."""
        counts = {
            "sources": self.db.sources.count_documents({"status": "active"}),
            "concepts": self.db.concepts.count_documents({}),
            "documents": self.db.source_documents.count_documents({"status": "active"}),
            "notes": self.db.latex_notes.count_documents({})
            + self.db.reading_notes.count_documents({"status": "active"}),
        }
        concepts = self._recent(
            "concepts", {}, {"id": 1, "source": 1, "titulo": 1, "tipo": 1, "updated_at": 1}
        )
        notes = self._recent(
            "latex_notes", {}, {"title": 1, "note_format": 1, "updated_at": 1, "date": 1}
        )
        documents = self._recent(
            "source_documents",
            {"status": "active"},
            {"document_id": 1, "title": 1, "source_id": 1, "kind": 1, "updated_at": 1},
        )
        reading = self._recent(
            "reading_notes", {"status": "active"}, {"note_id": 1, "title": 1, "updated_at": 1}
        )
        formats = {"cornell_math_v1": "cornell", "cpi_v1": "cpi"}
        return {
            "counts": counts,
            "concepts": [
                {
                    "key": str(row["id"]) + "@" + row["source"],
                    "title": row.get("titulo") or str(row["id"]),
                    "type": row.get("tipo", "nota"),
                    "updated": row.get("updated_at"),
                }
                for row in concepts
            ],
            "notes": [
                {
                    "note_id": str(row["_id"]),
                    "title": row.get("title") or "Nota sin título",
                    "family": formats.get(row.get("note_format"), "diary"),
                    "updated": row.get("updated_at") or row.get("date"),
                }
                for row in notes
            ],
            "reading_notes": [
                {
                    "note_id": row["note_id"],
                    "title": row.get("title") or "Nota sin título",
                    "updated": row.get("updated_at"),
                }
                for row in reading
            ],
            "documents": [
                {
                    "document_id": row["document_id"],
                    "title": row.get("title") or "Documento sin título",
                    "source_id": row.get("source_id"),
                    "kind": row.get("kind"),
                }
                for row in documents
            ],
        }
