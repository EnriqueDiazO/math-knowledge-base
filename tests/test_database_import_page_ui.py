"""Streamlit AppTest coverage for the existing-database update surface."""

# ruff: noqa: D103

from __future__ import annotations

from streamlit.testing.v1 import AppTest

_UPDATE_APP = r"""
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from editor import database_import_page as page
from editor.utils.db_update import CollectionUpdatePlan
from editor.utils.db_update import DatabaseUpdatePlan
from editor.utils.db_update import DatabaseUpdateReport
from editor.utils.db_update import UpdateStrategy


class Database:
    name = "MathV0"


class Client:
    def list_database_names(self):
        return ["admin", "MathV0"]

    def __getitem__(self, name):
        assert name == "MathV0"
        return Database()


class Mongo:
    client = Client()
    db = Database()


plan = DatabaseUpdatePlan(
    target_database="MathV0",
    strategy=UpdateStrategy.SAFE_MERGE,
    archive_sha256="archive-sha",
    archive_database="source",
    collection_plans=(
        CollectionUpdatePlan(
            name="future_collection",
            current_documents=0,
            backup_documents=2,
            identical=0,
            new=2,
            conflicts=0,
            invalid=0,
            managed=False,
            proposed_action="Insertar nuevos y omitir idénticos",
        ),
    ),
    actions=(),
    blocking_issues=(),
    warnings=("future_collection: colección no administrada; no se crearán índices",),
    blob_plans=(),
    media_plans=(),
    fingerprint="fingerprint",
    analyzed_at=datetime.now(timezone.utc),
)
report = DatabaseUpdateReport(
    target_database="MathV0",
    backup_path=Path("/tmp/mathmongo-ui-backup.zip"),
    inserted=2,
    identical=3,
    conflicts_preserved=0,
    replaced=0,
    blobs_created=0,
    blobs_identical=0,
    media_created=0,
    media_identical=0,
    unmanaged_collections=("future_collection",),
    operations=(),
)

page.analyze_database_update = lambda *_args, **_kwargs: plan
page.apply_database_update = lambda *_args, **_kwargs: report
mongo = Mongo()
selection = page._render_update_selection(st, mongo)
if selection is not None:
    target_name, strategy = selection
    page._render_update_mode(
        st,
        Path("/tmp/archive-not-read.zip"),
        {"archive_sha256": "archive-sha"},
        mongo,
        target_name=target_name,
        strategy=strategy,
    )
"""


def _with_label(elements, label: str):
    return next(element for element in elements if element.label == label)


def test_update_ui_requires_analysis_and_exact_confirmation() -> None:
    app = AppTest.from_string(_UPDATE_APP).run()

    assert not app.exception
    assert app.selectbox[0].label == "Base de destino"
    assert app.selectbox[0].value == "MathV0"
    assert "Fusión segura" in app.selectbox[1].options
    _with_label(app.button, "Analizar actualización").click().run()

    assert not app.exception
    assert len(app.dataframe) == 1
    confirmation = _with_label(app.text_input, "Escribe exactamente MathV0 para confirmar")
    assert _with_label(app.button, "Actualizar MathV0").disabled is True
    confirmation.set_value("MathV0").run()

    apply_button = _with_label(app.button, "Actualizar MathV0")
    assert apply_button.disabled is False
    apply_button.click().run()

    assert not app.exception
    assert any(
        "MathV0 fue actualizada. Se agregaron 2 documentos" in message.value
        for message in app.success
    )
