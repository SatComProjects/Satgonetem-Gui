"""SatGoNetEm node policy adapter: firewall, QoS, and rollback.

The policy is generated as explicit iptables/ip6tables and tc commands. The
adapter owns container command execution so the service layer never builds
shell strings from request data.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from ..schemas import NodePolicyRequest
from ..services.ports import NetworkOperationError

CHAIN_IN = "SGNT_IN"
CHAIN_OUT = "SGNT_OUT"
CHAIN_RAW = "SGNT_RAW"
CHAIN_RAWOUT = "SGNT_RAWOUT"
CHAIN_MANGLE = "SGNT_MANGLE"


@dataclass
class _Command:
    argv: list[str]
    display: str
    ignore_errors: bool = False


@dataclass
class _Plan:
    commands: list[_Command] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)


class SatGoNetemPolicyAdapter:
    """Apply and inspect per-node firewall and QoS policies."""

    def preview(self, topology: Any, policy: NodePolicyRequest) -> dict[str, Any]:
        """Return the planned commands without touching the node."""
        node = self._resolve_node(topology, policy.node, require_running=False)
        plan = self._build_plan(node, policy)
        current: dict[str, Any] = {"rules": []}
        if getattr(node, "container", None) is not None:
            current = self.status(topology, policy.node)
        diff = [f"- {rule['rule']}" for rule in current.get("rules", [])]
        diff.extend(f"+ {command.display}" for command in plan.commands)
        return {
            "node": policy.node,
            "family": policy.family,
            "commands": [command.display for command in plan.commands],
            "diff": diff,
            "warnings": plan.warnings,
        }

    def apply(self, topology: Any, policy: NodePolicyRequest) -> dict[str, Any]:
        """Apply a policy, replacing any previous policy on the node."""
        node = self._resolve_node(topology, policy.node)
        plan = self._build_plan(node, policy)
        self._clear_tc(node, plan.interfaces)
        try:
            self._restore_base(node, policy.family)
            self._cleanup_chains(node, policy.family)
            self._save_backup(node, policy.family)
            for command in plan.commands:
                try:
                    self._run(node, command.argv)
                except Exception:
                    if command.ignore_errors:
                        continue
                    raise
        except Exception as exc:
            try:
                self._restore_base(node, policy.family)
                self._cleanup_chains(node, policy.family)
                self._clear_tc(node, plan.interfaces)
            except Exception:
                pass
            raise NetworkOperationError(f"Could not apply policy: {exc}") from exc
        return self.status(topology, policy.node)

    def clear(
        self,
        topology: Any,
        node_name: str,
        interfaces: list[str] | None = None,
    ) -> None:
        """Remove the managed policy and restore the pre-policy ruleset."""
        node = self._resolve_node(topology, node_name)
        self._clear_tc(node, interfaces or [])
        try:
            self._cleanup_chains(node, "ipv4")
            self._cleanup_chains(node, "ipv6")
            for family in ("ipv4", "ipv6"):
                self._restore_base(node, family)
            self._remove_backup(node, "ipv4")
            self._remove_backup(node, "ipv6")
        except Exception as exc:
            raise NetworkOperationError(f"Could not clear policy: {exc}") from exc

    def status(self, topology: Any, node_name: str) -> dict[str, Any]:
        """Return whether the IPv4 policy chain exists and its counters."""
        node = self._resolve_node(topology, node_name)
        applied = False
        family = "ipv4"
        binary = "iptables"
        rules: list[dict[str, Any]] = []
        for candidate, candidate_family in (
            ("iptables", "ipv4"),
            ("ip6tables", "ipv6"),
        ):
            try:
                node.execute_command([candidate, "-w", "-S", CHAIN_IN])
            except RuntimeError:
                continue
            except Exception as exc:
                raise NetworkOperationError(
                    f"Could not read policy status: {exc}"
                ) from exc
            applied = True
            family = candidate_family
            binary = candidate
            break
        if applied:
            try:
                rules = self._read_chain_counters(node, binary)
            except Exception as exc:
                raise NetworkOperationError(
                    f"Could not read policy counters: {exc}"
                ) from exc
        qos = []
        for interface in getattr(node, "interfaces", []):
            name = self._interface_name(interface)
            if not name:
                continue
            try:
                output = node.execute_command(["tc", "qdisc", "show", "dev", name])
            except Exception:
                continue
            if "ffff:" in output:
                qos.append(name)
        return {
            "node": node_name,
            "applied": applied,
            "family": family,
            "chain": CHAIN_IN if applied else None,
            "rules": rules,
            "qos": qos,
        }

    def _build_plan(self, node: Any, policy: NodePolicyRequest) -> _Plan:
        binary = "ip6tables" if policy.family == "ipv6" else "iptables"
        plan = _Plan()
        icmp_proto = "ipv6-icmp" if policy.family == "ipv6" else "icmp"
        reject_with = (
            "icmp6-port-unreachable"
            if policy.family == "ipv6"
            else "icmp-port-unreachable"
        )

        def ipt(*args: str, table: str | None = None, ignore_errors: bool = False):
            argv = [binary, "-w"]
            if table:
                argv += ["-t", table]
            argv += list(args)
            plan.commands.append(
                _Command(argv, shlex.join(argv), ignore_errors=ignore_errors)
            )

        def tc(*args: str, ignore_errors: bool = False):
            argv = ["tc", *args]
            plan.commands.append(
                _Command(argv, shlex.join(argv), ignore_errors=ignore_errors)
            )

        ipt("-N", CHAIN_IN)
        ipt("-I", "INPUT", "1", "-j", CHAIN_IN)
        if policy.allow_loopback:
            ipt("-A", CHAIN_IN, "-i", "lo", "-j", "ACCEPT")
        if policy.allow_established:
            ipt(
                "-A",
                CHAIN_IN,
                "-m",
                "conntrack",
                "--ctstate",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            )
        if policy.allow_icmp:
            ipt("-A", CHAIN_IN, "-p", icmp_proto, "-j", "ACCEPT")

        self._add_allowlist(
            ipt,
            policy.management_sources,
            policy.management_ports,
            policy.management_protocol,
        )
        self._add_allowlist(
            ipt,
            policy.ttc_sources,
            policy.ttc_ports,
            policy.ttc_protocol,
        )
        self._add_allowlist(
            ipt,
            policy.telemetry_sources,
            policy.telemetry_ports,
            policy.telemetry_protocol,
        )
        if not policy.management_sources and policy.management_ports:
            plan.warnings.append(
                "Management ports have no management sources; no rule was generated."
            )
        if not policy.ttc_sources and policy.ttc_ports:
            plan.warnings.append("TTC ports have no TTC sources; no rule was generated.")
        if not policy.telemetry_sources and policy.telemetry_ports:
            plan.warnings.append(
                "Telemetry ports have no telemetry sources; no rule was generated."
            )
        if policy.default_inbound == "drop" and not (
            policy.management_sources
            or policy.ttc_sources
            or policy.telemetry_sources
        ):
            plan.warnings.append(
                "Default drop with no management/TTC/telemetry sources may make the node unreachable."
            )

        for index, limit in enumerate(policy.rate_limits):
            args = ["-A", CHAIN_IN]
            if limit.source_cidr:
                args += ["-s", limit.source_cidr]
            args += ["-p", limit.protocol]
            if limit.port is not None and limit.protocol != "icmp":
                args += ["--dport", str(limit.port)]
            if limit.syn_only and limit.protocol == "tcp":
                args += ["--syn"]
            args += [
                "-m",
                "hashlimit",
                "--hashlimit-above",
                f"{limit.packets_per_second}/sec",
                "--hashlimit-burst",
                str(limit.burst),
                "--hashlimit-mode",
                "srcip",
                "--hashlimit-name",
                f"sgnt{index}",
                "-j",
                "DROP",
            ]
            ipt(*args)

        for limit in policy.connection_limits:
            ipt(
                "-A",
                CHAIN_IN,
                "-p",
                "tcp",
                "--dport",
                str(limit.port),
                "-s",
                limit.source_cidr,
                "-m",
                "connlimit",
                "--connlimit-above",
                str(limit.max_connections),
                "--connlimit-mask",
                "128" if policy.family == "ipv6" else "32",
                "-j",
                "REJECT",
                "--reject-with",
                "tcp-reset",
            )

        out_chain_created = False
        for rule in policy.rules:
            chain = CHAIN_IN if rule.direction == "in" else CHAIN_OUT
            if rule.direction == "out" and not out_chain_created:
                ipt("-N", CHAIN_OUT)
                ipt("-I", "OUTPUT", "1", "-j", CHAIN_OUT)
                out_chain_created = True
            args = ["-A", chain]
            args = ["-A", chain]
            if rule.source_cidr:
                args += ["-s", rule.source_cidr]
            if rule.destination_cidr:
                args += ["-d", rule.destination_cidr]
            if rule.protocol != "any":
                args += ["-p", rule.protocol]
                if rule.port is not None and rule.protocol in {"tcp", "udp"}:
                    args += ["--dport", str(rule.port)]
            if rule.log:
                ipt(
                    *args,
                    "-m",
                    "limit",
                    "--limit",
                    "10/min",
                    "-j",
                    "LOG",
                    "--log-prefix",
                    "SGNT: ",
                )
            if rule.action == "accept":
                ipt(*args, "-j", "ACCEPT")
            elif rule.action == "drop":
                ipt(*args, "-j", "DROP")
            else:
                if rule.protocol == "tcp":
                    ipt(*args, "-j", "REJECT", "--reject-with", "tcp-reset")
                else:
                    ipt(*args, "-j", "REJECT", "--reject-with", reject_with)

        ipt("-A", CHAIN_IN, "-j", "DROP" if policy.default_inbound == "drop" else "RETURN")
        if out_chain_created:
            ipt("-A", CHAIN_OUT, "-j", "RETURN")

        if policy.bcp38_ingress:
            if policy.family == "ipv6":
                plan.warnings.append("BCP38 rpfilter is only implemented for IPv4.")
            else:
                ipt("-t", "raw", "-N", CHAIN_RAW)
                ipt("-t", "raw", "-I", "PREROUTING", "1", "-j", CHAIN_RAW)
                ipt(
                    "-t",
                    "raw",
                    "-A",
                    CHAIN_RAW,
                    "-m",
                    "rpfilter",
                    "--invert",
                    "-j",
                    "DROP",
                )

        if policy.bcp38_egress_cidrs:
            ipt("-t", "raw", "-N", CHAIN_RAWOUT)
            ipt("-t", "raw", "-I", "OUTPUT", "1", "-j", CHAIN_RAWOUT)
            for cidr in policy.bcp38_egress_cidrs:
                ipt("-t", "raw", "-A", CHAIN_RAWOUT, "-s", cidr, "-j", "RETURN")
            ipt("-t", "raw", "-A", CHAIN_RAWOUT, "-j", "DROP")

        if policy.dscp_marks:
            ipt("-t", "mangle", "-N", CHAIN_MANGLE)
            ipt("-t", "mangle", "-I", "POSTROUTING", "1", "-j", CHAIN_MANGLE)
            for mark in policy.dscp_marks:
                args = ["-t", "mangle", "-A", CHAIN_MANGLE, "-p", mark.protocol]
                if mark.port is not None:
                    args += ["--dport", str(mark.port)]
                args += ["-j", "DSCP", "--set-dscp", str(mark.dscp)]
                ipt(*args)

        for policing in policy.ingress_policing:
            if policy.family == "ipv6":
                plan.warnings.append(
                    "IPv6 ingress policing is not implemented; use firewall limits."
                )
                continue
            interface = self._resolve_interface(node, policing.interface)
            plan.interfaces.append(interface)
            plan.warnings.append(
                "Egress per-flow classes are not applied because SatGoNetEm owns "
                "the root qdisc; ingress policing and DSCP marking are applied."
            )
            tc(
                "qdisc",
                "add",
                "dev",
                interface,
                "handle",
                "ffff:",
                "ingress",
                ignore_errors=True,
            )
            protocol = "6" if policing.protocol == "tcp" else "17"
            args = [
                "filter",
                "add",
                "dev",
                interface,
                "parent",
                "ffff:",
                "protocol",
                "ip",
                "u32",
                "match",
                "ip",
                "protocol",
                protocol,
                "0xff",
            ]
            if policing.port is not None:
                args += ["match", "ip", "dport", str(policing.port), "0xffff"]
            args += [
                "police",
                "rate",
                f"{policing.rate_kbps}kbit",
                "burst",
                f"{policing.burst_kb}k",
                "drop",
            ]
            tc(*args)

        return plan

    @staticmethod
    def _read_chain_counters(node: Any, binary: str) -> list[dict[str, Any]]:
        chains = (
            (CHAIN_IN, "filter"),
            (CHAIN_OUT, "filter"),
            (CHAIN_RAW, "raw"),
            (CHAIN_RAWOUT, "raw"),
            (CHAIN_MANGLE, "mangle"),
        )
        rules: list[dict[str, Any]] = []
        for chain, table in chains:
            try:
                listing = node.execute_command(
                    [binary, "-w", "-t", table, "-L", chain, "-v", "-n", "-x"]
                )
            except RuntimeError:
                continue
            for line in listing.splitlines():
                parts = line.split()
                if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
                    continue
                rules.append(
                    {
                        "chain": chain,
                        "rule": " ".join(parts[3:]) or parts[2],
                        "packets": int(parts[0]),
                        "bytes": int(parts[1]),
                        "target": parts[2],
                    }
                )
        return rules

    @staticmethod
    def _add_allowlist(ipt, sources: list[str], ports: list[int], protocol: str) -> None:
        for source in sources:
            for port in ports:
                ipt(
                    "-A",
                    CHAIN_IN,
                    "-s",
                    source,
                    "-p",
                    protocol,
                    "--dport",
                    str(port),
                    "-j",
                    "ACCEPT",
                )

    def _cleanup_chains(self, node: Any, family: str) -> None:
        binary = "ip6tables" if family == "ipv6" else "iptables"
        hooks = [
            ("INPUT", CHAIN_IN),
            ("OUTPUT", CHAIN_OUT),
            ("PREROUTING", CHAIN_RAW),
            ("OUTPUT", CHAIN_RAWOUT),
            ("POSTROUTING", CHAIN_MANGLE),
        ]
        for hook, chain in hooks:
            table = "raw" if chain in {CHAIN_RAW, CHAIN_RAWOUT} else "mangle" if chain == CHAIN_MANGLE else "filter"
            self._run_ignore(
                node,
                [binary, "-w", "-t", table, "-D", hook, "-j", chain],
            )
            self._run_ignore(node, [binary, "-w", "-t", table, "-F", chain])
            self._run_ignore(node, [binary, "-w", "-t", table, "-X", chain])

    def _clear_tc(self, node: Any, interfaces: list[str]) -> None:
        for interface in dict.fromkeys(interfaces):
            self._run_ignore(node, ["tc", "filter", "del", "dev", interface, "parent", "ffff:"])
            self._run_ignore(node, ["tc", "qdisc", "del", "dev", interface, "ingress"])

    def _save_backup(self, node: Any, family: str) -> None:
        binary = "ip6tables" if family == "ipv6" else "iptables"
        path = self._backup_path(node, family)
        self._run(
            node,
            ["sh", "-lc", f"{binary}-save > {shlex.quote(path)}"],
        )

    def _restore_base(self, node: Any, family: str) -> bool:
        path = self._backup_path(node, family)
        if not self._file_exists(node, path):
            return False
        binary = "ip6tables" if family == "ipv6" else "iptables"
        self._run(
            node,
            ["sh", "-lc", f"{binary}-restore < {shlex.quote(path)}"],
        )
        return True

    def _remove_backup(self, node: Any, family: str) -> None:
        path = self._backup_path(node, family)
        self._run_ignore(node, ["sh", "-lc", f"rm -f {shlex.quote(path)}"])

    @staticmethod
    def _backup_path(node: Any, family: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", getattr(node, "name", "node"))
        return f"/tmp/sgnt_policy_{safe}_{family}.rules"

    def _file_exists(self, node: Any, path: str) -> bool:
        output = self._run(
            node,
            ["sh", "-lc", f"test -f {shlex.quote(path)} && echo yes || echo no"],
        )
        return output == "yes"

    @staticmethod
    def _run(node: Any, argv: list[str]) -> str:
        return node.execute_command(argv)

    def _run_ignore(self, node: Any, argv: list[str]) -> None:
        try:
            node.execute_command(argv)
        except Exception:
            return

    @staticmethod
    def _resolve_node(topology: Any, name: str, require_running: bool = True) -> Any:
        node = topology.get_node_by_name(name)
        if node is None:
            raise ValueError(f"Node not found: {name}")
        if require_running and getattr(node, "container", None) is None:
            raise ValueError(f"Node is not running: {name}")
        return node

    @staticmethod
    def _interface_name(interface: Any) -> str:
        get_iname = getattr(interface, "get_iname", None)
        if callable(get_iname):
            return get_iname() or getattr(interface, "name", "")
        return getattr(interface, "name", "")

    @classmethod
    def _resolve_interface(cls, node: Any, requested: str) -> str:
        for interface in getattr(node, "interfaces", []):
            name = getattr(interface, "name", "")
            iname = cls._interface_name(interface)
            if requested in (name, iname):
                return iname or name
        raise ValueError(f"Interface not found: {requested}")
