"""Narrow interfaces implemented by the satgonetem adapters."""

from dataclasses import dataclass
from typing import Any, Protocol

from ..schemas import Hping3Request, Iperf3Request, PingRequest, ProjectCreateRequest
from ..state import ProjectResult


class EnvironmentDoctor(Protocol):
    """Local environment readiness checks for preflight diagnostics."""

    def environment_checks(self) -> list[dict[str, Any]]: ...


class ProjectGateway(Protocol):
    """Project build, load, save, and configuration operations."""

    def build(self, payload: ProjectCreateRequest) -> ProjectResult: ...

    def load(self, content: str) -> ProjectResult: ...

    def save(self, topology: Any) -> str: ...

    def config(self, topology: Any, save_path: str) -> dict[str, Any]: ...

    def cleanup_ground_files(self, topology: Any) -> None: ...


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


class LinkUsageReader(Protocol):
    """Live per-link bandwidth sampling for the dashboard."""

    def link_usage(self, topology: Any) -> dict[str, Any]: ...


class PathReader(Protocol):
    """Diagnostic path queries over the current routing graph."""

    def routing_path(self, topology: Any, src: str, dst: str) -> dict[str, Any]: ...


class NetworkOperationError(RuntimeError):
    """Raised when a GoNetEm operation reports failure via a return code."""


class AddressabilityController(Protocol):
    """Satellite traffic-addressability queries and mutations."""

    def satellite_addressability(self, topology: Any) -> dict[str, Any]: ...

    def set_satellites_addressable(
        self,
        topology: Any,
        enabled: bool,
        names: list[str] | None = None,
    ) -> int: ...


class NetworkController(Protocol):
    """Routing and container lifecycle operations."""

    def routing_status(self, topology: Any) -> dict[str, Any]: ...

    def apply_addressing(self, topology: Any) -> None: ...

    def init_routing(self, topology: Any, method: str) -> None: ...

    def delete_routing(self, topology: Any) -> None: ...

    def start_gonetem(self, topology: Any) -> None: ...

    def stop_gonetem(self, topology: Any) -> None: ...


class SimulationController(Protocol):
    """Simulation loop transport controls."""

    def simulation_running(self, topology: Any) -> bool: ...

    def start_simulation(self, topology: Any) -> None: ...

    def stop_simulation(self, topology: Any) -> None: ...

    def step_simulation(self, topology: Any) -> None: ...

    def reset_simulation(self, topology: Any) -> None: ...

    def seek_simulation(self, topology: Any, step: int) -> None: ...

    def change_simulation_speed(self, topology: Any, direction: str) -> None: ...


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

    def release(self, flow: Any) -> None: ...

    def register_flow(self, topology: Any, flow: Any) -> None: ...
