"""Explicit preparation for authoring; no index replacement or record migration."""

from pymongo.errors import DuplicateKeyError
from pymongo.errors import PyMongoError

from mathdatabase.mathmongo import CORE_IDENTITY_INDEXES
from mathdatabase.mathmongo import ensure_compatible_index
from mathmongo.concurrency import digest
from mathmongo.source_catalog.indexes import SOURCE_CATALOG_INDEXES
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager

# Exactly the three canonical identity contracts in MathMongo.ensure_indexes.
CORE_IDENTITIES = CORE_IDENTITY_INDEXES
AUTHORING_VERSION = digest(
    [CORE_IDENTITIES, [(s.collection, s.name, s.keys, s.unique) for s in SOURCE_CATALOG_INDEXES]]
)


class AuthoringPreparation:
    """Inspect real metadata and recheck after explicit compatible creation."""

    def __init__(self, database):
        """Bind only; opening any study page remains read-only."""
        self.db = database

    def inspect(self, *, core_only=False):
        """Distinguish missing constraints, conflicts and failed inspection."""
        pending = False
        try:
            if not core_only:
                plan = SourceCatalogIndexManager(self.db).plan()
                if plan.conflicts:
                    return self._state(
                        "incompatible",
                        "La biblioteca requiere revisar índices incompatibles; no se sustituyó ninguno.",
                    )
                if any(
                    spec.unique and self._duplicates(spec.collection, spec.keys)
                    for spec in plan.missing
                ):
                    return self._state(
                        "incompatible",
                        "Hay identidades duplicadas en el catálogo. Sigue el procedimiento de revisión; no se fusionaron ni borraron registros.",
                    )
                pending = bool(plan.missing)
            collections = set(self.db.list_collection_names())
            for name, keys in CORE_IDENTITIES:
                indexes = list(self.db[name].list_indexes()) if name in collections else []
                matching = [index for index in indexes if tuple(index["key"].items()) == keys]
                if not matching:
                    if self._duplicates(name, keys):
                        return self._state(
                            "incompatible",
                            "Hay identidades duplicadas que requieren revisión antes de preparar la biblioteca.",
                        )
                    pending = True
                elif not any(
                    index.get("unique")
                    and not index.get("sparse", False)
                    and all(
                        index.get(option) is None
                        for option in ("partialFilterExpression", "collation", "expireAfterSeconds")
                    )
                    for index in matching
                ):
                    return self._state(
                        "incompatible",
                        "Una restricción de identidad es incompatible. Revisa el procedimiento en Ajustes; no se modificaron los datos.",
                    )
        except PyMongoError:
            return self._state(
                "unverified",
                "No se pudo comprobar la biblioteca. Revisa conexión o permisos y vuelve a comprobar.",
            )
        return self._state(
            "pending" if pending else "ready",
            "Falta preparar las restricciones compatibles de la biblioteca." if pending else "",
        )

    def _duplicates(self, collection, keys):
        """Inspect only missing unique constraints, without repairing records."""
        groups = self.db[collection].aggregate(
            [
                {
                    "$group": {
                        "_id": {field: "$" + field for field, _direction in keys},
                        "count": {"$sum": 1},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 1},
            ],
            maxTimeMS=5000,
        )
        return next(iter(groups), None) is not None

    @staticmethod
    def _state(state, reason):
        return {"state": state, "reason": reason, "version": AUTHORING_VERSION}

    def prepare(self, version):
        """Create missing compatible indexes only after a fresh successful check."""
        state = self.inspect()
        if version != AUTHORING_VERSION or state["state"] not in {"pending", "ready"}:
            return state
        try:
            SourceCatalogIndexManager(self.db).apply()
            for name, keys in CORE_IDENTITIES:
                ensure_compatible_index(self.db[name], list(keys), unique=True)
        except DuplicateKeyError:
            return self._state(
                "incompatible",
                "Hay identidades duplicadas que requieren el procedimiento de revisión. No se borraron ni fusionaron registros.",
            )
        except PyMongoError:
            return self._state(
                "unverified",
                "No se pudo completar la preparación. Comprueba conexión y permisos; no se sustituyeron índices.",
            )
        except RuntimeError:
            return self._state(
                "incompatible",
                "No se completó la preparación. Revisa permisos, duplicados o índices incompatibles en Ajustes; no se borraron ni fusionaron registros.",
            )
        return self.inspect()
