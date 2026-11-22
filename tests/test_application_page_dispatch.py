"""Compatibility routing keeps the selected connection explicit and pages lazy."""

from importlib import import_module
from types import SimpleNamespace

import pytest
import streamlit as st

from editor import application_navigation
from editor.application_context import PageContext


@pytest.mark.parametrize('label', ['💡 Nuevo concepto', '🖊️ Editar concepto', '📖 Reading Space', '🟥 CPI'])
def test_dispatch_loads_only_the_selected_page_with_the_same_database(monkeypatch, label):
    """Selecting a page cannot initialize other views or replace its DB scope."""
    loaded, rendered = [], []
    connection = object()
    context = PageContext(db=connection, current_db='owned', current_database_label='Temporal',
                          active_database_scope='endpoint-a/database-a')

    def load(module):
        loaded.append(module)
        return SimpleNamespace(render=rendered.append)

    monkeypatch.setattr(application_navigation, 'import_module', load)
    application_navigation.render_page(label, context)
    assert loaded == ['editor.app_pages.' + application_navigation.PAGES[label]]
    assert len(rendered) == 1
    assert rendered[0].db is connection
    assert rendered[0].active_database_scope == context.active_database_scope
    assert rendered[0].page == ('CPI' if label == '🟥 CPI' else label)
    assert context.page == ''  # dispatch creates a page-specific context


def test_importing_registered_pages_does_not_render_or_read_page_widgets(monkeypatch):
    """Imports remain reusable by the independent frontend's compatibility tools."""
    def unexpected(*_args, **_kwargs):
        pytest.fail('A page rendered while being imported')

    for command in ('title', 'header', 'write', 'button', 'selectbox', 'text_input', 'form'):
        monkeypatch.setattr(st, command, unexpected)
    for slug in application_navigation.PAGES.values():
        module = import_module('editor.app_pages.' + slug)
        assert callable(module.render)
