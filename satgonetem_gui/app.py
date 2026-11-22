"""FastAPI application factory and composition root."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from .adapters.satgonetem_traffic import SatGoNetemTrafficAdapter
from .config import Settings, load_settings
from .errors import install_error_handlers
from .resources import GROUND_STATIONS_DIR
from .routes import pages, projects, routing, topology, traffic
from .services.container import ApplicationServices
from .services.project_service import ProjectService
from .services.routing_service import RoutingService
from .services.topology_service import TopologyService
from .services.traffic_service import TrafficService
from .state import RuntimeState

BASE_DIR = Path(__file__).resolve().parent
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "testserver", "[::1]", "::1")
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _allowed_hosts(settings: Settings) -> list[str]:
    """Return loopback hosts plus explicit operator overrides."""
    hosts = set(LOOPBACK_HOSTS)
    if settings.host not in {"", "0.0.0.0", "::"}:
        hosts.add(settings.host)
    configured = os.getenv("SATGONETEM_GUI_ALLOWED_HOSTS", "")
    hosts.update(host.strip() for host in configured.split(",") if host.strip())
    return sorted(hosts)


def _install_origin_guard(app: FastAPI, hosts: list[str]) -> None:
    """Reject state-changing requests from a non-allowed browser origin."""
    allowed_names = {
        host.strip("[]") for host in hosts
    } | {"127.0.0.1", "localhost", "testserver", "::1"}

    @app.middleware("http")
    async def same_origin_guard(request, call_next):
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin:
                origin_host = (urlsplit(origin).hostname or "").strip("[]")
                if origin_host not in allowed_names:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "ok": False,
                            "error": "Cross-origin request rejected.",
                        },
                    )
        return await call_next(request)


def build_services(settings: Settings) -> ApplicationServices:
    """Build the production service graph for one application instance."""
    runtime = RuntimeState()
    topology_adapter = SatGoNetemTopologyAdapter(settings)
    traffic_adapter = SatGoNetemTrafficAdapter()

    topology = TopologyService(runtime.project, topology_adapter)
    project = ProjectService(
        runtime,
        topology_adapter,
        settings,
        GROUND_STATIONS_DIR,
        network_running=topology.network_running,
    )
    routing = RoutingService(topology, topology_adapter)
    traffic = TrafficService(topology, traffic_adapter)
    return ApplicationServices(
        runtime=runtime,
        project=project,
        topology=topology,
        routing=routing,
        traffic=traffic,
    )


def create_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Create an application with isolated state and injectable services."""
    settings = settings or load_settings()
    services = services or build_services(settings)

    app = FastAPI(title="SatGoNetem GUI")
    allowed_hosts = _allowed_hosts(settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    _install_origin_guard(app, allowed_hosts)
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
    return app
