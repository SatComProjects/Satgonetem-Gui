"""Unit tests for the telemetry adapter with fake nodes."""

import hashlib
from types import SimpleNamespace

from satgonetem_gui.adapters.satgonetem_telemetry import SatGoNetemTelemetryAdapter


class FakeNode:
    def __init__(self, name="Gnd0", routing_output="", fail=False) -> None:
        self.name = name
        self.container = object()
        self.fail = fail
        self.calls = []
        self.routing_output = routing_output
        self.interfaces = [
            SimpleNamespace(name="Gnd0.5", get_iname=lambda: "eth5"),
        ]

    def get_routing_table(self):
        return ["default via 10.0.0.1", "10.0.0.0/24 dev eth5"]

    def execute_command(self, argv):
        self.calls.append(argv)
        if self.fail:
            raise RuntimeError("container unavailable")
        if argv[0] == "birdc":
            return self.routing_output
        if "cat /proc/net/snmp" in " ".join(argv):
            return (
                "Tcp: RtoAlgorithm InSegs OutSegs RetransSegs InErrs OutRsts\n"
                "Tcp: 1 500 400 7 0 9\n"
                "Udp: InDatagrams NoPorts InErrors OutDatagrams\n"
                "Udp: 300 0 0 200\n"
                "Icmp: InMsgs InErrors InDestUnreachs\n"
                "Icmp: 11 0 0\n"
            )
        return "eth5 1000 2000 10 20 1 2 3 4"


def _link(source, target, interface):
    link = SimpleNamespace(
        source=source,
        target=target,
        type="GroundStationLink",
        direction="bidirectional",
        delay=5,
        is_active=True,
        peer_interfaces=[interface],
        link_budget_config=None,
        get_capacity=lambda: 5000,
    )
    return link


def test_sample_reads_interface_routes_and_links() -> None:
    """Interface counters and route hashes are returned for each node."""
    node = FakeNode()
    target = FakeNode("Gnd1")
    target.interfaces = [
        SimpleNamespace(name="Gnd1.5", get_iname=lambda: "eth6"),
    ]
    topology = SimpleNamespace(
        satellites={},
        ground_stations={0: node, 1: target},
        links={},
        routing="static",
    )
    topology.links = {frozenset(("Gnd0", "Gnd1")): _link(node, target, node.interfaces[0])}
    adapter = SatGoNetemTelemetryAdapter()

    result = adapter.sample(topology)

    assert result["nodes"][0]["name"] == "Gnd0"
    assert result["nodes"][0]["route_count"] == 2
    assert result["nodes"][0]["interfaces"][0]["rx_bytes"] == 1000
    assert result["nodes"][0]["interfaces"][0]["tx_errors"] == 4
    assert result["nodes"][0]["tcp_in_segs"] == 500
    assert result["nodes"][0]["tcp_out_rsts"] == 9
    assert result["nodes"][0]["udp_in_datagrams"] == 300
    assert result["nodes"][0]["icmp_in_msgs"] == 11
    assert result["links"][0]["capacity_kbps"] == 5000
    assert result["links"][0]["rx_bytes"] == 1000
    assert result["links"][0]["rx_errors"] == 3
    expected_hash = hashlib.sha1(
        "\n".join(["default via 10.0.0.1", "10.0.0.0/24 dev eth5"]).encode()
    ).hexdigest()
    assert result["nodes"][0]["route_hash"] == expected_hash


def test_sample_reads_dynamic_protocol_state() -> None:
    """OSPF/IS-IS state is included for dynamic routing methods."""
    node = FakeNode(routing_output="ospf1 BIRD 1.6.8 up 00:10:00\nkernel1 up")
    topology = SimpleNamespace(
        satellites={0: node},
        ground_stations={},
        links={},
        routing="dynamic-ospf",
    )
    result = SatGoNetemTelemetryAdapter().sample(topology)

    assert result["nodes"][0]["protocols"] == ["ospf1 BIRD 1.6.8 up 00:10:00"]


def test_sample_marks_node_errors_without_failing_the_snapshot() -> None:
    """A failed node command becomes a per-node error, not a crash."""
    node = FakeNode(fail=True)
    topology = SimpleNamespace(
        satellites={},
        ground_stations={0: node},
        links={},
        routing="static",
    )

    result = SatGoNetemTelemetryAdapter().sample(topology)

    assert result["nodes"][0]["error"] == "container unavailable"
    assert result["nodes"][0]["interfaces"] == []
