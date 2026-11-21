"""UTC clock for existing MongoDB/JSON contracts that store naive UTC values."""

from datetime import datetime
from datetime import timezone


def naive_utc_now() -> datetime:
    """Read an aware UTC clock, retaining the established naive storage contract.

    This adapter is for legacy fields only. New domain models that require an
    offset continue using their existing aware UTC clocks. It never interprets
    local wall-clock time as UTC or migrates historical timestamps.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
