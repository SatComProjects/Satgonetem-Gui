"""Minimal decoy listener for teaching scan/login detection."""

import base64
import json
import shlex
from typing import Any

SCRIPT = r'''
import json
import socket
import sys
import time

port = int(sys.argv[1])
path = sys.argv[2]
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", port))
server.listen(20)
while True:
    client, address = server.accept()
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": time.time(),
                "peer": address[0],
                "source_port": address[1],
            }) + "\n")
    except OSError:
        pass
    try:
        client.sendall(b"SSH-2.0-OpenSSH_9.0\r\n")
    except OSError:
        pass
    client.close()
'''


class SatGoNetemHoneypotAdapter:
    """Start/stop a small decoy TCP listener inside a node."""

    def start(self, topology: Any, node_name: str, port: int) -> dict[str, Any]:
        node = self._resolve_node(topology, node_name)
        script_path = self._script_path(port)
        log_path = self._log_path(port)
        encoded = base64.b64encode(SCRIPT.encode("utf-8")).decode("ascii")
        command = (
            f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(script_path)}; "
            f"nohup python3 {shlex.quote(script_path)} {int(port)} "
            f"{shlex.quote(log_path)} >/dev/null 2>&1 & echo started"
        )
        node.execute_command(["sh", "-lc", command])
        return self.status(topology, node_name, port)

    def status(self, topology: Any, node_name: str, port: int) -> dict[str, Any]:
        node = self._resolve_node(topology, node_name)
        marker = f"[s]gnt_honeypot_{int(port)}.py"
        output = node.execute_command(
            [
                "sh",
                "-lc",
                f"pgrep -f {shlex.quote(marker)} >/dev/null 2>&1 "
                "&& echo running || echo stopped",
            ]
        )
        running = output.strip() == "running"
        events = []
        try:
            log = node.execute_command(
                ["sh", "-lc", f"tail -n 100 {shlex.quote(self._log_path(port))}"]
            )
        except Exception:
            log = ""
        for line in log.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(
                {
                    "timestamp": float(event.get("timestamp", 0.0)),
                    "peer": str(event.get("peer", "")),
                    "source_port": int(event.get("source_port", 0)),
                }
            )
        return {
            "node": node_name,
            "port": int(port),
            "running": running,
            "events": events,
        }

    def stop(self, topology: Any, node_name: str, port: int) -> None:
        node = self._resolve_node(topology, node_name)
        marker = f"[s]gnt_honeypot_{int(port)}.py"
        node.execute_command(
            ["sh", "-lc", f"pkill -f {shlex.quote(marker)} 2>/dev/null || true"]
        )

    @staticmethod
    def _script_path(port: int) -> str:
        return f"/tmp/sgnt_honeypot_{int(port)}.py"

    @staticmethod
    def _log_path(port: int) -> str:
        return f"/tmp/sgnt_honeypot_{int(port)}.log"

    @staticmethod
    def _resolve_node(topology: Any, name: str) -> Any:
        node = topology.get_node_by_name(name)
        if node is None:
            raise ValueError(f"Node not found: {name}")
        if getattr(node, "container", None) is None:
            raise ValueError(f"Node is not running: {name}")
        return node
