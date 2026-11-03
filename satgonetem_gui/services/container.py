"""Application service container built once per FastAPI app."""

from dataclasses import dataclass

from ..state import RuntimeState
from .project_service import ProjectService
from .routing_service import RoutingService
from .topology_service import TopologyService
from .traffic_service import TrafficService


@dataclass(frozen=True)
class ApplicationServices:
    """Services injected into route handlers."""

    runtime: RuntimeState
    project: ProjectService
    topology: TopologyService
    routing: RoutingService
    traffic: TrafficService
