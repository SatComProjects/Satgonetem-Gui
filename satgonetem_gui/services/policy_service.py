"""Per-node firewall and QoS policy orchestration."""

import threading
from typing import Any

from ..errors import APIError
from ..schemas import NodePolicyRequest
from .ports import NetworkOperationError, PolicyGateway
from .topology_service import TopologyService


class PolicyService:
    """Preview, apply, inspect, and clear node policies."""

    def __init__(self, topology: TopologyService, gateway: PolicyGateway) -> None:
        self.topology = topology
        self.gateway = gateway
        self._applied: dict[str, NodePolicyRequest] = {}
        self._lock = threading.RLock()

    def preview(self, policy: NodePolicyRequest) -> dict[str, Any]:
        """Build a dry-run plan without changing the node."""
        topology = self.topology.require_topology()
        try:
            return self.gateway.preview(topology, policy)
        except APIError:
            raise
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            raise APIError(500, f"Policy operation failed: {exc}") from exc

    def apply(self, policy: NodePolicyRequest) -> dict[str, Any]:
        """Apply a policy, replacing any previous managed policy."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        with self._lock:
            try:
                current = self.gateway.status(topology, policy.node)
                if current.get("applied"):
                    self.gateway.clear(
                        topology,
                        policy.node,
                        current.get("qos", []),
                    )
                result = self.gateway.apply(topology, policy)
            except ValueError as exc:
                raise APIError(404, str(exc)) from exc
            except NetworkOperationError as exc:
                raise APIError(500, str(exc)) from exc
            except Exception as exc:
                raise APIError(500, f"Policy apply failed: {exc}") from exc
            self._applied[policy.node] = policy
            return result

    def clear(self, node: str) -> None:
        """Remove a managed policy and restore the saved ruleset."""
        topology = self.topology.require_topology()
        with self._lock:
            try:
                status = self.gateway.status(topology, node)
                interfaces = status.get("qos", [])
                if not interfaces:
                    policy = self._applied.get(node)
                    if policy is not None:
                        interfaces = [item.interface for item in policy.ingress_policing]
                self.gateway.clear(topology, node, interfaces)
            except ValueError as exc:
                raise APIError(404, str(exc)) from exc
            except NetworkOperationError as exc:
                raise APIError(500, str(exc)) from exc
            except Exception as exc:
                raise APIError(500, f"Policy clear failed: {exc}") from exc
            self._applied.pop(node, None)

    def status(self, node: str) -> dict[str, Any]:
        """Return the node's current policy status."""
        topology = self.topology.require_topology()
        try:
            return self.gateway.status(topology, node)
        except APIError:
            raise
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            raise APIError(500, f"Policy operation failed: {exc}") from exc

    def applied(self) -> list[str]:
        """Return nodes with a policy applied in this process."""
        with self._lock:
            return sorted(self._applied)
