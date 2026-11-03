"""Security lab orchestration: range state, link failure, reset, and capture."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..errors import APIError
from ..schemas import CaptureStartRequest
from .ports import NetworkOperationError, SecurityGateway
from .project_service import ProjectService
from .routing_service import RoutingService
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

CAPTURE_TTL_SECONDS = 3600.0
MAX_CAPTURE_BYTES = 5 * 1024 * 1024


@dataclass
class CaptureState:
    """Internal capture record; the path never leaves the server."""

    capture_id: str
    node: str
    interface: str
    path: str
    packet_limit: int
    duration_sec: int
    status: str = "capturing"
    size_bytes: int = 0
    created_at: float = field(default_factory=time.time)

    def view(self) -> dict[str, Any]:
        """Return the API-shaped view of this capture."""
        return {
            "id": self.capture_id,
            "node": self.node,
            "interface": self.interface,
            "status": self.status,
            "packet_limit": self.packet_limit,
            "duration_sec": self.duration_sec,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "download_url": (
                f"/api/security/captures/{self.capture_id}"
                if self.status == "ready"
                else None
            ),
        }


class SecurityService:
    """Coordinate the five SatSec labs without exposing arbitrary commands."""

    def __init__(
        self,
        topology: TopologyService,
        routing: RoutingService,
        project: ProjectService,
        gateway: SecurityGateway,
    ) -> None:
        self.topology = topology
        self.routing = routing
        self.project = project
        self.gateway = gateway
        self._snapshot: str | None = None
        self._failed_links: list[str] = []
        self._captures: dict[str, CaptureState] = {}

    def range(self) -> dict[str, Any]:
        """Return readiness, addressable targets, links, and captures."""
        if not self.topology.session.loaded:
            return {
                "project_name": None,
                "readiness": {
                    "project_loaded": False,
                    "gonetem_is_on": False,
                    "addressing_applied": False,
                    "routing_initiated": False,
                    "routing_method": None,
                },
                "nodes": [],
                "links": [],
                "routing_methods": [],
                "captures": [],
                "failed_links": [],
                "snapshot_available": False,
            }
        topology = self.topology.require_topology()
        status = self.topology.status()
        routing = self.routing.status()
        links = self.topology.links()
        nodes = self.topology.traffic_nodes()
        self._refresh_captures()
        return {
            "project_name": self.project.current_name,
            "readiness": {
                "project_loaded": bool(status.get("constellation_loaded")),
                "gonetem_is_on": bool(status.get("gonetem_is_on")),
                "addressing_applied": bool(routing.get("addressing_applied")),
                "routing_initiated": bool(routing.get("routing_initiated")),
                "routing_method": routing.get("routing_method"),
            },
            "nodes": nodes,
            "links": links,
            "routing_methods": self.gateway.routing_methods(topology),
            "captures": [capture.view() for capture in self._captures.values()],
            "failed_links": list(self._failed_links),
            "snapshot_available": self._snapshot is not None,
        }

    def fail_link(self, key: str) -> dict[str, Any]:
        """Snapshot the range and fail one link."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        if key in self._failed_links:
            raise APIError(409, "This link has already been failed.")
        self._ensure_snapshot()
        try:
            result = self.gateway.fail_link(topology, key)
        except KeyError as exc:
            raise APIError(404, f"Link not found: {key}") from exc
        except NetworkOperationError as exc:
            logger.exception("Could not fail link.")
            raise APIError(500, str(exc)) from exc
        self._failed_links.append(key)
        return result

    async def reset(self) -> dict[str, Any]:
        """Restore the pre-lab project snapshot and container state."""
        if self._snapshot is None:
            raise APIError(409, "No security snapshot is available.")
        self.topology.require_topology()
        routing_status = self.routing.status()
        method = routing_status.get("routing_method") or "static"
        was_running = self.topology.gonetem_is_on()

        if was_running:
            await self.routing.stop_gonetem()
        await self.project.load(self._snapshot)
        if was_running:
            await self.routing.start_gonetem()
            await self.routing.apply(method)

        self._failed_links.clear()
        self._captures.clear()
        return {"restored": True, "containers_restarted": was_running}

    def start_capture(self, request: CaptureStartRequest) -> dict[str, Any]:
        """Start a bounded packet capture on one node interface."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        self._ensure_snapshot()
        try:
            started = self.gateway.start_capture(
                topology,
                request.node,
                request.interface,
                request.packet_limit,
                request.duration_sec,
            )
        except ValueError as exc:
            raise APIError(404, str(exc)) from exc
        except NetworkOperationError as exc:
            logger.exception("Could not start capture.")
            raise APIError(500, str(exc)) from exc

        capture = CaptureState(
            capture_id=f"cap-{uuid.uuid4().hex[:10]}",
            node=request.node,
            interface=started.get("interface", request.interface),
            path=started["path"],
            packet_limit=request.packet_limit,
            duration_sec=request.duration_sec,
        )
        self._captures[capture.capture_id] = capture
        return capture.view()

    def list_captures(self) -> list[dict[str, Any]]:
        """Return tracked captures and refresh their status."""
        if not self.topology.session.loaded:
            return []
        self._refresh_captures()
        return [capture.view() for capture in self._captures.values()]

    def stop_capture(self, capture_id: str) -> dict[str, Any]:
        """Stop a capture and mark it ready for download."""
        capture = self._capture(capture_id)
        if capture.status != "capturing":
            return capture.view()
        topology = self.topology.require_topology()
        try:
            self.gateway.stop_capture(topology, capture.node, capture.path)
        except NetworkOperationError as exc:
            logger.exception("Could not stop capture.")
            raise APIError(500, str(exc)) from exc
        self._update_capture(capture)
        capture.status = "ready"
        return capture.view()

    def capture_bytes(self, capture_id: str) -> tuple[bytes, str]:
        """Return a capture payload and download filename."""
        capture = self._capture(capture_id)
        self._update_capture(capture)
        if capture.status != "ready":
            raise APIError(409, "Capture is still running.")
        topology = self.topology.require_topology()
        try:
            payload = self.gateway.read_capture(topology, capture.node, capture.path)
        except NetworkOperationError as exc:
            logger.exception("Could not read capture.")
            raise APIError(500, str(exc)) from exc
        if len(payload) > MAX_CAPTURE_BYTES:
            raise APIError(413, "Capture is too large to download.")
        return payload, f"{capture.capture_id}.pcap"

    def _ensure_snapshot(self) -> None:
        if self._snapshot is None:
            self._snapshot = self.project.snapshot()

    def _capture(self, capture_id: str) -> CaptureState:
        capture = self._captures.get(capture_id)
        if capture is None:
            raise APIError(404, "Capture not found.")
        return capture

    def _refresh_captures(self) -> None:
        topology = self.topology.require_topology()
        now = time.time()
        for capture_id, capture in list(self._captures.items()):
            if capture.status == "capturing":
                self._update_capture(capture)
                elapsed = now - capture.created_at
                if elapsed >= capture.duration_sec and not capture.status == "error":
                    capture.status = "ready"
            if (
                capture.status == "ready"
                and now - capture.created_at > CAPTURE_TTL_SECONDS
            ):
                try:
                    self.gateway.delete_capture(topology, capture.node, capture.path)
                except Exception:
                    logger.exception("Could not remove expired capture.")
                self._captures.pop(capture_id, None)

    def _update_capture(self, capture: CaptureState) -> None:
        topology = self.topology.require_topology()
        try:
            status = self.gateway.capture_status(
                topology, capture.node, capture.path
            )
        except NetworkOperationError:
            logger.exception("Could not refresh capture status.")
            capture.status = "error"
            return
        capture.size_bytes = int(status.get("size_bytes", 0) or 0)
        if not status.get("running") and capture.size_bytes > 0:
            capture.status = "ready"
