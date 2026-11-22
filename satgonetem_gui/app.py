"""FastAPI application factory and composition root."""

import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from .adapters.satgonetem_traffic import SatGoNetemTrafficAdapter
from .config import Settings, load_settings
from .errors import install_error_handlers
from .resources import GROUND_STATIONS_DIR
from .routes import (
    addressability,
    pages,
    projects,
    routing,
    simulation,
    topology,
    traffic,
)
from .services.addressability_service import AddressabilityService
from .services.container import ApplicationServices
from .services.project_service import ProjectService
from .services.routing_service import RoutingService
from .services.simulation_service import SimulationService
from .services.topology_service import TopologyService
from .services.traffic_service import TrafficService
from .state import RuntimeState

BASE_DIR = Path(__file__).resolve().parent
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "testserver", "[::1]", "::1")
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _local_host_names() -> set[str]:
    """Return the machine hostname and local addresses for wildcard binds."""
    names = {socket.gethostname(), socket.getfqdn()}
    try:
        names.update(str(info[4][0]) for info in socket.getaddrinfo(socket.gethostname(), None))
    except OSError:
        pass
    return {name.lower() for name in names if name}


def _allowed_hosts(settings: Settings) -> list[str]:
    """Return loopback hosts plus explicit operator overrides."""
    hosts = set(LOOPBACK_HOSTS)
    if settings.host in {"0.0.0.0", "::"}:
        hosts.update(_local_host_names())
    elif settings.host not in {"", "0.0.0.0", "::"}:
        hosts.add(settings.host)
    configured = os.getenv("SATGONETEM_GUI_ALLOWED_HOSTS", "")
    hosts.update(host.strip() for host in configured.split(",") if host.strip())
    return sorted(host.lower() for host in hosts)


def _install_request_guards(app: FastAPI, hosts: list[str]) -> None:
    """Reject untrusted Host headers and cross-origin browser mutations."""
    allowed_names = {
        host.strip("[]").lower() for host in hosts
    } | {"127.0.0.1", "localhost", "testserver", "::1"}

    @app.middleware("http")
    async def request_guard(request, call_next):
        host_header = request.headers.get("host", "")
        try:
            host_name = (urlsplit(f"//{host_header}").hostname or "").lower()
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Invalid Host header."},
            )
        if host_name not in allowed_names:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Invalid Host header."},
            )

        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin:
                try:
                    parsed_origin = urlsplit(origin)
                    origin_host = (parsed_origin.hostname or "").lower()
                    origin_port = parsed_origin.port or (
                        443 if parsed_origin.scheme == "https" else 80
                    )
                    parsed_host = urlsplit(f"//{host_header}")
                    request_port = parsed_host.port or (
                        443 if parsed_origin.scheme == "https" else 80
                    )
                except ValueError:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "ok": False,
                            "error": "Cross-origin request rejected.",
                        },
                    )
                same_host = (parsed_host.hostname or "").lower() == origin_host
                if (
                    origin_host.strip("[]") not in allowed_names
                    or not same_host
                    or origin_port != request_port
                ):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "ok": False,
                            "error": "Cross-origin request rejected.",
                        },
                    )
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy", "frame-ancestors 'none'"
        )
        return response


def build_services(settings: Settings) -> ApplicationServices:
    """Build the production service graph for one application instance."""
    runtime = RuntimeState()
    topology_adapter = SatGoNetemTopologyAdapter(settings)
    traffic_adapter = SatGoNetemTrafficAdapter()

    topology = TopologyService(runtime.project, topology_adapter)
    addressability = AddressabilityService(topology, topology_adapter)
    simulation = SimulationService(topology, topology_adapter)
    project = ProjectService(
        runtime,
        topology_adapter,
        settings,
        GROUND_STATIONS_DIR,
        network_running=topology.network_running,
        stop_simulation=simulation.stop_current,
    )
    routing = RoutingService(topology, topology_adapter)
    traffic = TrafficService(topology, traffic_adapter)
    return ApplicationServices(
        runtime=runtime,
        project=project,
        topology=topology,
        addressability=addressability,
        routing=routing,
        traffic=traffic,
        simulation=simulation,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Stop the simulation loop when the application shuts down."""
    yield
    await app.state.services.simulation.shutdown()


def create_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Create an application with isolated state and injectable services."""
    settings = settings or load_settings()
    services = services or build_services(settings)

    app = FastAPI(title="SatGoNetem GUI", lifespan=_lifespan)
    allowed_hosts = _allowed_hosts(settings)
    _install_request_guards(app, allowed_hosts)
    install_error_handlers(app)
    app.state.settings = settings
    app.state.services = services

    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    app.include_router(pages.create_pages_router(templates))
    app.include_router(projects.router)
    app.include_router(topology.router)
    app.include_router(addressability.router)
    app.include_router(routing.router)
    app.include_router(simulation.router)
    app.include_router(traffic.router)
    return app
