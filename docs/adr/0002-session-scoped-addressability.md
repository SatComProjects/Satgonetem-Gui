# 0002 — Session-scoped satellite addressability

Status: accepted

## Context

SatGoNetEm keeps an `addressable` flag on each satellite, defaulting to
`False`. Only addressable satellites are valid traffic endpoints, so a normal
GUI-built project can run traffic only between ground stations. The pinned core
exposes `set_addressable_satellites` and `Satellite.set_addressable`, but it
does not serialize the flag in `to_file`/`from_file`. Persisting a GUI-level
project option would therefore require a GUI project-document extension or a
core change followed by a pin bump.

Addressability also changes routing-daemon destination sets. Enabling it while
addressing/routing is already applied leaves the installed routes stale until
the operator re-applies them.

## Decision

1. Expose a global toggle (`POST /api/satellites/addressable`) and a per-node
   toggle (`POST /api/nodes/{name}/addressable`).
2. Keep the setting **session-scoped**. Do not pretend it is saved with the
   project, because the pinned core drops it on save/load.
3. Return `routing_refresh_required` when addressing is currently applied, and
   show a visible "re-apply Addressing & Routing" notice in the Traffic and
   Node Explorer pages.
4. Serialize addressability mutations with the existing session-level network
   operation gate and check the project generation, as routing and simulation
   mutations do.
5. Filter the Traffic endpoint list through the existing
   `traffic_nodes()`/`is_addressable()` path; no separate endpoint registry.

## Consequences

> **Update (v0.3.2):** the core now persists addressability in
> runtime-state projects. Simulation-property (Walker) projects — the GUI's
> normal project format — still do not serialize the flag, so the session-scoped
> behavior remains for those projects.

- Users can run satellite-to-satellite and ground-to-satellite traffic without
  changing the core pin.
- The setting must be re-enabled after loading or replacing a project. The UI
  states this; it is not silent.
- Enabling all satellites can make routing recomputation and endpoint lists
  large. The UI reports the count and requires an explicit action.
- The per-node state shown in Node Explorer is authoritative only for the
  current session.
- If persistence becomes a requirement, the clean path is an upstream
  serialized field and a pin bump, not a GUI-side side channel.

## Alternatives considered

- **Add a GUI project-document field.** Rejected for this slice: it would
  create a second source of truth that the core does not understand and would
  need a versioned document contract and migration.
- **Enable all satellites by default.** Rejected: it changes routing behavior
  and resource expectations for every existing project.
- **Change the core now.** Deferred: it needs an upstream release, a pin bump,
  and adapter contract updates; the session-scoped toggle is useful
  immediately.
- **Only a global toggle.** Rejected: per-node control is cheap and useful for
  targeted tests and resource-constrained experiments.

## Related documents

- [0001 — Simulation transport controls](0001-simulation-transport.md)
- [Specifications](../specs/README.md)
- [Architecture and test baseline](../architecture.md)
