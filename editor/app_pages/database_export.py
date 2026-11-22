"""Database export; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.utils.db_export import export_database_to_zip
from mathkb_config import EXPORT_COLLECTIONS
from mathkb_config import EXPORT_TIMEOUT_SECONDS
from mathmongo.paths import get_backups_dir
from mathmongo.paths import validate_mutable_path


def render(context):
    """Render only the selected page using its explicit application context."""
    db = context.db
    st.header("📦 Database Export")
    st.markdown(
        """
        Export the full Math Knowledge Base database as a ZIP archive.
        This operation is **read-only** and does not modify the database.
        """
    )
    st.caption(
        f"Timeout: {EXPORT_TIMEOUT_SECONDS}s · Expected collections: "
        + ", ".join(EXPORT_COLLECTIONS)
    )
    if st.button("📦 Export database"):
        with st.spinner("Exporting database..."):
            try:
                out_dir = validate_mutable_path(get_backups_dir())
                out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                zip_path = export_database_to_zip(db, out_dir)
                st.success(f"Export completed successfully: {zip_path}")
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Download ZIP",
                        data=f,
                        file_name=zip_path.name,
                        mime="application/zip",
                    )
            except Exception as e:
                st.error(f"Export failed: {e}")
