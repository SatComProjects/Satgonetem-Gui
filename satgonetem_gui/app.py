"""FastAPI application factory and composition root."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .adapters.satgonetem_security import SatGoNetemSecurityAdapter
from .adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from .adapters.satgonetem_traffic import SatGoNetemTrafficAdapter
from .config import Settings, load_settings
from .errors import install_error_handlers
from .resources import GROUND_STATIONS_DIR
from .routes import pages, projects, routing, security, topology, traffic
from .services.container import ApplicationServices
from .services.project_service import ProjectService
from .services.routing_service import RoutingService
from .services.security_service import SecurityService
from .services.topology_service import TopologyService
from .services.traffic_service import TrafficService
from .state import RuntimeState

BASE_DIR = Path(__file__).resolve().parent


def build_services(settings: Settings) -> ApplicationServices:
    """Build the production service graph for one application instance."""
    runtime = RuntimeState()
    topology_adapter = SatGoNetemTopologyAdapter(settings)
    traffic_adapter = SatGoNetemTrafficAdapter()
    security_adapter = SatGoNetemSecurityAdapter()

    project = ProjectService(runtime, topology_adapter, settings, GROUND_STATIONS_DIR)
    topology = TopologyService(runtime.project, topology_adapter)
    routing = RoutingService(topology, topology_adapter)
    traffic = TrafficService(topology, traffic_adapter)
    security = SecurityService(topology, routing, project, security_adapter)
    return ApplicationServices(
        runtime=runtime,
        project=project,
        topology=topology,
        routing=routing,
        traffic=traffic,
        security=security,
    )


def create_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Create an application with isolated state and injectable services."""
    settings = settings or load_settings()
    services = services or build_services(settings)

    app = FastAPI(title="SatGoNetem GUI")
    install_error_handlers(app)
    app.state.settings = settings
    app.state.services = services

    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    app.include_router(pages.create_pages_router(templates))
    app.include_router(projects.router)
    app.include_router(topology.router)
    app.include_router(routing.router)
    app.include_router(traffic.router)
    app.include_router(security.router)
    return app


app = create_app()
