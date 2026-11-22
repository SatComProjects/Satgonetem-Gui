# 0004 — Diagnostic forwarding paths

Status: accepted

## Context

The GUI can show routing status and raw `ip route` lines, but it cannot explain
which links a packet would take or why. SatGoNetEm exposes a public routing-graph
API:

- `get_path_between_nodes(source, target)` returns an ordered node path or an
  empty list.
- `get_current_graph()` returns the current routing graph with edge `type`,
  `direction`, `distance_km`, and weight attributes; inactive/disabled edges are
  removed.

That graph is not the same thing as the forwarding table installed by the
active routing daemon (static, OSPF, IS-IS, or SR-MPLS). Presenting it as a live
FIB would be misleading, and reading daemon internals would add a private-hook
dependency.

## Decision

1. Expose `GET /api/routing/path?src=&dst=` over the public graph path.
2. Return a hop-by-hop DTO with link type, direction, distance, propagation
   delay (distance / speed of light), and cumulative distance/delay.
3. Include the active routing method, whether routing was applied, and the
   preference, but label the result explicitly as a **routing-graph snapshot,
   not the live forwarding table**.
4. Treat two identical endpoints as 422, malformed/unknown nodes as 404, and a
   missing path as a successful response with `found=false` and a clear note.
5. Show the path as a hop table on Node Explorer and highlight it on World View,
   dimming unrelated links and enabling the link categories the path uses.
6. Keep the path a snapshot. Do not cache it across topology/routing changes;
   the user re-traces when needed.

## Consequences

- Users get an explainable path without a core change or private daemon access.
- The path can differ from the daemon's installed FIB, especially for dynamic
  protocols or SR-MPLS explicit paths. The UI and API say so.
- Delay is propagation delay only; it excludes queueing, serialization, and
  daemon policy.
- A dynamic topology can invalidate a displayed path; re-tracing is explicit.
- World View auto-enables the link categories present in the path, so the
  highlight is visible even when those categories were initially hidden.

## Alternatives considered

- **Read the live routing table from every node.** Deferred: it is
  container-dependent, protocol-specific, and not a stable cross-daemon
  contract.
- **Use routing-daemon internals.** Rejected: `routing_daemon` is not a
  documented accessor and would violate the private-hook rule.
- **Compute the path purely in the browser.** Rejected: the browser does not
  have the core graph or authoritative link state.
- **Add a preference setter now.** Deferred: v0.3.1 has no public setter; the
  response exposes the current preference instead.
- **Persist path history.** Deferred: paths are cheap to recompute and the
  existing history ledger is result-oriented.

## Related documents

- [0001 — Simulation transport controls](0001-simulation-transport.md)
- [0002 — Session-scoped satellite addressability](0002-session-scoped-addressability.md)
- [0003 — Client-side experiment history](0003-client-side-experiment-history.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
