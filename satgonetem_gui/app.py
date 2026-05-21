"""FastAPI application for the SatGoNetem GUI."""

import asyncio
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

from .state import app_state

BASE_DIR = Path(__file__).parent
SATGONETEM_DIR = BASE_DIR.parent / "satgonetem"
RESOURCES_DIR = BASE_DIR.parent / "resources" / "ground_station_files"

app = FastAPI(title="SatGoNetem GUI")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _resolve_data_file(data_file: str) -> str:
    """Resolve a ground station data file path to an absolute path.

    Checks the path as-is first (absolute), then resolves relative paths
    against the local satgonetem resources directory.

    Args:
        data_file: Absolute or relative path to the CSV ground station file.

    Returns:
        Absolute path string to the existing file.

    Raises:
        FileNotFoundError: If the file cannot be located.
    """
    p = Path(data_file)
    if p.is_absolute() and p.exists():
        return str(p)
    resolved = SATGONETEM_DIR / data_file
    if resolved.exists():
        return str(resolved)
    raise FileNotFoundError(f"Ground station data file not found: {data_file!r}")


def _parse_gs_file(path: Path) -> List[Dict[str, Any]]:
    """Parse a CSV ground station file into a list of station dicts.

    Args:
        path: Path to the CSV file with format: index,name,lat,lon,elevation_km.

    Returns:
        List of dicts with keys: index, name, latitude, longitude, elevation_km.
    """
    stations = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 4)
            if len(parts) < 5:
                continue
            try:
                stations.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1].strip(),
                        "latitude": float(parts[2]),
                        "longitude": float(parts[3]),
                        "elevation_km": float(parts[4]),
                    }
                )
            except ValueError:
                continue
    return stations


def _write_stations_to_tmp(identifier: str, stations: List[Dict[str, Any]]) -> str:
    """Write inline station dicts to a temporary CSV file.

    Args:
        identifier: Human-readable name used to form the filename.
        stations: List of dicts with keys: index, name, latitude, longitude,
            elevation_km.

    Returns:
        Absolute path to the written temp file.
    """
    name = identifier.lower().replace(" ", "_")
    path = Path(tempfile.gettempdir()) / f"gs_{name}.txt"
    lines = [
        f"{s['index']},{s['name']},{s['latitude']},{s['longitude']},{s['elevation_km']}"
        for s in stations
    ]
    path.write_text("\n".join(lines))
    return str(path)


def _build_topology(payload: Dict[str, Any]) -> None:
    """Build a TopologyManager from form payload and store it in app_state.

    Runs in a background thread. Sets app_state.creating while running and
    clears it when done regardless of outcome.

    Args:
        payload: Parsed JSON body from the /api/project/create endpoint.
            Accepts an optional 'save_path' key (str) with a directory or file
            path where the topology JSON should be written via to_file().
            Ground objects may carry an inline 'stations' list instead of a
            'data_file' path.
    """
    app_state.creating = True
    try:
        shells_raw: list = json.loads(payload["walker_shells_json"])
        grounds_raw: list = json.loads(payload["ground_objects_properties_json"])

        shells = [WalkerShellProperty(**s) for s in shells_raw]

        ground_props = []
        for g in grounds_raw:
            g = dict(g)
            if g.get("stations"):
                g["data_file"] = _write_stations_to_tmp(
                    g.get("identifier", "gs"), g.pop("stations")
                )
            else:
                g.pop("stations", None)
                g["data_file"] = _resolve_data_file(g["data_file"])
            ground_props.append(GroundObjectProperty(**g))

        sim_prop = SimulationProperty(
            simulation_name=payload["name"],
            start_date=payload["start_date"],
            end_date=payload["end_date"],
            walker_shells=shells,
            ground_objects_properties=ground_props,
        )

        tm = TopologyManager.from_satcom(sim_prop)
        net_cfg = NetworkConfig(
            project_name=payload["name"],
            update_time=int(payload.get("update_time", 5)),
            isl_link_capacity=int(payload.get("isl_capacity", 100000)),
            gnd_link_capacity=int(payload.get("gs_capacity", 100000)),
        )
        tm._apply_network_config(net_cfg)

        save_path = payload.get("save_path", "").strip()
        if save_path:
            sp = Path(save_path)
            if sp.is_dir():
                sp = sp / f"{payload['name']}.json"
            tm.to_file(str(sp))

        app_state.topology_manager = tm
        app_state.project_name = payload["name"]
        tm.set_status(True)
        logging.info("Project '%s' loaded successfully.", payload["name"])
    except Exception:
        logging.exception("Project creation failed.")
    finally:
        app_state.creating = False


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


@app.get("/api/ground_stations/presets")
async def api_ground_station_presets() -> JSONResponse:
    """Return all preset ground station files and their stations.

    Returns:
        JSON array of objects, each with keys: name (str) and stations (list
        of dicts with index, name, latitude, longitude, elevation_km).
    """
    result = []
    for p in sorted(RESOURCES_DIR.glob("*.txt")):
        result.append({"name": p.stem, "stations": _parse_gs_file(p)})
    return JSONResponse(result)


@app.post("/api/project/create")
async def api_project_create(request: Request) -> Dict[str, Any]:
    """Start building a constellation project in a background thread.

    Accepts a JSON body with the following keys:
        name (str): Project name.
        start_date (str): Simulation start in 'DD/MM/YYYY HH:MM:SS' format.
        end_date (str): Simulation end in the same format.
        update_time (str|int): Topology update interval in seconds.
        isl_capacity (str|int): ISL link capacity in Kbps.
        gs_capacity (str|int): Ground-station link capacity in Kbps.
        save_path (str): Optional directory or file path to save the topology.
        walker_shells_json (str): JSON array of WalkerShell dicts.
        ground_objects_properties_json (str): JSON array of ground object dicts.
            Each object may have a 'stations' list instead of 'data_file'.

    Returns:
        JSON object with key 'ok' set to True on successful dispatch, or
        'ok' False and 'error' message on validation failure.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    if app_state.creating:
        return JSONResponse(
            {"ok": False, "error": "A project is already being created."},
            status_code=409,
        )

    thread = threading.Thread(target=_build_topology, args=(payload,), daemon=True)
    thread.start()
    return {"ok": True}


@app.get("/api/project/exists")
async def api_project_exists(name: str) -> Dict[str, Any]:
    """Check whether a named project has finished loading.

    Args:
        name: The project name to check (query parameter).

    Returns:
        JSON object with key 'exists' set to True if the project is loaded.
    """
    exists = (
        app_state.topology_manager is not None
        and app_state.project_name == name
        and not app_state.creating
    )
    return {"exists": exists}


@app.get("/api/project/config")
async def api_project_config(name: str) -> JSONResponse:
    """Return the configuration of the currently loaded project.

    Used by the new_project form when editing an existing project.

    Args:
        name: Project name to retrieve config for (query parameter).

    Returns:
        JSON object with the project configuration, or 404 if not found.
    """
    if app_state.project_name != name or app_state.topology_manager is None:
        return JSONResponse({"error": "Project not found."}, status_code=404)
    tm = app_state.topology_manager
    try:
        cfg = (
            tm.simulation_manager.configuration_manager.simulation_property.model_dump()
        )
    except Exception:
        return JSONResponse(
            {"error": "Could not read project config."}, status_code=500
        )
    return JSONResponse(cfg)


@app.post("/api/project/load")
async def api_project_load(request: Request) -> JSONResponse:
    """Load a topology from an uploaded JSON file.

    Expects a JSON body with a single key 'content' containing the raw
    JSON text of a previously saved topology file (from to_file()).

    Returns:
        JSON object with 'ok' True and 'name' on success, or 'ok' False
        and 'error' on failure.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    content = payload.get("content", "")
    if not content:
        return JSONResponse(
            {"ok": False, "error": "No file content provided."}, status_code=400
        )

    tmp_path = (
        Path(tempfile.gettempdir()) / f"satgonetem_load_{os.urandom(8).hex()}.json"
    )
    tmp_path.write_text(content, encoding="utf-8")
    try:
        tm = await asyncio.to_thread(TopologyManager.from_file, str(tmp_path))
        app_state.topology_manager = tm
        app_state.project_name = tm.project_name or "Loaded Project"
        tm.set_status(True)
        logging.info("Project '%s' loaded from file.", app_state.project_name)
        return JSONResponse({"ok": True, "name": app_state.project_name})
    except Exception as exc:
        logging.exception("Project load failed.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/project/save")
async def api_project_save() -> JSONResponse:
    """Return the currently loaded project as a downloadable JSON string.

    Serialises the active TopologyManager to a temporary file and returns
    its contents so the browser can trigger a client-side download.

    Returns:
        JSON object with 'ok' True, 'content' (raw JSON text), and 'filename'.
        Returns 404 if no project is currently loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    tmp_path = (
        Path(tempfile.gettempdir()) / f"satgonetem_save_{os.urandom(8).hex()}.json"
    )
    try:
        await asyncio.to_thread(tm.to_file, str(tmp_path))
        content = tmp_path.read_text(encoding="utf-8")
        filename = f"{(app_state.project_name or 'project').replace(' ', '_')}.json"
        return JSONResponse({"ok": True, "content": content, "filename": filename})
    except Exception as exc:
        logging.exception("Project save failed.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/satellites")
async def api_satellites() -> JSONResponse:
    """Return all satellites with their current positions.

    Syncs positions from the underlying sat_com_model before serialising.

    Returns:
        JSON array of satellite objects, each with keys:
        id (int), name (str), position (dict with latitude, longitude, altitude).
        Returns 404 if no project is loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    try:
        tm._sync_node_positions()
    except Exception:
        logging.exception("Failed to sync satellite positions.")

    result = []
    for sat in tm.satellites.values():
        result.append(
            {
                "id": sat.id,
                "name": sat.name,
                "position": {
                    "latitude": sat.position.get("latitude"),
                    "longitude": sat.position.get("longitude"),
                    "altitude": sat.position.get("altitude"),
                },
            }
        )
    return JSONResponse(result)


@app.get("/api/ground_stations")
async def api_ground_stations() -> JSONResponse:
    """Return all ground stations with their positions.

    Returns:
        JSON array of ground station objects, each with keys:
        id (int), name (str), city (str|None), position (dict with latitude,
        longitude, altitude). Returns 404 if no project is loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    result = []
    for gs in tm.ground_stations.values():
        result.append(
            {
                "id": gs.id,
                "name": gs.name,
                "city": getattr(gs, "city", None),
                "position": {
                    "latitude": gs.position.get("latitude"),
                    "longitude": gs.position.get("longitude"),
                    "altitude": gs.position.get("altitude"),
                },
            }
        )
    return JSONResponse(result)


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    """Return the current constellation and emulation status.

    Returns:
        JSON object with constellation_loaded, satellites, ground_stations,
        links, gonetem_is_on, simulation_updating, current_step, current_time.
    """
    return app_state.get_status_dict()


@app.get("/api/routing/status")
async def api_routing_status() -> JSONResponse:
    """Return the current routing and addressing status.

    Returns:
        JSON object with gonetem_is_on, addressing_applied,
        routing_initiated, and routing_method.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    tm = app_state.topology_manager
    gonetem_on = tm.get_gonetem_status()
    return JSONResponse(
        {
            "ok": True,
            "gonetem_is_on": gonetem_on,
            "addressing_applied": gonetem_on,
            "routing_initiated": tm.get_routing_initiated(),
            "routing_method": tm.routing,
        }
    )


@app.post("/api/routing/apply")
async def api_routing_apply(request: Request) -> JSONResponse:
    """Apply IP addressing and initialize routing.

    Expects a JSON body with 'method' (str) choosing one of the supported
    routing methods: static, dynamic-ospf, dynamic-isis, sr-mpls.

    Returns:
        JSON object with 'ok' True on success, or 'ok' False and 'error'.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    tm = app_state.topology_manager
    if not tm.get_gonetem_status():
        return JSONResponse(
            {"ok": False, "error": "GoNetEm is not running. Start containers first."},
            status_code=409,
        )

    method = payload.get("method", "static")
    try:
        await asyncio.to_thread(tm.set_ip_addresses)
        await asyncio.to_thread(tm.init_routing, routing_method=method)
    except Exception as exc:
        logging.exception("Failed to apply addressing and routing.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    return JSONResponse({"ok": True})


@app.post("/api/routing/delete")
async def api_routing_delete() -> JSONResponse:
    """Delete all installed routing state.

    Returns:
        JSON object with 'ok' True on success, or 'ok' False and 'error'.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    try:
        await asyncio.to_thread(app_state.topology_manager.delete_routing)
    except Exception as exc:
        logging.exception("Failed to delete routing.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True})


@app.post("/api/gonetem/start")
async def api_gonetem_start() -> JSONResponse:
    """Start the Docker containers via GoNetem.

    Returns:
        JSON object with 'ok' True on success, or 'ok' False and 'error' on failure.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    try:
        await asyncio.to_thread(app_state.topology_manager.start_gonetem)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logging.exception("Failed to start GoNetem.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/gonetem/stop")
async def api_gonetem_stop() -> JSONResponse:
    """Stop the Docker containers via GoNetem.

    Returns:
        JSON object with 'ok' True on success, or 'ok' False and 'error' on failure.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    try:
        tm = app_state.topology_manager
        await asyncio.to_thread(tm.stop_gonetem)
        tm.set_status(True)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logging.exception("Failed to stop GoNetem.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/world", response_class=HTMLResponse)
async def world_page(request: Request) -> HTMLResponse:
    """Render the Cesium world view page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered world template.
    """
    return templates.TemplateResponse(request, "world.html")


@app.get("/api/links")
async def api_links() -> JSONResponse:
    """Return all links with their endpoints, type, and direction.

    Link types are as returned by the topology model:
    - InterSatelliteLink: inter-satellite link; direction is ORBITAL or ADJACENT.
    - GroundStationLink: ground-station-to-satellite link.
    - UserTerminalLink: user-terminal-to-satellite link.

    Returns:
        JSON array of link objects, each with keys: src (str), dst (str),
        type (str), direction (str), distance_km (float).
        Returns 404 if no project is loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    result = []
    for link in tm.links.values():
        result.append(
            {
                "src": link.source.name,
                "dst": link.target.name,
                "type": link.type,
                "direction": link.direction,
                "distance_km": round(link.distance / 1000.0, 2),
            }
        )
    return JSONResponse(result)


@app.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request) -> HTMLResponse:
    """Render the node explorer page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered nodes template.
    """
    return templates.TemplateResponse(request, "nodes.html")


@app.get("/api/nodes")
async def api_nodes() -> JSONResponse:
    """Return all nodes with basic identity and position info.

    Returns:
        JSON array of node objects, each with keys:
        name (str), type (str), id (int), position (dict),
        and city (str|None) for ground stations.
        Returns 404 if no project is loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    try:
        tm._sync_node_positions()
    except Exception:
        logging.exception("Failed to sync node positions.")

    result = []
    for sat in tm.satellites.values():
        result.append(
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
    for gs in tm.ground_stations.values():
        result.append(
            {
                "name": gs.name,
                "type": "ground_station",
                "id": gs.id,
                "city": getattr(gs, "city", None),
                "position": {
                    "latitude": gs.position.get("latitude"),
                    "longitude": gs.position.get("longitude"),
                    "altitude": gs.position.get("altitude"),
                },
            }
        )
    return JSONResponse(result)


@app.get("/api/nodes/{name}")
async def api_node_detail(name: str) -> JSONResponse:
    """Return detailed information for a single node.

    Args:
        name: Node name (e.g. 'Sat0' or 'Gnd0').

    Returns:
        JSON object with name, type, id, position, interfaces,
        loopback, routing_table, and type-specific fields.
        Returns 404 if no project is loaded or node not found.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )

    tm = app_state.topology_manager
    node = tm.get_node_by_name(name)
    if node is None:
        return JSONResponse(
            {"ok": False, "error": f"Node not found: {name}"},
            status_code=404,
        )

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
    loopback_data = {
        "ipv4": getattr(loopback, "ipv4", ""),
    }

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
        "loopback": loopback_data,
        "routing_table": routing_table,
    }

    if name.startswith("Sat"):
        data["default_qos_is_on"] = getattr(node, "default_qos_is_on", False)
        data["program_specific_qos_is_on"] = getattr(
            node, "program_specific_qos_is_on", False
        )
    else:
        data["city"] = getattr(node, "city", None)

    return JSONResponse({"ok": True, "node": data})


@app.get("/traffic", response_class=HTMLResponse)
async def traffic_page(request: Request) -> HTMLResponse:
    """Render the traffic generator page.

    Args:
        request: Incoming HTTP request.

    Returns:
        HTML response with the rendered traffic template.
    """
    return templates.TemplateResponse(request, "traffic.html")


def _clean_numeric(val: Any) -> Any:
    """Convert a scalar value to a JSON-safe number, preserving None.

    Handles pandas/numpy scalar types via ``.item()`` and replaces
    NaN / inf with None so the result is JSON-serialisable.
    """
    if val is None:
        return None
    if hasattr(val, "item"):
        val = val.item()
    if isinstance(val, float):
        if val != val or val == float("inf") or val == float("-inf"):
            return None
        return val
    if isinstance(val, (int, str, bool)):
        return val
    try:
        f = float(val)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except TypeError, ValueError:
        return str(val) if val is not None else None


def _serialize_iperf3_results(result: Any) -> Dict[str, Any]:
    """Extract chart-friendly data from an Iperf3Results object.

    Args:
        result: An Iperf3Results instance.

    Returns:
        Dict with summary metrics and per-interval arrays (including
        per-stream data) so the frontend can plot all available metrics.
    """
    data: Dict[str, Any] = {
        "protocol": result.protocol,
        "duration_seconds": result.duration_seconds,
        "num_streams": result.num_streams,
        "avg_throughput_mbps": result.avg_throughput_mbps,
        "max_throughput_mbps": result.max_throughput_mbps,
        "min_throughput_mbps": result.min_throughput_mbps,
        "pmtu": result.pmtu,
        "intervals": [],
    }
    if result.protocol == "TCP":
        data["total_bytes_sent"] = result.total_bytes_sent
        data["total_bytes_received"] = result.total_bytes_received
        data["total_retransmits"] = result.total_retransmits
        data["avg_rtt_ms"] = result.avg_rtt_ms
        data["max_rtt_ms"] = result.max_rtt_ms
    else:
        data["total_bytes"] = result.total_bytes
        data["total_packets"] = result.total_packets
        data["avg_jitter_ms"] = result.avg_jitter_ms
        data["total_lost_packets"] = result.total_lost_packets
        data["avg_loss_percent"] = result.avg_loss_percent
        data["total_out_of_order"] = result.total_out_of_order

    try:
        raw_intervals = result._data.get("intervals", [])
        for iv in raw_intervals:
            entry: Dict[str, Any] = {"t": 0.0, "sum": {}, "sums": {}, "streams": []}

            # Determine timestamp from the first available aggregate
            t = 0.0
            for key in (
                "sum",
                "sum_received",
                "sum_sent",
                "sum_bidir",
                "sum_bidir_reverse",
            ):
                if key in iv:
                    t = float(iv[key].get("end", iv[key].get("start", 0.0)))
                    break
            if t == 0.0 and iv.get("streams"):
                t = float(
                    iv["streams"][0].get("end", iv["streams"][0].get("start", 0.0))
                )
            entry["t"] = t

            # Store all aggregate objects under "sums"
            for key in (
                "sum",
                "sum_received",
                "sum_sent",
                "sum_bidir",
                "sum_bidir_reverse",
            ):
                if key in iv:
                    entry["sums"][key] = {
                        k: _clean_numeric(v) for k, v in iv[key].items()
                    }

            # Primary aggregate for simple plotting: prefer sum, then sum_received, then sum_sent
            primary = (
                iv.get("sum") or iv.get("sum_received") or iv.get("sum_sent") or {}
            )
            entry["sum"] = {k: _clean_numeric(v) for k, v in primary.items()}

            # Per-stream metrics
            for st in iv.get("streams", []):
                entry["streams"].append({k: _clean_numeric(v) for k, v in st.items()})

            data["intervals"].append(entry)
    except Exception:
        logging.exception("Failed to serialize iperf3 intervals.")
    return data


def _serialize_ping_results(result: Any) -> Dict[str, Any]:
    """Extract data from a PingResults object.

    Args:
        result: A PingResults instance.

    Returns:
        Dict with summary statistics.
    """
    return {
        "packets_transmitted": result.packets_transmitted,
        "packets_received": result.packets_received,
        "packet_loss_percent": result.packet_loss_percent,
        "reachable": result.reachable,
        "rtt_min_ms": result.rtt_min_ms,
        "rtt_avg_ms": result.rtt_avg_ms,
        "rtt_max_ms": result.rtt_max_ms,
        "rtt_mdev_ms": result.rtt_mdev_ms,
    }


def _serialize_hping3_results(result: Any) -> Dict[str, Any]:
    """Extract chart-friendly data from an Hping3Results object.

    Args:
        result: An Hping3Results instance.

    Returns:
        Dict with per-packet arrays and summary statistics.
    """
    return {
        "payload_bytes": result.payload_bytes,
        "seq": result.seq,
        "rtt_ms": [
            None if (isinstance(v, float) and v != v) else v for v in result.rtt_ms
        ],
        "cumulative_mbit": result.cumulative_mbit,
        "packets_transmitted": result.packets_transmitted,
        "packets_received": result.packets_received,
        "packet_loss_percent": result.packet_loss_percent,
        "rtt_min_ms": result.rtt_min_ms,
        "rtt_avg_ms": result.rtt_avg_ms,
        "rtt_max_ms": result.rtt_max_ms,
        "reachable": result.reachable,
    }


@app.get("/api/traffic/nodes")
async def api_traffic_nodes() -> JSONResponse:
    """Return all nodes that can be used as traffic endpoints.

    Returns:
        JSON object with 'ok' True and a 'nodes' list containing name and type.
        Returns 404 if no project is loaded.
    """
    if app_state.topology_manager is None:
        return JSONResponse(
            {"ok": False, "error": "No project is currently loaded."},
            status_code=404,
        )
    tm = app_state.topology_manager
    nodes = []
    for sat in tm.satellites.values():
        nodes.append({"name": sat.name, "type": "satellite"})
    for gs in tm.ground_stations.values():
        nodes.append({"name": gs.name, "type": "ground_station"})
    return JSONResponse({"ok": True, "nodes": nodes})


@app.post("/api/traffic/iperf3")
async def api_traffic_iperf3(request: Request) -> JSONResponse:
    """Start an iperf3 flow between two nodes.

    Accepts a JSON body with keys: src (str), dst (str), protocol (str),
    duration (int), bandwidth_mbps (float), parallel (int), interval (float),
    port (int), congestion_control (str), window_size (str), bidir (bool).

    Returns:
        JSON object with 'ok' True and 'job_id' on success.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    tm = app_state.topology_manager
    if tm is None:
        return JSONResponse(
            {"ok": False, "error": "No project loaded."}, status_code=404
        )
    if not tm.get_gonetem_status():
        return JSONResponse(
            {"ok": False, "error": "GoNetEm is not running."}, status_code=409
        )

    src_name = payload.get("src", "")
    dst_name = payload.get("dst", "")
    src = tm.get_node_by_name(src_name)
    dst = tm.get_node_by_name(dst_name)
    if src is None or dst is None:
        return JSONResponse(
            {"ok": False, "error": f"Node not found: {src_name} or {dst_name}"},
            status_code=404,
        )

    config = Iperf3Config(
        protocol=payload.get("protocol", "TCP"),
        duration=int(payload.get("duration", 10)),
        bandwidth_mbps=float(payload.get("bandwidth_mbps", 0.0)),
        parallel=int(payload.get("parallel", 1)),
        interval=float(payload.get("interval", 1.0)),
        port=int(payload.get("port", 5201)),
        congestion_control=payload.get("congestion_control", "bbr"),
        window_size=payload.get("window_size") or None,
        bidir=bool(payload.get("bidir", False)),
    )

    try:
        flow = Iperf3Flow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start iperf3 flow.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "iperf3",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": src_name,
            "dst": dst_name,
        }
    return JSONResponse({"ok": True, "job_id": job_id})


@app.post("/api/traffic/ping")
async def api_traffic_ping(request: Request) -> JSONResponse:
    """Start a ping flow between two nodes.

    Accepts a JSON body with keys: src (str), dst (str), count (int),
    timeout_sec (float), interval_sec (float), packet_size (int).

    Returns:
        JSON object with 'ok' True and 'job_id' on success.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    tm = app_state.topology_manager
    if tm is None:
        return JSONResponse(
            {"ok": False, "error": "No project loaded."}, status_code=404
        )
    if not tm.get_gonetem_status():
        return JSONResponse(
            {"ok": False, "error": "GoNetEm is not running."}, status_code=409
        )

    src_name = payload.get("src", "")
    dst_name = payload.get("dst", "")
    src = tm.get_node_by_name(src_name)
    dst = tm.get_node_by_name(dst_name)
    if src is None or dst is None:
        return JSONResponse(
            {"ok": False, "error": f"Node not found: {src_name} or {dst_name}"},
            status_code=404,
        )

    config = PingConfig(
        count=int(payload.get("count", 5)),
        timeout_sec=float(payload.get("timeout_sec", 0.5)),
        interval_sec=float(payload.get("interval_sec", 0.2)),
        packet_size=int(payload.get("packet_size", 56)),
    )

    try:
        flow = PingFlow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start ping flow.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "ping",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": src_name,
            "dst": dst_name,
        }
    return JSONResponse({"ok": True, "job_id": job_id})


@app.post("/api/traffic/hping3")
async def api_traffic_hping3(request: Request) -> JSONResponse:
    """Start an hping3 flow between two nodes.

    Accepts a JSON body with keys: src (str), dst (str), proto (str),
    dport (int), count (int), size (int), rate_type (str), interval (str),
    flags (list[str]).

    Returns:
        JSON object with 'ok' True and 'job_id' on success.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    tm = app_state.topology_manager
    if tm is None:
        return JSONResponse(
            {"ok": False, "error": "No project loaded."}, status_code=404
        )
    if not tm.get_gonetem_status():
        return JSONResponse(
            {"ok": False, "error": "GoNetEm is not running."}, status_code=409
        )

    src_name = payload.get("src", "")
    dst_name = payload.get("dst", "")
    src = tm.get_node_by_name(src_name)
    dst = tm.get_node_by_name(dst_name)
    if src is None or dst is None:
        return JSONResponse(
            {"ok": False, "error": f"Node not found: {src_name} or {dst_name}"},
            status_code=404,
        )

    config = Hping3Config(
        proto=payload.get("proto", "tcp"),
        dport=int(payload.get("dport", 0)),
        count=int(payload.get("count", 100)),
        size=int(payload.get("size", 0)),
        rate_type=payload.get("rate_type", "interval"),
        interval=payload.get("interval", ""),
        flags=payload.get("flags", []),
    )

    try:
        flow = Hping3Flow(src, dst, config, delay=0.0)
        flow.start()
    except Exception as exc:
        logging.exception("Failed to start hping3 flow.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    job_id = f"j{os.urandom(8).hex()}"
    with app_state.jobs_lock:
        app_state.jobs[job_id] = {
            "kind": "hping3",
            "flow": flow,
            "status": "running",
            "results": None,
            "error": None,
            "src": src_name,
            "dst": dst_name,
        }
    return JSONResponse({"ok": True, "job_id": job_id})


@app.get("/api/traffic/status")
async def api_traffic_status(job_id: str) -> JSONResponse:
    """Poll the status of a traffic job.

    Args:
        job_id: The job identifier returned by the start endpoint.

    Returns:
        JSON object with 'status' ('running', 'done', 'error', 'cancelled')
        and result data when finished.
    """
    with app_state.jobs_lock:
        job = app_state.jobs.get(job_id)
    if job is None:
        return JSONResponse({"ok": False, "error": "Job not found."}, status_code=404)

    flow = job["flow"]
    kind = job["kind"]

    try:
        if kind == "iperf3":
            st = flow.status()
            if st == FlowStatus.RUNNING:
                return JSONResponse({"ok": True, "status": "running"})
            elif st == FlowStatus.DONE:
                result = flow.results()
                job["results"] = _serialize_iperf3_results(result)
                job["status"] = "done"
                return JSONResponse(
                    {"ok": True, "status": "done", "results": job["results"]}
                )
            elif st == FlowStatus.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return JSONResponse(
                    {
                        "ok": True,
                        "status": "error",
                        "error": job.get("error", "Unknown error."),
                    }
                )
        elif kind == "ping":
            st = flow.status()
            if st == PingStatus.RUNNING:
                return JSONResponse({"ok": True, "status": "running"})
            elif st == PingStatus.DONE:
                result = flow.results()
                job["results"] = _serialize_ping_results(result)
                job["status"] = "done"
                return JSONResponse(
                    {"ok": True, "status": "done", "results": job["results"]}
                )
            elif st == PingStatus.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return JSONResponse(
                    {
                        "ok": True,
                        "status": "error",
                        "error": job.get("error", "Unknown error."),
                    }
                )
        elif kind == "hping3":
            st = flow.status()
            if st == Hping3Status.RUNNING:
                return JSONResponse({"ok": True, "status": "running"})
            elif st == Hping3Status.DONE:
                result = flow.results()
                job["results"] = _serialize_hping3_results(result)
                job["status"] = "done"
                return JSONResponse(
                    {"ok": True, "status": "done", "results": job["results"]}
                )
            elif st == Hping3Status.ERROR:
                job["status"] = "error"
                try:
                    _ = flow.results()
                except Exception as exc:
                    job["error"] = str(exc)
                return JSONResponse(
                    {
                        "ok": True,
                        "status": "error",
                        "error": job.get("error", "Unknown error."),
                    }
                )
    except Exception as exc:
        logging.exception("Error polling traffic job status.")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    return JSONResponse({"ok": True, "status": job.get("status", "unknown")})


@app.post("/api/traffic/cancel")
async def api_traffic_cancel(request: Request) -> JSONResponse:
    """Cancel a running traffic job.

    Expects a JSON body with 'job_id'.

    Returns:
        JSON object with 'ok' True if the job was marked cancelled.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    job_id = payload.get("job_id", "")
    with app_state.jobs_lock:
        job = app_state.jobs.get(job_id)
    if job is None:
        return JSONResponse({"ok": False, "error": "Job not found."}, status_code=404)

    job["status"] = "cancelled"
    return JSONResponse({"ok": True})
