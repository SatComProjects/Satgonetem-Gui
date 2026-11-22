"""Satellite addressability orchestration."""

import logging
import re
from contextlib import contextmanager
from typing import Any

from ..errors import APIError
from .ports import AddressabilityController, NetworkOperationError
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

_SATELLITE_NAME_RE = re.compile(r"^Sat\d+$")


class AddressabilityService:
    """Expose and change which satellites can be traffic endpoints."""

    def __init__(
        self,
        topology: TopologyService,
        controller: AddressabilityController,
    ) -> None:
        self.topology = topology
        self.controller = controller

    def status(self) -> dict[str, Any]:
        """Return the addressable satellites and the routing-refresh flag."""
        topology, _generation = self.topology.context()
        state = self.controller.satellite_addressability(topology)
        addressable = state["addressable"]
        return {
            "ok": True,
            "addressable": addressable,
            "count": len(addressable),
            "total": state["total"],
            "routing_refresh_required": self.topology.addressing_applied,
        }

    def set_all(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable addressability for every satellite."""
        return self._set(enabled, None)

    def set_one(self, name: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable addressability for one satellite."""
        if not _SATELLITE_NAME_RE.fullmatch(name):
            raise APIError(404, f"Satellite not found: {name}")
        return self._set(enabled, name)

    def _require_current_project(self, generation: int) -> None:
        """Reject a completed mutation whose project was replaced mid-flight."""
        if self.topology.generation != generation:
            raise APIError(
                409,
                "Project changed during the addressability operation. Retry on "
                "the current project.",
            )

    @contextmanager
    def _network_operation(self):
        """Reserve the session's network slot for one mutation."""
        if not self.topology.session.begin_network_operation():
            raise APIError(
                409,
                "A project operation is already running.",
            )
        try:
            yield
        finally:
            self.topology.session.end_network_operation()

    def _set(self, enabled: bool, name: str | None) -> dict[str, Any]:
        """Run one mutation behind the session and generation guards."""
        topology, generation = self.topology.context()
        with self._network_operation():
            try:
                updated = self.controller.set_satellites_addressable(
                    topology,
                    enabled,
                    None if name is None else [name],
                )
                self._require_current_project(generation)
                routing_refresh_required = self.topology.addressing_applied
            except APIError:
                raise
            except NetworkOperationError as exc:
                logger.exception("Satellite addressability update failed.")
                raise APIError(500, str(exc)) from exc
            except ValueError as exc:
                if name is not None:
                    raise APIError(404, str(exc)) from exc
                logger.exception("Satellite addressability update failed.")
                raise APIError(
                    500,
                    "Failed to update satellite addressability.",
                ) from exc
            except Exception as exc:
                logger.exception("Satellite addressability update failed.")
                raise APIError(
                    500,
                    "Failed to update satellite addressability.",
                ) from exc

        result: dict[str, Any] = {
            "ok": True,
            "enabled": enabled,
            "updated": updated,
            "routing_refresh_required": routing_refresh_required,
        }
        if name is not None:
            result.update(name=name, addressable=enabled)
        return result
