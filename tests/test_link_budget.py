"""Adapter and API tests for the link-budget workbench."""

import pytest

from satgonetem_gui.adapters import link_budget_adapter
from satgonetem_gui.adapters.link_budget_adapter import SatGoNetemLinkBudgetAdapter
from satgonetem_gui.schemas import LinkBudgetRequest


def _calculate(**overrides):
    return SatGoNetemLinkBudgetAdapter().calculate(LinkBudgetRequest(**overrides))


def test_default_downlink_budget_is_positive() -> None:
    """A sensible downlink produces a full, positive budget."""
    result = _calculate()

    assert result["capacity_kbps"] > 0
    assert result["capacity_mbps"] > 0
    assert 0 < result["eirp_db"] < 100
    assert result["g_over_t_db"] > 0
    assert result["fspl_db"] > 100
    assert result["cn0_dbhz"] > 0
    assert result["cn_db"] < result["cn0_dbhz"]
    assert result["atmospheric_db"] >= 0
    assert isinstance(result["atmospheric_available"], bool)


def test_higher_noise_temperature_lowers_capacity() -> None:
    """Noisier receivers reduce the achievable capacity."""
    quiet = _calculate(rx_tsys_k=100)
    noisy = _calculate(rx_tsys_k=1000)

    assert noisy["cn0_dbhz"] < quiet["cn0_dbhz"]
    assert noisy["capacity_kbps"] < quiet["capacity_kbps"]


def test_larger_receiver_antenna_increases_capacity() -> None:
    """A larger ground antenna raises downlink G/T and capacity."""
    small = _calculate(ground_antenna_diameter_m=0.6)
    large = _calculate(ground_antenna_diameter_m=3.0)

    assert large["g_over_t_db"] > small["g_over_t_db"]
    assert large["capacity_kbps"] > small["capacity_kbps"]


def test_longer_distance_lowers_cn0() -> None:
    """Free-space loss grows with distance."""
    near = _calculate(distance_km=500)
    far = _calculate(distance_km=2000)

    assert far["fspl_db"] > near["fspl_db"]
    assert far["cn0_dbhz"] < near["cn0_dbhz"]


def test_modcod_and_uplink_strategies_return_capacity() -> None:
    """The MODCOD strategy and uplink direction remain usable."""
    modcod = _calculate(strategy="modcod")
    uplink = _calculate(
        direction="uplink",
        frequency_ghz=14.25,
        bandwidth_mhz=250,
    )

    assert isinstance(modcod["capacity_kbps"], int)
    assert modcod["capacity_kbps"] >= 0
    assert uplink["capacity_kbps"] > 0
    assert uplink["cn0_dbhz"] > 0


def test_explicit_eirp_overrides_the_antenna_model() -> None:
    """An explicit satellite EIRP is echoed in the breakdown."""
    result = _calculate(satellite_eirp_db=25.0)

    assert result["eirp_db"] == pytest.approx(25.0, abs=0.1)


def test_atmospheric_failure_falls_back_and_reports(monkeypatch) -> None:
    """A missing optional atmospheric model does not fail the calculation."""

    def explode(**_kwargs):
        raise RuntimeError("itur unavailable")

    monkeypatch.setattr(
        link_budget_adapter,
        "calculate_atmospheric_attenuation_dB",
        explode,
    )

    result = _calculate()

    assert result["atmospheric_available"] is False
    assert result["atmospheric_db"] == 0.0
    assert result["capacity_kbps"] > 0
