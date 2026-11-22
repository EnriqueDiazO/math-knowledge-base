"""Keep imported graph data from escaping its inline script element."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from editor import interactive_graph
from visualizations.grafoconocimiento import GrafoConocimiento


class ScriptInventory(HTMLParser):
    """Use HTML parsing semantics, including case-insensitive script end tags."""

    def __init__(self):
        """Record script attributes without executing any content."""
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        """Collect only actual script elements produced by the HTML parser."""
        if tag == "script":
            self.scripts.append(dict(attrs))


def test_graph_state_cannot_close_the_bootstrap_script_with_mixed_case():
    """Preserve arbitrary mathematical text while containing script-like data."""
    state = {"title": '</ScRiPt><script id="graph-injected">alert(1)</script>',
             "math": r"\frac{α}{β} < 1 & x > 0"}
    html = GrafoConocimiento([], [])._restore_state_bootstrap(state)
    parser = ScriptInventory()
    parser.feed(html)
    assert parser.scripts == [{"id": "exported-graph-state-script"}]
    literal = re.search(r"const stateJson = (.*);", html).group(1)
    assert json.loads(json.loads(literal)) == state


def test_graph_layout_keys_cannot_inject_a_second_script_element():
    """Node identities are untrusted JSON data, including in layout presets."""
    identity = '</ScRiPt><script id="graph-injected">alert(1)</script>'
    graph = GrafoConocimiento([{"id": identity, "source": "Book", "titulo": "Safe", "tipo": ["teorema"]}], [])
    graph.construir_grafo()
    html = graph.exportar_html()
    parser = ScriptInventory()
    parser.feed(html)
    assert not any(script.get("id") == "graph-injected" for script in parser.scripts)


def test_small_graph_preview_escapes_imported_labels(tmp_path, monkeypatch):
    """Small graphs must treat titles and relation labels as text."""
    monkeypatch.setattr(interactive_graph, "get_graph_runtime_dir", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    manager = interactive_graph.InteractiveGraphManager(None)
    payload = '<script id="graph-injected">alert(1)</script>'
    output = manager.build_interactive_graph(
        [{"id": "one", "source": payload, "titulo": payload, "tipo": "teorema"}],
        [{"tipo": payload}],
    )
    parser = ScriptInventory()
    parser.feed(Path(output).read_text())
    assert not any(script.get("id") == "graph-injected" for script in parser.scripts)


@pytest.mark.parametrize("write_fails", [False, True])
def test_graph_handles_schema_lists_optional_titles_and_safe_fallback(tmp_path, monkeypatch, write_fails):
    """Exercise real PyVis generation and failure fallback with canonical metadata."""
    monkeypatch.setattr(interactive_graph, "get_graph_runtime_dir", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    manager = interactive_graph.InteractiveGraphManager(None)
    real_network = interactive_graph.Network
    networks = []

    def factory(**kwargs):
        network = real_network(**kwargs)
        networks.append(network)
        if write_fails:
            def fail_write(*_args, **_kwargs):
                raise OSError("injected PyVis output failure")
            network.write_html = fail_write
        return network

    monkeypatch.setattr(interactive_graph, "Network", factory)
    payload = '<script id="graph-injected">alert(1)</script>'
    output = manager.build_interactive_graph([
        {"id": "one", "source": "Book", "titulo": None, "tipo": ["teorema"]},
        {"id": "two", "source": payload, "titulo": payload, "tipo": ["definicion"]},
    ], [])
    html = Path(output).read_text()
    parser = ScriptInventory()
    parser.feed(html)
    assert not any(script.get("id") == "graph-injected" for script in parser.scripts)
    assert len(networks[0].nodes) == 2
    for node in networks[0].nodes:
        tooltip_parser = ScriptInventory()
        tooltip_parser.feed(node["title"])
        assert tooltip_parser.scripts == []
    if not write_fails:
        assert "new vis.Network" in html
