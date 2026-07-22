"""Isolated Streamlit validation surface for the seeded COCID tutorials."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import streamlit as st  # noqa: E402

from editor.cornell.persistence import extract_cornell_document  # noqa: E402
from editor.cornell.streamlit_page import apply_loaded_note_state as load_cornell  # noqa: E402
from editor.cornell.streamlit_page import render_cornell_page  # noqa: E402
from editor.cpi.persistence import extract_cpi_document  # noqa: E402
from editor.cpi.streamlit_page import apply_loaded_note_state as load_cpi  # noqa: E402
from editor.cpi.streamlit_page import render_cpi_page  # noqa: E402
from mathdatabase.mathmongo import MathMongo  # noqa: E402
from mathmongo.config import resolve_config  # noqa: E402

SEEDS = {
    "cornell": "cocid_google_drive_docs_cornell_v1",
    "cpi": "cocid_google_drive_docs_cpi_v1",
}


@st.cache_resource
def _database() -> MathMongo:
    config = resolve_config()
    return MathMongo(config.mongo_uri, config.mongo_database)


def main() -> None:
    """Open exactly one seeded note with the production Cornell/CPI editor."""
    st.set_page_config(page_title="Validación COCID", layout="wide")
    mode = str(st.query_params.get("mode", "cornell")).lower()
    if mode not in SEEDS:
        mode = "cornell"
    db = _database()
    note = db.db["latex_notes"].find_one({"seed_id": SEEDS[mode]})
    if note is None:
        st.error(f"No se encontró el seed {SEEDS[mode]} en {db.db.name}.")
        return
    identity_key = f"cocid_validation_loaded_{mode}"
    if st.session_state.get(identity_key) != str(note["_id"]):
        if mode == "cornell":
            load_cornell(
                st.session_state,
                note_id=note["_id"],
                note=note,
                document=extract_cornell_document(note),
            )
        else:
            load_cpi(
                st.session_state,
                note_id=note["_id"],
                note=note,
                document=extract_cpi_document(note),
            )
        st.session_state[identity_key] = str(note["_id"])
    st.caption(f"Validación aislada · base {db.db.name} · seed {SEEDS[mode]}")
    if mode == "cornell":
        render_cornell_page(db)
    else:
        render_cpi_page(db)


main()
