"""Simulation loop transport orchestration."""

import asyncio
import logging
from contextlib import contextmanager
from typing import Any, Callable

from ..errors import APIError
from .ports import NetworkOperationError, SimulationController
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

SIMULATION_OPERATION_TIMEOUT_SECONDS = 300.0
SIMULATION_SHUTDOWN_TIMEOUT_SECONDS = 10.0


class SimulationService:
    """Start, pause, step, reset, seek, and change simulation playback."""

    def __init__(
        self,
        topology: TopologyService,
        controller: SimulationController,
        operation_timeout_seconds: float = SIMULATION_OPERATION_TIMEOUT_SECONDS,
    ) -> None:
        self.topology = topology
        self.controller = controller
        self.operation_timeout_seconds = operation_timeout_seconds
        self._operation_lock: asyncio.Lock | None = None
        self._operation_loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task | None = None

    def _require_current_project(self, generation: int) -> None:
        """Reject a completed operation whose project was replaced mid-flight."""
        if self.topology.generation != generation:
            raise APIError(
                409,
                "Project changed during the simulation operation. Retry on the "
                "current project.",
            )

    def _operation_lock_for_loop(self) -> asyncio.Lock:
        """Return a lock owned by the current event loop (tests use several)."""
        loop = asyncio.get_running_loop()
        if self._operation_lock is None or self._operation_loop is not loop:
            self._operation_lock = asyncio.Lock()
            self._operation_loop = loop
        return self._operation_lock

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

    async def _run_controller(self, func, *args: Any):
        """Run a blocking controller call without abandoning it on cancellation."""
        if self._worker is not None and not self._worker.done():
            raise APIError(
                409,
                "A previous simulation operation is still running in the background.",
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
                "Simulation operation timed out; the worker is still running."
            )
            raise APIError(504, "Simulation operation timed out.") from exc
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(
                    asyncio.shield(worker),
                    timeout=self.operation_timeout_seconds,
                )
            except Exception:
                logger.error(
                    "Cancelled simulation operation is still running in the "
                    "background."
                )
            raise

    async def _run_operation(
        self,
        func: Callable[..., None],
        *args: Any,
        require_paused: bool = False,
        invalid_target: bool = False,
    ) -> None:
        """Run one controller call behind the shared operation guards."""
        operation = getattr(func, "__name__", "simulation operation")
        async with self._operation_lock_for_loop():
            with self._network_operation():
                topology, generation = self.topology.context()
                try:
                    if require_paused and self.controller.simulation_running(
                        topology
                    ):
                        raise APIError(
                            409,
                            "Pause the simulation before changing its position.",
                        )
                    await self._run_controller(func, topology, *args)
                    self._require_current_project(generation)
                except APIError:
                    raise
                except NetworkOperationError as exc:
                    logger.exception("Simulation %s failed.", operation)
                    raise APIError(500, str(exc)) from exc
                except ValueError as exc:
                    if invalid_target:
                        raise APIError(422, str(exc)) from exc
                    logger.exception("Simulation %s failed.", operation)
                    raise APIError(
                        500,
                        "Simulation operation failed.",
                    ) from exc
                except Exception as exc:
                    logger.exception("Simulation %s failed.", operation)
                    raise APIError(
                        500,
                        "Simulation operation failed.",
                    ) from exc

    async def start(self) -> None:
        """Start the simulation loop."""
        await self._run_operation(self.controller.start_simulation)

    async def stop(self) -> None:
        """Pause the simulation loop."""
        await self._run_operation(self.controller.stop_simulation)

    async def step(self) -> None:
        """Advance the simulation by one step."""
        await self._run_operation(
            self.controller.step_simulation,
            require_paused=True,
        )

    async def reset(self) -> None:
        """Reset the simulation clock to the project start."""
        await self._run_operation(
            self.controller.reset_simulation,
            require_paused=True,
        )

    async def seek(self, step: int) -> None:
        """Jump to an absolute step index."""
        await self._run_operation(
            self.controller.seek_simulation,
            step,
            require_paused=True,
            invalid_target=True,
        )

    async def change_speed(self, direction: str) -> None:
        """Change playback speed by one step in the requested direction."""
        await self._run_operation(
            self.controller.change_simulation_speed,
            direction,
        )

    def stop_current(self) -> None:
        """Stop the loop for the loaded project, if any.

        Used by project replacement and application shutdown; exceptions
        propagate so a failed replacement is reported rather than hidden.
        """
        topology = self.topology.session.get_topology()
        if topology is None:
            return
        self.controller.stop_simulation(topology)

    async def shutdown(self) -> None:
        """Stop the simulation loop on a best-effort basis at shutdown."""
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.stop_current),
                timeout=SIMULATION_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception(
                "Could not stop the simulation loop during shutdown."
            )
