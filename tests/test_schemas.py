"""Validation tests for the request schema boundary."""

import json

import pytest
from pydantic import ValidationError

from satgonetem_gui.schemas import (
    GroundStationPoint,
    Hping3Request,
    Iperf3Request,
    PingRequest,
    ProjectCreateRequest,
    RoutingApplyRequest,
)


def _project_payload(**overrides):
    payload = {
        "name": "Project",
        "start_date": "01/01/2024 00:00:00",
        "end_date": "01/01/2024 00:10:00",
        "walker_shells_json": json.dumps([]),
        "ground_objects_properties_json": json.dumps([]),
    }
    payload.update(overrides)
    return payload


def test_documented_traffic_defaults_validate() -> None:
    """The documented defaults remain accepted after adding constraints."""
    iperf = Iperf3Request(src="a", dst="b")
    ping = PingRequest(src="a", dst="b")
    hping = Hping3Request(src="a", dst="b")

    assert iperf.protocol == "TCP"
    assert iperf.duration == 10
    assert iperf.bandwidth_mbps == 0.0
    assert iperf.parallel == 1
    assert iperf.interval == 1.0
    assert iperf.port == 5201
    assert iperf.congestion_control == "bbr"
    assert iperf.window_size is None
    assert iperf.bidir is False

    assert ping.count == 5
    assert ping.timeout_sec == 0.5
    assert ping.interval_sec == 0.2
    assert ping.packet_size == 56

    assert hping.proto == "tcp"
    assert hping.dport == 0
    assert hping.count == 100
    assert hping.size == 0
    assert hping.rate_type == "interval"
    assert hping.interval == ""
    assert hping.flags == []


def test_hping_interval_requires_a_value_after_the_unit() -> None:
    """A bare microsecond marker is rejected; empty, digits, and u<digits> pass."""
    assert Hping3Request(src="a", dst="b", interval="").interval == ""
    assert Hping3Request(src="a", dst="b", interval="1000").interval == "1000"
    assert Hping3Request(src="a", dst="b", interval="u1000").interval == "u1000"

    with pytest.raises(ValidationError):
        Hping3Request(src="a", dst="b", interval="u")


@pytest.mark.parametrize(
    "point",
    [
        {"latitude": 91},
        {"latitude": float("nan")},
        {"longitude": -181},
        {"longitude": float("inf")},
        {"elevation_m": -1001},
        {"elevation_m": float("inf")},
        {"index": -1},
    ],
)
def test_ground_station_point_rejects_out_of_range_values(point: dict) -> None:
    """Preset response rows enforce the same bounds as inline stations."""
    base = {
        "index": 0,
        "name": "Berlin",
        "latitude": 52.52,
        "longitude": 13.405,
        "elevation_m": 34.0,
    }
    base.update(point)

    with pytest.raises(ValidationError):
        GroundStationPoint(**base)


def test_project_load_content_is_bounded() -> None:
    """Uploaded project JSON cannot allocate an unbounded request body."""
    from satgonetem_gui.schemas import ProjectLoadRequest

    with pytest.raises(ValidationError):
        ProjectLoadRequest(content="x" * 10_000_001)


def test_hidden_project_json_is_bounded() -> None:
    """The form's hidden JSON fields have a fixed upper bound."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(**_project_payload(walker_shells_json="x" * 2_000_001))


def test_project_create_defaults_validate() -> None:
    """The project form defaults remain accepted after adding bounds."""
    request = ProjectCreateRequest(**_project_payload())

    assert request.update_time == 5
    assert request.isl_capacity == 100000
    assert request.gs_capacity == 100000
    assert request.save_path == ""


@pytest.mark.parametrize("value", ["", "bbr", "cubic", "reno", "bbr2_x-y"])
def test_iperf3_accepts_safe_congestion_controls(value: str) -> None:
    """Lowercase congestion-control names and the empty default are allowed."""
    assert Iperf3Request(src="a", dst="b", congestion_control=value).congestion_control == value


@pytest.mark.parametrize(
    "value",
    [
        "bbr; touch /tmp/pwned",
        "bbr && id",
        "bbr`id`",
        "bbr|id",
        "bbr\nid",
        "BBR",
        "a" * 33,
    ],
)
def test_iperf3_rejects_unsafe_congestion_control(value: str) -> None:
    """Shell metacharacters and over-long names never reach the core."""
    with pytest.raises(ValidationError):
        Iperf3Request(src="a", dst="b", congestion_control=value)


@pytest.mark.parametrize("value", ["", None, "256K", "1M", "4G", "1048576"])
def test_iperf3_accepts_safe_window_sizes(value: str | None) -> None:
    """Empty, omitted, and numbered window sizes are allowed."""
    request = Iperf3Request(src="a", dst="b", window_size=value)

    assert request.window_size == value


@pytest.mark.parametrize(
    "value",
    [
        "1M; id",
        "1M; touch /tmp/pwned",
        "1M && id",
        "1M`id`",
        "1M|id",
        "1M\n",
        "K",
        "1T",
        "size",
    ],
)
def test_iperf3_rejects_unsafe_window_sizes(value: str) -> None:
    """Window sizes outside the digit/suffix grammar are rejected."""
    with pytest.raises(ValidationError):
        Iperf3Request(src="a", dst="b", window_size=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol", "tcp"),
        ("protocol", "SCTP"),
        ("duration", 0),
        ("duration", 3601),
        ("bandwidth_mbps", -0.1),
        ("parallel", 0),
        ("parallel", 65),
        ("interval", 0),
        ("interval", 60.1),
        ("port", 0),
        ("port", 65536),
    ],
)
def test_iperf3_rejects_out_of_range_values(field: str, value) -> None:
    """Numeric iperf3 fields stay inside the documented bounds."""
    with pytest.raises(ValidationError):
        Iperf3Request(src="a", dst="b", **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("count", 0),
        ("timeout_sec", 0),
        ("timeout_sec", 60.1),
        ("interval_sec", 0.002),
        ("interval_sec", 60.1),
        ("packet_size", 0),
        ("packet_size", 65501),
    ],
)
def test_ping_rejects_out_of_range_values(field: str, value) -> None:
    """Numeric ping fields stay inside the documented bounds."""
    with pytest.raises(ValidationError):
        PingRequest(src="a", dst="b", **{field: value})


@pytest.mark.parametrize("value", ["", "1", "u10000", "u1"])
def test_hping3_accepts_safe_intervals(value: str) -> None:
    """The hping3 interval grammar accepts empty and numeric forms."""
    assert Hping3Request(src="a", dst="b", interval=value).interval == value


@pytest.mark.parametrize(
    "value",
    [
        "u10000; id",
        "u10000; touch /tmp/pwned",
        "u10000 && id",
        "u10000`id`",
        "u10000|id",
        "u10000\n",
        "-1",
        "u-1",
        "abc",
    ],
)
def test_hping3_rejects_unsafe_intervals(value: str) -> None:
    """Shell metacharacters never reach the hping3 command builder."""
    with pytest.raises(ValidationError):
        Hping3Request(src="a", dst="b", interval=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("proto", "raw"),
        ("proto", "TCP"),
        ("rate_type", "flood"),
        ("rate_type", "slow"),
        ("dport", -1),
        ("dport", 65536),
        ("count", 0),
        ("size", -1),
        ("size", 65501),
        ("flags", ["S"] * 7),
    ],
)
def test_hping3_rejects_out_of_range_values(field: str, value) -> None:
    """Numeric and enumerated hping3 fields stay inside the documented bounds."""
    with pytest.raises(ValidationError):
        Hping3Request(src="a", dst="b", **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("update_time", 0),
        ("update_time", -5),
        ("isl_capacity", 0),
        ("gs_capacity", 0),
        ("name", ""),
        ("name", "x" * 129),
        ("start_date", "x" * 65),
        ("end_date", "x" * 65),
        ("save_path", "x" * 4097),
    ],
)
def test_project_create_rejects_out_of_range_values(field: str, value) -> None:
    """Project form fields keep sensible lengths and positive capacities."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(**_project_payload(**{field: value}))


@pytest.mark.parametrize("method", ["bogus", "STATIC", "", "dynamic-bgp"])
def test_routing_request_rejects_unknown_methods(method: str) -> None:
    """Only routing methods the UI can apply reach the core."""
    with pytest.raises(ValidationError):
        RoutingApplyRequest(method=method)


def test_routing_request_accepts_supported_methods() -> None:
    """All four routing methods offered by the control panel validate."""
    for method in ("static", "dynamic-ospf", "dynamic-isis", "sr-mpls"):
        assert RoutingApplyRequest(method=method).method == method
