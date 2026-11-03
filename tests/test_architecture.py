"""Structural checks for the Phase 3 dependency boundaries."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
ADAPTERS = PACKAGE / "adapters"


def _python_sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_topology_manager_is_confined_to_the_topology_adapter() -> None:
    """Only the topology adapter may import TopologyManager."""
    offenders = []
    for path in _python_sources():
        if path.name == "satgonetem_topology.py":
            continue
        if "TopologyManager" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_traffic_flow_classes_are_confined_to_the_traffic_adapter() -> None:
    """Only the traffic adapter may import concrete flow classes."""
    names = ("Iperf3Flow", "PingFlow", "Hping3Flow")
    offenders = []
    for path in _python_sources():
        if path.name == "satgonetem_traffic.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in names):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_private_dependency_hooks_are_confined_to_adapters() -> None:
    """Private satgonetem calls stay behind adapter seams."""
    offenders = []
    for path in _python_sources():
        if ADAPTERS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        private_hooks = ("_sync_node_positions", "_apply_network_config", '"_data"')
        if any(hook in text for hook in private_hooks):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_route_handlers_stay_small() -> None:
    """Route modules remain translation layers, not orchestration modules."""
    for path in sorted((PACKAGE / "routes").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                assert length <= 60, f"{path.name}:{node.name} is {length} lines"
