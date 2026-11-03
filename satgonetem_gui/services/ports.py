"""Narrow interfaces implemented by the satgonetem adapters."""

from dataclasses import dataclass
from typing import Any, Protocol

from ..schemas import Hping3Request, Iperf3Request, PingRequest, ProjectCreateRequest
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


class NetworkController(Protocol):
    """Routing and container lifecycle operations."""

    def routing_status(self, topology: Any) -> dict[str, Any]: ...

    def apply_routing(self, topology: Any, method: str) -> None: ...

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
