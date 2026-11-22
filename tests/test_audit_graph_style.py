"""Verify the graph style helper's public behavior with real PyVis options."""

import json

import pytest
from pyvis.network import Network

from editor.interactive_graph import InteractiveGraphManager


@pytest.mark.parametrize("profile", ["full", "compact"])
def test_style_profiles_keep_the_existing_interaction_contract(profile):
    """Both supported legacy profiles must yield the same disabled-physics style."""
    manager = InteractiveGraphManager.__new__(InteractiveGraphManager)
    network = Network()
    manager._apply_style(network, profile=profile)
    options = json.loads(network.options.to_json()) if hasattr(network.options, "to_json") else network.options
    assert options["configure"]["enabled"] is False
    assert options["physics"] == {"enabled": False, "stabilization": {"enabled": False}}
    assert options["interaction"] == {"hover": True, "navigationButtons": False, "keyboard": True}
    assert options["edges"]["smooth"] == {"enabled": True, "type": "dynamic"}
