"""Pure structural health checks over reader topology payloads."""

import math
from collections import Counter
from typing import Any, Iterable

ITEM_PREVIEW_LIMIT = 20


def _finite_number(value: Any) -> float | None:
    """Return a finite float for numeric input, or None for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _as_list(items: Any) -> list[Any]:
    """Treat a missing or malformed collection as empty."""
    return items if isinstance(items, list) else []


def _named_nodes(nodes: list[Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return well-formed ``(name, node)`` pairs from a reader payload."""
    named: list[tuple[str, dict[str, Any]]] = []
    for node in _as_list(nodes):
        if not isinstance(node, dict):
            continue
        name = node.get("name")
        if isinstance(name, str) and name:
            named.append((name, node))
    return named


def _links(links: list[Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return well-formed ``(src, dst, link)`` triples from a reader payload."""
    parsed: list[tuple[str, str, dict[str, Any]]] = []
    for link in _as_list(links):
        if not isinstance(link, dict):
            continue
        src = link.get("src")
        dst = link.get("dst")
        if isinstance(src, str) and isinstance(dst, str):
            parsed.append((src, dst, link))
    return parsed


def _position(node: dict[str, Any]) -> dict[str, Any]:
    """Return a node's position mapping, or an empty mapping."""
    position = node.get("position")
    return position if isinstance(position, dict) else {}


def _complete_position(node: dict[str, Any]) -> tuple[float, float, float] | None:
    """Return a finite position triple, or None when any field is missing."""
    position = _position(node)
    latitude = _finite_number(position.get("latitude"))
    longitude = _finite_number(position.get("longitude"))
    altitude = _finite_number(position.get("altitude"))
    if latitude is None or longitude is None or altitude is None:
        return None
    return latitude, longitude, altitude


def _isolated_nodes(
    nodes: Iterable[tuple[str, dict[str, Any]]],
    links: Iterable[tuple[str, str, dict[str, Any]]],
) -> list[str]:
    """Return node names with no incident link; self-links count as incident."""
    incident: set[str] = set()
    for src, dst, _link in links:
        incident.add(src)
        incident.add(dst)
    return sorted(name for name, _node in nodes if name not in incident)


def _missing_positions(nodes: Iterable[tuple[str, dict[str, Any]]]) -> list[str]:
    """Return node names without a complete finite position."""
    return sorted(name for name, node in nodes if _complete_position(node) is None)


def _duplicate_positions(nodes: Iterable[tuple[str, dict[str, Any]]]) -> list[str]:
    """Return ``NameA/NameB`` groups sharing a rounded position."""
    groups: dict[tuple[float, float, float], list[str]] = {}
    for name, node in nodes:
        position = _complete_position(node)
        if position is None:
            continue
        latitude, longitude, altitude = position
        key = (round(latitude, 6), round(longitude, 6), round(altitude, 3))
        groups.setdefault(key, []).append(name)
    return sorted("/".join(sorted(names)) for names in groups.values() if len(names) >= 2)


def _zero_capacity_links(
    links: Iterable[tuple[str, str, dict[str, Any]]],
) -> list[str]:
    """Return ``src->dst`` labels for links with non-positive capacity."""
    findings: list[str] = []
    for src, dst, link in links:
        capacity = _finite_number(link.get("capacity_kbps"))
        if capacity is not None and capacity <= 0:
            findings.append(f"{src}->{dst}")
    return sorted(findings)


def _negative_delay_links(
    links: Iterable[tuple[str, str, dict[str, Any]]],
) -> list[str]:
    """Return ``src->dst`` labels for links with a negative delay."""
    findings: list[str] = []
    for src, dst, link in links:
        delay = _finite_number(link.get("delay_ms"))
        if delay is not None and delay < 0:
            findings.append(f"{src}->{dst}")
    return sorted(findings)


def _self_links(links: Iterable[tuple[str, str, dict[str, Any]]]) -> list[str]:
    """Return ``src->src`` labels for self-referential links."""
    return sorted(f"{src}->{dst}" for src, dst, _link in links if src == dst)


def _duplicate_links(links: Iterable[tuple[str, str, dict[str, Any]]]) -> list[str]:
    """Return ``A<->B`` labels for unordered pairs seen more than once."""
    pairs = Counter(tuple(sorted((src, dst))) for src, dst, _link in links)
    return sorted(f"{src}<->{dst}" for (src, dst), count in pairs.items() if count > 1)


def _check(
    check_id: str,
    severity: str,
    findings: list[str],
    message,
) -> dict[str, Any]:
    """Shape one check with a bounded, sorted item preview."""
    return {
        "id": check_id,
        "severity": severity,
        "count": len(findings),
        "message": message(len(findings)),
        "items": findings[:ITEM_PREVIEW_LIMIT],
    }


def build_health(nodes: list[dict], links: list[dict]) -> dict:
    """Return every structural health check for one topology payload."""
    named_nodes = _named_nodes(nodes)
    parsed_links = _links(links)

    checks = [
        _check(
            "isolated_nodes",
            "info",
            _isolated_nodes(named_nodes, parsed_links),
            lambda count: (
                f"{count} node{'s' if count != 1 else ''} "
                f"{'have' if count != 1 else 'has'} no links"
            ),
        ),
        _check(
            "missing_positions",
            "warning",
            _missing_positions(named_nodes),
            lambda count: (
                f"{count} node{'s' if count != 1 else ''} "
                f"{'have' if count != 1 else 'has'} an incomplete position"
            ),
        ),
        _check(
            "duplicate_positions",
            "warning",
            _duplicate_positions(named_nodes),
            lambda count: (
                f"{count} position group{'s' if count != 1 else ''} "
                f"{'are' if count != 1 else 'is'} shared by multiple nodes"
            ),
        ),
        _check(
            "zero_capacity_links",
            "warning",
            _zero_capacity_links(parsed_links),
            lambda count: (
                f"{count} link{'s' if count != 1 else ''} "
                f"{'have' if count != 1 else 'has'} zero capacity"
            ),
        ),
        _check(
            "negative_delay_links",
            "warning",
            _negative_delay_links(parsed_links),
            lambda count: (
                f"{count} link{'s' if count != 1 else ''} "
                f"{'have' if count != 1 else 'has'} negative delay"
            ),
        ),
        _check(
            "self_links",
            "warning",
            _self_links(parsed_links),
            lambda count: (
                f"{count} link{'s' if count != 1 else ''} "
                f"{'are' if count != 1 else 'is'} a self-link"
            ),
        ),
        _check(
            "duplicate_links",
            "warning",
            _duplicate_links(parsed_links),
            lambda count: (
                f"{count} link pair{'s' if count != 1 else ''} "
                f"{'are' if count != 1 else 'is'} duplicated"
            ),
        ),
    ]

    healthy = all(check["count"] == 0 for check in checks if check["severity"] == "warning")
    return {
        "ok": True,
        "nodes": len(_as_list(nodes)),
        "links": len(_as_list(links)),
        "healthy": healthy,
        "checks": checks,
    }
