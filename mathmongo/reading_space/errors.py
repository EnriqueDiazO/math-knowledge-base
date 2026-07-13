"""Controlled errors for the persistent document reading space."""


class ReadingSpaceError(RuntimeError):
    """Base class for controlled Reading Space failures."""


class ReadingStateRepositoryError(ReadingSpaceError):
    """A reading-state persistence operation failed."""


class ReadingStateConflictError(ReadingStateRepositoryError):
    """A stable reading-state identity conflicts with persisted data."""


class ReadingSpaceIndexConflictError(ReadingSpaceError):
    """An approved Reading Space index has a conflicting definition."""


__all__ = [
    "ReadingSpaceError",
    "ReadingSpaceIndexConflictError",
    "ReadingStateConflictError",
    "ReadingStateRepositoryError",
]
