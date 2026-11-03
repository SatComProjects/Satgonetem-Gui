"""Node/link telemetry adapter for the security detection layer."""

import hashlib
import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..links import link_key

STAT_NAMES = (
    "rx_bytes",
    "tx_bytes",
    "rx_packets",
    "tx_packets",
    "rx_dropped",
    "tx_dropped",
    "rx_errors",
    "tx_errors",
)


class SatGoNetemTelemetryAdapter:
    """Read interface counters, routes, and protocol state from nodes."""

    def sample(self, topology: Any) -> dict[str, Any]:
        """Return raw cumulative counters and route/protocol state."""
        nodes = list(topology.satellites.values()) + list(
            topology.ground_stations.values()
        )
        routing = getattr(topology, "routing", "static")
        node_metrics: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(nodes)))) as pool:
            futures = {
                pool.submit(self._sample_node, node, routing): node for node in nodes
            }
            for future in as_completed(futures):
                node_metrics.append(future.result())
        node_metrics.sort(key=lambda item: item["name"])
        by_node = {item["name"]: item for item in node_metrics}
        links = [
            self._sample_link(link, by_node)
            for link in topology.links.values()
        ]
        links.sort(key=lambda item: item["key"])
        return {"nodes": node_metrics, "links": links}

    def _sample_node(self, node: Any, routing: str) -> dict[str, Any]:
        try:
            interfaces = self._interface_stats(node)
        except Exception as exc:
            return {
                "name": node.name,
                "type": self._node_type(node),
                "interfaces": [],
                "route_count": 0,
                "route_hash": "",
                "protocols": [],
                "tcp_in_segs": 0,
                "tcp_out_rsts": 0,
                "tcp_retrans_segs": 0,
                "udp_in_datagrams": 0,
                "icmp_in_msgs": 0,
                "error": str(exc),
            }
        routes: list[str] = []
        try:
            routes = list(node.get_routing_table())
        except Exception:
            routes = []
        protocols = self._protocol_states(node, routing)
        counters = self._kernel_counters(node)
        route_hash = hashlib.sha1("\n".join(routes).encode("utf-8")).hexdigest()
        return {
            "name": node.name,
            "type": self._node_type(node),
            "interfaces": interfaces,
            "route_count": len(routes),
            "route_hash": route_hash,
            "protocols": protocols,
            "tcp_in_segs": counters["tcp_in_segs"],
            "tcp_out_rsts": counters["tcp_out_rsts"],
            "tcp_retrans_segs": counters["tcp_retrans_segs"],
            "udp_in_datagrams": counters["udp_in_datagrams"],
            "icmp_in_msgs": counters["icmp_in_msgs"],
            "error": None,
        }

    def _interface_stats(self, node: Any) -> list[dict[str, Any]]:
        interfaces = []
        for interface in getattr(node, "interfaces", []):
            iname = self._interface_name(interface)
            if iname:
                interfaces.append((interface, iname))
        if not interfaces:
            return []
        names = " ".join(shlex.quote(iname) for _, iname in interfaces)
        script = (
            f"for i in {names}; do "
            'base="/sys/class/net/$i/statistics"; '
            'printf "%s " "$i"; '
            "for f in "
            + " ".join(STAT_NAMES)
            + '; do if [ -r "$base/$f" ]; then cat "$base/$f"; '
            'else echo 0; fi; done; done'
        )
        output = node.execute_command(["sh", "-lc", script])
        parsed: dict[str, list[int]] = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 1 + len(STAT_NAMES):
                continue
            values = []
            for value in parts[1 : 1 + len(STAT_NAMES)]:
                values.append(int(value) if value.isdigit() else 0)
            parsed[parts[0]] = values
        result = []
        for interface, iname in interfaces:
            values = parsed.get(iname, [0] * len(STAT_NAMES))
            data = dict(zip(STAT_NAMES, values))
            result.append(
                {
                    "name": interface.name,
                    "iname": iname,
                    **data,
                    "rx_mbps": 0.0,
                    "tx_mbps": 0.0,
                }
            )
        return result

    def _kernel_counters(self, node: Any) -> dict[str, int]:
        counters = {
            "tcp_in_segs": 0,
            "tcp_out_rsts": 0,
            "tcp_retrans_segs": 0,
            "udp_in_datagrams": 0,
            "icmp_in_msgs": 0,
        }
        try:
            output = node.execute_command(["sh", "-lc", "cat /proc/net/snmp"])
        except Exception:
            return counters
        lines = output.splitlines()
        for index in range(0, len(lines) - 1):
            header = lines[index].split()
            values = lines[index + 1].split()
            if not header or not values or header[0] != values[0]:
                continue
            mapping = dict(zip(header[1:], values[1:]))
            if header[0] == "Tcp:":
                counters["tcp_in_segs"] = int(mapping.get("InSegs", 0))
                counters["tcp_out_rsts"] = int(mapping.get("OutRsts", 0))
                counters["tcp_retrans_segs"] = int(mapping.get("RetransSegs", 0))
            elif header[0] == "Udp:":
                counters["udp_in_datagrams"] = int(mapping.get("InDatagrams", 0))
            elif header[0] == "Icmp:":
                counters["icmp_in_msgs"] = int(mapping.get("InMsgs", 0))
        return counters

    def _protocol_states(self, node: Any, routing: str) -> list[str]:
        if routing not in {"dynamic-ospf", "dynamic-isis"}:
            return []
        try:
            output = node.execute_command(["birdc", "show", "protocols"])
        except Exception:
            return []
        lines = []
        for line in output.splitlines():
            lowered = line.lower()
            if "ospf" in lowered or "isis" in lowered:
                lines.append(" ".join(line.split()))
        return lines[:20]

    def _sample_link(self, link: Any, by_node: dict[str, dict[str, Any]]) -> dict[str, Any]:
        stats = []
        for interface in getattr(link, "peer_interfaces", []):
            iname = self._interface_name(interface)
            for endpoint in (link.source, link.target):
                endpoint_iface = next(
                    (
                        item
                        for item in getattr(endpoint, "interfaces", [])
                        if item is interface or item.name == interface.name
                    ),
                    None,
                )
                if endpoint_iface is None:
                    continue
                node_stats = by_node.get(endpoint.name)
                if node_stats is None:
                    continue
                for item in node_stats["interfaces"]:
                    if item["iname"] == iname or item["name"] == interface.name:
                        stats.append(item)
                        break
        budget = None
        config = getattr(link, "link_budget_config", None)
        if config is not None:
            budget = {
                "enabled": bool(getattr(link, "use_budget", False)),
                "downlink_freq_ghz": config.downlink_freq_ghz,
                "uplink_freq_ghz": config.uplink_freq_ghz,
                "bandwidth_hz_downlink": config.bandwidth_hz_downlink,
                "bandwidth_hz_uplink": config.bandwidth_hz_uplink,
            }
        return {
            "key": link_key(link),
            "src": link.source.name,
            "dst": link.target.name,
            "type": link.type,
            "capacity_kbps": int(link.get_capacity() or 0),
            "delay_ms": int(getattr(link, "delay", 0) or 0),
            "state": "active" if getattr(link, "is_active", True) else "inactive",
            "rx_bytes": sum(item["rx_bytes"] for item in stats),
            "tx_bytes": sum(item["tx_bytes"] for item in stats),
            "rx_mbps": 0.0,
            "tx_mbps": 0.0,
            "rx_dropped": sum(item["rx_dropped"] for item in stats),
            "tx_dropped": sum(item["tx_dropped"] for item in stats),
            "rx_errors": sum(item["rx_errors"] for item in stats),
            "tx_errors": sum(item["tx_errors"] for item in stats),
            "budget": budget,
        }

    @staticmethod
    def _interface_name(interface: Any) -> str:
        get_iname = getattr(interface, "get_iname", None)
        if callable(get_iname):
            return get_iname() or getattr(interface, "name", "")
        return getattr(interface, "name", "")

    @staticmethod
    def _node_type(node: Any) -> str:
        return "satellite" if node.name.startswith("Sat") else "ground_station"
