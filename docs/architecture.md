# Architecture and test baseline

Status: Phase 1 complete. The refactor is tracked in
[issue #1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1);
Phase 0 is [issue #2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2)
and Phase 1 is [issue #3](https://github.com/SatComProjects/Satgonetem-Gui/issues/3).

## Current shape

`satgonetem_gui/app.py` is still a single FastAPI module that owns page
rendering, static mounting, request parsing, topology construction, save/load,
ground-station CSV handling, routing/GoNetem access, and traffic flows.

Phase 1 extracted the project lifecycle into `state.py`:

- `ProjectSession` owns the loaded topology, the user-facing project name, the
  save path, and an explicit `idle -> creating -> loaded | error` state.
- `ProjectTaskManager` enforces one build at a time and records the outcome in
  the session. The loaded topology is preserved while a replacement is built
  and if the replacement fails.
- The process-global `app_state` singleton still exists. Phase 3 replaces it
  with an app factory and injected services.

Phase 0 added the test, lint, and CI safety net. Phase 1 used it to fix the P0
lifecycle defects D1-D5.

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

## Phase 1 changes

- Added `ProjectSession`/`ProjectTaskManager` with single-flight reservation,
  explicit states, and a preserved previous project on failure.
- Added `GET /api/project/status` for the New Project page. The page now stops
  polling on `error` and shows the failure message instead of waiting ten
  minutes.
- Fixed `GET /api/project/config`: it reads `TopologyManager.simulation_property`
  and the network attributes, returns the submitted `name`, dates, capacities,
  shells, save path, and ground objects with their stations embedded.
- Load now derives the user-facing name from `simulation_property.simulation_name`
  instead of the timestamp-suffixed `tm.project_name`. Save/download uses the
  same name.
- The edit form keeps ground stations, capacities, and the save path when it is
  submitted back through `/api/project/create`.
- Create and load participate in the same single-flight guard. A second
  operation returns HTTP 409.

## Test strategy

- The integration fixture is a **10x10 Walker delta** constellation (100
  satellites) with one Berlin ground station. It is chosen to exercise realistic
  inter-satellite and ground-station links; the earlier 3x3 smoke topology was
  too small for routing checks.
- The fixture builds in-process with `TopologyManager.from_satcom`; no Docker,
  no GoNetem server, and no containers are required for the default suite.
- Page routes, read APIs, save/load, lifecycle errors, and the edit round-trip
  are covered in `tests/`.
- Known-broken behavior is marked with `xfail(strict=True)` and a defect ID
  from issue #1. D1, D4, and the Phase 1 lifecycle defects are fixed; the two
  remaining strict xfails cover D9 (typed request validation) for Phase 2.
- Tests reset the global state before and after each case through the
  `AppState.reset()` method.
- Docker-backed routing and traffic happy paths are not part of the default
  suite. They will be covered by fake-adapter tests and optional contract tests.

## Current measurements

Measured on 2026-11-03 with Python 3.15.0, pytest 9.2.0, and coverage 7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **64 passed, 2 xfailed** in about 0.5 s. (Phase 0 started at 50 passed,
4 xfailed, and 58% total coverage.)

| Module | Statements | Coverage |
|---|---:|---:|
| `satgonetem_gui/app.py` | 573 | 59% |
| `satgonetem_gui/state.py` | 152 | 91% |
| `satgonetem_gui/main.py` | 6 | 0% |
| **Total** | **731** | **64%** |

Branch coverage is enabled. No coverage threshold is enforced yet; Phase 2
adds typed request validation and will gate new domain and service modules.

## Tooling decisions

- `uv.lock` is the source of truth and is committed.
- `requirements.txt` is generated from the lock for pip users. Regenerate it
  with:

  ```bash
  uv export --no-hashes --no-emit-project --format requirements-txt
  ```

  Keep the two-line warning header at the top of the file.
- Ruff checks `E9`, `F`, and `I` across the repository. Formatting is checked
  for the test suite; `app.py` will be formatted as it is touched so the
  refactor does not produce a whitespace-only rewrite.
- CI runs on pushes and pull requests to `main` and `develop`, installs from the
  lockfile, runs lint and tests, and verifies that the wheel contains the
  templates and static assets.

## Next phase

Phase 2 adds Pydantic request/response schemas, consistent error handling, and
the remaining typed-validation fixes for D9. See issue #1 for the full phased
plan.
