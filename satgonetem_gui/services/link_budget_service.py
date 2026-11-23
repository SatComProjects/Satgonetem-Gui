"""Standalone link-budget workbench use case."""

import logging
from typing import Any

from ..errors import APIError
from ..schemas import LinkBudgetRequest
from .ports import LinkBudgetGateway

logger = logging.getLogger(__name__)


class LinkBudgetService:
    """Validate and calculate one standalone one-way RF budget."""

    def __init__(self, gateway: LinkBudgetGateway) -> None:
        self.gateway = gateway

    def calculate(self, request: LinkBudgetRequest) -> dict[str, Any]:
        """Return the budget breakdown plus the echoed request parameters."""
        try:
            result = self.gateway.calculate(request)
        except ValueError as exc:
            raise APIError(
                422, f"Link budget inputs are invalid: {exc}"
            ) from exc
        except Exception as exc:
            logger.exception("Link budget calculation failed.")
            raise APIError(500, "Link budget calculation failed.") from exc

        return {
            "ok": True,
            **result,
            "direction": request.direction,
            "strategy": request.strategy,
            "frequency_ghz": request.frequency_ghz,
            "bandwidth_mhz": request.bandwidth_mhz,
            "distance_km": request.distance_km,
            "elevation_deg": request.elevation_deg,
        }
