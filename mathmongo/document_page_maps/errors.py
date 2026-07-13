"""Controlled errors for S4.2 Document page maps."""


class DocumentPageMapError(RuntimeError):
    """Base error for logical Document page maps."""


class DocumentPageMapRepositoryError(DocumentPageMapError):
    """A controlled page-map persistence operation failed."""


class DocumentPageMapConflictError(DocumentPageMapRepositoryError):
    """A stable page-map identity or active mapping conflicts."""


class DocumentPageMapIndexConflictError(DocumentPageMapError):
    """An installed page-map index differs from the approved definition."""


__all__ = [
    "DocumentPageMapConflictError",
    "DocumentPageMapError",
    "DocumentPageMapIndexConflictError",
    "DocumentPageMapRepositoryError",
]
