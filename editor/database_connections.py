"""Small helpers for explicit Streamlit database connection bootstrap."""

from __future__ import annotations

from typing import Any
from typing import Protocol

CONFIGURED_CONNECTION_LABEL = "MathMongo (Current)"


def active_database_display_label(connection_label: object, connection: Any) -> str:
    """Show the real database first and a safe connection alias second."""
    database = getattr(connection, "db", None)
    database_name = getattr(database, "name", None)
    if not isinstance(database_name, str) or not database_name.strip():
        raise ValueError("The active connection has no usable MongoDB database name.")
    database_name = database_name.strip()

    alias = " ".join(str(connection_label or "").split())
    if (
        not alias
        or alias.casefold() == database_name.casefold()
        or "://" in alias
        or "@" in alias
    ):
        return database_name
    return f"{database_name} — {alias}"


class ConnectionSettings(Protocol):
    """Configuration fields required to open the selected database."""

    mongo_uri: str
    mongo_database: str


class ConnectionManager(Protocol):
    """Minimal manager interface used during application bootstrap."""

    def add_connection(self, label: str, uri: str, database: str) -> bool:
        """Register one explicit database connection."""

    def set_current_connection(self, label: str) -> bool:
        """Select a previously registered connection."""


def initialize_configured_connection(
    manager: ConnectionManager,
    settings: ConnectionSettings,
) -> bool:
    """Open and select only the database resolved from configuration."""
    if not manager.add_connection(
        CONFIGURED_CONNECTION_LABEL,
        settings.mongo_uri,
        settings.mongo_database,
    ):
        return False
    return bool(manager.set_current_connection(CONFIGURED_CONNECTION_LABEL))
