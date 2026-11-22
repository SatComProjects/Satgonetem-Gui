# 0003 — Client-side experiment history

Status: accepted

## Context

Completed traffic results currently exist only in the browser queue item and,
briefly, in the server job registry. The browser strips results when persisting
the queue, and the registry evicts finished jobs after one hour or when it
reaches its 100-job cap. Users therefore cannot reopen a run after a reload,
compare two runs, or export evidence without re-running the experiment.

Server-side history would need stable project identity, a retention policy, a
storage format, and a public API; that is a larger change than the first useful
slice. The GUI already has a bounded queue model, localStorage persistence, and
Chart.js rendering, so a client-local ledger can deliver reopen/export/compare
immediately.

## Decision

1. Add a browser-local experiment ledger under `sgnt_traffic_history`.
2. Capture only successful terminal (`done`) runs, keyed by backend `job_id`.
   Errors and cancellations remain queue state, not experiments.
3. Store a compact copy of the result payload: summary fields plus a capped
   interval series (`MAX_INTERVALS`) so one long iperf3 run cannot exhaust
   localStorage. Cap the ledger by record count and approximate byte size.
4. Record the endpoints, tool, request payload, start/finish timestamps,
   duration, summary metrics, and a best-effort project name. A project-status
   lookup failure must not drop the run.
5. Provide the History modal actions: reopen in the existing result view,
   delete, export one/all as JSON, export all as CSV, and compare two
   same-kind runs. Comparison is a summary table plus one primary series
   (iperf3 throughput or hping3 RTT); ping comparison is summary-only.
6. Do not add a backend endpoint in this phase. Keep the storage/UI behavior
   behind pure `history_model.js` functions so a future server-backed store can
   reuse normalization, export, and comparison.

## Consequences

- History is per-browser and per-browser-profile. It is not shared across
  machines, tabs are eventual via the `storage` event, and private mode or
  cleared storage loses it.
- Truncated interval series are marked; charts are representative, not a full
  packet-level record.
- The ledger is not a substitute for server-side run provenance. A future
  server store should carry a project/config hash, core version, and retention
  policy.
- A record can be exported and inspected without the server, which covers the
  immediate "reopen and compare" workflow.

## Alternatives considered

- **Persist on the server now.** Deferred: it needs project identity and a
  storage contract; the GUI has no stable project ID today.
- **Store full result payloads.** Rejected: iperf3 interval arrays can exceed
  localStorage quotas quickly.
- **Use IndexedDB.** Deferred: more machinery than the first slice needs; the
  pure model makes a later storage swap possible.
- **Keep history only in the open modal.** Rejected: it would not survive a
  reload, which is the core user problem.

## Related documents

- [0001 — Simulation transport controls](0001-simulation-transport.md)
- [0002 — Session-scoped satellite addressability](0002-session-scoped-addressability.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
