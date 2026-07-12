"""Business rules for the Source catalog, scoped to one explicit database."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import ValidationError

from mathmongo.source_catalog.bibtex import BibTeXParseResult
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_text
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.duplicates import find_reference_duplicates
from mathmongo.source_catalog.duplicates import find_source_duplicates
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import utc_now
from mathmongo.source_catalog.repository import ImmutableFieldError
from mathmongo.source_catalog.repository import PhysicalDeletionBlockedError
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import RepositoryConflictError
from mathmongo.source_catalog.repository import SourceRepository

T = TypeVar("T")
FutureLinkDetector = Callable[[Any, str], Iterable[str]]


class CatalogResultStatus(str, Enum):
    """Severity and disposition of a catalog service operation."""

    SUCCESS = "success"
    WARNING = "warning"
    CONFLICT = "conflict"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CatalogResult(Generic[T]):
    """Typed service outcome; callers never need to infer warning severity."""

    status: CatalogResultStatus
    value: T | None = None
    message: str = ""
    duplicates: tuple[DuplicateMatch, ...] = ()
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    persisted: bool = False

    @property
    def ok(self) -> bool:
        """Return whether the caller may treat the operation as non-failing."""
        return self.status in {CatalogResultStatus.SUCCESS, CatalogResultStatus.WARNING}


@dataclass(frozen=True, slots=True)
class DeletionInspection:
    """Read-only decision and blockers for a requested physical deletion."""

    entity_id: str
    exists: bool
    allowed: bool
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BibTeXCandidateImport:
    """Outcome for one explicitly selected BibTeX entry."""

    entry_index: int
    result: CatalogResult[Reference]


@dataclass(frozen=True, slots=True)
class BibTeXImportSummary:
    """Typed aggregate of selected BibTeX import operations."""

    items: tuple[BibTeXCandidateImport, ...] = field(default_factory=tuple)

    @property
    def imported_count(self) -> int:
        """Return how many selected candidates were persisted."""
        return sum(item.result.persisted for item in self.items)


def _source_from_repository(value: Source | Mapping[str, Any]) -> Source:
    return value if isinstance(value, Source) else Source.model_validate(value)


def _reference_from_repository(value: Reference | Mapping[str, Any]) -> Reference:
    return value if isinstance(value, Reference) else Reference.model_validate(value)


def _warning_text(matches: Iterable[DuplicateMatch]) -> tuple[str, ...]:
    warnings: list[str] = []
    for match in matches:
        for warning in match.warnings:
            if warning not in warnings:
                warnings.append(warning)
    return tuple(warnings)


def _repository_database(repository: Any) -> Any:
    for attribute in ("database", "db"):
        if hasattr(repository, attribute):
            return getattr(repository, attribute)
    return None


class SourceCatalogService:
    """Rules for one selected MongoDB database.

    Source/Reference merge is intentionally excluded from S1A. Duplicate
    evidence is returned for an explicit caller decision and never causes an
    automatic merge or a write to a legacy collection.
    """

    _SOURCE_UPDATE_FIELDS = frozenset(
        {
            "name",
            "aliases",
            "source_type",
            "description",
            "language",
            "tags",
            "rights_default",
            "legacy",
        }
    )
    _REFERENCE_DUPLICATE_FIELDS = frozenset(
        {
            "reference_type",
            "bibtex",
            "authors",
            "title",
            "year",
            "year_raw",
            "journal",
            "publisher",
            "volume",
            "number",
            "edition",
            "isbn",
            "doi",
            "url",
        }
    )
    _REFERENCE_UPDATE_FIELDS = frozenset(
        {
            "reference_type",
            "bibtex",
            "authors",
            "title",
            "year",
            "year_raw",
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
            "notes",
            "provenance",
        }
    )

    def __init__(
        self,
        database: Any,
        *,
        source_repository: SourceRepository | None = None,
        reference_repository: ReferenceRepository | None = None,
        future_source_link_detectors: Iterable[FutureLinkDetector] = (),
        future_reference_link_detectors: Iterable[FutureLinkDetector] = (),
    ) -> None:
        """Bind repositories and future blockers to one explicit database."""
        if database is None:
            raise ValueError("An explicit active MongoDB database is required.")
        self.database = database
        self.sources = source_repository or SourceRepository(database)
        self.references = reference_repository or ReferenceRepository(database)
        for repository in (self.sources, self.references):
            repository_database = _repository_database(repository)
            if repository_database is not database:
                raise ValueError("Repositories must use the same explicit active database.")
        self._future_source_link_detectors = tuple(future_source_link_detectors)
        self._future_reference_link_detectors = tuple(future_reference_link_detectors)

    def detect_source_duplicates(
        self,
        candidate: Source,
        *,
        exclude_source_id: str | None = None,
    ) -> list[DuplicateMatch]:
        """Return classified Source matches without changing data."""
        values = self.sources.duplicate_candidates(candidate)
        if values and isinstance(values[0], DuplicateMatch):
            matches = list(values)
        else:
            matches = find_source_duplicates(candidate, values)
        if exclude_source_id is not None:
            matches = [match for match in matches if match.entity_id != exclude_source_id]
        return matches

    def detect_reference_duplicates(
        self,
        candidate: Reference,
        *,
        import_context: str | None = None,
        exclude_reference_id: str | None = None,
    ) -> list[DuplicateMatch]:
        """Return classified Reference matches in Source/import context."""
        values = self.references.duplicate_candidates(candidate)
        if values and isinstance(values[0], DuplicateMatch):
            matches = list(values)
        else:
            matches = find_reference_duplicates(
                candidate,
                values,
                source_context_ids=candidate.source_ids,
                import_context=import_context,
            )
        if exclude_reference_id is not None:
            matches = [
                match for match in matches if match.entity_id != exclude_reference_id
            ]
        return matches

    @staticmethod
    def _duplicate_gate(
        candidate: T,
        duplicates: list[DuplicateMatch],
        *,
        allow_duplicate: bool,
    ) -> CatalogResult[T] | None:
        if not duplicates:
            return None
        duplicate_tuple = tuple(duplicates)
        warnings = _warning_text(duplicates)
        has_conflict = any(
            match.classification
            in {DuplicateClassification.EXACT, DuplicateClassification.STRONG}
            for match in duplicates
        )
        if allow_duplicate:
            return None
        if has_conflict:
            return CatalogResult(
                status=CatalogResultStatus.CONFLICT,
                value=candidate,
                message="Strong duplicate evidence requires an explicit decision.",
                duplicates=duplicate_tuple,
                warnings=warnings,
            )
        return CatalogResult(
            status=CatalogResultStatus.WARNING,
            value=candidate,
            message="Possible duplicate evidence requires confirmation.",
            duplicates=duplicate_tuple,
            warnings=warnings,
        )

    def create_source(
        self,
        data: Source | Mapping[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> CatalogResult[Source]:
        """Create a Source after returning any unaccepted duplicate evidence."""
        try:
            candidate = data if isinstance(data, Source) else Source.model_validate(data)
            duplicates = self.detect_source_duplicates(candidate)
            gated = self._duplicate_gate(
                candidate,
                duplicates,
                allow_duplicate=allow_duplicate,
            )
            if gated is not None:
                return gated
            stored = _source_from_repository(self.sources.insert(candidate))
        except ValidationError as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        return CatalogResult(
            CatalogResultStatus.WARNING if duplicates else CatalogResultStatus.SUCCESS,
            value=stored,
            duplicates=tuple(duplicates),
            warnings=_warning_text(duplicates),
            persisted=True,
        )

    def rename_source(
        self,
        source_id: str,
        new_name: str,
        *,
        keep_previous_as_alias: bool = False,
        allow_duplicate: bool = False,
    ) -> CatalogResult[Source]:
        """Rename while preserving ID and optionally the old name as alias."""
        return self.update_source(
            source_id,
            {"name": new_name},
            preserve_previous_name_as_alias=keep_previous_as_alias,
            allow_duplicate=allow_duplicate,
        )

    def update_source(
        self,
        source_id: str,
        changes: Mapping[str, Any],
        *,
        preserve_previous_name_as_alias: bool = False,
        allow_duplicate: bool = False,
    ) -> CatalogResult[Source]:
        """Update one validated Source profile with duplicate protection."""
        unexpected = set(changes) - self._SOURCE_UPDATE_FIELDS
        if unexpected:
            return CatalogResult(
                CatalogResultStatus.ERROR,
                errors=(f"Unsupported or immutable Source fields: {sorted(unexpected)}",),
            )
        try:
            current_value = self.sources.get_by_id(source_id)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        if current_value is None:
            return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Source not found.")
        try:
            current = _source_from_repository(current_value)
            data = current.model_dump(mode="python")
            data.update(dict(changes))
            changed_fields = set(changes)
            if preserve_previous_name_as_alias and "name" in changes:
                aliases_value = data.get("aliases")
                if aliases_value is None:
                    aliases: list[Any] = []
                elif isinstance(aliases_value, (str, Mapping)) or hasattr(
                    aliases_value,
                    "model_dump",
                ):
                    aliases = [aliases_value]
                else:
                    aliases = list(aliases_value)
                aliases.append({"value": current.name})
                data["aliases"] = aliases
                changed_fields.add("aliases")
            data["updated_at"] = utc_now()
            candidate = Source.model_validate(data)
            duplicates = (
                self.detect_source_duplicates(
                    candidate,
                    exclude_source_id=source_id,
                )
                if changed_fields & {"name", "aliases"}
                else []
            )
            gated = self._duplicate_gate(
                candidate,
                duplicates,
                allow_duplicate=allow_duplicate,
            )
            if gated is not None:
                return gated
            candidate_dump = candidate.model_dump(mode="python")
            controlled = {
                key: candidate_dump[key]
                for key in (*self._SOURCE_UPDATE_FIELDS, "updated_at")
                if key in changed_fields or key == "updated_at"
            }
            updated = self.sources.update(source_id, controlled)
            if updated is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Source not found.")
            return CatalogResult(
                CatalogResultStatus.WARNING if duplicates else CatalogResultStatus.SUCCESS,
                value=_source_from_repository(updated),
                duplicates=tuple(duplicates),
                warnings=_warning_text(duplicates),
                persisted=True,
            )
        except (ValidationError, ImmutableFieldError) as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def archive_source(self, source_id: str) -> CatalogResult[Source]:
        """Archive a Source as the normal removal action."""
        return self._source_state_change(source_id, archive=True)

    def reactivate_source(self, source_id: str) -> CatalogResult[Source]:
        """Reactivate an archived Source."""
        return self._source_state_change(source_id, archive=False)

    def _source_state_change(self, source_id: str, *, archive: bool) -> CatalogResult[Source]:
        try:
            value = self.sources.archive(source_id) if archive else self.sources.reactivate(source_id)
            if value is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Source not found.")
            return CatalogResult(
                CatalogResultStatus.SUCCESS,
                value=_source_from_repository(value),
                persisted=True,
            )
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def _missing_source_ids(self, source_ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            source_id
            for source_id in source_ids
            if self.sources.get_by_id(source_id) is None
        )

    def create_reference(
        self,
        data: Reference | Mapping[str, Any],
        *,
        allow_duplicate: bool = False,
        import_context: str | None = None,
    ) -> CatalogResult[Reference]:
        """Create a Reference without creating any missing Source."""
        try:
            candidate = data if isinstance(data, Reference) else Reference.model_validate(data)
            missing = self._missing_source_ids(candidate.source_ids)
            if missing:
                return CatalogResult(
                    CatalogResultStatus.ERROR,
                    message="Reference cannot create missing Sources.",
                    errors=(f"Unknown source_ids: {list(missing)}",),
                )
            duplicates = self.detect_reference_duplicates(
                candidate,
                import_context=import_context,
            )
            gated = self._duplicate_gate(
                candidate,
                duplicates,
                allow_duplicate=allow_duplicate,
            )
            if gated is not None:
                return gated
            stored = _reference_from_repository(self.references.insert(candidate))
        except ValidationError as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        return CatalogResult(
            CatalogResultStatus.WARNING if duplicates else CatalogResultStatus.SUCCESS,
            value=stored,
            duplicates=tuple(duplicates),
            warnings=_warning_text(duplicates),
            persisted=True,
        )

    def update_reference(
        self,
        reference_id: str,
        changes: Mapping[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> CatalogResult[Reference]:
        """Update approved bibliographic fields and derived fingerprints."""
        unexpected = set(changes) - self._REFERENCE_UPDATE_FIELDS
        if unexpected:
            return CatalogResult(
                CatalogResultStatus.ERROR,
                errors=(f"Unsupported or immutable Reference fields: {sorted(unexpected)}",),
            )
        try:
            current_value = self.references.get_by_id(reference_id)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        if current_value is None:
            return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Reference not found.")
        try:
            current = _reference_from_repository(current_value)
            data = current.model_dump(mode="python")
            data.update(dict(changes))
            data["updated_at"] = utc_now()
            candidate = Reference.model_validate(data)
            duplicates = (
                self.detect_reference_duplicates(
                    candidate,
                    exclude_reference_id=reference_id,
                )
                if set(changes) & self._REFERENCE_DUPLICATE_FIELDS
                else []
            )
            gated = self._duplicate_gate(
                candidate,
                duplicates,
                allow_duplicate=allow_duplicate,
            )
            if gated is not None:
                return gated
            controlled_dump = candidate.model_dump(mode="python")
            controlled = {
                key: controlled_dump[key]
                for key in (
                    *self._REFERENCE_UPDATE_FIELDS,
                    "doi_normalized",
                    "fingerprints",
                    "status",
                    "updated_at",
                )
                if key in changes
                or key in {"doi_normalized", "fingerprints", "status", "updated_at"}
            }
            updated = self.references.update(reference_id, controlled)
            if updated is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Reference not found.")
            return CatalogResult(
                CatalogResultStatus.WARNING if duplicates else CatalogResultStatus.SUCCESS,
                value=_reference_from_repository(updated),
                duplicates=tuple(duplicates),
                warnings=_warning_text(duplicates),
                persisted=True,
            )
        except (ValidationError, ImmutableFieldError) as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def archive_reference(self, reference_id: str) -> CatalogResult[Reference]:
        """Archive a Reference as the normal removal action."""
        return self._reference_state_change(reference_id, archive=True)

    def reactivate_reference(self, reference_id: str) -> CatalogResult[Reference]:
        """Reactivate an archived Reference."""
        return self._reference_state_change(reference_id, archive=False)

    def _reference_state_change(
        self,
        reference_id: str,
        *,
        archive: bool,
    ) -> CatalogResult[Reference]:
        try:
            value = (
                self.references.archive(reference_id)
                if archive
                else self.references.reactivate(reference_id)
            )
            if value is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Reference not found.")
            return CatalogResult(
                CatalogResultStatus.SUCCESS,
                value=_reference_from_repository(value),
                persisted=True,
            )
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def associate_reference(
        self,
        reference_id: str,
        source_id: str,
    ) -> CatalogResult[Reference]:
        """Associate an existing Reference with an existing Source."""
        try:
            source = self.sources.get_by_id(source_id)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        if source is None:
            return CatalogResult(
                CatalogResultStatus.ERROR,
                errors=(f"Unknown source_id: {source_id}",),
            )
        try:
            value = self.references.associate_source(reference_id, source_id)
            if value is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Reference not found.")
            return CatalogResult(
                CatalogResultStatus.SUCCESS,
                value=_reference_from_repository(value),
                persisted=True,
            )
        except (ValidationError, ImmutableFieldError) as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def disassociate_reference(
        self,
        reference_id: str,
        source_id: str,
    ) -> CatalogResult[Reference]:
        """Remove a Source association without deleting either entity."""
        try:
            value = self.references.disassociate_source(reference_id, source_id)
            if value is None:
                return CatalogResult(CatalogResultStatus.NOT_FOUND, message="Reference not found.")
            return CatalogResult(
                CatalogResultStatus.SUCCESS,
                value=_reference_from_repository(value),
                persisted=True,
            )
        except (ValidationError, ImmutableFieldError) as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        except RepositoryConflictError as exc:
            return CatalogResult(CatalogResultStatus.CONFLICT, errors=(str(exc),))
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))

    def _future_blockers(
        self,
        entity_id: str,
        detectors: Iterable[FutureLinkDetector],
    ) -> list[str]:
        blockers: list[str] = []
        for detector in detectors:
            try:
                values = detector(self.database, entity_id)
                for value in values:
                    text = str(value)
                    if text and text not in blockers:
                        blockers.append(text)
            except Exception as exc:
                blockers.append(f"Future-link detector failed closed: {exc}")
        return blockers

    def inspect_source_deletion(self, source_id: str) -> DeletionInspection:
        """Collect present and future Source deletion blockers read-only."""
        if self.sources.get_by_id(source_id) is None:
            return DeletionInspection(source_id, exists=False, allowed=False, blockers=("not_found",))
        blockers = list(self.sources.deletion_blockers(source_id))
        blockers.extend(
            self._future_blockers(source_id, self._future_source_link_detectors)
        )
        blockers = list(dict.fromkeys(blockers))
        return DeletionInspection(
            source_id,
            exists=True,
            allowed=not blockers,
            blockers=tuple(blockers),
        )

    def delete_source_if_unused(self, source_id: str) -> CatalogResult[bool]:
        """Physically delete only a Source confirmed unused."""
        try:
            inspection = self.inspect_source_deletion(source_id)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, value=False, errors=(str(exc),))
        if not inspection.exists:
            return CatalogResult(CatalogResultStatus.NOT_FOUND, value=False)
        if not inspection.allowed:
            return CatalogResult(
                CatalogResultStatus.BLOCKED,
                value=False,
                blockers=inspection.blockers,
            )
        try:
            deleted = bool(self.sources.physical_delete_if_unused(source_id))
        except PhysicalDeletionBlockedError as exc:
            return CatalogResult(
                CatalogResultStatus.BLOCKED,
                value=False,
                blockers=tuple(getattr(exc, "blockers", ()) or (str(exc),)),
            )
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, value=False, errors=(str(exc),))
        return CatalogResult(
            CatalogResultStatus.SUCCESS if deleted else CatalogResultStatus.NOT_FOUND,
            value=deleted,
            persisted=deleted,
        )

    def inspect_reference_deletion(self, reference_id: str) -> DeletionInspection:
        """Collect present and future Reference deletion blockers read-only."""
        if self.references.get_by_id(reference_id) is None:
            return DeletionInspection(
                reference_id,
                exists=False,
                allowed=False,
                blockers=("not_found",),
            )
        blockers = list(self.references.deletion_blockers(reference_id))
        blockers.extend(
            self._future_blockers(reference_id, self._future_reference_link_detectors)
        )
        blockers = list(dict.fromkeys(blockers))
        return DeletionInspection(
            reference_id,
            exists=True,
            allowed=not blockers,
            blockers=tuple(blockers),
        )

    def delete_reference_if_unused(self, reference_id: str) -> CatalogResult[bool]:
        """Physically delete only a Reference confirmed unused."""
        try:
            inspection = self.inspect_reference_deletion(reference_id)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, value=False, errors=(str(exc),))
        if not inspection.exists:
            return CatalogResult(CatalogResultStatus.NOT_FOUND, value=False)
        if not inspection.allowed:
            return CatalogResult(
                CatalogResultStatus.BLOCKED,
                value=False,
                blockers=inspection.blockers,
            )
        try:
            deleted = bool(self.references.physical_delete_if_unused(reference_id))
        except PhysicalDeletionBlockedError as exc:
            return CatalogResult(
                CatalogResultStatus.BLOCKED,
                value=False,
                blockers=tuple(getattr(exc, "blockers", ()) or (str(exc),)),
            )
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, value=False, errors=(str(exc),))
        return CatalogResult(
            CatalogResultStatus.SUCCESS if deleted else CatalogResultStatus.NOT_FOUND,
            value=deleted,
            persisted=deleted,
        )

    def preview_bibtex(
        self,
        content: str | bytes,
        *,
        from_file: bool = False,
    ) -> BibTeXParseResult:
        """Return a pure preview. This method deliberately performs no write."""
        if from_file or isinstance(content, bytes):
            return parse_bibtex_file_content(content)
        return parse_bibtex_text(content)

    def import_selected_bibtex_candidates(
        self,
        preview: BibTeXParseResult,
        selected_entry_indices: Iterable[int],
        *,
        source_ids: Iterable[str] = (),
        allow_duplicate: bool = False,
    ) -> CatalogResult[BibTeXImportSummary]:
        """Persist only selected valid preview entries, preserving raw data."""
        selected = tuple(dict.fromkeys(int(index) for index in selected_entry_indices))
        source_id_list = list(dict.fromkeys(source_ids))
        try:
            missing_sources = self._missing_source_ids(source_id_list)
        except Exception as exc:
            return CatalogResult(CatalogResultStatus.ERROR, errors=(str(exc),))
        if missing_sources:
            return CatalogResult(
                CatalogResultStatus.ERROR,
                errors=(f"Unknown source_ids: {list(missing_sources)}",),
            )
        candidates = {int(item["entry_index"]): item for item in preview.candidates}
        unknown = [index for index in selected if index not in candidates]
        if unknown:
            return CatalogResult(
                CatalogResultStatus.ERROR,
                errors=(f"Unknown BibTeX entry indices: {unknown}",),
            )

        items: list[BibTeXCandidateImport] = []
        for entry_index in selected:
            data = deepcopy(candidates[entry_index]["reference_data"])
            data["source_ids"] = source_id_list
            result = self.create_reference(
                data,
                allow_duplicate=allow_duplicate,
                import_context=f"bibtex-entry:{entry_index}",
            )
            items.append(BibTeXCandidateImport(entry_index, result))

        summary = BibTeXImportSummary(tuple(items))
        statuses = {item.result.status for item in items}
        if CatalogResultStatus.ERROR in statuses:
            status = CatalogResultStatus.ERROR
        elif CatalogResultStatus.CONFLICT in statuses:
            status = CatalogResultStatus.CONFLICT
        elif CatalogResultStatus.BLOCKED in statuses:
            status = CatalogResultStatus.BLOCKED
        elif CatalogResultStatus.WARNING in statuses:
            status = CatalogResultStatus.WARNING
        else:
            status = CatalogResultStatus.SUCCESS
        return CatalogResult(
            status,
            value=summary,
            persisted=summary.imported_count > 0,
        )


__all__ = [
    "BibTeXCandidateImport",
    "BibTeXImportSummary",
    "CatalogResult",
    "CatalogResultStatus",
    "DeletionInspection",
    "FutureLinkDetector",
    "SourceCatalogService",
]
