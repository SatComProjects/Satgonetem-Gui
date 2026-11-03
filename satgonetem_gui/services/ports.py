"""Narrow interfaces implemented by the satgonetem adapters."""

from dataclasses import dataclass
from typing import Any, Protocol

from ..schemas import (
    Hping3Request,
    Iperf3Request,
    NodePolicyRequest,
    PingRequest,
    ProjectCreateRequest,
)
from ..state import ProjectResult


class ProjectGateway(Protocol):
    """Project build, load, save, and configuration operations."""

    def build(self, payload: ProjectCreateRequest) -> ProjectResult: ...

    def load(self, content: str) -> ProjectResult: ...

    def save(self, topology: Any) -> str: ...

    def config(self, topology: Any, save_path: str) -> dict[str, Any]: ...


class TopologyReader(Protocol):
    """Read-only topology queries used by the dashboard and explorers."""

    def status(self, topology: Any) -> dict[str, Any]: ...

    def satellites(self, topology: Any) -> list[dict[str, Any]]: ...

    def ground_stations(self, topology: Any) -> list[dict[str, Any]]: ...

    def links(self, topology: Any) -> list[dict[str, Any]]: ...

    def nodes(self, topology: Any) -> list[dict[str, Any]]: ...

    def node_detail(self, topology: Any, name: str) -> dict[str, Any] | None: ...

    def find_node(self, topology: Any, name: str) -> Any | None: ...

    def traffic_nodes(self, topology: Any) -> list[dict[str, str]]: ...

    def gonetem_is_on(self, topology: Any) -> bool: ...


class NetworkOperationError(RuntimeError):
    """Raised when a GoNetEm operation reports failure via a return code."""


class NetworkController(Protocol):
    """Routing and container lifecycle operations."""

    def routing_status(self, topology: Any) -> dict[str, Any]: ...

    def apply_addressing(self, topology: Any) -> None: ...

    def init_routing(self, topology: Any, method: str) -> None: ...

    def delete_routing(self, topology: Any) -> None: ...

    def start_gonetem(self, topology: Any) -> None: ...

    def stop_gonetem(self, topology: Any) -> None: ...


@dataclass(frozen=True)
class TrafficPoll:
    """Normalized traffic-flow state."""

    status: str
    results: dict[str, Any] | None = None
    error: str | None = None


class TrafficGateway(Protocol):
    """Traffic flow lifecycle operations."""

    def start_iperf3(
        self, source: Any, destination: Any, request: Iperf3Request
    ) -> Any: ...

    def start_ping(
        self, source: Any, destination: Any, request: PingRequest
    ) -> Any: ...

    def start_hping3(
        self, source: Any, destination: Any, request: Hping3Request
    ) -> Any: ...

    def poll(self, kind: str, flow: Any) -> TrafficPoll: ...

    def stop(self, flow: Any) -> None: ...


class SecurityGateway(Protocol):
    """Destructive and capture operations used by the security lab."""

    def routing_methods(self, topology: Any) -> list[str]: ...

    def fail_link(self, topology: Any, key: str) -> dict[str, Any]: ...

    def start_capture(
        self,
        topology: Any,
        node: str,
        interface: str,
        packet_limit: int,
        duration_sec: int,
    ) -> dict[str, Any]: ...

    def stop_capture(self, topology: Any, node: str, path: str) -> None: ...

    def capture_status(
        self,
        topology: Any,
        node: str,
        path: str,
    ) -> dict[str, Any]: ...

    def read_capture(self, topology: Any, node: str, path: str) -> bytes: ...

    def delete_capture(self, topology: Any, node: str, path: str) -> None: ...


class PolicyGateway(Protocol):
    """Per-node firewall and QoS policy operations."""

    def preview(
        self, topology: Any, policy: NodePolicyRequest
    ) -> dict[str, Any]: ...

    def apply(
        self, topology: Any, policy: NodePolicyRequest
    ) -> dict[str, Any]: ...

    def clear(
        self,
        topology: Any,
        node: str,
        interfaces: list[str] | None = None,
    ) -> None: ...

    def status(self, topology: Any, node: str) -> dict[str, Any]: ...
