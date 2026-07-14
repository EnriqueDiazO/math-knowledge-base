"""Explicit dependency graph for the side-effect-free app factory."""

# ruff: noqa: D102

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathmongo.document_page_maps.service import DocumentPageMapService
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.service import ReadingSpaceService
from mathmongo.source_documents.service import SourceDocumentService


def default_frontend_root() -> Path:
    """Resolve packaged read-only assets without creating any directory."""
    return Path(__file__).resolve().parent / "static" / "advanced_reader"


@dataclass(frozen=True, slots=True)
class AdvancedReaderDependencies:
    """All stateful collaborators required by one local reader process."""

    database_name: str
    document_service: SourceDocumentService
    reading_service: ReadingSpaceService
    page_map_service: DocumentPageMapService
    frontend_root: Path
    health_check: Callable[[], bool]
    annotation_service: ReadingAnnotationService | None = None
    annotation_index_manager: ReadingAnnotationIndexManager | None = None

    @classmethod
    def from_database(
        cls,
        database: Any,
        *,
        database_name: str,
        frontend_root: str | Path | None = None,
        health_check: Callable[[], bool] | None = None,
    ) -> AdvancedReaderDependencies:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("Advanced Reader requires an explicit database")
        name = " ".join(str(database_name or "").strip().split())
        if not name or len(name) > 128:
            raise ValueError("Advanced Reader requires a bounded database name")
        document_service = SourceDocumentService(database)
        reading_service = ReadingSpaceService(
            database,
            document_service=document_service,
            documents=document_service.documents,
            sources=document_service.sources,
            references=document_service.references,
        )
        annotation_index_manager = ReadingAnnotationIndexManager(database)
        return cls(
            database_name=name,
            document_service=document_service,
            reading_service=reading_service,
            page_map_service=DocumentPageMapService(
                database,
                documents=document_service.documents,
                sources=document_service.sources,
            ),
            frontend_root=Path(frontend_root or default_frontend_root()),
            health_check=health_check or (lambda: True),
            annotation_service=ReadingAnnotationService(
                database,
                documents=document_service.documents,
                sources=document_service.sources,
                references=document_service.references,
                index_manager=annotation_index_manager,
                document_service=document_service,
            ),
            annotation_index_manager=annotation_index_manager,
        )

    @property
    def visual_annotation_writes_ready(self) -> bool:
        """Inspect the explicit Notes & Evidence plan without applying indexes."""
        if self.annotation_service is None or self.annotation_index_manager is None:
            return False
        try:
            return self.annotation_index_manager.plan().initialized
        except Exception:
            return False

    @property
    def frontend_ready(self) -> bool:
        index = self.frontend_root / "index.html"
        assets = self.frontend_root / "assets"
        favicon = self.frontend_root / "favicon.svg"
        notices = self.frontend_root / "third-party"
        try:
            if (
                not index.is_file()
                or index.is_symlink()
                or index.stat().st_size > 64 * 1024
                or not assets.is_dir()
                or assets.is_symlink()
                or not favicon.is_file()
                or favicon.is_symlink()
            ):
                return False
            html = index.read_text(encoding="utf-8")
            references = re.findall(r'(?:src|href)="(/assets/[A-Za-z0-9_.-]+)"', html)
            referenced_files = [
                self.frontend_root / value.removeprefix("/") for value in references
            ]
            has_script = any(path.suffix == ".js" for path in referenced_files)
            has_style = any(path.suffix == ".css" for path in referenced_files)
            if not has_script or not has_style:
                return False
            if any(not path.is_file() or path.is_symlink() for path in referenced_files):
                return False
            workers = tuple(assets.glob("pdf.worker.min-*.mjs"))
            if len(workers) != 1 or workers[0].is_symlink() or not workers[0].is_file():
                return False
            required_notices = (
                "THIRD_PARTY_NOTICES.txt",
                "pdfjs-LICENSE.txt",
                "react-LICENSE.txt",
                "react-dom-LICENSE.txt",
            )
            return all(
                (notices / name).is_file() and not (notices / name).is_symlink()
                for name in required_notices
            )
        except OSError:
            return False


__all__ = ["AdvancedReaderDependencies", "default_frontend_root"]
