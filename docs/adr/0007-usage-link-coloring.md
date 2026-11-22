# 0007 — Usage-based link coloring

Status: accepted

## Context

World View already sizes links by capacity and marks inactive links red. Users
asked for color coding by live usage, from green (idle) to red (at/above
capacity), when explicitly enabled.

SatGoNetEm exposes `get_all_links_usage()` / `monitor_links()`, which read
`/tmp/interfaces/<project>.<SatN>` files and return `{src, dst, value, type}`
with `value` in bits per second. The file-path contract has not been verified
against the net-logger output in this environment, so usage may be unavailable.

## Decision

1. Add `GET /api/links/usage` behind the existing topology reader boundary.
   Return `available`, `sampled_at`, normalized entries (`value_bps`,
   `capacity_kbps`, `utilization`), and an explanatory note.
2. Derive utilization from the public link capacity:
   `min(1.0, value_bps / (capacity_kbps * 1000))`; unknown/zero capacity yields
   `null`.
3. When containers are stopped, return `available=false` with an explanatory
   note instead of an error. Monitor exceptions degrade the same way.
4. World View adds an opt-in checkbox. When enabled, it samples usage every
   five seconds (not with the 2 s topology poll), colors active links green →
   amber → red, keeps inactive links red, and still applies forwarding-path
   width/dimming. Missing entries mean zero usage when the sample is available;
   unknown capacity is neutral gray.
5. Do not cache or persist usage; there is no history.

## Consequences

- Usage coloring is explicitly opt-in and may show "unavailable" when the core
  monitor files are absent or containers are stopped.
- The UI does not invent traffic: unavailable data is gray, not green.
- Sampling scans the core interface files every five seconds while enabled; a
  very large topology may need a lower rate or a core-side sampler later.
- Utilization is instantaneous and unidirectional as reported by the core; it
  is not a time series.

## Alternatives considered

- **Color by capacity instead of usage.** Rejected: capacity is already encoded
  in line width and does not answer current load.
- **Synthesize usage from traffic jobs.** Rejected: it would not reflect other
  traffic or routing behavior.
- **Add a backend sampler/cache now.** Deferred: the endpoint is read-only and
  the UI polls slowly; a cache can be added with the core monitor work.
- **Block the control until the monitor is verified.** Rejected: the user
  explicitly wants opt-in coloring and the endpoint degrades safely.

## Related documents

- [0005 — Link metrics scope and deferred utilization](0005-link-metrics-scope.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
