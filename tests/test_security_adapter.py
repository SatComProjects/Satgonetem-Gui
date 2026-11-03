"""Contract tests for the security adapter with fake nodes."""

from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters.satgonetem_security import SatGoNetemSecurityAdapter
from satgonetem_gui.services.ports import NetworkOperationError


def _node(name="Sat0"):
    iface = SimpleNamespace(name="eth0", get_iname=lambda: "eth0")
    calls = []

    def execute(command, detach=False):
        calls.append((command, detach))
        return "128 0" if "echo" in str(command) else ""

    node = SimpleNamespace(
        name=name,
        container=object(),
        interfaces=[iface],
        execute_command=execute,
        calls=calls,
    )
    return node


def _topology(node):
    failed = []

    def get_node_by_name(name):
        return node if name == node.name else None

    def simulate_link_failure(link):
        failed.append(link)

    topology = SimpleNamespace(
        get_node_by_name=get_node_by_name,
        simulate_link_failure=simulate_link_failure,
        links={},
        failed=failed,
    )
    return topology


def test_fail_link_finds_the_stable_key() -> None:
    """The adapter maps a URL key back to the concrete link."""
    adapter = SatGoNetemSecurityAdapter()
    node = _node()
    target = SimpleNamespace(name="Sat1")
    link = SimpleNamespace(
        source=node,
        target=target,
        type="InterSatelliteLink",
        direction="bidirectional",
    )
    topology = _topology(node)
    topology.links = {frozenset(("Sat0", "Sat1")): link}

    result = adapter.fail_link(
        topology, "Sat0|Sat1|InterSatelliteLink|bidirectional"
    )

    assert result["src"] == "Sat0"
    assert topology.failed == [link]


def test_fail_link_reports_unknown_key() -> None:
    """Unknown link keys are a 404 candidate, not a shell error."""
    adapter = SatGoNetemSecurityAdapter()

    with pytest.raises(KeyError):
        adapter.fail_link(_topology(_node()), "missing")


def test_capture_start_uses_a_bounded_command() -> None:
    """Capture commands validate the node/interface and use a packet cap."""
    adapter = SatGoNetemSecurityAdapter()
    node = _node()
    topology = _topology(node)

    result = adapter.start_capture(topology, "Sat0", "eth0", 25, 5)

    assert result["interface"] == "eth0"
    assert result["path"].startswith("/tmp/satsec_")
    command, detached = node.calls[-1]
    assert detached is True
    assert "-c 25" in command[-1]
    assert "timeout 5" in command[-1]


def test_capture_rejects_unknown_node_and_interface() -> None:
    """Only topology nodes and real interfaces are accepted."""
    adapter = SatGoNetemSecurityAdapter()
    topology = _topology(_node())

    with pytest.raises(ValueError):
        adapter.start_capture(topology, "Missing", "eth0", 10, 5)
    with pytest.raises(ValueError):
        adapter.start_capture(topology, "Sat0", "missing", 10, 5)


def test_capture_status_and_read() -> None:
    """Status and read operations stay on the selected node."""
    adapter = SatGoNetemSecurityAdapter()
    node = _node()
    topology = _topology(node)

    status = adapter.capture_status(topology, "Sat0", "/tmp/satsec_test.pcap")
    assert status == {"size_bytes": 128, "running": False}

    payload = adapter.read_capture(topology, "Sat0", "/tmp/satsec_test.pcap")
    assert payload == b""


def test_capture_stop_and_status_avoid_pkill_self_match() -> None:
    """The process pattern must not match the shell running pkill/pgrep."""
    adapter = SatGoNetemSecurityAdapter()
    node = _node()
    topology = _topology(node)

    adapter.stop_capture(topology, "Sat0", "/tmp/satsec_test.pcap")
    adapter.capture_status(topology, "Sat0", "/tmp/satsec_test.pcap")

    commands = [str(call[0]) for call in node.calls]
    assert any("[t]cpdump" in command for command in commands)


def test_capture_start_maps_dependency_failure() -> None:
    """Container command failures become NetworkOperationError."""
    adapter = SatGoNetemSecurityAdapter()
    node = _node()

    def fail(*_args, **_kwargs):
        raise RuntimeError("container unavailable")

    node.execute_command = fail
    topology = _topology(node)

    with pytest.raises(NetworkOperationError):
        adapter.start_capture(topology, "Sat0", "eth0", 10, 5)
