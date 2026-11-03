"""Unit tests for policy orchestration with fake gateways."""

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import NodePolicyRequest
from satgonetem_gui.services.policy_service import PolicyService


class FakeTopology:
    def __init__(self, running: bool = True) -> None:
        self.running = running

    def require_topology(self):
        return object()

    def gonetem_is_on(self):
        return self.running


class FakeGateway:
    def __init__(self) -> None:
        self.applied = False
        self.calls = []

    def preview(self, topology, policy):
        self.calls.append(("preview", policy.node))
        return {
            "node": policy.node,
            "family": policy.family,
            "commands": ["iptables -N SGNT_IN"],
            "diff": ["+ iptables -N SGNT_IN"],
            "warnings": [],
        }

    def apply(self, topology, policy):
        self.calls.append(("apply", policy.node))
        self.applied = True
        return {
            "node": policy.node,
            "applied": True,
            "family": policy.family,
            "chain": "SGNT_IN",
            "rules": [],
            "qos": ["eth0"],
        }

    def clear(self, topology, node, interfaces=None):
        self.calls.append(("clear", node, tuple(interfaces or [])))
        self.applied = False

    def status(self, topology, node):
        self.calls.append(("status", node))
        if node == "Missing":
            raise ValueError("Node not found: Missing")
        return {
            "node": node,
            "applied": self.applied,
            "family": "ipv4",
            "chain": "SGNT_IN" if self.applied else None,
            "rules": [],
            "qos": ["eth0"] if self.applied else [],
        }


def _policy(node="Gnd24") -> NodePolicyRequest:
    return NodePolicyRequest(node=node, default_inbound="drop")


def test_preview_does_not_require_running_containers() -> None:
    """Policy editing can be previewed before the range is started."""
    service = PolicyService(FakeTopology(running=False), FakeGateway())

    result = service.preview(_policy())

    assert result["commands"] == ["iptables -N SGNT_IN"]


def test_apply_requires_running_containers() -> None:
    """Applying a policy requires a live node."""
    service = PolicyService(FakeTopology(running=False), FakeGateway())

    with pytest.raises(APIError) as error:
        service.apply(_policy())

    assert error.value.status_code == 409


def test_apply_replaces_an_existing_policy() -> None:
    """Applying again clears the old managed policy first."""
    gateway = FakeGateway()
    gateway.applied = True
    service = PolicyService(FakeTopology(), gateway)

    result = service.apply(_policy())

    assert result["applied"] is True
    assert gateway.calls[:2] == [("status", "Gnd24"), ("clear", "Gnd24", ("eth0",))]
    assert service.applied() == ["Gnd24"]


def test_clear_uses_qos_interfaces_from_status() -> None:
    """Clear removes ingress qdiscs reported by the node."""
    gateway = FakeGateway()
    gateway.applied = True
    service = PolicyService(FakeTopology(), gateway)

    service.clear("Gnd24")

    assert ("clear", "Gnd24", ("eth0",)) in gateway.calls


def test_status_maps_unknown_node_to_404() -> None:
    """Unknown nodes use the common not-found envelope."""
    service = PolicyService(FakeTopology(), FakeGateway())

    with pytest.raises(APIError) as error:
        service.status("Missing")

    assert error.value.status_code == 404


class FailingGateway(FakeGateway):
    """Raise a selected dependency failure."""

    def __init__(self, error):
        super().__init__()
        self.error = error

    def preview(self, topology, policy):
        raise self.error

    def apply(self, topology, policy):
        raise self.error

    def status(self, topology, node):
        raise self.error


def test_preview_maps_dependency_error_to_500() -> None:
    """Adapter failures use the shared 500 envelope."""
    service = PolicyService(FakeTopology(), FailingGateway(RuntimeError("bad rule")))

    with pytest.raises(APIError) as error:
        service.preview(_policy())

    assert error.value.status_code == 500


def test_apply_maps_dependency_error_to_500() -> None:
    """An apply failure is reported without storing the policy."""
    service = PolicyService(FakeTopology(), FailingGateway(RuntimeError("bad rule")))

    with pytest.raises(APIError) as error:
        service.apply(_policy())

    assert error.value.status_code == 500
    assert service.applied() == []


def test_status_maps_dependency_error_to_500() -> None:
    """A status read failure is a server-side error."""
    service = PolicyService(FakeTopology(), FailingGateway(RuntimeError("no node")))

    with pytest.raises(APIError) as error:
        service.status("Gnd24")

    assert error.value.status_code == 500


def test_clear_maps_dependency_error_to_500() -> None:
    """A rollback failure is not silently swallowed."""
    service = PolicyService(FakeTopology(), FailingGateway(RuntimeError("no node")))

    with pytest.raises(APIError) as error:
        service.clear("Gnd24")

    assert error.value.status_code == 500
