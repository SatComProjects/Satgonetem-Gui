"""Telemetry sampling, anomaly detection, and alert history."""

import statistics
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable

from ..errors import APIError
from .ports import NetworkOperationError, TelemetryGateway
from .topology_service import TopologyService


class TelemetryService:
    """Turn raw node/link counters into rates, alerts, and baselines."""

    def __init__(
        self,
        topology: TopologyService,
        gateway: TelemetryGateway,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.topology = topology
        self.gateway = gateway
        self.clock = clock
        self._lock = threading.RLock()
        self._previous: dict[str, Any] | None = None
        self._previous_time: float | None = None
        self._samples = 0
        self._baselines: dict[str, deque[float]] = {}
        self._alerts: deque[dict[str, Any]] = deque(maxlen=200)
        self._last_alert: dict[tuple[str, str, str], float] = {}

    def sample(self) -> dict[str, Any]:
        """Sample the range and update baselines/alerts."""
        topology = self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        with self._lock:
            try:
                raw = self.gateway.sample(topology)
            except NetworkOperationError as exc:
                raise APIError(500, str(exc)) from exc
            except Exception as exc:
                raise APIError(500, f"Telemetry sample failed: {exc}") from exc

            now = self.clock()
            interval = now - self._previous_time if self._previous_time is not None else 0.0
            nodes = self._with_node_rates(raw["nodes"], interval)
            links = self._with_link_rates(raw["links"], interval)
            if self._previous is not None:
                self._detect(self._previous, raw, links, interval, now)
            self._update_baselines(links, now)
            self._previous = raw
            self._previous_time = now
            self._samples += 1
            return {
                "sampled_at": now,
                "interval_seconds": round(interval, 3),
                "nodes": nodes,
                "links": links,
                "alerts": list(self._alerts)[:100],
                "baseline_samples": self._samples,
            }

    def clear_alerts(self) -> None:
        """Drop the alert history."""
        with self._lock:
            self._alerts.clear()
            self._last_alert.clear()

    def prometheus(self) -> str:
        """Return the latest sample as Prometheus text metrics."""
        data = self.sample()
        lines = [
            "# HELP sgnt_interface_rx_mbps Receive rate per node interface.",
            "# TYPE sgnt_interface_rx_mbps gauge",
        ]
        for node in data["nodes"]:
            for interface in node["interfaces"]:
                labels = f'node="{node["name"]}",interface="{interface["iname"]}"'
                lines.append(f"sgnt_interface_rx_mbps{{{labels}}} {interface['rx_mbps']}")
                lines.append(f"sgnt_interface_tx_mbps{{{labels}}} {interface['tx_mbps']}")
                lines.append(f"sgnt_interface_rx_dropped{{{labels}}} {interface['rx_dropped']}")
                lines.append(f"sgnt_interface_tx_dropped{{{labels}}} {interface['tx_dropped']}")
                lines.append(f"sgnt_interface_rx_errors{{{labels}}} {interface['rx_errors']}")
                lines.append(f"sgnt_interface_tx_errors{{{labels}}} {interface['tx_errors']}")
                lines.append(f"sgnt_interface_rx_packets{{{labels}}} {interface['rx_packets']}")
                lines.append(f"sgnt_interface_tx_packets{{{labels}}} {interface['tx_packets']}")
            lines.append(
                f'sgnt_node_tcp_retrans_segs{{node="{node["name"]}"}} {node["tcp_retrans_segs"]}'
            )
        lines.extend(
            [
                "# HELP sgnt_link_capacity_kbps Configured link capacity.",
                "# TYPE sgnt_link_capacity_kbps gauge",
            ]
        )
        for link in data["links"]:
            labels = f'src="{link["src"]}",dst="{link["dst"]}"'
            lines.append(f"sgnt_link_capacity_kbps{{{labels}}} {link['capacity_kbps']}")
            lines.append(f"sgnt_link_rx_mbps{{{labels}}} {link['rx_mbps']}")
            lines.append(f"sgnt_link_tx_mbps{{{labels}}} {link['tx_mbps']}")
            lines.append(f"sgnt_link_rx_dropped{{{labels}}} {link['rx_dropped']}")
            lines.append(f"sgnt_link_tx_dropped{{{labels}}} {link['tx_dropped']}")
            lines.append(f"sgnt_link_rx_errors{{{labels}}} {link['rx_errors']}")
            lines.append(f"sgnt_link_tx_errors{{{labels}}} {link['tx_errors']}")
        lines.append(f"sgnt_alerts_total {len(data['alerts'])}")
        return "\n".join(lines) + "\n"

    def _with_node_rates(
        self, nodes: list[dict[str, Any]], interval: float
    ) -> list[dict[str, Any]]:
        previous = {node["name"]: node for node in (self._previous or {}).get("nodes", [])}
        result = []
        for node in nodes:
            node_copy = dict(node)
            node_copy["interfaces"] = []
            prior_node = previous.get(node["name"], {})
            prior_ifaces = {item["iname"]: item for item in prior_node.get("interfaces", [])}
            for interface in node["interfaces"]:
                item = dict(interface)
                prior = prior_ifaces.get(item["iname"], {})
                item["rx_mbps"] = self._rate(item["rx_bytes"], prior.get("rx_bytes", 0), interval)
                item["tx_mbps"] = self._rate(item["tx_bytes"], prior.get("tx_bytes", 0), interval)
                node_copy["interfaces"].append(item)
            result.append(node_copy)
        return result

    def _with_link_rates(
        self, links: list[dict[str, Any]], interval: float
    ) -> list[dict[str, Any]]:
        previous = {link["key"]: link for link in (self._previous or {}).get("links", [])}
        result = []
        for link in links:
            item = dict(link)
            prior = previous.get(link["key"], {})
            item["rx_mbps"] = self._rate(
                item.get("rx_bytes", 0), prior.get("rx_bytes", 0), interval
            )
            item["tx_mbps"] = self._rate(
                item.get("tx_bytes", 0), prior.get("tx_bytes", 0), interval
            )
            result.append(item)
        return result

    @staticmethod
    def _rate(current: int, previous: int, interval: float) -> float:
        if interval <= 0:
            return 0.0
        delta = max(0, int(current) - int(previous))
        return round(delta * 8.0 / 1_000_000.0 / interval, 3)

    def _detect(
        self,
        previous: dict[str, Any],
        current: dict[str, Any],
        links: list[dict[str, Any]],
        interval: float,
        now: float,
    ) -> None:
        prior_nodes = {node["name"]: node for node in previous.get("nodes", [])}
        for node in current["nodes"]:
            prior = prior_nodes.get(node["name"])
            if prior is None:
                continue
            if node["route_hash"] != prior["route_hash"]:
                delta = node["route_count"] - prior["route_count"]
                self._add_alert(
                    "warning",
                    node["name"],
                    "route_change",
                    f"route table changed ({delta:+d} entries)",
                    float(delta),
                    now,
                )
            if node["protocols"] != prior["protocols"]:
                self._add_alert(
                    "warning",
                    node["name"],
                    "protocol_change",
                    "routing protocol state changed",
                    1.0,
                    now,
                )
            for interface in node["interfaces"]:
                prior_iface = next(
                    (item for item in prior["interfaces"] if item["iname"] == interface["iname"]),
                    None,
                )
                if prior_iface is None:
                    continue
                rx_drops = max(0, interface["rx_dropped"] - prior_iface["rx_dropped"])
                tx_drops = max(0, interface["tx_dropped"] - prior_iface["tx_dropped"])
                errors = max(0, interface["rx_errors"] - prior_iface["rx_errors"]) + max(
                    0, interface["tx_errors"] - prior_iface["tx_errors"]
                )
                if rx_drops + tx_drops > 0:
                    self._add_alert(
                        "warning",
                        node["name"],
                        f"drops:{interface['iname']}",
                        f"{rx_drops + tx_drops} interface drops in {interval:.1f}s",
                        float(rx_drops + tx_drops),
                        now,
                    )
                if errors > 0:
                    self._add_alert(
                        "warning",
                        node["name"],
                        f"errors:{interface['iname']}",
                        f"{errors} interface errors in {interval:.1f}s",
                        float(errors),
                        now,
                    )
            if interval > 0:
                rst_rate = max(0, node["tcp_out_rsts"] - prior["tcp_out_rsts"]) / interval
                udp_rate = max(0, node["udp_in_datagrams"] - prior["udp_in_datagrams"]) / interval
                icmp_rate = max(0, node["icmp_in_msgs"] - prior["icmp_in_msgs"]) / interval
                retrans_rate = (
                    max(0, node["tcp_retrans_segs"] - prior["tcp_retrans_segs"]) / interval
                )
                if rst_rate > 100:
                    self._add_alert(
                        "warning",
                        node["name"],
                        "tcp_rst_rate",
                        f"TCP RST rate {rst_rate:.0f}/s",
                        round(rst_rate, 2),
                        now,
                    )
                if udp_rate > 2000:
                    self._add_alert(
                        "warning",
                        node["name"],
                        "udp_rate",
                        f"UDP receive rate {udp_rate:.0f}/s",
                        round(udp_rate, 2),
                        now,
                    )
                if icmp_rate > 500:
                    self._add_alert(
                        "warning",
                        node["name"],
                        "icmp_rate",
                        f"ICMP receive rate {icmp_rate:.0f}/s",
                        round(icmp_rate, 2),
                        now,
                    )
                if retrans_rate > 50:
                    self._add_alert(
                        "warning",
                        node["name"],
                        "tcp_retrans_rate",
                        f"TCP retransmission rate {retrans_rate:.0f}/s",
                        round(retrans_rate, 2),
                        now,
                    )
        prior_links = {link["key"]: link for link in previous.get("links", [])}
        for link in links:
            prior = prior_links.get(link["key"])
            if prior is None:
                continue
            if link["state"] != prior["state"]:
                self._add_alert(
                    "critical",
                    link["src"],
                    f"link_state:{link['key']}",
                    f"link {link['src']} -> {link['dst']} is {link['state']}",
                    1.0,
                    now,
                )
            capacity_mbps = link["capacity_kbps"] / 1000.0
            usage = max(link["rx_mbps"], link["tx_mbps"])
            if capacity_mbps > 0 and usage > capacity_mbps * 0.9:
                self._add_alert(
                    "warning",
                    link["src"],
                    f"link_util:{link['key']}",
                    f"link {link['src']} -> {link['dst']} above 90% capacity",
                    round(usage, 3),
                    now,
                )

    def _update_baselines(self, links: list[dict[str, Any]], now: float) -> None:
        for link in links:
            key = link["key"]
            values = self._baselines.setdefault(key, deque(maxlen=30))
            usage = max(link["rx_mbps"], link["tx_mbps"])
            if len(values) >= 5:
                mean = statistics.mean(values)
                deviation = statistics.pstdev(values)
                if mean > 0.2 and usage > mean + max(0.3, 3 * deviation):
                    self._add_alert(
                        "warning",
                        link["src"],
                        f"link_spike:{key}",
                        f"throughput spike on {link['src']} -> {link['dst']}: {usage:.2f} Mbps",
                        usage,
                        now,
                    )
                elif mean > 0.2 and usage < mean * 0.25:
                    self._add_alert(
                        "warning",
                        link["src"],
                        f"link_drop:{key}",
                        f"throughput drop on {link['src']} -> {link['dst']}: {usage:.2f} Mbps",
                        usage,
                        now,
                    )
            values.append(usage)

    def _add_alert(
        self,
        severity: str,
        node: str,
        metric: str,
        message: str,
        value: float | None,
        now: float,
    ) -> None:
        key = (node, metric, message)
        if now - self._last_alert.get(key, 0.0) < 20.0:
            return
        self._last_alert[key] = now
        self._alerts.appendleft(
            {
                "id": f"a{uuid.uuid4().hex[:10]}",
                "timestamp": now,
                "severity": severity,
                "node": node,
                "metric": metric,
                "message": message,
                "value": value,
            }
        )
