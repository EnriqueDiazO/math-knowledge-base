"""Explicit, non-destructive preparation of reading and annotation capabilities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pymongo.errors import ConnectionFailure
from pymongo.errors import DuplicateKeyError
from pymongo.errors import OperationFailure

from mathmongo.reading_annotations.errors import ReadingAnnotationIndexConflictError
from mathmongo.reading_annotations.indexes import READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_space.errors import ReadingSpaceIndexConflictError
from mathmongo.reading_space.indexes import READING_SPACE_INDEXES
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager


class PreparationState(str, Enum):
    """A failed inspection is distinct from an approved missing-index plan."""

    READY = "ready"
    PENDING = "pending"
    INCOMPATIBLE = "incompatible"
    UNVERIFIED = "unverified"


def _version() -> str:
    specifications = [
        (getattr(spec, 'collection', 'document_reading_state'), spec.name, spec.keys, spec.unique)
        for spec in (*READING_SPACE_INDEXES, *READING_ANNOTATION_INDEXES)
    ]
    return hashlib.sha256(json.dumps(specifications, sort_keys=True).encode()).hexdigest()


PREPARATION_VERSION = _version()


@dataclass(frozen=True)
class ReadingPreparationStatus:
    """Backend-verified result bound to the active database object and contract."""

    state: PreparationState
    context: str
    version: str
    reason: str = ''
    plans: tuple[tuple[str, Any], ...] = ()

    @property
    def ready(self) -> bool:
        """Only a complete read-back can enable writes."""
        return self.state == PreparationState.READY

    def capability_ready(self, name: str) -> bool:
        """Keep independent capabilities available when another one is blocked."""
        return any(label == name and plan.initialized for label, plan in self.plans)


class ReadingPreparation:
    """Reuse approved index managers; never drop indexes or edit user records."""

    def __init__(self, database: Any, *, connection_label: str = '', managers=None):
        """Bind without I/O; an endpoint replacement invalidates earlier results."""
        self.database = database
        self.context = f'{connection_label}\x1f{database.name}\x1f{id(database):x}'
        self.version = PREPARATION_VERSION
        self.managers = tuple(managers) if managers is not None else (
            ('reading', ReadingSpaceIndexManager(database)),
            ('notes', ReadingAnnotationIndexManager(database)),
        )

    def _result(self, state, *, reason='', plans=()) -> ReadingPreparationStatus:
        return ReadingPreparationStatus(state, self.context, self.version, reason, tuple(plans))

    def _failure(self, error: Exception, *, plans=()) -> ReadingPreparationStatus:
        if isinstance(error, (DuplicateKeyError, ReadingAnnotationIndexConflictError,
                              ReadingSpaceIndexConflictError)):
            return self._result(PreparationState.INCOMPATIBLE, reason='conflict', plans=plans)
        if isinstance(error, OperationFailure):
            if error.code in {85, 86, 11000}:
                return self._result(PreparationState.INCOMPATIBLE, reason='conflict', plans=plans)
            if error.code in {13, 18}:
                return self._result(PreparationState.UNVERIFIED, reason='permission', plans=plans)
        reason = 'connection' if isinstance(error, ConnectionFailure) else 'inspection'
        return self._result(PreparationState.UNVERIFIED, reason=reason, plans=plans)

    def _duplicates(self, manager, plan) -> bool:
        """Bounded preflight for unique indexes, including missing/null keys."""
        for spec in plan.missing:
            if not spec.unique:
                continue
            collection = getattr(spec, 'collection', manager.COLLECTION if hasattr(manager, 'COLLECTION') else '')
            grouped_keys = {f'k{i}': {'$ifNull': ['$' + field, None]}
                            for i, (field, _direction) in enumerate(spec.keys)}
            duplicate = next(iter(self.database[collection].aggregate([
                {'$group': {'_id': grouped_keys, 'count': {'$sum': 1}}},
                {'$match': {'count': {'$gt': 1}}}, {'$limit': 1},
            ], maxTimeMS=3000, allowDiskUse=False)), None)
            if duplicate is not None:
                return True
        return False

    def inspect(self) -> ReadingPreparationStatus:
        """Inspect only; permission/network failures never become missing indexes."""
        plans = []
        try:
            for name, manager in self.managers:
                plan = manager.plan()
                plans.append((name, plan))
            if any(plan.conflicts for _, plan in plans):
                return self._result(PreparationState.INCOMPATIBLE, reason='index', plans=plans)
            for (_name, manager), (_label, plan) in zip(self.managers, plans, strict=True):
                if not plan.initialized and self._duplicates(manager, plan):
                    return self._result(PreparationState.INCOMPATIBLE, reason='duplicates', plans=plans)
        except Exception as error:
            return self._failure(error, plans=plans)
        state = PreparationState.READY if all(plan.initialized for _, plan in plans) else PreparationState.PENDING
        return self._result(state, plans=plans)

    def prepare(self, expected: ReadingPreparationStatus) -> ReadingPreparationStatus:
        """Apply only compatible missing indexes and verify again from the backend."""
        if expected.context != self.context or expected.version != self.version:
            return self._result(PreparationState.UNVERIFIED, reason='context')
        before = self.inspect()
        if before.state != PreparationState.PENDING:
            return before
        try:
            for (_name, manager), (_label, plan) in zip(self.managers, before.plans, strict=True):
                if not plan.initialized:
                    manager.apply()
        except Exception as error:
            after = self.inspect()
            return after if after.ready else self._failure(error, plans=after.plans)
        after = self.inspect()
        if after.state == PreparationState.PENDING:
            return self._result(PreparationState.UNVERIFIED, reason='verification', plans=after.plans)
        return after
