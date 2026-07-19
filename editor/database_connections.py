"""Small helpers for explicit Streamlit database connection bootstrap."""

from __future__ import annotations

from typing import Protocol

CONFIGURED_CONNECTION_LABEL = "MathMongo (Current)"


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
