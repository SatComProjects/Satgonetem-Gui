"""Network, simulation, addressability, and connectivity controllers.

Implements the mutation protocols in ``services/ports.py``; the blocking core
calls happen behind these adapters and are offloaded by the services.
"""

import logging
from datetime import timedelta
from typing import Any

import satgonetem.connectivity as satgonetem_connectivity
from satgonetem.traffic import PingConfig

from ..services.ports import NetworkOperationError
from .core import addressable_endpoints, initialize_core

logger = logging.getLogger(__name__)


class NetworkAdapter:
    """Concrete ``NetworkController`` and related mutation controllers."""

    def __init__(self) -> None:
        initialize_core()

    def simulation_running(self, topology: Any) -> bool:
        """Return whether the core simulation loop is running."""
        return bool(topology.get_running())

    def start_simulation(self, topology: Any) -> None:
        """Start the core simulation loop."""
        topology.start()

    def stop_simulation(self, topology: Any) -> None:
        """Stop the core simulation loop and join its thread."""
        topology.stop()

    def step_simulation(self, topology: Any) -> None:
        """Advance the simulation by one step."""
        topology.next_step()

    def reset_simulation(self, topology: Any) -> None:
        """Reset the simulation clock to the project start."""
        topology.reset_simulation()

    def seek_simulation(self, topology: Any, step: int) -> None:
        """Jump to an absolute step and rebuild routing through the core."""
        total_steps = topology.get_project_duration_in_timesteps()
        if step < 0 or step > total_steps:
            raise ValueError(f"Step {step} is outside 0..{total_steps}.")
        target = topology.start_time + timedelta(seconds=step * topology.update_time)
        topology.move_to_time(target)

    def change_simulation_speed(self, topology: Any, direction: str) -> None:
        """Change playback speed through the core's public controls."""
        if direction == "faster":
            topology.speed_up()
        elif direction == "slower":
            topology.speed_down()
        else:
            raise ValueError(f"Unknown simulation speed direction: {direction!r}")

    def satellite_addressability(self, topology: Any) -> dict[str, Any]:
        """Return the addressable satellite names and the satellite total."""
        satellites = list(topology.satellites.values())
        return {
            "addressable": sorted(
                satellite.name for satellite in satellites if satellite.is_addressable()
            ),
            "total": len(satellites),
        }

    def set_satellites_addressable(
        self,
        topology: Any,
        enabled: bool,
        names: list[str] | None = None,
    ) -> int:
        """Enable or disable addressability for all or selected satellites."""
        satellites = list(topology.satellites.values())
        if names is None:
            targets = satellites
        else:
            by_name = {satellite.name: satellite for satellite in satellites}
            missing = [name for name in names if name not in by_name]
            if missing:
                raise ValueError(f"Unknown satellite: {missing[0]}")
            targets = [by_name[name] for name in names]

        if not targets:
            return 0
        if enabled:
            topology.set_addressable_satellites(targets)
        else:
            for satellite in targets:
                satellite.set_addressable(False)
        return len(targets)

    def routing_status(self, topology: Any) -> dict[str, Any]:
        """Return routing and container state without guessing addressing state."""
        return {
            "ok": True,
            "gonetem_is_on": topology.get_gonetem_status(),
            "routing_initiated": topology.get_routing_initiated(),
            "routing_method": topology.routing,
        }

    def apply_addressing(self, topology: Any) -> None:
        """Apply IP addresses and raise if the dependency reports failure."""
        try:
            result = topology.set_ip_addresses()
        except RuntimeError as exc:
            raise NetworkOperationError(str(exc)) from exc
        if result is not None and result < 0:
            raise NetworkOperationError("IP addressing failed.")

    def init_routing(self, topology: Any, method: str) -> None:
        """Initialize routing and map the dependency's negative return code."""
        result = topology.init_routing(routing_method=method)
        if result is not None and result < 0:
            raise NetworkOperationError("Routing initialization failed.")

    def delete_routing(self, topology: Any) -> None:
        """Delete routing state; a no-op when routing was never initialized."""
        if not topology.get_routing_initiated():
            return
        result = topology.delete_routing()
        if result is not None and result < 0:
            raise NetworkOperationError("Routing deletion failed.")

    def start_gonetem(self, topology: Any) -> None:
        """Start emulated containers and clean up a partial startup on failure."""
        try:
            topology.start_gonetem()
            if not topology.get_gonetem_status():
                raise NetworkOperationError("GoNetEm failed to start.")
        except Exception:
            try:
                topology.stop_gonetem()
            except Exception:
                logger.exception("Failed to clean up a partial GoNetEm startup.")
            raise

    def stop_gonetem(self, topology: Any) -> None:
        """Stop emulated containers without faking the loaded-project status."""
        topology.stop_gonetem()
        if topology.get_gonetem_status():
            raise NetworkOperationError("GoNetEm failed to stop.")

    def run_connectivity_matrix(
        self,
        topology: Any,
        names: list[str],
        *,
        ping_count: int,
        max_workers: int,
        flow_timeout_seconds: float,
    ) -> dict[str, Any]:
        """Ping every ordered pair through the core connectivity API."""
        nodes = []
        for name in names:
            node = topology.get_node_by_name(name)
            if node is None:
                raise ValueError(f"Node is not an addressable traffic endpoint: {name}")
            nodes.append(node)

        try:
            matrix = satgonetem_connectivity.build_connectivity_matrix(
                nodes,
                config=PingConfig(
                    count=ping_count,
                    interval_sec=0.01,
                    preload=1,
                    packet_size=64,
                ),
                max_workers=max_workers,
                flow_timeout_sec=flow_timeout_seconds,
            )
            result = matrix.to_dict()
        except Exception as exc:
            logger.exception("Connectivity matrix failed.")
            raise RuntimeError("Connectivity check failed.") from exc

        return {"nodes": list(names), **result}


    def resolve_connectivity_nodes(
        self,
        topology: Any,
        names: list[str] | None,
    ) -> list[str]:
        """Return the validated ordered node names for a connectivity matrix."""
        candidates = [node.name for _kind, node in addressable_endpoints(topology)]

        if names is None:
            selected = list(candidates)
        else:
            available = set(candidates)
            selected = []
            seen: set[str] = set()
            for name in names:
                if name not in available:
                    raise ValueError(f"Node is not an addressable traffic endpoint: {name}")
                if name in seen:
                    continue
                seen.add(name)
                selected.append(name)

        if len(selected) < 2:
            raise ValueError("At least two addressable nodes are required.")
        return selected
