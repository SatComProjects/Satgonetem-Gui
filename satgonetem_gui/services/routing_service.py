"""Routing and container lifecycle orchestration."""

import asyncio
import logging

from ..errors import APIError
from .ports import NetworkController, NetworkOperationError, PathReader
from .topology_service import TopologyService, is_node_name

logger = logging.getLogger(__name__)

NETWORK_OPERATION_TIMEOUT_SECONDS = 300.0


class RoutingService:
    """Apply routing and control GoNetem containers."""

    def __init__(
        self,
        topology: TopologyService,
        controller: NetworkController,
        operation_timeout_seconds: float = NETWORK_OPERATION_TIMEOUT_SECONDS,
        reader: PathReader | None = None,
    ) -> None:
        self.topology = topology
        self.controller = controller
        self.operation_timeout_seconds = operation_timeout_seconds
        self.reader = reader
        self._operation_lock: asyncio.Lock | None = None
        self._operation_loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task | None = None

    def status(self) -> dict:
        """Return routing and addressing state, including explicit address state."""
        status = self.controller.routing_status(self.topology.require_topology())
        status["addressing_applied"] = self.topology.addressing_applied
        return status

    def path(self, src: str, dst: str) -> dict:
        """Return a diagnostic path over the current routing graph.

        Read-only: this bypasses the network-operation gate and reports a path
        computed from the routing graph, not the live forwarding table.
        """
        if not is_node_name(src):
            raise APIError(404, f"Node not found: {src}")
        if not is_node_name(dst):
            raise APIError(404, f"Node not found: {dst}")
        if src == dst:
            raise APIError(422, "Source and destination must be different.")
        topology, _ = self.topology.context()
        if self.reader is None:
            raise APIError(500, "Routing path support is unavailable.")
        try:
            return self.reader.routing_path(topology, src, dst)
        except (ValueError, KeyError) as exc:
            raise APIError(404, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to compute the routing path.")
            raise APIError(500, "Failed to compute the routing path.") from exc

    def _require_current_project(self, generation: int) -> None:
        """Reject a completed operation whose project was replaced mid-flight."""
        if self.topology.generation != generation:
            raise APIError(
                409,
                "Project changed during the routing operation. Retry on the "
                "current project.",
            )

    def _operation_lock_for_loop(self) -> asyncio.Lock:
        """Return a lock owned by the current event loop (tests use several)."""
        loop = asyncio.get_running_loop()
        if self._operation_lock is None or self._operation_loop is not loop:
            self._operation_lock = asyncio.Lock()
            self._operation_loop = loop
        return self._operation_lock

    async def _run_controller(self, func, *args):
        """Run a blocking controller call without abandoning it on cancellation."""
        if self._worker is not None and not self._worker.done():
            raise APIError(
                409,
                "A previous network operation is still running in the background.",
            )
        worker = asyncio.create_task(asyncio.to_thread(func, *args))
        self._worker = worker

        def clear(_task: asyncio.Task) -> None:
            if self._worker is worker:
                self._worker = None
            if not worker.cancelled():
                worker.exception()

        worker.add_done_callback(clear)
        try:
            return await asyncio.wait_for(
                asyncio.shield(worker),
                timeout=self.operation_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                "Network operation timed out; the worker is still running."
            )
            raise APIError(504, "Network operation timed out.") from exc
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(
                    asyncio.shield(worker),
                    timeout=self.operation_timeout_seconds,
                )
            except Exception:
                logger.error(
                    "Cancelled network operation is still running in the background."
                )
            raise

    async def apply(self, method: str) -> None:
        """Apply addressing, then initialize the requested routing method."""
        async with self._operation_lock_for_loop():
            with self.topology.network_operation():
                await self._apply(method)

    async def _apply(self, method: str) -> None:
        topology, generation = self.topology.context()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running. Start containers first.")
        try:
            await self._run_controller(self.controller.apply_addressing, topology)
            self._require_current_project(generation)
            self.topology.set_addressing_applied(True)
            await self._run_controller(
                self.controller.init_routing, topology, method
            )
            self._require_current_project(generation)
        except APIError:
            raise
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while applying routing.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to apply addressing and routing.")
            raise APIError(500, "Failed to apply addressing and routing.") from exc

    async def delete(self) -> None:
        """Delete installed routing state."""
        async with self._operation_lock_for_loop():
            with self.topology.network_operation():
                await self._delete()

    async def _delete(self) -> None:
        topology, generation = self.topology.context()
        try:
            await self._run_controller(self.controller.delete_routing, topology)
            self._require_current_project(generation)
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
        async with self._operation_lock_for_loop():
            with self.topology.network_operation():
                await self._start_gonetem()

    async def _start_gonetem(self) -> None:
        topology, generation = self.topology.context()
        try:
            await self._run_controller(self.controller.start_gonetem, topology)
            self._require_current_project(generation)
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
        async with self._operation_lock_for_loop():
            with self.topology.network_operation():
                await self._stop_gonetem()

    async def _stop_gonetem(self) -> None:
        topology, generation = self.topology.context()
        try:
            await self._run_controller(self.controller.stop_gonetem, topology)
            self._require_current_project(generation)
            self.topology.set_addressing_applied(False)
        except APIError:
            raise
        except NetworkOperationError as exc:
            logger.exception("Network operation failed while stopping GoNetem.")
            raise APIError(500, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to stop GoNetem.")
            raise APIError(500, "Failed to stop GoNetem.") from exc
