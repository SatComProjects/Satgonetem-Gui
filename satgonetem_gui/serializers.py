"""Traffic result serializers shared by the traffic endpoints."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def clean_numeric(value: Any) -> Any:
    """Convert a scalar to a JSON-safe number, preserving None.

    Handles pandas/numpy scalar types via ``.item()`` and replaces NaN/inf with
    None so responses can be serialized.
    """
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, (int, str, bool)):
        return value
    try:
        converted = float(value)
        if converted != converted or converted in (float("inf"), float("-inf")):
            return None
        return converted
    except (TypeError, ValueError):
        return str(value) if value is not None else None


def serialize_iperf3_results(
    result: Any,
    intervals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract chart-friendly data from an iperf3 result object.

    Args:
        result: Parsed iperf3 result object.
        intervals: Raw interval dictionaries extracted by the adapter.
    """
    data: dict[str, Any] = {
        "protocol": result.protocol,
        "duration_seconds": result.duration_seconds,
        "num_streams": result.num_streams,
        "avg_throughput_mbps": result.avg_throughput_mbps,
        "max_throughput_mbps": result.max_throughput_mbps,
        "min_throughput_mbps": result.min_throughput_mbps,
        "pmtu": result.pmtu,
        "intervals": [],
    }
    if result.protocol == "TCP":
        data["total_bytes_sent"] = result.total_bytes_sent
        data["total_bytes_received"] = result.total_bytes_received
        data["total_retransmits"] = result.total_retransmits
        data["avg_rtt_ms"] = result.avg_rtt_ms
        data["max_rtt_ms"] = result.max_rtt_ms
    else:
        data["total_bytes"] = result.total_bytes
        data["total_packets"] = result.total_packets
        data["avg_jitter_ms"] = result.avg_jitter_ms
        data["total_lost_packets"] = result.total_lost_packets
        data["avg_loss_percent"] = result.avg_loss_percent
        data["total_out_of_order"] = result.total_out_of_order

    try:
        for interval in intervals:
            entry: dict[str, Any] = {"t": 0.0, "sum": {}, "sums": {}, "streams": []}
            timestamp = 0.0
            for key in (
                "sum",
                "sum_received",
                "sum_sent",
                "sum_bidir",
                "sum_bidir_reverse",
            ):
                if key in interval:
                    timestamp = float(
                        interval[key].get("end", interval[key].get("start", 0.0))
                    )
                    break
            if timestamp == 0.0 and interval.get("streams"):
                stream = interval["streams"][0]
                timestamp = float(stream.get("end", stream.get("start", 0.0)))
            entry["t"] = timestamp

            for key in (
                "sum",
                "sum_received",
                "sum_sent",
                "sum_bidir",
                "sum_bidir_reverse",
            ):
                if key in interval:
                    entry["sums"][key] = {
                        name: clean_numeric(value)
                        for name, value in interval[key].items()
                    }

            primary = (
                interval.get("sum")
                or interval.get("sum_received")
                or interval.get("sum_sent")
                or {}
            )
            entry["sum"] = {
                name: clean_numeric(value) for name, value in primary.items()
            }

            for stream in interval.get("streams", []):
                entry["streams"].append(
                    {name: clean_numeric(value) for name, value in stream.items()}
                )
            data["intervals"].append(entry)
    except Exception:
        logger.exception("Failed to serialize iperf3 intervals.")
    return data


def serialize_ping_results(result: Any) -> dict[str, Any]:
    """Extract summary data from a ping result object."""
    return {
        "packets_transmitted": result.packets_transmitted,
        "packets_received": result.packets_received,
        "packet_loss_percent": result.packet_loss_percent,
        "reachable": result.reachable,
        "rtt_min_ms": result.rtt_min_ms,
        "rtt_avg_ms": result.rtt_avg_ms,
        "rtt_max_ms": result.rtt_max_ms,
        "rtt_mdev_ms": result.rtt_mdev_ms,
    }


def serialize_hping3_results(result: Any) -> dict[str, Any]:
    """Extract chart-friendly data from an hping3 result object."""
    return {
        "payload_bytes": result.payload_bytes,
        "seq": result.seq,
        "rtt_ms": [
            None if (isinstance(value, float) and value != value) else value
            for value in result.rtt_ms
        ],
        "cumulative_mbit": result.cumulative_mbit,
        "packets_transmitted": result.packets_transmitted,
        "packets_received": result.packets_received,
        "packet_loss_percent": result.packet_loss_percent,
        "rtt_min_ms": result.rtt_min_ms,
        "rtt_avg_ms": result.rtt_avg_ms,
        "rtt_max_ms": result.rtt_max_ms,
        "reachable": result.reachable,
    }
