"""Honeypot lifecycle orchestration."""

from typing import Any

from ..errors import APIError
from ..schemas import HoneypotRequest
from .ports import HoneypotGateway, NetworkOperationError
from .topology_service import TopologyService


class HoneypotService:
    """Start, inspect, and stop decoy listeners on nodes."""

    def __init__(self, topology: TopologyService, gateway: HoneypotGateway) -> None:
        self.topology = topology
        self.gateway = gateway

    def start(self, request: HoneypotRequest) -> dict[str, Any]:
        """Start a decoy listener."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        try:
            return self.gateway.start(topology, request.node, request.port)
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            raise APIError(500, f"Could not start honeypot: {exc}") from exc

    def status(self, node: str, port: int) -> dict[str, Any]:
        """Return listener state and recent connections."""
        topology = self.topology.require_topology()
        try:
            return self.gateway.status(topology, node, port)
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            raise APIError(500, str(exc)) from exc

    def stop(self, node: str, port: int) -> None:
        """Stop a decoy listener."""
        topology = self.topology.require_topology()
        try:
            self.gateway.stop(topology, node, port)
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            raise APIError(500, str(exc)) from exc
