"""Check that the CCv2 boundary only dispatches explicit validated intentions."""
import importlib
import sys
from types import SimpleNamespace

import pytest
import streamlit
from pymongo.errors import AutoReconnect

from editor.source_catalog.state import PENDING_LEGACY_CONCEPT
from editor.source_catalog.state import PENDING_NAVIGATION
from mathmongo.knowledge_map.service import MapConflictError


@pytest.fixture
def bridge(monkeypatch):
    """Replace only the UI transport while retaining the real routing contract."""
    with monkeypatch.context() as context:
        context.setattr(streamlit.components.v2, 'component', lambda *a, **k: lambda **kw: None)
        sys.modules.pop('editor.knowledge_map', None)
        module = importlib.import_module('editor.knowledge_map')
    calls = []
    state = {}
    api = SimpleNamespace(graph=lambda: {'nodes': [], 'edges': []}, execute=lambda payload: {'status': 'saved', 'operation_id': payload['operation_id']}, find=lambda key: {'id': 'nota:exact', 'source': 'S'})
    monkeypatch.setattr(module, 'KnowledgeMapService', lambda connection: api)
    monkeypatch.setattr(module.st, 'session_state', state)
    monkeypatch.setattr(module, '_COMPONENT', lambda **kwargs: calls.append(kwargs))
    yield module, state, api, calls
    sys.modules.pop('editor.knowledge_map', None)


def test_mount_reads_and_scopes_without_dispatching_writes(bridge):
    """Mount reads and scopes without dispatching writes."""
    module, state, api, calls = bridge
    module.render_knowledge_map(object(), 'private connection/database')
    mount = calls[0]
    assert mount['data']['nodes'] == [] and 'private' not in str(mount)
    assert state == {}
    assert len(mount['data']['scope']) == 32


def test_callback_stores_acknowledged_result_for_next_hydration(bridge):
    """Callback stores acknowledged result for next hydration."""
    module, state, api, calls = bridge
    module.render_knowledge_map(object(), 'scope')
    mount = calls[0]
    state[mount['key']] = {'intent': {'operation_id': 'stable'}}
    mount['on_intent_change']()
    module.render_knowledge_map(object(), 'scope')
    assert calls[-1]['data']['result'] == {'status': 'saved', 'operation_id': 'stable'}
    state[mount['key']] = {'intent': 'malformed'}
    mount['on_intent_change']()
    assert state[mount['key'] + '_result']['operation_id'] == 'stable'


def test_open_uses_existing_exact_note_route_and_handles_invalid_keys(bridge):
    """Open uses existing exact note route and handles invalid keys."""
    module, state, api, calls = bridge
    module.render_knowledge_map(object(), 'scope')
    mount = calls[0]
    state[mount['key']] = {'open_note': {'key': 'nota:exact@S'}}
    mount['on_open_note_change']()
    assert state[PENDING_LEGACY_CONCEPT] == {'id': 'nota:exact', 'source': 'S'}
    assert state[PENDING_NAVIGATION] == '🖊️ Editar concepto'
    api.find = lambda key: None
    mount['on_open_note_change']()
    def invalid(key):
        raise MapConflictError('bad')
    api.find = invalid
    mount['on_open_note_change']()
    state[mount['key']] = {'open_note': {'key': 1}}
    mount['on_open_note_change']()


def test_read_failure_is_safe_and_does_not_mount_or_dispatch(bridge, monkeypatch):
    """Read failure is safe and does not mount or dispatch."""
    module, state, api, calls = bridge
    def fail():
        raise AutoReconnect('mongodb://private:user@host secret')
    api.graph = fail
    errors = []
    monkeypatch.setattr(module.st, 'error', errors.append)
    module.render_knowledge_map(object(), 'scope')
    assert len(errors) == 1 and 'mongodb://' not in errors[0] and 'secret' not in errors[0]
    assert calls == [] and state == {}
