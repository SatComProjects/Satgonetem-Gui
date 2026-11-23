"""SatGoNetem link-budget workbench adapter.

This is the only module that imports the core RF link-budget chain. Services
use the narrow :class:`~satgonetem_gui.services.ports.LinkBudgetGateway`
protocol.
"""

import logging
from typing import Any

from satgonetem.link_budget import (
    AntennaConfig,
    LinkBudgetInputs,
    ModCodCapacityStrategy,
    ShannonCapacityStrategy,
    calculate_atmospheric_attenuation_dB,
    calculate_carrier_to_noise_power_spectral_density_ratio,
    calculate_carrier_to_noise_ratio,
    calculate_free_space_loss_db,
    linear_to_db,
)
from satgonetem.link_budget import LinkBudgetService as CoreLinkBudgetService

from ..schemas import LinkBudgetRequest

logger = logging.getLogger(__name__)


def _rounded(value: float) -> float:
    """Round one displayed budget value to two decimals."""
    return round(float(value), 2)


class SatGoNetemLinkBudgetAdapter:
    """Concrete adapter around the public core link-budget helpers."""

    def calculate(self, request: LinkBudgetRequest) -> dict[str, Any]:
        """Return the breakdown and capacity for one one-way link."""
        try:
            return self._calculate(request)
        except ValueError as exc:
            raise ValueError(
                f"unable to compute this budget: {exc}"
            ) from exc
        except ArithmeticError as exc:
            raise ValueError(
                f"invalid numeric input for this budget: {exc}"
            ) from exc

    def _calculate(self, request: LinkBudgetRequest) -> dict[str, Any]:
        satellite = AntennaConfig(
            diameter=request.satellite_antenna_diameter_m,
            efficiency=request.satellite_antenna_efficiency,
            sspa_output_power_db=request.satellite_sspa_output_power_db,
            losses_db=request.satellite_losses_db,
            eirp_db=request.satellite_eirp_db,
        ).to_antenna()
        ground = AntennaConfig(
            diameter=request.ground_antenna_diameter_m,
            efficiency=request.ground_antenna_efficiency,
            losses_db=request.ground_losses_db,
            eirp_db=request.ground_eirp_db,
        ).to_antenna()

        if request.direction == "uplink":
            tx_antenna, rx_antenna = ground, satellite
        else:
            tx_antenna, rx_antenna = satellite, ground

        frequency_ghz = request.frequency_ghz
        bandwidth_hz = request.bandwidth_mhz * 1e6

        eirp_db = float(tx_antenna.get_eirp_db(frequency_ghz))
        g_over_t_db = float(
            rx_antenna.calculate_gain_db(frequency_ghz)
        ) - linear_to_db(request.rx_tsys_k)
        fspl_db = float(
            calculate_free_space_loss_db(frequency_ghz, request.distance_km)
        )
        atmospheric_db, atmospheric_available = self._atmospheric(
            request,
        )

        cn0_dbhz = calculate_carrier_to_noise_power_spectral_density_ratio(
            eirp_db=eirp_db,
            g_over_t_db=g_over_t_db,
            free_space_loss_db=fspl_db,
            other_losses_db=atmospheric_db,
        )
        cn_db = calculate_carrier_to_noise_ratio(cn0_dbhz, bandwidth_hz)

        strategy = (
            ModCodCapacityStrategy()
            if request.strategy == "modcod"
            else ShannonCapacityStrategy()
        )
        capacity_kbps = CoreLinkBudgetService(
            capacity_strategy=strategy,
        ).compute_one_way(
            LinkBudgetInputs(
                tx_antenna=tx_antenna,
                rx_antenna=rx_antenna,
                frequency_ghz=frequency_ghz,
                distance_km=request.distance_km,
                elevation_angle=request.elevation_deg,
                gs_lat=request.gs_latitude,
                gs_lon=request.gs_longitude,
                gs_diameter=request.ground_antenna_diameter_m,
                bandwidth_hz=bandwidth_hz,
                rx_tsys_k=request.rx_tsys_k,
                unavailability_percent=request.unavailability_percent,
            )
        )

        return {
            "capacity_kbps": int(capacity_kbps),
            "capacity_mbps": float(capacity_kbps) / 1000.0,
            "eirp_db": _rounded(eirp_db),
            "g_over_t_db": _rounded(g_over_t_db),
            "fspl_db": _rounded(fspl_db),
            "atmospheric_db": _rounded(atmospheric_db),
            "atmospheric_available": atmospheric_available,
            "cn0_dbhz": _rounded(cn0_dbhz),
            "cn_db": _rounded(cn_db),
        }

    def _atmospheric(
        self,
        request: LinkBudgetRequest,
    ) -> tuple[float, bool]:
        """Return atmospheric attenuation and whether the model ran."""
        try:
            attenuation = calculate_atmospheric_attenuation_dB(
                lat_GS=request.gs_latitude,
                lon_GS=request.gs_longitude,
                frequency_ghz=request.frequency_ghz,
                elevation_angle=request.elevation_deg,
                unavailability=request.unavailability_percent,
                antenna_diameter=request.ground_antenna_diameter_m,
            )
        except Exception as exc:
            logger.warning(
                "Atmospheric attenuation unavailable; using 0 dB: %s", exc
            )
            return 0.0, False

        if isinstance(attenuation, (list, tuple)):
            return float(attenuation[0]), True
        return float(attenuation), True
