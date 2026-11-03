"""SatGoNetem security adapter: link failure and packet capture.

The security service owns lab state and policy. This adapter is the only place
that touches container commands for the security section.
"""

import base64
import secrets
import shlex
from typing import Any

from ..links import link_key
from ..services.ports import NetworkOperationError


class SatGoNetemSecurityAdapter:
    """Concrete link-failure and packet-capture operations."""

    def routing_methods(self, topology: Any) -> list[str]:
        """Return the routing methods the loaded topology supports."""
        getter = getattr(topology, "get_allowed_routing_methods", None)
        if callable(getter):
            return list(getter())
        return ["static", "dynamic-ospf", "dynamic-isis", "sr-mpls"]

    def fail_link(self, topology: Any, key: str) -> dict[str, Any]:
        """Remove one link from the simulated topology by its stable key."""
        links = getattr(topology, "links", {})
        for link in links.values():
            if link_key(link) != key:
                continue
            try:
                topology.simulate_link_failure(link)
            except Exception as exc:
                raise NetworkOperationError(f"Could not fail link: {exc}") from exc
            return {
                "key": key,
                "src": getattr(link.source, "name", ""),
                "dst": getattr(link.target, "name", ""),
                "type": getattr(link, "type", ""),
            }
        raise KeyError(key)

    def start_capture(
        self,
        topology: Any,
        node: str,
        interface: str,
        packet_limit: int,
        duration_sec: int,
    ) -> dict[str, Any]:
        """Start a bounded tcpdump process on one node interface."""
        target = self._resolve_node(topology, node)
        iface = self._resolve_interface(target, interface)
        token = secrets.token_hex(8)
        path = f"/tmp/satsec_{token}.pcap"
        command = (
            f"timeout {int(duration_sec)} tcpdump -i {shlex.quote(iface)} "
            f"-s 0 -c {int(packet_limit)} -w {shlex.quote(path)}"
        )
        try:
            target.execute_command(["sh", "-lc", command], detach=True)
        except Exception as exc:
            raise NetworkOperationError(f"Could not start capture: {exc}") from exc
        return {"path": path, "token": token, "interface": iface}

    def stop_capture(self, topology: Any, node: str, path: str) -> None:
        """Stop the tcpdump process associated with a capture path."""
        target = self._resolve_node(topology, node)
        marker = f"tcpdump.*{shlex.quote(path)}"
        try:
            target.execute_command(
                ["sh", "-lc", f"pkill -f {marker} 2>/dev/null || true"]
            )
        except Exception as exc:
            raise NetworkOperationError(f"Could not stop capture: {exc}") from exc

    def capture_status(
        self,
        topology: Any,
        node: str,
        path: str,
    ) -> dict[str, Any]:
        """Return capture size and whether a matching tcpdump is still running."""
        target = self._resolve_node(topology, node)
        quoted = shlex.quote(path)
        command = (
            f"size=0; [ -f {quoted} ] && size=$(stat -c %s {quoted}); "
            f"if pgrep -f {shlex.quote('tcpdump.*' + path)} >/dev/null 2>&1; "
            "then running=1; else running=0; fi; "
            'echo "$size $running"'
        )
        try:
            output = target.execute_command(["sh", "-lc", command])
        except Exception as exc:
            raise NetworkOperationError(f"Could not read capture status: {exc}") from exc

        parts = (output or "0 0").split()
        size = int(parts[0]) if parts and parts[0].isdigit() else 0
        running = len(parts) > 1 and parts[1] == "1"
        return {"size_bytes": size, "running": running}

    def read_capture(self, topology: Any, node: str, path: str) -> bytes:
        """Read a capture as bytes through the node command channel."""
        target = self._resolve_node(topology, node)
        try:
            encoded = target.execute_command(
                ["sh", "-lc", f"base64 {shlex.quote(path)}"]
            )
        except Exception as exc:
            raise NetworkOperationError(f"Could not read capture: {exc}") from exc
        try:
            return base64.b64decode("".join(encoded.split()))
        except Exception as exc:
            raise NetworkOperationError("Capture file is not valid base64.") from exc

    def delete_capture(self, topology: Any, node: str, path: str) -> None:
        """Remove a capture file from the node container."""
        target = self._resolve_node(topology, node)
        try:
            target.execute_command(["sh", "-lc", f"rm -f {shlex.quote(path)}"])
        except Exception as exc:
            raise NetworkOperationError(f"Could not remove capture: {exc}") from exc

    @staticmethod
    def _resolve_node(topology: Any, name: str) -> Any:
        node = topology.get_node_by_name(name)
        if node is None:
            raise ValueError(f"Node not found: {name}")
        if getattr(node, "container", None) is None:
            raise ValueError(f"Node is not running: {name}")
        return node

    @staticmethod
    def _resolve_interface(node: Any, requested: str) -> str:
        for interface in getattr(node, "interfaces", []):
            name = getattr(interface, "name", "")
            iname = ""
            get_iname = getattr(interface, "get_iname", None)
            if callable(get_iname):
                iname = get_iname() or ""
            if requested in (name, iname):
                return iname or name
        raise ValueError(f"Interface not found: {requested}")
