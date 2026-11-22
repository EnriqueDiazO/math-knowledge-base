"""Connection manager; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from mathdatabase.mathmongo import MathMongo
from mathdatabase.mathmongo import MongoIndexInitializationError
from mathmongo.config import mongo_connection_guidance
from mathmongo.config import sanitize_mongo_error


class DatabaseManager:
    """Keep the explicit set of database connections used by the interface."""

    def __init__(self):
        """Initialize the empty connection registry."""
        self.connections = {}
        self.current_connection = None

    def add_connection(self, name, mongo_uri, db_name):
        """Add a new database connection."""
        try:
            connection = MathMongo(mongo_uri, db_name)
            self.connections[name] = {
                'connection': connection,
                'uri': mongo_uri,
                'db_name': db_name,
                'status': 'connected'
            }
            return True
        except MongoIndexInitializationError as e:
            safe_error = sanitize_mongo_error(e, mongo_uri)
            st.error(
                "MongoDB conectado para "
                f"{name}, pero falló la inicialización de índices:\n\n{safe_error}"
            )
            return False
        except Exception as e:
            public_error, technical_detail = mongo_connection_guidance(e, mongo_uri, db_name)
            st.error(public_error)
            with st.expander("Detalle técnico de conexión", expanded=False):
                st.code(technical_detail, language=None)
            return False

    def get_connection(self, name):
        """Get a specific database connection."""
        return self.connections.get(name, {}).get('connection')

    def list_connections(self):
        """List all available connections."""
        return list(self.connections.keys())

    def get_current_connection(self):
        """Get the currently active connection."""
        return self.current_connection

    def set_current_connection(self, name):
        """Set the current active connection."""
        if name in self.connections:
            self.current_connection = self.connections[name]['connection']
            return True
        return False
