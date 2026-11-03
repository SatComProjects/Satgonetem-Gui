"""FastAPI application for the SatGoNetem GUI."""

import asyncio
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sat_com_builder.models import (
    GroundObjectProperty,
    SimulationProperty,
    WalkerShellProperty,
)
from satgonetem.services.topology_satcom import NetworkConfig, TopologyManager
from satgonetem.traffic import (
    FlowStatus,
    Hping3Config,
    Hping3Flow,
    Hping3Status,
    Iperf3Config,
    Iperf3Flow,
    PingConfig,
    PingFlow,
    PingStatus,
)
from satgonetem.utils.satcom_fix import apply_satcom_fix

apply_satcom_fix()

from . import schemas
from .config import load_settings
from .errors import APIError, install_error_handlers
from .ground_stations import parse_ground_station_file, write_stations_to_temp
from .serializers import (
    serialize_hping3_results,
    serialize_iperf3_results,
    serialize_ping_results,
)
from .state import ProjectResult, app_state
from .storage import SavePathError, resolve_data_file, resolve_save_path

BASE_DIR = Path(__file__).parent
SATGONETEM_DIR = BASE_DIR.parent / "satgonetem"
RESOURCES_DIR = BASE_DIR.parent / "resources" / "ground_station_files"
SETTINGS = load_settings()
SAVE_ROOT = SETTINGS.save_root

app = FastAPI(title="SatGoNetem GUI")
install_error_handlers(app)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _build_topology(payload: schemas.ProjectCreateRequest) -> TopologyManager:
    """Build a TopologyManager from a typed create-form payload.

    Args:
        payload: Validated project creation request.

    Returns:
        The initialised TopologyManager.

    Raises:
        Exception: Validation or topology-building errors are propagated to
            the task manager, which records them in the project session.
    """
    shells_raw: list = json.loads(payload.walker_shells_json)
    grounds_raw: list = json.loads(payload.ground_objects_properties_json)

    shells = [WalkerShellProperty(**shell) for shell in shells_raw]

    ground_props = []
    for ground in grounds_raw:
        ground = dict(ground)
        if ground.get("stations"):
            ground["data_file"] = str(write_stations_to_temp(ground.pop("stations")))
        else:
            ground.pop("stations", None)
            data_file = ground.get("data_file")
            if not data_file:
                raise ValueError("Ground object has no stations or data_file.")
            ground["data_file"] = str(resolve_data_file(data_file, SATGONETEM_DIR))
        ground_props.append(GroundObjectProperty(**ground))

    simulation_property = SimulationProperty(
        simulation_name=payload.name.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        walker_shells=shells,
        ground_objects_properties=ground_props,
    )

    tm = TopologyManager.from_satcom(simulation_property)
    network_config = NetworkConfig(
        project_name=payload.name.strip(),
        update_time=payload.update_time,
        isl_link_capacity=payload.isl_capacity,
        gnd_link_capacity=payload.gs_capacity,
    )
    tm._apply_network_config(network_config)

    save_target = resolve_save_path(payload.save_path, payload.name, SAVE_ROOT)
    if save_target is not None:
        save_target.parent.mkdir(parents=True, exist_ok=True)
        tm.to_file(str(save_target))

    return tm


def _create_project(payload: schemas.ProjectCreateRequest) -> ProjectResult:
    """Build a project and return the result stored by the task manager."""
    name = payload.name.strip()
    save_path = str(payload.save_path or "").strip()
    tm = _build_topology(payload)
    tm.set_status(True)
    logging.info("Project '%s' loaded successfully.", name)
    return ProjectResult(tm, name, save_path)


def _project_display_name(tm: TopologyManager) -> str:
    """Return the user-facing project name from a loaded topology manager."""
    simulation_property = getattr(tm, "simulation_property", None)
    name = (
        getattr(simulation_property, "simulation_name", None)
        if simulation_property
        else None
    )
    if not name:
        raw_name = str(getattr(tm, "project_name", "") or "Loaded Project")
        name = re.sub(r"_\d{10}$", "", raw_name)
    return str(name).strip() or "Loaded Project"


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered dashboard template.
    """
    return templates.TemplateResponse(request, "index.html")


@app.get("/new_project", response_class=HTMLResponse)
async def new_project(request: Request) -> HTMLResponse:
    """Render the new project creation page.

    Args:
        request: Incoming HTTP request. Accepts an optional 'edit' query param
            containing the name of an existing project to pre-populate the form.

    Returns:
        HTML response with the rendered new_project template.
    """
    return templates.TemplateResponse(request, "new_project.html")


@app.get("/ground_stations", response_class=HTMLResponse)
async def ground_stations_page(request: Request) -> HTMLResponse:
    """Render the ground station selection page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered ground_stations template.
    """
    return templates.TemplateResponse(request, "ground_stations.html")


@app.get(
    "/api/ground_stations/presets",
    response_model=list[schemas.GroundStationPreset],
)
async def api_ground_station_presets() -> list[schemas.GroundStationPreset]:
    """Return all preset ground station files and their stations."""
    return [
        {"name": path.stem, "stations": parse_ground_station_file(path)}
        for path in sorted(RESOURCES_DIR.glob("*.txt"))
    ]


@app.post("/api/project/create", response_model=schemas.OperationResponse)
async def api_project_create(
    payload: schemas.ProjectCreateRequest,
) -> schemas.OperationResponse:
    """Start building a constellation project in a background thread."""
    name = payload.name.strip()
    if not name:
        raise APIError(400, "Project name is required.")

    try:
        resolve_save_path(payload.save_path, name, SAVE_ROOT)
    except SavePathError as exc:
        raise APIError(400, str(exc)) from exc

    save_path = str(payload.save_path or "").strip()
    started = app_state.project_tasks.start(
        name=name,
        save_path=save_path,
        operation="create",
        runner=lambda: _create_project(payload),
    )
    if not started:
        raise APIError(409, "A project operation is already running.")
    return schemas.OperationResponse()


@app.get("/api/project/status", response_model=schemas.ProjectStatusResponse)
async def api_project_status() -> schemas.ProjectStatusResponse:
    """Return the explicit state of the project lifecycle."""
    return schemas.ProjectStatusResponse(**app_state.project.snapshot())


@app.get("/api/project/exists", response_model=schemas.ProjectExistsResponse)
async def api_project_exists(name: str) -> schemas.ProjectExistsResponse:
    """Check whether a named project has finished loading."""
    return schemas.ProjectExistsResponse(exists=app_state.project.exists(name))


@app.get("/api/project/config", response_model=schemas.ProjectConfigResponse)
async def api_project_config(name: str) -> schemas.ProjectConfigResponse:
    """Return the editable configuration of the loaded project."""
    tm = app_state.project.get_topology(name)
    if tm is None:
        raise APIError(404, "Project not found.")

    try:
        simulation_property = getattr(tm, "simulation_property", None)
        if simulation_property is None:
            raise APIError(500, "Project configuration is unavailable.")

        config = simulation_property.model_dump(mode="json")
        config["name"] = (
            app_state.project.project_name or simulation_property.simulation_name
        )
        config["update_time"] = tm.update_time
        config["isl_capacity"] = tm.isl_link_capacity
        config["gs_capacity"] = tm.gnd_link_capacity
        config["save_path"] = app_state.project.save_path

        for ground in config.get("ground_objects_properties", []):
            data_file = ground.get("data_file")
            ground["stations"] = []
            if not data_file:
                continue
            try:
                ground["stations"] = parse_ground_station_file(Path(data_file))
            except Exception:
                logging.exception(
                    "Could not read ground station file for project config: %s",
                    data_file,
                )
        return schemas.ProjectConfigResponse.model_validate(config)
    except APIError:
        raise
    except Exception as exc:
        logging.exception("Could not read project config.")
        raise APIError(500, "Could not read project config.") from exc


@app.post("/api/project/load", response_model=schemas.ProjectLoadedResponse)
async def api_project_load(
    payload: schemas.ProjectLoadRequest,
) -> schemas.ProjectLoadedResponse:
    """Load a topology from an uploaded saved-project JSON file."""
    if not app_state.project.begin(name="", save_path="", operation="load"):
        raise APIError(409, "A project operation is already running.")

    tmp_path = (
        Path(tempfile.gettempdir()) / f"satgonetem_load_{os.urandom(8).hex()}.json"
    )
    try:
        tmp_path.write_text(payload.content, encoding="utf-8")
        tm = await asyncio.to_thread(TopologyManager.from_file, str(tmp_path))
        project_name = _project_display_name(tm)
        tm.set_status(True)
        app_state.project.succeed(tm, project_name, "")
        logging.info("Project '%s' loaded from file.", project_name)
        return schemas.ProjectLoadedResponse(name=project_name)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        message = str(exc).strip() or exc.__class__.__name__
        app_state.project.fail(message)
        raise APIError(400, f"Invalid project file: {message}") from exc
    except Exception as exc:
        logging.exception("Project load failed.")
        message = str(exc).strip() or exc.__class__.__name__
        app_state.project.fail(message)
        raise APIError(500, "Project load failed.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/project/save", response_model=schemas.ProjectSaveResponse)
async def api_project_save() -> schemas.ProjectSaveResponse:
    """Return the loaded project as a downloadable JSON string."""
    tm = app_state.project.get_topology()
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    tmp_path = (
        Path(tempfile.gettempdir()) / f"satgonetem_save_{os.urandom(8).hex()}.json"
    )
    try:
        await asyncio.to_thread(tm.to_file, str(tmp_path))
        content = tmp_path.read_text(encoding="utf-8")
        filename = f"{(app_state.project_name or 'project').replace(' ', '_')}.json"
        return schemas.ProjectSaveResponse(content=content, filename=filename)
    except Exception as exc:
        logging.exception("Project save failed.")
        raise APIError(500, "Project save failed.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/satellites", response_model=list[schemas.SatelliteResponse])
async def api_satellites() -> list[schemas.SatelliteResponse]:
    """Return all satellites with their current positions."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    try:
        tm._sync_node_positions()
    except Exception:
        logging.exception("Failed to sync satellite positions.")

    return [
        {
            "id": sat.id,
            "name": sat.name,
            "position": {
                "latitude": sat.position.get("latitude"),
                "longitude": sat.position.get("longitude"),
                "altitude": sat.position.get("altitude"),
            },
        }
        for sat in tm.satellites.values()
    ]


@app.get(
    "/api/ground_stations",
    response_model=list[schemas.GroundStationResponse],
)
async def api_ground_stations() -> list[schemas.GroundStationResponse]:
    """Return all ground stations with their positions."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    return [
        {
            "id": station.id,
            "name": station.name,
            "city": getattr(station, "city", None),
            "position": {
                "latitude": station.position.get("latitude"),
                "longitude": station.position.get("longitude"),
                "altitude": station.position.get("altitude"),
            },
        }
        for station in tm.ground_stations.values()
    ]


@app.get("/api/status", response_model=schemas.StatusResponse)
async def api_status() -> schemas.StatusResponse:
    """Return the current constellation and emulation status."""
    return schemas.StatusResponse(**app_state.get_status_dict())


@app.get("/api/routing/status", response_model=schemas.RoutingStatusResponse)
async def api_routing_status() -> schemas.RoutingStatusResponse:
    """Return the current routing and addressing status."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    gonetem_on = tm.get_gonetem_status()
    return schemas.RoutingStatusResponse(
        gonetem_is_on=gonetem_on,
        addressing_applied=gonetem_on,
        routing_initiated=tm.get_routing_initiated(),
        routing_method=tm.routing,
    )


@app.post("/api/routing/apply", response_model=schemas.OperationResponse)
async def api_routing_apply(
    payload: schemas.RoutingApplyRequest,
) -> schemas.OperationResponse:
    """Apply IP addressing and initialize routing."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")
    if not tm.get_gonetem_status():
        raise APIError(409, "GoNetEm is not running. Start containers first.")

    try:
        await asyncio.to_thread(tm.set_ip_addresses)
        await asyncio.to_thread(tm.init_routing, routing_method=payload.method)
    except Exception as exc:
        logging.exception("Failed to apply addressing and routing.")
        raise APIError(500, "Failed to apply addressing and routing.") from exc

    return schemas.OperationResponse()


@app.post("/api/routing/delete", response_model=schemas.OperationResponse)
async def api_routing_delete() -> schemas.OperationResponse:
    """Delete all installed routing state."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    try:
        await asyncio.to_thread(tm.delete_routing)
    except Exception as exc:
        logging.exception("Failed to delete routing.")
        raise APIError(500, "Failed to delete routing.") from exc
    return schemas.OperationResponse()


@app.post("/api/gonetem/start", response_model=schemas.OperationResponse)
async def api_gonetem_start() -> schemas.OperationResponse:
    """Start the Docker containers via GoNetem."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    try:
        await asyncio.to_thread(tm.start_gonetem)
    except Exception as exc:
        logging.exception("Failed to start GoNetem.")
        raise APIError(500, "Failed to start GoNetem.") from exc
    return schemas.OperationResponse()


@app.post("/api/gonetem/stop", response_model=schemas.OperationResponse)
async def api_gonetem_stop() -> schemas.OperationResponse:
    """Stop the Docker containers via GoNetem."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    try:
        await asyncio.to_thread(tm.stop_gonetem)
        tm.set_status(True)
    except Exception as exc:
        logging.exception("Failed to stop GoNetem.")
        raise APIError(500, "Failed to stop GoNetem.") from exc
    return schemas.OperationResponse()


@app.get("/world", response_class=HTMLResponse)
async def world_page(request: Request) -> HTMLResponse:
    """Render the Cesium world view page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered world template.
    """
    return templates.TemplateResponse(request, "world.html")


@app.get("/api/links", response_model=list[schemas.LinkResponse])
async def api_links() -> list[schemas.LinkResponse]:
    """Return all links with their endpoints, type, and direction."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    return [
        {
            "src": link.source.name,
            "dst": link.target.name,
            "type": link.type,
            "direction": link.direction,
            "distance_km": round(link.distance / 1000.0, 2),
        }
        for link in tm.links.values()
    ]


@app.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request) -> HTMLResponse:
    """Render the node explorer page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered nodes template.
    """
    return templates.TemplateResponse(request, "nodes.html")


@app.get("/api/nodes", response_model=list[schemas.NodeSummary])
async def api_nodes() -> list[schemas.NodeSummary]:
    """Return all nodes with basic identity and position info."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    try:
        tm._sync_node_positions()
    except Exception:
        logging.exception("Failed to sync node positions.")

    nodes = []
    for sat in tm.satellites.values():
        nodes.append(
            {
                "name": sat.name,
                "type": "satellite",
                "id": sat.id,
                "position": {
                    "latitude": sat.position.get("latitude"),
                    "longitude": sat.position.get("longitude"),
                    "altitude": sat.position.get("altitude"),
                },
            }
        )
    for station in tm.ground_stations.values():
        nodes.append(
            {
                "name": station.name,
                "type": "ground_station",
                "id": station.id,
                "city": getattr(station, "city", None),
                "position": {
                    "latitude": station.position.get("latitude"),
                    "longitude": station.position.get("longitude"),
                    "altitude": station.position.get("altitude"),
                },
            }
        )
    return nodes


@app.get("/api/nodes/{name}", response_model=schemas.NodeDetailResponse)
async def api_node_detail(name: str) -> schemas.NodeDetailResponse:
    """Return detailed information for a single node."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    node = tm.get_node_by_name(name)
    if node is None:
        raise APIError(404, f"Node not found: {name}")

    try:
        tm._sync_node_positions()
    except Exception:
        logging.exception("Failed to sync node positions.")

    interfaces = []
    for iface in node.interfaces:
        peer_name = ""
        if iface.peer is not None:
            peer_name = getattr(iface.peer, "name", "")
        interfaces.append(
            {
                "name": iface.name,
                "iname": iface.get_iname(),
                "ipv4": iface.ipv4,
                "type": iface.type,
                "is_active": iface.is_active,
                "peer_name": peer_name,
            }
        )

    loopback = node.loopback
    routing_table: list[str] = []
    try:
        routing_table = node.get_routing_table()
    except Exception:
        logging.exception("Failed to read routing table for %s", name)

    data: Dict[str, Any] = {
        "name": node.name,
        "type": "satellite" if name.startswith("Sat") else "ground_station",
        "id": node.id,
        "position": {
            "latitude": node.position.get("latitude"),
            "longitude": node.position.get("longitude"),
            "altitude": node.position.get("altitude"),
        },
        "interfaces": interfaces,
        "loopback": {"ipv4": getattr(loopback, "ipv4", "")},
        "routing_table": routing_table,
    }

    if name.startswith("Sat"):
        data["default_qos_is_on"] = getattr(node, "default_qos_is_on", False)
        data["program_specific_qos_is_on"] = getattr(
            node, "program_specific_qos_is_on", False
        )
    else:
        data["city"] = getattr(node, "city", None)

    return schemas.NodeDetailResponse(node=schemas.NodeDetail(**data))


@app.get("/traffic", response_class=HTMLResponse)
async def traffic_page(request: Request) -> HTMLResponse:
    """Render the traffic generator page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered traffic template.
    """
    return templates.TemplateResponse(request, "traffic.html")


@app.get("/api/traffic/nodes", response_model=schemas.TrafficNodesResponse)
async def api_traffic_nodes() -> schemas.TrafficNodesResponse:
    """Return all nodes that can be used as traffic endpoints."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project is currently loaded.")

    nodes = [
        {"name": satellite.name, "type": "satellite"}
        for satellite in tm.satellites.values()
    ]
    nodes.extend(
        {"name": station.name, "type": "ground_station"}
        for station in tm.ground_stations.values()
    )
    return schemas.TrafficNodesResponse(nodes=nodes)


@app.post("/api/traffic/iperf3", response_model=schemas.TrafficStartResponse)
async def api_traffic_iperf3(
    payload: schemas.Iperf3Request,
) -> schemas.TrafficStartResponse:
    """Start an iperf3 flow between two nodes."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project loaded.")
    if not tm.get_gonetem_status():
        raise APIError(409, "GoNetEm is not running.")

    src = tm.get_node_by_name(payload.src)
    dst = tm.get_node_by_name(payload.dst)
    if src is None or dst is None:
        raise APIError(404, f"Node not found: {payload.src} or {payload.dst}")

    config = Iperf3Config(
        protocol=payload.protocol,
        duration=payload.duration,
        bandwidth_mbps=payload.bandwidth_mbps,
        parallel=payload.parallel,
        interval=payload.interval,
        port=payload.port,
        congestion_control=payload.congestion_control,
        window_size=payload.window_size or None,
        bidir=payload.bidir,
    )

    try:
        flow = Iperf3Flow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start iperf3 flow.")
        raise APIError(500, "Failed to start iperf3 flow.") from exc

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "iperf3",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": payload.src,
            "dst": payload.dst,
        }
    return schemas.TrafficStartResponse(job_id=job_id)


@app.post("/api/traffic/ping", response_model=schemas.TrafficStartResponse)
async def api_traffic_ping(payload: schemas.PingRequest) -> schemas.TrafficStartResponse:
    """Start a ping flow between two nodes."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project loaded.")
    if not tm.get_gonetem_status():
        raise APIError(409, "GoNetEm is not running.")

    src = tm.get_node_by_name(payload.src)
    dst = tm.get_node_by_name(payload.dst)
    if src is None or dst is None:
        raise APIError(404, f"Node not found: {payload.src} or {payload.dst}")

    config = PingConfig(
        count=payload.count,
        timeout_sec=payload.timeout_sec,
        interval_sec=payload.interval_sec,
        packet_size=payload.packet_size,
    )

    try:
        flow = PingFlow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start ping flow.")
        raise APIError(500, "Failed to start ping flow.") from exc

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "ping",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": payload.src,
            "dst": payload.dst,
        }
    return schemas.TrafficStartResponse(job_id=job_id)


@app.post("/api/traffic/hping3", response_model=schemas.TrafficStartResponse)
async def api_traffic_hping3(
    payload: schemas.Hping3Request,
) -> schemas.TrafficStartResponse:
    """Start an hping3 flow between two nodes."""
    tm = app_state.topology_manager
    if tm is None:
        raise APIError(404, "No project loaded.")
    if not tm.get_gonetem_status():
        raise APIError(409, "GoNetEm is not running.")

    src = tm.get_node_by_name(payload.src)
    dst = tm.get_node_by_name(payload.dst)
    if src is None or dst is None:
        raise APIError(404, f"Node not found: {payload.src} or {payload.dst}")

    config = Hping3Config(
        proto=payload.proto,
        dport=payload.dport,
        count=payload.count,
        size=payload.size,
        rate_type=payload.rate_type,
        interval=payload.interval,
        flags=payload.flags,
    )

    try:
        flow = Hping3Flow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start hping3 flow.")
        raise APIError(500, "Failed to start hping3 flow.") from exc

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "hping3",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": payload.src,
            "dst": payload.dst,
        }
    return schemas.TrafficStartResponse(job_id=job_id)


@app.get("/api/traffic/status", response_model=schemas.TrafficStatusResponse)
async def api_traffic_status(job_id: str) -> schemas.TrafficStatusResponse:
    """Poll the status of a traffic job."""
    with app_state.jobs_lock:
        job = app_state.jobs.get(job_id)
    if job is None:
        raise APIError(404, "Job not found.")

    flow = job["flow"]
    kind = job["kind"]

    try:
        if kind == "iperf3":
            status = flow.status()
            if status == FlowStatus.RUNNING:
                return schemas.TrafficStatusResponse(status="running")
            if status == FlowStatus.DONE:
                job["results"] = serialize_iperf3_results(flow.results())
                job["status"] = "done"
                return schemas.TrafficStatusResponse(
                    status="done",
                    results=job["results"],
                )
            if status == FlowStatus.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return schemas.TrafficStatusResponse(
                    status="error",
                    error=job.get("error", "Unknown error."),
                )
        elif kind == "ping":
            status = flow.status()
            if status == PingStatus.RUNNING:
                return schemas.TrafficStatusResponse(status="running")
            if status == PingStatus.DONE:
                job["results"] = serialize_ping_results(flow.results())
                job["status"] = "done"
                return schemas.TrafficStatusResponse(
                    status="done",
                    results=job["results"],
                )
            if status == PingStatus.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return schemas.TrafficStatusResponse(
                    status="error",
                    error=job.get("error", "Unknown error."),
                )
        elif kind == "hping3":
            status = flow.status()
            if status == Hping3Status.RUNNING:
                return schemas.TrafficStatusResponse(status="running")
            if status == Hping3Status.DONE:
                job["results"] = serialize_hping3_results(flow.results())
                job["status"] = "done"
                return schemas.TrafficStatusResponse(
                    status="done",
                    results=job["results"],
                )
            if status == Hping3Status.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return schemas.TrafficStatusResponse(
                    status="error",
                    error=job.get("error", "Unknown error."),
                )
    except Exception as exc:
        logging.exception("Error polling traffic job status.")
        raise APIError(500, "Error polling traffic job status.") from exc

    return schemas.TrafficStatusResponse(status=job.get("status", "unknown"))


@app.post("/api/traffic/cancel", response_model=schemas.OperationResponse)
async def api_traffic_cancel(
    payload: schemas.TrafficCancelRequest,
) -> schemas.OperationResponse:
    """Cancel a running traffic job."""
    with app_state.jobs_lock:
        job = app_state.jobs.get(payload.job_id)
    if job is None:
        raise APIError(404, "Job not found.")

    job["status"] = "cancelled"
    return schemas.OperationResponse()
