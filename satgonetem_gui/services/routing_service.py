"""Routing and container lifecycle orchestration."""

import asyncio
import logging

from ..errors import APIError
from .ports import NetworkController, NetworkOperationError
from .topology_service import TopologyService

logger = logging.getLogger(__name__)


class RoutingService:
    """Apply routing and control GoNetem containers."""

    def __init__(
        self,
        topology: TopologyService,
        controller: NetworkController,
    ) -> None:
        self.topology = topology
        self.controller = controller

    def status(self) -> dict:
        """Return routing and addressing state, including explicit address state."""
        status = self.controller.routing_status(self.topology.require_topology())
        status["addressing_applied"] = self.topology.addressing_applied
        return status

    async def apply(self, method: str) -> None:
        """Apply addressing, then initialize the requested routing method."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running. Start containers first.")
        try:
            await asyncio.to_thread(self.controller.apply_addressing, topology)
            self.topology.set_addressing_applied(True)
            await asyncio.to_thread(self.controller.init_routing, topology, method)
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while applying routing.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to apply addressing and routing.")
            raise APIError(500, "Failed to apply addressing and routing.") from exc

    async def delete(self) -> None:
        """Delete installed routing state."""
        try:
            await asyncio.to_thread(
                self.controller.delete_routing,
                self.topology.require_topology(),
            )
            self.topology.set_addressing_applied(False)
        except APIError:
            raise
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while deleting routing.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to delete routing.")
            raise APIError(500, "Failed to delete routing.") from exc

    async def start_gonetem(self) -> None:
        """Start the emulated network containers."""
        try:
            await asyncio.to_thread(
                self.controller.start_gonetem,
                self.topology.require_topology(),
            )
        except APIError:
            raise
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while starting GoNetem.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to start GoNetem.")
            raise APIError(500, "Failed to start GoNetem.") from exc

    async def stop_gonetem(self) -> None:
        """Stop the emulated network containers."""
        try:
            await asyncio.to_thread(
                self.controller.stop_gonetem,
                self.topology.require_topology(),
            )
            self.topology.set_addressing_applied(False)
        except APIError:
            raise
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while stopping GoNetem.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to stop GoNetem.")
            raise APIError(500, "Failed to stop GoNetem.") from exc
