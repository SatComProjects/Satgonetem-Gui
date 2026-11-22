# 0001 — Simulation transport controls

Status: accepted

## Context

SatGoNetem v0.3.2 owns a discrete-time simulation loop with public operations
for start, stop, single step, reset, speed, seek, total duration, and last-tick
error. The GUI only read `simulation_updating`, `current_step`, and
`current_time` and rendered them as a passive card. Users could watch the
clock but could not drive it, which made dynamic topology, handover, and
routing-reconvergence experiments impossible from the control panel.

The loop runs on a core-owned background thread and mutates the same topology
that routing and container operations mutate. Exposing controls therefore
introduces lifecycle and serialization questions that are costly to reverse
once public routes exist.

## Decision

1. Add a dedicated `SimulationService` and a narrow `SimulationController`
   protocol in `services/ports.py`. Routes only translate HTTP; the adapter is
   the only module that calls the public core loop methods.
2. Expose `POST /api/simulation/{start,stop,step,reset,seek,speed}`.
   Extend `GET /api/status` with `total_steps`, `simulation_rate`, and
   `last_simulation_error` rather than adding a second status endpoint.
3. Serialize simulation mutations with the existing session-level
   `begin_network_operation()` gate, shared with routing and container
   lifecycle operations. Step/reset/seek require the loop to be paused;
   start/stop/speed are legal while running.
4. Seek takes an integer step, not a timestamp. The adapter computes
   `start_time + step * update_time`. This avoids timezone ambiguity between
   the browser and the core's naive datetime values.
5. Run every blocking core call through `asyncio.to_thread` with a timeout,
   a single in-flight worker, and a project-generation check. A timed-out
   worker may keep running; the service returns 504 and refuses to start a
   second worker.
6. Stop the simulation loop before a project replacement and during application
   shutdown. Do not stop GoNetEm containers on application shutdown; container
   lifetime remains an explicit operator action, consistent with the existing
   behavior.
7. The GUI may drive the simulation while containers are stopped (topology and
   orbit updates still work), but routing and traffic effects require GoNetEm.
   The panel states this rather than blocking playback.

## Consequences

- The GUI now owns the visible transport contract, while the core remains the
  owner of the loop thread and topology mutation.
- A simulation operation can return 504 while the worker is still finishing.
  The UI must be able to retry from a fresh status read; it cannot start a
  second worker in the meantime.
- Project replacement is intentionally slower when a tick is in flight because
  the loop is joined before the build/load starts.
- Simulation cannot be advanced while it is running; users must pause to step,
  reset, or seek. This keeps the displayed step and the user's action coherent.
- Failures from a loop tick are surfaced in the status response and dashboard,
  but a failed tick is retried by the core on the next interval.
- Loss/jitter injection and one-way link failure remain out of scope and need
  upstream support.
- Tests use a fake `SimulationController` for orchestration, the real adapter
  for the 10x10 fixture, and do not require Docker or GoNetEm.

## Alternatives considered

- **Call core methods directly from routes.** Rejected: routes would import
  core types and would bypass the operation gate and adapter boundary.
- **Extend `RoutingService`.** Rejected: it would mix routing/container
  lifecycle with simulation playback and violate single responsibility.
- **Seek by ISO timestamp.** Rejected for the first version: the project form,
  core datetimes, and browser local time do not share a clear timezone
  contract. An integer step is unambiguous and matches the displayed step.
- **Drive the loop from the server without client polling.** Deferred: the core
  already runs the loop in a background thread, but a server-side event stream
  or persisted playback state would be a larger public-contract change.
- **Stop containers on application shutdown.** Rejected: it would make a GUI
  restart tear down a network the operator may be using, and it is outside the
  transport feature's scope.

## Related documents

- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
- [Development guide](../../AGENTS.md)
