"""SatGoNetem traffic adapter.

This is the only module that imports concrete traffic-flow classes.
"""

import logging
from typing import Any

from satgonetem.traffic import (
    FlowStatus,
    Hping3Config,
    Hping3Flow,
    Hping3Status,
    Iperf3Config,
    Iperf3Flow,
    PingConfig,
    PingFlow,
    PingStatus,
)

from ..schemas import Hping3Request, Iperf3Request, PingRequest
from ..serializers import (
    serialize_hping3_results,
    serialize_iperf3_results,
    serialize_ping_results,
)
from ..services.ports import TrafficPoll

logger = logging.getLogger(__name__)


class SatGoNetemTrafficAdapter:
    """Concrete adapter for iperf3, ping, and hping3 flows."""

    def __init__(self) -> None:
        self._pollers = {
            "iperf3": self._poll_iperf3,
            "ping": self._poll_ping,
            "hping3": self._poll_hping3,
        }

    def start_iperf3(
        self,
        source: Any,
        destination: Any,
        request: Iperf3Request,
    ) -> Any:
        """Start an iperf3 flow."""
        config = Iperf3Config(
            protocol=request.protocol,
            duration=request.duration,
            bandwidth_mbps=request.bandwidth_mbps,
            parallel=request.parallel,
            interval=request.interval,
            port=request.port,
            congestion_control=request.congestion_control,
            window_size=request.window_size or None,
            bidir=request.bidir,
        )
        flow = Iperf3Flow(source, destination, config, delay=0.0)
        flow.start()
        return flow

    def start_ping(
        self,
        source: Any,
        destination: Any,
        request: PingRequest,
    ) -> Any:
        """Start a ping flow."""
        config = PingConfig(
            count=request.count,
            timeout_sec=request.timeout_sec,
            interval_sec=request.interval_sec,
            packet_size=request.packet_size,
        )
        flow = PingFlow(source, destination, config, delay=0.0)
        flow.start()
        return flow

    def start_hping3(
        self,
        source: Any,
        destination: Any,
        request: Hping3Request,
    ) -> Any:
        """Start an hping3 flow."""
        config = Hping3Config(
            proto=request.proto,
            dport=request.dport,
            count=request.count,
            size=request.size,
            rate_type=request.rate_type,
            interval=request.interval,
            flags=request.flags,
        )
        flow = Hping3Flow(source, destination, config, delay=0.0)
        flow.start()
        return flow

    def poll(self, kind: str, flow: Any) -> TrafficPoll:
        """Return normalized flow state and serialized results."""
        poller = self._pollers.get(kind)
        if poller is None:
            raise ValueError(f"Unsupported traffic kind: {kind!r}")
        return poller(flow)

    def stop(self, flow: Any) -> None:
        """Stop a running flow if it supports termination."""
        stop = getattr(flow, "stop", None)
        if callable(stop):
            stop()

    @staticmethod
    def _poll_iperf3(flow: Iperf3Flow) -> TrafficPoll:
        status = flow.status()
        if status == FlowStatus.RUNNING:
            return TrafficPoll("running")
        if status == FlowStatus.DONE:
            try:
                result = flow.results()
                raw = getattr(result, "_data", None)
                if not isinstance(raw, dict):
                    raise RuntimeError(
                        "Unsupported Iperf3Results shape: missing interval data."
                    )
                intervals = raw.get("intervals")
                if not isinstance(intervals, list):
                    raise RuntimeError(
                        "Unsupported Iperf3Results shape: missing interval data."
                    )
                return TrafficPoll(
                    "done",
                    results=serialize_iperf3_results(result, intervals),
                )
            except Exception as exc:
                logger.exception("Failed to read iperf3 results.")
                return TrafficPoll("error", error=str(exc))
        if status == FlowStatus.ERROR:
            try:
                flow.results()
            except Exception as exc:
                return TrafficPoll("error", error=str(exc))
            return TrafficPoll("error", error="Unknown error.")
        return TrafficPoll("error", error="Unknown flow state.")

    @staticmethod
    def _poll_ping(flow: PingFlow) -> TrafficPoll:
        status = flow.status()
        if status == PingStatus.RUNNING:
            return TrafficPoll("running")
        if status == PingStatus.DONE:
            try:
                return TrafficPoll("done", results=serialize_ping_results(flow.results()))
            except Exception as exc:
                logger.exception("Failed to read ping results.")
                return TrafficPoll("error", error=str(exc))
        if status == PingStatus.ERROR:
            try:
                flow.results()
            except Exception as exc:
                return TrafficPoll("error", error=str(exc))
            return TrafficPoll("error", error="Unknown error.")
        return TrafficPoll("error", error="Unknown flow state.")

    @staticmethod
    def _poll_hping3(flow: Hping3Flow) -> TrafficPoll:
        status = flow.status()
        if status == Hping3Status.RUNNING:
            return TrafficPoll("running")
        if status == Hping3Status.DONE:
            try:
                return TrafficPoll("done", results=serialize_hping3_results(flow.results()))
            except Exception as exc:
                logger.exception("Failed to read hping3 results.")
                return TrafficPoll("error", error=str(exc))
        if status == Hping3Status.ERROR:
            try:
                flow.results()
            except Exception as exc:
                return TrafficPoll("error", error=str(exc))
            return TrafficPoll("error", error="Unknown error.")
        return TrafficPoll("error", error="Unknown flow state.")
