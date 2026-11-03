"""Unit tests for telemetry rates, baselines, and alerts."""

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.ports import NetworkOperationError
from satgonetem_gui.services.telemetry_service import TelemetryService


class FakeTopology:
    def __init__(self, running: bool = True) -> None:
        self.running = running

    def require_topology(self):
        return object()

    def gonetem_is_on(self):
        return self.running


class FakeGateway:
    def __init__(self) -> None:
        self.snapshot = _snapshot()
        self.fail = False

    def sample(self, topology):
        if self.fail:
            raise NetworkOperationError("sampling failed")
        return self.snapshot


def _snapshot(
    rx_bytes: int = 0,
    route_hash: str = "a",
    state: str = "active",
    rx_dropped: int = 0,
    tcp_out_rsts: int = 0,
) -> dict:
    return {
        "nodes": [
            {
                "name": "Gnd0",
                "type": "ground_station",
                "interfaces": [
                    {
                        "name": "Gnd0.5",
                        "iname": "eth5",
                        "rx_bytes": rx_bytes,
                        "tx_bytes": 0,
                        "rx_packets": 0,
                        "tx_packets": 0,
                        "rx_dropped": rx_dropped,
                        "tx_dropped": 0,
                        "rx_errors": 0,
                        "tx_errors": 0,
                    }
                ],
                "route_count": 2,
                "route_hash": route_hash,
                "protocols": [],
                "tcp_in_segs": 0,
                "tcp_out_rsts": tcp_out_rsts,
                "tcp_retrans_segs": 0,
                "udp_in_datagrams": 0,
                "icmp_in_msgs": 0,
                "error": None,
            }
        ],
        "links": [
            {
                "key": "Gnd0|Gnd1|GroundStationLink|bidirectional",
                "src": "Gnd0",
                "dst": "Gnd1",
                "type": "GroundStationLink",
                "capacity_kbps": 5000,
                "delay_ms": 5,
                "state": state,
                "rx_bytes": rx_bytes,
                "tx_bytes": 0,
                "rx_mbps": 0.0,
                "tx_mbps": 0.0,
                "rx_dropped": rx_dropped,
                "tx_dropped": 0,
                "rx_errors": 0,
                "tx_errors": 0,
                "budget": None,
            }
        ],
    }


def _run_samples(snapshots, times):
    gateway = FakeGateway()
    clock = iter(times).__next__
    service = TelemetryService(FakeTopology(), gateway, clock=clock)
    results = []
    for snapshot in snapshots:
        gateway.snapshot = snapshot
        results.append(service.sample())
    return service, results


def test_first_sample_has_zero_rates() -> None:
    """Rates need a previous sample; the first snapshot is a baseline."""
    _service, results = _run_samples([_snapshot(rx_bytes=1000)], [100.0])

    assert results[0]["nodes"][0]["interfaces"][0]["rx_mbps"] == 0.0
    assert results[0]["links"][0]["rx_mbps"] == 0.0
    assert results[0]["baseline_samples"] == 1


def test_second_sample_computes_rates_and_route_change() -> None:
    """Byte deltas become Mbps and route hashes produce alerts."""
    _service, results = _run_samples(
        [
            _snapshot(rx_bytes=1_000_000, route_hash="a"),
            _snapshot(rx_bytes=2_250_000, route_hash="b"),
        ],
        [100.0, 110.0],
    )

    assert results[1]["nodes"][0]["interfaces"][0]["rx_mbps"] == 1.0
    assert results[1]["links"][0]["rx_mbps"] == 1.0
    assert any(alert["metric"] == "route_change" for alert in results[1]["alerts"])


def test_link_state_change_is_critical() -> None:
    """An active/inactive transition is a critical alert."""
    _service, results = _run_samples(
        [
            _snapshot(rx_bytes=0, state="active"),
            _snapshot(rx_bytes=0, state="inactive"),
        ],
        [100.0, 105.0],
    )

    alert = next(
        alert for alert in results[1]["alerts"] if alert["metric"].startswith("link_state")
    )
    assert alert["severity"] == "critical"


def test_interface_drops_produce_warning() -> None:
    """Drop counter deltas are surfaced as interface alerts."""
    _service, results = _run_samples(
        [
            _snapshot(rx_bytes=0, rx_dropped=0),
            _snapshot(rx_bytes=0, rx_dropped=7),
        ],
        [100.0, 105.0],
    )

    assert any(
        alert["metric"].startswith("drops:") and alert["severity"] == "warning"
        for alert in results[1]["alerts"]
    )


def test_throughput_spike_triggers_baseline_alert() -> None:
    """A spike after five baseline samples creates a throughput alert."""
    snapshots = [_snapshot(rx_bytes=index * 1_250_000) for index in range(5)] + [
        _snapshot(rx_bytes=5 * 1_250_000 + 12_500_000)
    ]
    times = [100.0 + index * 10.0 for index in range(6)]
    _service, results = _run_samples(snapshots, times)

    assert any(alert["metric"].startswith("link_spike:") for alert in results[-1]["alerts"])


def test_clear_alerts_resets_history() -> None:
    """The alert history can be cleared without dropping baselines."""
    service, results = _run_samples(
        [
            _snapshot(rx_bytes=0, route_hash="a"),
            _snapshot(rx_bytes=0, route_hash="b"),
        ],
        [100.0, 105.0, 110.0],
    )
    assert results[1]["alerts"]

    service.clear_alerts()

    assert service.sample()["alerts"] == []


def test_sample_requires_running_containers() -> None:
    """Telemetry does not attempt to read stopped containers."""
    service = TelemetryService(FakeTopology(running=False), FakeGateway())

    with pytest.raises(APIError) as error:
        service.sample()

    assert error.value.status_code == 409


def test_gateway_failure_maps_to_500() -> None:
    """Adapter failures use the shared error envelope."""
    gateway = FakeGateway()
    gateway.fail = True
    service = TelemetryService(FakeTopology(), gateway)

    with pytest.raises(APIError) as error:
        service.sample()

    assert error.value.status_code == 500


def test_packet_rate_alert_is_derived_from_kernel_counters() -> None:
    """A TCP RST burst becomes a packet-rate alert."""
    _service, results = _run_samples(
        [
            _snapshot(tcp_out_rsts=0),
            _snapshot(tcp_out_rsts=1000),
        ],
        [100.0, 105.0],
    )

    assert any(alert["metric"] == "tcp_rst_rate" for alert in results[1]["alerts"])


def test_prometheus_exports_rates_and_alert_count() -> None:
    """The scrape endpoint exposes interface/link metrics as text."""
    gateway = FakeGateway()
    service = TelemetryService(
        FakeTopology(),
        gateway,
        clock=iter([100.0, 105.0]).__next__,
    )
    service.sample()

    text = service.prometheus()

    assert 'sgnt_interface_rx_mbps{node="Gnd0",interface="eth5"}' in text
    assert 'sgnt_link_capacity_kbps{src="Gnd0",dst="Gnd1"}' in text
    assert "sgnt_alerts_total" in text
