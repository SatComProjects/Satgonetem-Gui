"""Pydantic request and response schemas for the JSON API."""

import ipaddress
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

    key: str
    src: str
    dst: str
    type: str
    direction: str
    distance_km: float
    capacity_kbps: int = 0
    delay_ms: int = 0
    state: str = "unknown"


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
    proto: Literal["tcp", "udp", "icmp"] = "tcp"
    dport: int = Field(default=0, ge=0, le=65535)
    sport: int | None = Field(default=None, ge=1, le=65535)
    count: int = Field(default=100, ge=1, le=1_000_000)
    size: int = Field(default=0, ge=0, le=65507)
    ttl: int | None = Field(default=None, ge=1, le=255)
    rate_type: Literal["interval", "fast", "faster", "flood"] = "interval"
    interval: str = ""
    flags: list[str] = Field(default_factory=list)
    spoof_src: str | None = None

    @field_validator("flags")
    @classmethod
    def _validate_flags(cls, value: list[str]) -> list[str]:
        """Accept only the TCP flag letters supported by hping3."""
        allowed = {"S", "A", "F", "R", "P", "U"}
        invalid = [flag for flag in value if flag not in allowed]
        if invalid:
            raise ValueError(f"unsupported TCP flags: {invalid}")
        return value

    @field_validator("spoof_src")
    @classmethod
    def _validate_spoof_src(cls, value: str | None) -> str | None:
        """Reject a spoofed source unless it is a valid IPv4 address."""
        if value is None or not value.strip():
            return None
        try:
            ipaddress.IPv4Address(value.strip())
        except ValueError as exc:
            raise ValueError("spoof_src must be a valid IPv4 address") from exc
        return value.strip()


class SecurityNode(BaseModel):
    """An addressable node exposed by the security lab."""

    name: str
    type: str
    label: str


class SecurityLink(BaseModel):
    """A security-relevant link with its capacity and state."""

    key: str
    src: str
    dst: str
    type: str
    direction: str
    distance_km: float
    capacity_kbps: int = 0
    delay_ms: int = 0
    state: str = "unknown"


class SecurityReadiness(BaseModel):
    """Whether the range is ready for a lab action."""

    project_loaded: bool
    gonetem_is_on: bool
    addressing_applied: bool
    routing_initiated: bool
    routing_method: str | None = None


class SecurityCapture(BaseModel):
    """One packet capture managed by the security lab."""

    id: str
    node: str
    interface: str
    status: str
    packet_limit: int
    duration_sec: int
    size_bytes: int = 0
    created_at: float
    download_url: str | None = None


class SecurityRangeResponse(BaseModel):
    """Readiness, targets, links, and captures for the security page."""

    ok: bool = True
    project_name: str | None = None
    readiness: SecurityReadiness
    nodes: list[SecurityNode] = Field(default_factory=list)
    links: list[SecurityLink] = Field(default_factory=list)
    routing_methods: list[str] = Field(default_factory=list)
    captures: list[SecurityCapture] = Field(default_factory=list)
    failed_links: list[str] = Field(default_factory=list)
    snapshot_available: bool = False


class CaptureStartRequest(BaseModel):
    """Start a packet capture on one node interface."""

    node: str = Field(min_length=1)
    interface: str = Field(min_length=1)
    packet_limit: int = Field(default=200, ge=1, le=1000)
    duration_sec: int = Field(default=15, ge=1, le=60)
