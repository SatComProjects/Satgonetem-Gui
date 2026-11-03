"""Unit tests for the firewall/QoS policy adapter."""

from types import SimpleNamespace

from satgonetem_gui.adapters.satgonetem_policy import SatGoNetemPolicyAdapter
from satgonetem_gui.schemas import NodePolicyRequest


class FakeNode:
    """Record commands and emulate the few status queries used by the adapter."""

    def __init__(self) -> None:
        self.name = "Gnd24"
        self.container = object()
        self.interfaces = [
            SimpleNamespace(name="eth5", get_iname=lambda: "eth5"),
        ]
        self.calls: list[list[str]] = []
        self.backup_exists = False

    def execute_command(self, argv: list[str]) -> str:
        self.calls.append(argv)
        joined = " ".join(argv)
        if "test -f" in joined:
            return "yes" if self.backup_exists else "no"
        if "iptables-save" in joined:
            self.backup_exists = True
            return ""
        if "rm -f" in joined:
            self.backup_exists = False
            return ""
        if "-S" in argv:
            return ""
        if "-L" in argv:
            return "1 100 ACCEPT tcp -- 0.0.0.0/0 0.0.0.0/0 tcp dpt:5201"
        if "tc qdisc show" in joined:
            return "qdisc ingress ffff: parent ffff:fff1"
        return ""

    def has_command(self, *fragments: str) -> bool:
        return any(all(part in " ".join(call) for part in fragments) for call in self.calls)


def _topology(node):
    return SimpleNamespace(get_node_by_name=lambda name: node if name == node.name else None)


def _policy() -> NodePolicyRequest:
    return NodePolicyRequest(
        node="Gnd24",
        preset="ddos-mitigation",
        default_inbound="accept",
        allow_established=True,
        management_sources=["10.0.0.0/8"],
        management_ports=[22],
        bcp38_ingress=True,
        rate_limits=[
            {
                "protocol": "udp",
                "port": 5201,
                "source_cidr": "192.0.2.0/24",
                "packets_per_second": 100,
                "burst": 200,
            }
        ],
        connection_limits=[
            {
                "port": 5201,
                "source_cidr": "192.0.2.0/24",
                "max_connections": 10,
            }
        ],
        dscp_marks=[{"protocol": "udp", "port": 5201, "dscp": 46}],
        ingress_policing=[
            {
                "interface": "eth5",
                "protocol": "udp",
                "port": 5201,
                "rate_kbps": 1000,
                "burst_kb": 32,
            }
        ],
    )


def test_preview_builds_firewall_qos_plan_without_executing() -> None:
    """Preview shows the intended chains, limits, marking, and policing."""
    node = FakeNode()
    adapter = SatGoNetemPolicyAdapter()

    result = adapter.preview(_topology(node), _policy())

    assert result["commands"]
    assert any("SGNT_IN" in command for command in result["commands"])
    assert any("hashlimit" in command for command in result["commands"])
    assert any("connlimit" in command for command in result["commands"])
    assert any("rpfilter" in command for command in result["commands"])
    assert any("DSCP" in command for command in result["commands"])
    assert any("police rate 1000kbit" in command for command in result["commands"])
    assert not any("-N" in call or "-A" in call or "iptables-save" in call for call in node.calls)
    assert result["warnings"]


def test_apply_executes_and_reports_status() -> None:
    """Apply creates the chain, saves a backup, and reads counters."""
    node = FakeNode()
    adapter = SatGoNetemPolicyAdapter()

    result = adapter.apply(_topology(node), _policy())

    assert result["applied"] is True
    assert result["family"] == "ipv4"
    assert result["rules"][0]["chain"] == "SGNT_IN"
    assert result["qos"] == ["eth5"]
    assert node.has_command("SGNT_IN")
    assert node.has_command("hashlimit")
    assert node.has_command("iptables-save")


def test_clear_restores_backup_and_removes_qos() -> None:
    """Clear restores the saved ruleset and removes managed ingress qdiscs."""
    node = FakeNode()
    adapter = SatGoNetemPolicyAdapter()

    adapter.apply(_topology(node), _policy())
    adapter.clear(_topology(node), "Gnd24", ["eth5"])

    assert node.has_command("iptables-restore")
    assert node.has_command("tc", "qdisc", "del", "dev", "eth5")
    assert node.has_command("rm", "-f")


def test_status_without_policy_reports_not_applied() -> None:
    """A node with no managed chain is safe to query."""
    node = FakeNode()

    def execute(argv):
        if "-S" in argv:
            raise RuntimeError("no chain")
        return ""

    node.execute_command = execute
    result = SatGoNetemPolicyAdapter().status(_topology(node), "Gnd24")

    assert result["applied"] is False
    assert result["rules"] == []


def test_preview_works_before_containers_start() -> None:
    """A stopped node can still produce a plan for the editor."""
    node = FakeNode()
    node.container = None
    adapter = SatGoNetemPolicyAdapter()

    result = adapter.preview(
        _topology(node),
        NodePolicyRequest(node="Gnd24", default_inbound="drop"),
    )

    assert result["commands"]
    assert node.calls == []


def test_apply_failure_restores_the_saved_ruleset() -> None:
    """A failed command triggers the rollback path."""
    import pytest

    from satgonetem_gui.services.ports import NetworkOperationError

    node = FakeNode()
    original = node.execute_command

    def flaky(argv):
        if "-N" in argv:
            raise RuntimeError("iptables unavailable")
        return original(argv)

    node.execute_command = flaky

    with pytest.raises(NetworkOperationError):
        SatGoNetemPolicyAdapter().apply(_topology(node), _policy())

    assert node.has_command("iptables-restore")


def test_clear_without_backup_cleans_managed_chains() -> None:
    """A missing backup still removes the managed chains."""
    node = FakeNode()
    adapter = SatGoNetemPolicyAdapter()

    adapter.clear(_topology(node), "Gnd24", [])

    assert node.has_command("-D", "INPUT", "SGNT_IN")
    assert node.has_command("-X", "SGNT_IN")
    assert not node.has_command("iptables-restore")


def test_status_reads_ipv6_when_ipv4_chain_is_absent() -> None:
    """IPv6-only policies report their family and counters."""
    node = FakeNode()
    original = node.execute_command

    def ipv6_only(argv):
        if argv[0] == "iptables" and "-S" in argv:
            raise RuntimeError("no ipv4 chain")
        if argv[0] == "ip6tables" and "-S" in argv:
            return ""
        if argv[0] == "ip6tables" and "-L" in argv:
            return "2 200 DROP tcp -- ::/0 ::/0 tcp dpt:22"
        return original(argv)

    node.execute_command = ipv6_only
    result = SatGoNetemPolicyAdapter().status(_topology(node), "Gnd24")

    assert result["applied"] is True
    assert result["family"] == "ipv6"
    assert result["rules"][0]["packets"] == 2


def test_plan_covers_outbound_and_egress_validation() -> None:
    """Custom outbound rules and egress source validation are emitted."""
    node = FakeNode()
    policy = NodePolicyRequest(
        node="Gnd24",
        default_inbound="drop",
        rules=[
            {
                "name": "block outbound udp",
                "action": "drop",
                "direction": "out",
                "protocol": "udp",
                "port": 53,
                "log": True,
            }
        ],
        bcp38_egress_cidrs=["192.0.2.0/24"],
    )

    result = SatGoNetemPolicyAdapter().preview(_topology(node), policy)
    commands = result["commands"]

    assert any("SGNT_OUT" in command for command in commands)
    assert any("SGNT_RAWOUT" in command for command in commands)
    outbound = [command for command in commands if "SGNT_OUT" in command]
    assert outbound[-1].endswith("-j RETURN")
    assert any("LOG" in command for command in commands)


def test_ipv6_plan_warns_about_qos_limits() -> None:
    """IPv6 policy previews warn about unsupported ingress policing/rpfilter."""
    node = FakeNode()
    policy = NodePolicyRequest(
        node="Gnd24",
        family="ipv6",
        allow_icmp=True,
        bcp38_ingress=True,
        ingress_policing=[
            {
                "interface": "eth5",
                "protocol": "udp",
                "port": 5201,
                "rate_kbps": 1000,
                "burst_kb": 32,
            }
        ],
    )

    result = SatGoNetemPolicyAdapter().preview(_topology(node), policy)

    assert any("IPv6 ingress policing" in warning for warning in result["warnings"])
    assert any("BCP38 rpfilter" in warning for warning in result["warnings"])
