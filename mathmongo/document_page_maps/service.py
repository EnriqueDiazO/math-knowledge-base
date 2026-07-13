"""Validated service for logical PDF-to-book page mapping."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import ValidationError

from mathmongo.document_page_maps.errors import DocumentPageMapConflictError
from mathmongo.document_page_maps.errors import DocumentPageMapIndexConflictError
from mathmongo.document_page_maps.errors import DocumentPageMapRepositoryError
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import ManualPageOverride
from mathmongo.document_page_maps.models import PageLabelRule
from mathmongo.document_page_maps.models import PageLabelStyle
from mathmongo.document_page_maps.models import PageMapStatus
from mathmongo.document_page_maps.models import compute_book_page_label
from mathmongo.document_page_maps.models import utc_now
from mathmongo.document_page_maps.models import validate_rule_id
from mathmongo.document_page_maps.repository import DocumentPageMapPage
from mathmongo.document_page_maps.repository import DocumentPageMapRepository
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.repository import SourceDocumentRepository

T = TypeVar("T")


class PageMapOperationStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ARCHIVED = "archived"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"
    BLOCKED = "blocked"
    ERROR = "error"


class PageLabelMatch(str, Enum):
    OVERRIDE = "override"
    RULE = "rule"
    UNMAPPED = "unmapped"


@dataclass(frozen=True, slots=True)
class PageMapServiceResult(Generic[T]):
    status: PageMapOperationStatus
    value: T | None = None
    message: str = ""

    @property
    def completed(self) -> bool:
        return self.status == PageMapOperationStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class PageLabelComputation:
    page_map: DocumentPageMap
    pdf_page: int
    book_page_label: str | None
    matched_by: PageLabelMatch
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class PageMapDocumentContext:
    document: SourceDocument
    source: Source


class DocumentPageMapService:
    """Coordinate page maps with immutable S2 Document and Source identities."""

    def __init__(
        self,
        database: Any,
        *,
        page_maps: DocumentPageMapRepository | None = None,
        documents: SourceDocumentRepository | None = None,
        sources: SourceRepository | None = None,
        index_manager: DocumentPageMapIndexManager | None = None,
    ) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("DocumentPageMapService requires an explicit database")
        self.database = database
        self.page_maps = page_maps or DocumentPageMapRepository(database)
        self.documents = documents or SourceDocumentRepository(database)
        self.sources = sources or SourceRepository(database)
        self.index_manager = index_manager or DocumentPageMapIndexManager(database)

    @staticmethod
    def _result(
        status: PageMapOperationStatus,
        value: T | None = None,
        message: str = "",
    ) -> PageMapServiceResult[T]:
        return PageMapServiceResult(status, value, message)

    @staticmethod
    def _scope_is_local(user_scope: str) -> PageMapServiceResult[None] | None:
        if user_scope != "local":
            return PageMapServiceResult(
                PageMapOperationStatus.INVALID_STATE,
                message="Document page maps currently support only user_scope='local'.",
            )
        return None

    def _write_gate(self) -> PageMapServiceResult[None] | None:
        try:
            plan = self.index_manager.plan()
        except DocumentPageMapIndexConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR,
                message="Could not inspect Document page-map indexes.",
            )
        if plan.conflicts:
            return self._result(
                PageMapOperationStatus.CONFLICT,
                message="Document page-map indexes conflict with the approved plan.",
            )
        if plan.missing:
            return self._result(
                PageMapOperationStatus.INVALID_STATE,
                message="Initialize the approved Document page-map indexes before writing.",
            )
        return None

    def _document_context(
        self,
        document_id: str,
        *,
        require_active: bool,
    ) -> PageMapServiceResult[PageMapDocumentContext]:
        try:
            document = self.documents.get_by_id(document_id)
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not load the Document."
            )
        if document is None:
            return self._result(PageMapOperationStatus.NOT_FOUND, message="Document not found.")
        try:
            source = self.sources.get_by_id(document.source_id)
        except Exception:
            return self._result(PageMapOperationStatus.ERROR, message="Could not load the Source.")
        if source is None:
            return self._result(
                PageMapOperationStatus.NOT_FOUND,
                message="The Document Source does not exist.",
            )
        if document.kind != DocumentKind.PDF:
            return self._result(
                PageMapOperationStatus.BLOCKED,
                message="Logical page maps apply only to PDF Documents.",
            )
        if require_active and document.status == DocumentStatus.ARCHIVED:
            return self._result(
                PageMapOperationStatus.ARCHIVED,
                PageMapDocumentContext(document, source),
                "Archived Documents cannot receive page-map changes.",
            )
        return self._result(
            PageMapOperationStatus.SUCCESS,
            PageMapDocumentContext(document, source),
        )

    def _validate_map_context(
        self,
        page_map: DocumentPageMap,
        *,
        require_active_document: bool,
    ) -> PageMapServiceResult[PageMapDocumentContext]:
        context = self._document_context(
            page_map.document_id,
            require_active=require_active_document,
        )
        if not context.completed or context.value is None:
            return context
        if context.value.document.source_id != page_map.source_id:
            return self._result(
                PageMapOperationStatus.CONFLICT,
                message="Page-map Source does not match its Document.",
            )
        return context

    def get_page_map(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        context = self._document_context(document_id, require_active=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        try:
            page_map = self.page_maps.get_active(document_id, user_scope=user_scope)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not load the page map."
            )
        if page_map is None:
            return self._result(
                PageMapOperationStatus.NOT_FOUND, message="No active page map exists."
            )
        if context.value is None or page_map.source_id != context.value.document.source_id:
            return self._result(
                PageMapOperationStatus.CONFLICT,
                message="Page-map Source does not match its Document.",
            )
        return self._result(PageMapOperationStatus.SUCCESS, page_map)

    def get_page_map_by_id(self, page_map_id: str) -> PageMapServiceResult[DocumentPageMap]:
        try:
            page_map = self.page_maps.get_by_id(page_map_id)
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not load the page map."
            )
        if page_map is None:
            return self._result(PageMapOperationStatus.NOT_FOUND, message="Page map not found.")
        context = self._validate_map_context(page_map, require_active_document=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        return self._result(PageMapOperationStatus.SUCCESS, page_map)

    def list_page_maps(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
        status: PageMapStatus | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PageMapServiceResult[DocumentPageMapPage]:
        """List bounded active or archived maps after validating their Document context."""
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        context = self._document_context(document_id, require_active=False)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        try:
            result = self.page_maps.list_by_document(
                document_id,
                user_scope=user_scope,
                status=status,
                page=page,
                page_size=page_size,
            )
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(PageMapOperationStatus.ERROR, message="Could not list page maps.")
        if any(item.source_id != context.value.document.source_id for item in result.items):
            return self._result(
                PageMapOperationStatus.CONFLICT,
                message="A Page-map Source does not match its Document.",
            )
        return self._result(PageMapOperationStatus.SUCCESS, result)

    def compute_page_label(
        self,
        document_id: str,
        pdf_page: int,
        *,
        user_scope: str = "local",
    ) -> PageMapServiceResult[PageLabelComputation]:
        current = self.get_page_map(document_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return self._result(current.status, message=current.message)
        try:
            label = compute_book_page_label(current.value, pdf_page)
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        override = next(
            (item for item in current.value.manual_overrides if item.pdf_page == pdf_page),
            None,
        )
        rule = next(
            (
                item
                for item in current.value.rules
                if item.pdf_start_page <= pdf_page
                and (item.pdf_end_page is None or pdf_page <= item.pdf_end_page)
            ),
            None,
        )
        matched_by = (
            PageLabelMatch.OVERRIDE
            if override is not None
            else PageLabelMatch.RULE
            if rule is not None
            else PageLabelMatch.UNMAPPED
        )
        return self._result(
            PageMapOperationStatus.SUCCESS,
            PageLabelComputation(
                page_map=current.value,
                pdf_page=pdf_page,
                book_page_label=label,
                matched_by=matched_by,
                rule_id=rule.rule_id if rule is not None and override is None else None,
            ),
        )

    def _active_or_new(
        self,
        context: PageMapDocumentContext,
        *,
        user_scope: str,
    ) -> tuple[DocumentPageMap, bool]:
        current = self.page_maps.get_active(
            context.document.document_id,
            user_scope=user_scope,
        )
        if current is not None:
            if current.source_id != context.document.source_id:
                raise DocumentPageMapConflictError(
                    "Active page-map Source does not match its Document"
                )
            return current, True
        return (
            DocumentPageMap(
                document_id=context.document.document_id,
                source_id=context.document.source_id,
                user_scope=user_scope,
            ),
            False,
        )

    def _persist(
        self,
        page_map: DocumentPageMap,
        *,
        existed: bool,
    ) -> PageMapServiceResult[DocumentPageMap]:
        try:
            stored = (
                self.page_maps.replace(page_map) if existed else self.page_maps.insert(page_map)
            )
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except DocumentPageMapRepositoryError:
            return self._result(
                PageMapOperationStatus.ERROR,
                message="Could not persist the Document page map.",
            )
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR,
                message="Unexpected Document page-map persistence error.",
            )
        if stored is None:
            return self._result(PageMapOperationStatus.NOT_FOUND, message="Page map not found.")
        return self._result(PageMapOperationStatus.SUCCESS, stored)

    def _write_context(
        self,
        document_id: str,
        *,
        user_scope: str,
    ) -> PageMapServiceResult[PageMapDocumentContext]:
        gate = self._write_gate() or self._scope_is_local(user_scope)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        return self._document_context(document_id, require_active=True)

    def set_quick_rule(
        self,
        document_id: str,
        *,
        current_pdf_page: int,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        context = self._write_context(document_id, user_scope=user_scope)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        try:
            current, existed = self._active_or_new(context.value, user_scope=user_scope)
            rule = PageLabelRule(
                pdf_start_page=current_pdf_page,
                label_start=1,
                label_style=PageLabelStyle.ARABIC,
            )
            payload = current.model_dump(mode="python")
            payload.update({"rules": [rule], "updated_at": utc_now()})
            candidate = DocumentPageMap.model_validate(payload)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        return self._persist(candidate, existed=existed)

    def add_rule(
        self,
        document_id: str,
        *,
        pdf_start_page: int,
        label_start: int | str,
        label_style: PageLabelStyle | str,
        pdf_end_page: int | None = None,
        label_prefix: str | None = None,
        rule_id: str | None = None,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        context = self._write_context(document_id, user_scope=user_scope)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        values: dict[str, Any] = {
            "pdf_start_page": pdf_start_page,
            "pdf_end_page": pdf_end_page,
            "label_start": label_start,
            "label_style": label_style,
            "label_prefix": label_prefix,
        }
        if rule_id is not None:
            values["rule_id"] = rule_id
        try:
            rule = PageLabelRule.model_validate(values)
            current, existed = self._active_or_new(context.value, user_scope=user_scope)
            if any(_rules_overlap(existing, rule) for existing in current.rules):
                return self._result(
                    PageMapOperationStatus.CONFLICT,
                    message="Page label rule overlaps an existing rule.",
                )
            payload = current.model_dump(mode="python")
            payload.update({"rules": [*current.rules, rule], "updated_at": utc_now()})
            candidate = DocumentPageMap.model_validate(payload)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        return self._persist(candidate, existed=existed)

    def update_rule(
        self,
        document_id: str,
        rule_id: str,
        *,
        pdf_start_page: int,
        label_start: int | str,
        label_style: PageLabelStyle | str,
        pdf_end_page: int | None = None,
        label_prefix: str | None = None,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        context = self._write_context(document_id, user_scope=user_scope)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        try:
            validate_rule_id(rule_id)
            current = self.page_maps.get_active(document_id, user_scope=user_scope)
            if current is None:
                return self._result(
                    PageMapOperationStatus.NOT_FOUND, message="No active page map exists."
                )
            if current.source_id != context.value.document.source_id:
                return self._result(
                    PageMapOperationStatus.CONFLICT,
                    message="Page-map Source does not match its Document.",
                )
            if all(item.rule_id != rule_id for item in current.rules):
                return self._result(
                    PageMapOperationStatus.NOT_FOUND, message="Page label rule not found."
                )
            replacement = PageLabelRule(
                rule_id=rule_id,
                pdf_start_page=pdf_start_page,
                pdf_end_page=pdf_end_page,
                label_start=label_start,
                label_style=label_style,
                label_prefix=label_prefix,
            )
            others = [item for item in current.rules if item.rule_id != rule_id]
            if any(_rules_overlap(item, replacement) for item in others):
                return self._result(
                    PageMapOperationStatus.CONFLICT,
                    message="Updated page label rule overlaps an existing rule.",
                )
            payload = current.model_dump(mode="python")
            payload.update({"rules": [*others, replacement], "updated_at": utc_now()})
            candidate = DocumentPageMap.model_validate(payload)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        return self._persist(candidate, existed=True)

    def upsert_override(
        self,
        document_id: str,
        *,
        pdf_page: int,
        book_page_label: str,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        context = self._write_context(document_id, user_scope=user_scope)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        try:
            override = ManualPageOverride(
                pdf_page=pdf_page,
                book_page_label=book_page_label,
            )
            current, existed = self._active_or_new(context.value, user_scope=user_scope)
            overrides = [item for item in current.manual_overrides if item.pdf_page != pdf_page]
            payload = current.model_dump(mode="python")
            payload.update({"manual_overrides": [*overrides, override], "updated_at": utc_now()})
            candidate = DocumentPageMap.model_validate(payload)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        return self._persist(candidate, existed=existed)

    def archive_page_map(self, page_map_id: str) -> PageMapServiceResult[DocumentPageMap]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        try:
            value = self.page_maps.archive(page_map_id)
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not archive the page map."
            )
        if value is None:
            return self._result(PageMapOperationStatus.NOT_FOUND, message="Page map not found.")
        return self._result(PageMapOperationStatus.SUCCESS, value)

    def reactivate_page_map(self, page_map_id: str) -> PageMapServiceResult[DocumentPageMap]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        try:
            current = self.page_maps.get_by_id(page_map_id)
            if current is None:
                return self._result(PageMapOperationStatus.NOT_FOUND, message="Page map not found.")
            context = self._validate_map_context(current, require_active_document=True)
            if not context.completed:
                return self._result(context.status, message=context.message)
            active = self.page_maps.get_active(
                current.document_id,
                user_scope=current.user_scope,
            )
            if active is not None and active.page_map_id != current.page_map_id:
                return self._result(
                    PageMapOperationStatus.CONFLICT,
                    message="Another active page map already exists for this Document.",
                )
            value = self.page_maps.reactivate(page_map_id)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(PageMapOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not reactivate the page map."
            )
        return self._result(PageMapOperationStatus.SUCCESS, value)

    def reset_page_map(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> PageMapServiceResult[DocumentPageMap]:
        context = self._write_context(document_id, user_scope=user_scope)
        if not context.completed or context.value is None:
            return self._result(context.status, message=context.message)
        try:
            current = self.page_maps.get_active(document_id, user_scope=user_scope)
            if current is None:
                return self._result(
                    PageMapOperationStatus.NOT_FOUND, message="No active page map exists."
                )
            if current.source_id != context.value.document.source_id:
                return self._result(
                    PageMapOperationStatus.CONFLICT,
                    message="Page-map Source does not match its Document.",
                )
            value = self.page_maps.reset(current.page_map_id)
        except DocumentPageMapConflictError as exc:
            return self._result(PageMapOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                PageMapOperationStatus.ERROR, message="Could not reset the page map."
            )
        return self._result(PageMapOperationStatus.SUCCESS, value)


def _rules_overlap(left: PageLabelRule, right: PageLabelRule) -> bool:
    left_end = left.pdf_end_page if left.pdf_end_page is not None else float("inf")
    right_end = right.pdf_end_page if right.pdf_end_page is not None else float("inf")
    return left.pdf_start_page <= right_end and right.pdf_start_page <= left_end


__all__ = [
    "DocumentPageMapService",
    "PageLabelComputation",
    "PageLabelMatch",
    "PageMapDocumentContext",
    "PageMapOperationStatus",
    "PageMapServiceResult",
]
