"""Unit tests for traffic flow normalization and flow construction."""

from types import SimpleNamespace

import pytest
from satgonetem.traffic import (
    FlowStatus,
    Hping3Flow,
    Hping3Status,
    Iperf3Flow,
    PingFlow,
    PingStatus,
)

import satgonetem_gui.adapters.satgonetem_traffic as adapter_module
from satgonetem_gui.adapters.satgonetem_traffic import SatGoNetemTrafficAdapter
from satgonetem_gui.schemas import Hping3Request, Iperf3Request, PingRequest


def _flow(flow_class, status, results=None, error: str = "flow failed"):
    flow = object.__new__(flow_class)
    flow.status = lambda: status
    if results is None:
        flow.results = lambda: (_ for _ in ()).throw(RuntimeError(error))
    else:
        flow.results = lambda: results
    return flow


def _iperf_result() -> SimpleNamespace:
    return SimpleNamespace(
        protocol="TCP",
        duration_seconds=1,
        num_streams=1,
        avg_throughput_mbps=1.0,
        max_throughput_mbps=1.0,
        min_throughput_mbps=1.0,
        pmtu=1500,
        total_bytes_sent=100,
        total_bytes_received=100,
        total_retransmits=0,
        avg_rtt_ms=1.0,
        max_rtt_ms=1.0,
        _data={"intervals": []},
    )


def _ping_result() -> SimpleNamespace:
    return SimpleNamespace(
        packets_transmitted=1,
        packets_received=1,
        packet_loss_percent=0.0,
        reachable=True,
        rtt_min_ms=1.0,
        rtt_avg_ms=1.0,
        rtt_max_ms=1.0,
        rtt_mdev_ms=0.0,
    )


def _hping_result() -> SimpleNamespace:
    return SimpleNamespace(
        payload_bytes=56,
        seq=[1],
        rtt_ms=[1.0],
        cumulative_mbit=[1.0],
        packets_transmitted=1,
        packets_received=1,
        packet_loss_percent=0.0,
        rtt_min_ms=1.0,
        rtt_avg_ms=1.0,
        rtt_max_ms=1.0,
        reachable=True,
    )


def test_poll_running_for_all_flow_types() -> None:
    """Running flows normalize to the common running state."""
    adapter = SatGoNetemTrafficAdapter()

    assert adapter.poll(_flow(Iperf3Flow, FlowStatus.RUNNING)).status == "running"
    assert adapter.poll(_flow(PingFlow, PingStatus.RUNNING)).status == "running"
    assert adapter.poll(_flow(Hping3Flow, Hping3Status.RUNNING)).status == "running"


def test_poll_done_serializes_results() -> None:
    """Completed flows return their serialized result payloads."""
    adapter = SatGoNetemTrafficAdapter()

    iperf = adapter.poll(_flow(Iperf3Flow, FlowStatus.DONE, _iperf_result()))
    ping = adapter.poll(_flow(PingFlow, PingStatus.DONE, _ping_result()))
    hping = adapter.poll(_flow(Hping3Flow, Hping3Status.DONE, _hping_result()))

    assert iperf.status == "done"
    assert iperf.results is not None and iperf.results["protocol"] == "TCP"
    assert ping.results is not None and ping.results["reachable"] is True
    assert hping.results is not None and hping.results["packets_received"] == 1


def test_poll_error_reports_the_flow_error() -> None:
    """Failed flows surface the error from the result object."""
    adapter = SatGoNetemTrafficAdapter()

    poll = adapter.poll(_flow(Iperf3Flow, FlowStatus.ERROR))

    assert poll.status == "error"
    assert poll.error == "flow failed"


def test_start_methods_build_and_start_flows(monkeypatch) -> None:
    """The adapter constructs the concrete flow classes and starts them."""
    created = []

    class FakeFlow:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.started = False
            self.stopped = False
            created.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(adapter_module, "Iperf3Flow", FakeFlow)
    monkeypatch.setattr(adapter_module, "PingFlow", FakeFlow)
    monkeypatch.setattr(adapter_module, "Hping3Flow", FakeFlow)
    adapter = SatGoNetemTrafficAdapter()

    iperf = adapter.start_iperf3(object(), object(), Iperf3Request(src="a", dst="b"))
    ping = adapter.start_ping(object(), object(), PingRequest(src="a", dst="b"))
    hping = adapter.start_hping3(object(), object(), Hping3Request(src="a", dst="b"))

    assert len(created) == 3
    assert iperf.started and ping.started and hping.started
    adapter.stop(iperf)
    assert iperf.stopped is True


def test_poll_rejects_unknown_flow_types() -> None:
    """Unexpected flow objects are an explicit type error."""
    with pytest.raises(TypeError):
        SatGoNetemTrafficAdapter().poll(object())
