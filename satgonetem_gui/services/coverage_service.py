"""Coverage analytics orchestration and bounded snapshot cache."""

import copy
import logging
import math
import threading
from collections import OrderedDict
from typing import Any

from ..errors import APIError
from ..schemas import CoverageRequest
from .ports import CoverageController
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

MAX_WORK = 100_000_000
MAX_GRID_CELLS = 1_200_000
MAX_SHELLS = 24
MAX_GROUND_STATIONS = 64
MAX_GROUND_STATION_PAIRS = 100_000
CACHE_SIZE = 16
DEFAULT_ELEVATION_DEG = 10.0
DEFAULT_GRID_RESOLUTION_DEG = 1.0


class CoverageService:
    """Validate coverage requests, cache snapshots, and enforce work caps."""

    def __init__(
        self,
        topology: TopologyService,
        controller: CoverageController,
    ) -> None:
        self.topology = topology
        self.controller = controller
        self._cache: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def analyze(self, request: CoverageRequest) -> dict[str, Any]:
        """Return one coverage snapshot for the loaded topology."""
        topology, generation = self.topology.context()
        satellites = len(getattr(topology, "satellites", {}) or {})
        if satellites == 0:
            raise APIError(422, "No satellites to analyze.")

        elevation = float(request.elevation_deg)
        resolution = float(request.grid_resolution_deg)
        cells = math.ceil(180.0 / resolution) * math.ceil(360.0 / resolution)
        work = cells * satellites
        if cells > MAX_GRID_CELLS or work > MAX_WORK:
            raise APIError(
                422,
                f"Coverage grid too large: {work:,} satellite-cells for "
                f"{satellites:,} satellites; choose a coarser resolution.",
            )

        step = int(getattr(topology, "current_time_step", 0) or 0)
        key = (
            generation,
            step,
            round(elevation, 6),
            round(resolution, 6),
            bool(request.include_shells),
            bool(request.include_ground_stations),
        )
        cached = self._cached(key)
        if cached is not None:
            cached["cached"] = True
            cached["duration_ms"] = 0.0
            return cached

        station_limit = min(
            MAX_GROUND_STATIONS,
            MAX_GROUND_STATION_PAIRS // max(1, satellites),
        )
        try:
            payload = self.controller.coverage_snapshot(
                topology,
                elevation_deg=elevation,
                grid_resolution_deg=resolution,
                include_shells=request.include_shells,
                include_ground_stations=request.include_ground_stations,
                max_shells=MAX_SHELLS,
                max_ground_stations=station_limit,
            )
        except Exception as exc:
            logger.exception("Coverage analysis failed.")
            raise APIError(500, "Coverage analysis failed.") from exc

        result: dict[str, Any] = {
            "ok": True,
            **payload,
            "sampled_cells": cells,
            "elevation_deg": request.elevation_deg,
            "grid_resolution_deg": request.grid_resolution_deg,
            "step": step,
            "generation": generation,
            "cached": False,
        }
        if self.topology.generation == generation:
            self._store(key, result)
        return result

    def _cached(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        """Return a deep copy of a cached payload, or None on a miss."""
        with self._lock:
            payload = self._cache.get(key)
            if payload is None:
                return None
            self._cache.move_to_end(key)
            return copy.deepcopy(payload)

    def _store(self, key: tuple[Any, ...], payload: dict[str, Any]) -> None:
        """Store one payload and evict the least recently used entry."""
        with self._lock:
            self._cache[key] = copy.deepcopy(payload)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
