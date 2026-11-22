# 0005 — Link metrics scope and deferred utilization

Status: accepted

## Context

SatGoNetEm keeps useful per-link state: propagation delay, peer capacities,
active state, and `rx`/`tx` counters. The GUI previously returned only
endpoints, type, direction, and distance, so users could not explain throughput
or latency from the topology.

The core also exposes `monitor_links()`/`get_all_links_usage()`, but it reads
`/tmp/interfaces/<project>.<SatN>` files. A prior audit found that this path
contract does not match the pattern written by `start_net_logger`, and no live
container verification was available in this environment.

## Decision

1. Extend `LinkResponse` with:
   - `delay_ms` computed as propagation delay from distance and the speed of
     light, rounded to two decimals;
   - `capacity_kbps` from the public `Link.get_capacity()` (peer1 capacity:
     downlink for SAT→GS, otherwise the configured/current capacity);
   - `is_active` from the public link state.
2. Show a per-node Links table in Node Explorer with peer, type, direction,
   distance, delay, capacity, and active state.
3. Size World View links logarithmically by capacity and color inactive links
   red; keep the path-highlight width override.
4. Do **not** expose utilization or `rx`/`tx` yet. The file-based monitor
   contract must be verified or replaced upstream before a utilization UI is
   trustworthy.
5. Treat zero/unavailable capacity as “Unknown” in the UI rather than implying
   a zero-rate link.

## Consequences

- Users can correlate traffic results with link distance, propagation delay,
  capacity, and active state without a container shell.
- Capacity is a single peer1 value, not a full directional breakdown. A future
  schema can add both peers if needed.
- Congestion and live utilization remain unavailable in the GUI. This is an
  explicit limitation, not a silent zero.
- The Node Explorer link table is a snapshot refreshed with the node poll; a
  topology change can require collapsing/reopening the node or waiting for the
  next poll.

## Alternatives considered

- **Expose `monitor_links()` immediately.** Rejected: the `/tmp/interfaces`
  contract is unverified and the existing audit reports a mismatch.
- **Use `Link.rx`/`Link.tx`.** Rejected for now: they are zero unless the
  monitoring path is running correctly, which would look like idle links.
- **Return both peer capacities.** Deferred: the UI needs one meaningful number
  first; `get_capacity()` is the public contract.
- **Add a separate link-detail endpoint.** Rejected: `/api/links` already
  returns the full list and the inspector filters by node.

## Related documents

- [0004 — Diagnostic forwarding paths](0004-diagnostic-forwarding-path.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
