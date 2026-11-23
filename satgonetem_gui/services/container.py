"""Application service container built once per FastAPI app."""

from dataclasses import dataclass

from ..state import RuntimeState
from .addressability_service import AddressabilityService
from .connectivity_service import ConnectivityService
from .coverage_service import CoverageService
from .experiment_service import ExperimentService
from .link_budget_service import LinkBudgetService
from .preflight_service import PreflightService
from .project_catalog_service import ProjectCatalogService
from .project_service import ProjectService
from .routing_service import RoutingService
from .simulation_service import SimulationService
from .topology_export_service import TopologyExportService
from .topology_history_service import TopologyHistoryService
from .topology_service import TopologyService
from .traffic_service import TrafficService


@dataclass(frozen=True)
class ApplicationServices:
    """Services injected into route handlers."""

    runtime: RuntimeState
    project: ProjectService
    catalog: ProjectCatalogService
    topology: TopologyService
    topology_export: TopologyExportService
    topology_history: TopologyHistoryService
    addressability: AddressabilityService
    routing: RoutingService
    traffic: TrafficService
    simulation: SimulationService
    preflight: PreflightService
    connectivity: ConnectivityService
    coverage: CoverageService
    experiments: ExperimentService
    link_budget: LinkBudgetService
