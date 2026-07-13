"""Controlled S4 domain, persistence, and index errors."""


class ReadingAnnotationError(RuntimeError):
    """Base error for S4 reading annotations."""


class ReadingAnnotationRepositoryError(ReadingAnnotationError):
    """A controlled S4 persistence operation failed."""


class ReadingAnnotationConflictError(ReadingAnnotationRepositoryError):
    """A stable S4 identity conflicts with persisted data."""


class ReadingAnnotationIndexConflictError(ReadingAnnotationError):
    """An installed S4 index differs from the approved definition."""


__all__ = [
    "ReadingAnnotationConflictError",
    "ReadingAnnotationError",
    "ReadingAnnotationIndexConflictError",
    "ReadingAnnotationRepositoryError",
]
