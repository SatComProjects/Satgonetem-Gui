# Architecture and test baseline

Status: Phase 0 baseline. The refactor is tracked in
[issue #1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1);
Phase 0 is [issue #2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2).

## Current shape

`satgonetem_gui/app.py` is a single FastAPI module that currently owns:

- page rendering and static-file mounting;
- request parsing and untyped payload handling;
- project construction, background-thread lifecycle, save/load;
- ground-station CSV parsing and temporary-file handling;
- topology, routing, and GoNetem access;
- traffic-flow creation, polling, cancellation, and result serialization.

`state.py` exposes a process-global `app_state` singleton. This is the main
obstacle to isolated tests: every test has to reset the same module-level
object.

Phase 0 does not change this behavior. It adds the tests, tooling, and CI that
later phases will use as a safety net.

## Target dependency rule

The target is a small modular monolith:

```text
app.py (composition root)
  -> api/routes (HTTP only)
      -> services (orchestration)
          -> domain (pure rules and state)
          -> adapters (satgonetem / files)
```

Routes translate HTTP. Services coordinate use cases. Adapters are the only
modules that import `TopologyManager`, traffic-flow classes, or other
`satgonetem` internals. Domain code depends on nothing external and is tested
without Docker.

The detailed target layout and SOLID mapping are in issue #1.

## Test strategy

- The integration fixture is a **10x10 Walker delta** constellation (100
  satellites) with one Berlin ground station. It is chosen to exercise realistic
  inter-satellite and ground-station links; the earlier 3x3 smoke topology was
  too small for routing checks.
- The fixture builds in-process with `TopologyManager.from_satcom`; no Docker,
  no GoNetem server, and no containers are required for the default suite.
- Page routes, read APIs, save/load, and error guards are characterized in
  `tests/`.
- Known-broken behavior is marked with `xfail(strict=True)` and a defect ID
  from issue #1. When a defect is fixed, the strict xfail turns into a failure,
  which forces the test to be updated.
- Tests reset the global state before and after each case through the `client`
  fixture. Phase 3 replaces that global object with an app factory and injected
  services.
- Docker-backed routing and traffic happy paths are not part of the default
  suite. They will be covered by fake-adapter tests and optional contract tests.

## Baseline measurements

Measured on 2026-11-03 with Python 3.15.0, pytest 9.2.0, and coverage 7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **50 passed, 4 xfailed** in about 0.4 s.

| Module | Statements | Coverage |
|---|---:|---:|
| `satgonetem_gui/app.py` | 536 | 57% |
| `satgonetem_gui/state.py` | 31 | 82% |
| `satgonetem_gui/main.py` | 6 | 0% |
| **Total** | **573** | **58%** |

Branch coverage is enabled. The initial gap is concentrated in traffic flows,
routing/GoNetem handlers, background project creation, and the server entry
point. No coverage threshold is enforced in Phase 0; later phases gate new
domain and service modules.

## Tooling decisions

- `uv.lock` is the source of truth and is committed.
- `requirements.txt` is generated from the lock for pip users. Regenerate it
  with:

  ```bash
  uv export --no-hashes --no-emit-project --format requirements-txt
  ```

  Keep the two-line warning header at the top of the file.
- Ruff currently checks `E9`, `F`, and `I` across the repository. Formatting is
  checked only for new Python files under `tests/`; `app.py` will be formatted
  as it is touched so that Phase 0 does not produce a whitespace-only rewrite.
- CI runs on pushes and pull requests to `main` and `develop`, installs from the
  lockfile, runs lint and tests, and verifies that the wheel contains the
  templates and static assets.

## Next phase

Phase 1 makes project creation a first-class state machine and fixes the P0
defects D1-D5. The xfail tests for D1, D4, and D9 are the starting points.
See issue #1 for the full phased plan.
