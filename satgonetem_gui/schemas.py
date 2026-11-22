"""Pydantic request and response schemas for the JSON API."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorResponse(BaseModel):
    """Common error envelope for every failed API request."""

    ok: Literal[False] = False
    error: str
    details: Any | None = None


def error_responses(*statuses: int) -> dict[int, dict[str, Any]]:
    """Build OpenAPI response declarations for the shared error envelope."""
    return {status: {"model": ErrorResponse} for status in statuses}


class Position(BaseModel):
    """Geodetic position returned by topology endpoints."""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None


class GroundStationPoint(BaseModel):
    """One row from a ground-station CSV file."""

    index: int = Field(ge=0)
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float = Field(ge=-1000, le=100_000)


class GroundStationPreset(BaseModel):
    """A named ground-station preset file."""

    name: str
    stations: list[GroundStationPoint]


class OperationResponse(BaseModel):
    """Generic success response for mutations."""

    ok: bool = True


class ProjectCreateRequest(BaseModel):
    """Form payload for creating a constellation project."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=128)
    start_date: str = Field(min_length=1, max_length=64)
    end_date: str = Field(min_length=1, max_length=64)
    update_time: int = Field(default=5, ge=1)
    isl_capacity: int = Field(default=100000, ge=1)
    gs_capacity: int = Field(default=100000, ge=1)
    save_path: str = Field(default="", max_length=4096)
    walker_shells_json: str = Field(min_length=1, max_length=2_000_000)
    ground_objects_properties_json: str = Field(
        min_length=1, max_length=2_000_000
    )

    @field_validator("walker_shells_json", "ground_objects_properties_json")
    @classmethod
    def _validate_json_array(cls, value: str) -> str:
        """Reject malformed JSON embedded in the form's hidden fields."""
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("must be valid JSON") from exc
        if not isinstance(parsed, list):
            raise ValueError("must be a JSON array")
        return value


class ProjectLoadRequest(BaseModel):
    """Raw saved-project JSON uploaded by the browser."""

    content: str = Field(min_length=1, max_length=10_000_000)


class ProjectStatusResponse(BaseModel):
    """Explicit project lifecycle snapshot with honest phase progress."""

    state: str
    operation: str | None = None
    project_name: str | None = None
    pending_name: str | None = None
    loaded: bool
    error: str | None = None
    phase: str | None = None
    progress: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_ms: int | None = None


class ProjectExistsResponse(BaseModel):
    """Result of the create-page existence poll."""

    exists: bool


class ProjectConfigResponse(BaseModel):
    """Editable project configuration returned to the New Project form."""

    model_config = ConfigDict(extra="allow")

    name: str
    simulation_name: str | None = None
    start_date: str
    end_date: str
    update_time: int
    isl_capacity: int
    gs_capacity: int
    save_path: str
    walker_shells: list[dict[str, Any]]
    ground_objects_properties: list[dict[str, Any]]


class ProjectLoadedResponse(BaseModel):
    """Successful project load response."""

    ok: bool = True
    name: str


class ProjectSaveResponse(BaseModel):
    """Downloadable project JSON response."""

    ok: bool = True
    content: str
    filename: str


class ProjectSummary(BaseModel):
    """One project file in the workspace catalog."""

    id: str
    name: str
    filename: str
    modified_at: str
    size_bytes: int
    satellites: int | None = None
    ground_stations: int | None = None
    shells: int | None = None
    valid: bool


class ProjectListResponse(BaseModel):
    """Workspace catalog listing with non-fatal file warnings."""

    ok: bool = True
    projects: list[ProjectSummary]
    warnings: list[str] = Field(default_factory=list)


class ProjectSaveToRequest(BaseModel):
    """Save the loaded project into the workspace under a new name."""

    name: str = Field(min_length=1, max_length=128)
    overwrite: bool = False


class ProjectDuplicateRequest(BaseModel):
    """Duplicate a workspace project under a new name."""

    name: str = Field(min_length=1, max_length=128)


class ProjectSavedResponse(BaseModel):
    """Result of a workspace save or duplicate."""

    ok: bool = True
    id: str
    name: str
    filename: str
    overwritten: bool = False


class SatelliteResponse(BaseModel):
    """Satellite identity and position."""

    id: int
    name: str
    position: Position


class SatelliteAddressabilityResponse(BaseModel):
    """Satellites currently exposed as traffic endpoints."""

    ok: bool = True
    addressable: list[str]
    count: int
    total: int
    routing_refresh_required: bool = False


class AddressabilityUpdateRequest(BaseModel):
    """Requested addressability state for all or one satellite."""

    enabled: bool


class AddressabilityUpdateResponse(BaseModel):
    """Result of an addressability mutation."""

    ok: bool = True
    name: str | None = None
    addressable: bool | None = None
    enabled: bool
    updated: int
    routing_refresh_required: bool = False


class GroundStationResponse(BaseModel):
    """Ground-station identity and position."""

    id: int
    name: str
    city: str | None = None
    position: Position


class LinkResponse(BaseModel):
    """One topology link and its current metric snapshot."""

    src: str
    dst: str
    type: str
    direction: str
    distance_km: float
    delay_ms: float
    capacity_kbps: int
    is_active: bool


class LinkUsageEntry(BaseModel):
    """One sampled link's bandwidth usage and nominal capacity."""

    src: str
    dst: str
    type: str | None = None
    value_bps: int
    capacity_kbps: int | None = None
    utilization: float | None = None


class LinkUsageResponse(BaseModel):
    """Live link usage sample, or a safe unavailable state."""

    ok: bool = True
    available: bool
    sampled_at: str | None = None
    links: list[LinkUsageEntry]
    note: str | None = None


class StatusResponse(BaseModel):
    """Dashboard status snapshot."""

    constellation_loaded: bool
    satellites: int
    ground_stations: int
    links: int
    gonetem_is_on: bool
    simulation_updating: bool
    current_step: int | None = None
    current_time: str | None = None
    total_steps: int | None = None
    simulation_rate: float | None = None
    last_simulation_error: str | None = None


class SimulationSpeedRequest(BaseModel):
    """Playback direction for the simulation loop."""

    direction: Literal["faster", "slower"]


class SimulationSeekRequest(BaseModel):
    """Absolute step target for the simulation clock."""

    step: int = Field(ge=0)


class RoutingStatusResponse(BaseModel):
    """Routing and container status."""

    ok: bool = True
    gonetem_is_on: bool
    addressing_applied: bool
    routing_initiated: bool
    routing_method: str | None = None


class PathHop(BaseModel):
    """One hop of a diagnostic path over the current routing graph."""

    source: str
    target: str
    type: str | None
    direction: str | None
    distance_km: float
    delay_ms: float
    cumulative_distance_km: float
    cumulative_delay_ms: float


class RoutingPathResponse(BaseModel):
    """Diagnostic hop-by-hop path; not the live forwarding table."""

    ok: bool = True
    src: str
    dst: str
    found: bool
    hops: list[PathHop]
    node_count: int
    total_distance_km: float
    total_delay_ms: float
    routing_method: str | None = None
    routing_initiated: bool
    preference: str | None = None
    path_source: Literal["routing_graph"] = "routing_graph"
    note: str


class RoutingApplyRequest(BaseModel):
    """Requested routing method."""

    method: Literal[
        "static",
        "dynamic-ospf",
        "dynamic-isis",
        "sr-mpls",
    ] = "static"


class LoopbackInfo(BaseModel):
    """Loopback addressing for a node."""

    ipv4: str = ""


class InterfaceInfo(BaseModel):
    """One node interface."""

    name: str
    iname: str
    ipv4: str | None = None
    type: str | None = None
    is_active: bool = False
    peer_name: str = ""


class NodeDetail(BaseModel):
    """Detailed node information for the explorer."""

    name: str
    type: str
    id: int
    position: Position
    interfaces: list[InterfaceInfo]
    loopback: LoopbackInfo
    routing_table: list[str]
    city: str | None = None
    default_qos_is_on: bool | None = None
    program_specific_qos_is_on: bool | None = None
    addressable: bool | None = None


class NodeDetailResponse(BaseModel):
    """Envelope for one node detail response."""

    ok: bool = True
    node: NodeDetail


class NodeSummary(BaseModel):
    """Node list entry."""

    name: str
    type: str
    id: int
    city: str | None = None
    position: Position


class TrafficNode(BaseModel):
    """Traffic source or destination."""

    name: str
    type: str
    label: str


class TrafficNodesResponse(BaseModel):
    """Traffic endpoint list."""

    ok: bool = True
    nodes: list[TrafficNode]


class TrafficStartResponse(BaseModel):
    """Started traffic job."""

    ok: bool = True
    job_id: str


class TrafficStatusResponse(BaseModel):
    """Polled traffic job state."""

    ok: bool = True
    status: str
    results: dict[str, Any] | None = None
    error: str | None = None


class TrafficCancelRequest(BaseModel):
    """Job cancellation request."""

    job_id: str = Field(min_length=1)


class Iperf3Request(BaseModel):
    """iperf3 flow configuration."""

    model_config = ConfigDict(extra="ignore")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    protocol: Literal["TCP", "UDP"] = "TCP"
    duration: int = Field(default=10, ge=1, le=3600)
    bandwidth_mbps: float = Field(default=0.0, ge=0)
    parallel: int = Field(default=1, ge=1, le=64)
    interval: float = Field(default=1.0, ge=0.1, le=60)
    port: int = Field(default=5201, ge=1, le=65535)
    congestion_control: str = Field(default="bbr", pattern=r"^[a-z0-9_-]{0,32}$")
    window_size: str | None = Field(default=None, pattern=r"^(?:\d+[KMG]?)?$")
    bidir: bool = False


class PingRequest(BaseModel):
    """ping flow configuration."""

    model_config = ConfigDict(extra="ignore")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    count: int = Field(default=5, ge=1, le=10000)
    timeout_sec: float = Field(default=0.5, gt=0, le=60)
    interval_sec: float = Field(default=0.2, gt=0.002, le=60)
    packet_size: int = Field(default=56, ge=1, le=65500)


class Hping3Request(BaseModel):
    """hping3 flow configuration."""

    model_config = ConfigDict(extra="ignore")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    proto: Literal["tcp", "udp", "icmp"] = "tcp"
    dport: int = Field(default=0, ge=0, le=65535)
    count: int = Field(default=100, ge=1, le=10000)
    size: int = Field(default=0, ge=0, le=65500)
    rate_type: Literal["interval", "fast", "faster"] = "interval"
    interval: str = Field(default="", pattern=r"^(?:u?\d+)?$")
    flags: list[str] = Field(default_factory=list, max_length=6)


class PreflightRequest(BaseModel):
    """Optional project configuration to estimate before building."""

    model_config = ConfigDict(extra="ignore")

    walker_shells_json: str | None = Field(default=None, max_length=2_000_000)
    ground_objects_properties_json: str | None = Field(
        default=None, max_length=2_000_000
    )


class PreflightCheck(BaseModel):
    """One environment check reported by the preflight doctor."""

    id: str
    label: str
    status: Literal["ok", "warning", "error", "unknown"]
    message: str
    hint: str | None = None


class ProjectEstimate(BaseModel):
    """Rough container and memory estimate for a submitted project."""

    satellites: int
    ground_stations: int
    containers: int
    estimated_memory_mb: int
    note: str
    warnings: list[str] = Field(default_factory=list)


class PreflightResponse(BaseModel):
    """Environment readiness and an optional project size estimate."""

    ok: bool
    blocking: bool
    checks: list[PreflightCheck]
    estimate: ProjectEstimate | None = None
