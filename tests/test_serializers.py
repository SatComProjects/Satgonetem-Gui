"""Tests for traffic-result serialization."""

from types import SimpleNamespace

from satgonetem_gui.serializers import (
    clean_numeric,
    serialize_hping3_results,
    serialize_iperf3_results,
    serialize_ping_results,
)


def test_clean_numeric_handles_nan_and_inf() -> None:
    """Non-finite numbers become JSON-safe nulls."""
    assert clean_numeric(None) is None
    assert clean_numeric(float("nan")) is None
    assert clean_numeric(float("inf")) is None
    assert clean_numeric("3.5") == "3.5"
    assert clean_numeric(True) is True


def test_serialize_ping_results() -> None:
    """Ping summaries preserve the frontend field names."""
    result = SimpleNamespace(
        packets_transmitted=3,
        packets_received=2,
        packet_loss_percent=33.3,
        reachable=True,
        rtt_min_ms=1.0,
        rtt_avg_ms=2.0,
        rtt_max_ms=3.0,
        rtt_mdev_ms=0.5,
    )

    assert serialize_ping_results(result) == {
        "packets_transmitted": 3,
        "packets_received": 2,
        "packet_loss_percent": 33.3,
        "reachable": True,
        "rtt_min_ms": 1.0,
        "rtt_avg_ms": 2.0,
        "rtt_max_ms": 3.0,
        "rtt_mdev_ms": 0.5,
    }


def test_serialize_hping3_results_filters_nan_rtts() -> None:
    """NaN RTT samples are emitted as null for the chart code."""
    result = SimpleNamespace(
        payload_bytes=56,
        seq=[1, 2],
        rtt_ms=[1.5, float("nan")],
        cumulative_mbit=[1.0, 2.0],
        packets_transmitted=2,
        packets_received=1,
        packet_loss_percent=50.0,
        rtt_min_ms=1.5,
        rtt_avg_ms=1.5,
        rtt_max_ms=1.5,
        reachable=True,
    )

    data = serialize_hping3_results(result)

    assert data["rtt_ms"] == [1.5, None]
    assert data["packets_received"] == 1


def test_serialize_iperf3_results_includes_intervals_and_tcp_metrics() -> None:
    """TCP summaries expose aggregate and per-interval fields."""
    result = SimpleNamespace(
        protocol="TCP",
        duration_seconds=1,
        num_streams=1,
        avg_throughput_mbps=8.0,
        max_throughput_mbps=9.0,
        min_throughput_mbps=7.0,
        pmtu=1500,
        total_bytes_sent=1000,
        total_bytes_received=900,
        total_retransmits=1,
        avg_rtt_ms=2.0,
        max_rtt_ms=3.0,
        _data={
            "intervals": [
                {
                    "sum": {
                        "start": 0.0,
                        "end": 1.0,
                        "seconds": 1.0,
                        "bits_per_second": 8000000.0,
                        "bytes": 1000,
                        "rtt": float("nan"),
                    },
                    "streams": [{"bits_per_second": 8000000.0, "snd_cwnd": 10}],
                }
            ]
        },
    )

    data = serialize_iperf3_results(result, result._data["intervals"])

    assert data["protocol"] == "TCP"
    assert data["total_retransmits"] == 1
    assert data["intervals"][0]["t"] == 1.0
    assert data["intervals"][0]["sum"]["rtt"] is None
    assert data["intervals"][0]["streams"][0]["snd_cwnd"] == 10


def test_serialize_iperf3_results_includes_udp_metrics() -> None:
    """UDP results use the UDP summary fields, not TCP-only metrics."""
    result = SimpleNamespace(
        protocol="UDP",
        duration_seconds=2,
        num_streams=1,
        avg_throughput_mbps=5.0,
        max_throughput_mbps=6.0,
        min_throughput_mbps=4.0,
        pmtu=1500,
        total_bytes=2000,
        total_packets=10,
        avg_jitter_ms=1.2,
        total_lost_packets=1,
        avg_loss_percent=10.0,
        total_out_of_order=0,
        _data={"intervals": []},
    )

    data = serialize_iperf3_results(result, [])

    assert data["total_packets"] == 10
    assert data["avg_jitter_ms"] == 1.2
    assert "total_bytes_sent" not in data
