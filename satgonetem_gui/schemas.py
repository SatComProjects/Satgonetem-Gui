"""Pydantic request and response schemas for the JSON API."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorResponse(BaseModel):
    """Common error envelope for every failed API request."""

    ok: Literal[False] = False
    error: str
    details: Any | None = None


class Position(BaseModel):
    """Geodetic position returned by topology endpoints."""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None


class GroundStationPoint(BaseModel):
    """One row from a ground-station CSV file."""

    index: int
    name: str
    latitude: float
    longitude: float
    elevation_km: float


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

    name: str = Field(min_length=1)
    start_date: str = Field(min_length=1)
    end_date: str = Field(min_length=1)
    update_time: int = 5
    isl_capacity: int = 100000
    gs_capacity: int = 100000
    save_path: str = ""
    walker_shells_json: str = Field(min_length=1)
    ground_objects_properties_json: str = Field(min_length=1)

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

    content: str = Field(min_length=1)


class ProjectStatusResponse(BaseModel):
    """Explicit project lifecycle snapshot."""

    state: str
    operation: str | None = None
    project_name: str | None = None
    pending_name: str | None = None
    loaded: bool
    error: str | None = None


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


class SatelliteResponse(BaseModel):
    """Satellite identity and position."""

    id: int
    name: str
    position: Position


class GroundStationResponse(BaseModel):
    """Ground-station identity and position."""

    id: int
    name: str
    city: str | None = None
    position: Position


class LinkResponse(BaseModel):
    """One topology link."""

    src: str
    dst: str
    type: str
    direction: str
    distance_km: float


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


class RoutingStatusResponse(BaseModel):
    """Routing and container status."""

    ok: bool = True
    gonetem_is_on: bool
    addressing_applied: bool
    routing_initiated: bool
    routing_method: str | None = None


class RoutingApplyRequest(BaseModel):
    """Requested routing method."""

    method: str = "static"


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
    protocol: str = "TCP"
    duration: int = 10
    bandwidth_mbps: float = 0.0
    parallel: int = 1
    interval: float = 1.0
    port: int = 5201
    congestion_control: str = "bbr"
    window_size: str | None = None
    bidir: bool = False


class PingRequest(BaseModel):
    """ping flow configuration."""

    model_config = ConfigDict(extra="ignore")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    count: int = 5
    timeout_sec: float = 0.5
    interval_sec: float = 0.2
    packet_size: int = 56


class Hping3Request(BaseModel):
    """hping3 flow configuration."""

    model_config = ConfigDict(extra="ignore")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    proto: str = "tcp"
    dport: int = 0
    count: int = 100
    size: int = 0
    rate_type: str = "interval"
    interval: str = ""
    flags: list[str] = Field(default_factory=list)
