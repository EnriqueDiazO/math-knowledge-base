"""Pure parsing for one bounded HTTP byte range."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RangeErrorCode(str, Enum):
    INVALID = "invalid_range"
    MULTIPLE = "multiple_ranges_not_supported"


class RangeRequestError(ValueError):
    """A safe typed range error that never carries a filesystem value."""

    def __init__(self, code: RangeErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int
    total: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.total}"


def parse_range_header(value: str, size: int) -> ByteRange:
    """Parse ``bytes=start-end``, open-ended, or suffix syntax."""
    if size <= 0 or not isinstance(value, str) or len(value) > 128:
        raise RangeRequestError(RangeErrorCode.INVALID)
    unit, separator, raw_spec = value.partition("=")
    if separator != "=" or unit.strip().casefold() != "bytes":
        raise RangeRequestError(RangeErrorCode.INVALID)
    spec = raw_spec.strip()
    if "," in spec:
        raise RangeRequestError(RangeErrorCode.MULTIPLE)
    if not spec or spec.count("-") != 1:
        raise RangeRequestError(RangeErrorCode.INVALID)
    raw_start, raw_end = (part.strip() for part in spec.split("-", 1))
    if raw_start:
        if not raw_start.isascii() or not raw_start.isdecimal():
            raise RangeRequestError(RangeErrorCode.INVALID)
        start = int(raw_start)
        if start >= size:
            raise RangeRequestError(RangeErrorCode.INVALID)
        if raw_end:
            if not raw_end.isascii() or not raw_end.isdecimal():
                raise RangeRequestError(RangeErrorCode.INVALID)
            requested_end = int(raw_end)
            if requested_end < start:
                raise RangeRequestError(RangeErrorCode.INVALID)
            end = min(requested_end, size - 1)
        else:
            end = size - 1
        return ByteRange(start, end, size)
    if not raw_end or not raw_end.isascii() or not raw_end.isdecimal():
        raise RangeRequestError(RangeErrorCode.INVALID)
    suffix_length = int(raw_end)
    if suffix_length <= 0:
        raise RangeRequestError(RangeErrorCode.INVALID)
    length = min(suffix_length, size)
    return ByteRange(size - length, size - 1, size)


__all__ = [
    "ByteRange",
    "RangeErrorCode",
    "RangeRequestError",
    "parse_range_header",
]
