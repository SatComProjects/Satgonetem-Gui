"""Unit tests for the decoy listener adapter."""

import json
from types import SimpleNamespace

from satgonetem_gui.adapters.satgonetem_honeypot import SatGoNetemHoneypotAdapter


class FakeNode:
    def __init__(self) -> None:
        self.name = "Gnd24"
        self.container = object()
        self.running = False
        self.calls = []
        self.events = [
            {"timestamp": 100.0, "peer": "192.0.2.9", "source_port": 5555},
        ]

    def execute_command(self, argv):
        self.calls.append(argv)
        joined = " ".join(argv)
        if "printf" in joined:
            self.running = True
            return "started"
        if "pgrep" in joined:
            return "running" if self.running else "stopped"
        if "tail" in joined:
            return "\n".join(json.dumps(event) for event in self.events)
        if "pkill" in joined:
            self.running = False
            return ""
        return ""


def _topology(node):
    return SimpleNamespace(get_node_by_name=lambda name: node if name == node.name else None)


def test_start_status_and_stop() -> None:
    """The adapter writes the script and reads connection events."""
    node = FakeNode()
    adapter = SatGoNetemHoneypotAdapter()

    started = adapter.start(_topology(node), "Gnd24", 2222)
    assert started["running"] is True
    assert started["events"][0]["peer"] == "192.0.2.9"
    assert any("printf" in " ".join(call) for call in node.calls)

    stopped = adapter.stop(_topology(node), "Gnd24", 2222)
    assert stopped is None
    assert node.running is False


def test_unknown_node_is_rejected() -> None:
    """Unknown nodes fail before any command runs."""
    import pytest

    with pytest.raises(ValueError):
        SatGoNetemHoneypotAdapter().status(_topology(FakeNode()), "Missing", 2222)
