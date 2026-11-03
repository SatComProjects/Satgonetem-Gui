# Architecture and test baseline

Status: Phase 2 complete. The refactor is tracked in
[issue #1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1);
completed phases are
[#2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2),
[#3](https://github.com/SatComProjects/Satgonetem-Gui/issues/3), and
[#4](https://github.com/SatComProjects/Satgonetem-Gui/issues/4).

## Current shape

`satgonetem_gui/app.py` still contains the route handlers and topology
orchestration, but the supporting concerns now have dedicated modules:

- `schemas.py` - Pydantic request/response models shared by every JSON route.
- `errors.py` - `APIError` and the FastAPI handlers that produce one error
  envelope.
- `config.py` - host, port, and save-root settings from environment variables.
- `storage.py` - data-file resolution, safe project filenames, and save-root
  containment.
- `ground_stations.py` - CSV parsing and unique temporary station files.
- `serializers.py` - iperf3/ping/hping3 result shaping for the frontend.
- `state.py` - `ProjectSession`/`ProjectTaskManager` and the process-global
  `app_state` singleton.

The process-global `app_state` still exists. Phase 3 replaces it with an app
factory and injected services.

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
- Added `GET /api/project/status`; the New Project page stops polling on
  `error` and shows the failure message.
- Fixed `/api/project/config` to return the editable name, dates, capacities,
  shells, save path, and ground objects with their stations embedded.
- Load now derives the user-facing name from `simulation_property.simulation_name`
  instead of the timestamp-suffixed `tm.project_name`.
- The edit form round-trips ground stations, capacities, and save path.

## Phase 2 changes

- Every JSON API route now declares Pydantic request/response models and a
  `response_model`; `tests/test_openapi_contract.py` verifies the schema.
- Lifted request parsing out of route bodies. FastAPI now returns 422 for
  malformed or incomplete bodies before handlers run.
- Added one error envelope, `{ok: false, error: ...}`, for 400, 404, 409, 422,
  and 500 responses. Unexpected exceptions are logged and converted to a 500
  envelope.
- Invalid project files now return 400 instead of 500. Unsupported project
  operation conflicts remain 409.
- Moved ground-station CSV parsing/writing and traffic-result serialization
  into pure, independently tested modules.
- Added `Settings`: `SATGONETEM_GUI_HOST`, `SATGONETEM_GUI_PORT`, and
  `SATGONETEM_GUI_SAVE_ROOT`. The server binds `127.0.0.1` by default.
- Enforced save-root containment. `save_path` values outside the root return
  400, and relative paths resolve under the root.
- Inline ground-station data now uses unique `mkstemp` names instead of a
  filename derived from user input.

## Test strategy

- The integration fixture is a **10x10 Walker delta** constellation (100
  satellites) with one Berlin ground station. It is chosen to exercise realistic
  inter-satellite and ground-station links; the earlier 3x3 smoke topology was
  too small for routing checks.
- The fixture builds in-process with `TopologyManager.from_satcom`; no Docker,
  no GoNetem server, and no containers are required for the default suite.
- Page routes, read APIs, lifecycle errors, typed validation, save/load, the
  edit round-trip, settings, path containment, serializers, and OpenAPI schemas
  are covered in `tests/`.
- Tests reset the global state before and after each case through
  `AppState.reset()`.
- Docker-backed routing and traffic happy paths are not part of the default
  suite. They will be covered by fake-adapter tests and optional contract tests.

## Current measurements

Measured on 2026-11-03 with Python 3.15.0, pytest 9.2.0, and coverage 7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **99 passed** in about 0.6 s.

| Module | Statements | Coverage |
|---|---:|---:|
| `satgonetem_gui/app.py` | 445 | 65% |
| `satgonetem_gui/config.py` | 17 | 88% |
| `satgonetem_gui/ground_stations.py` | 30 | 87% |
| `satgonetem_gui/main.py` | 8 | 80% |
| `satgonetem_gui/schemas.py` | 120 | 98% |
| `satgonetem_gui/serializers.py` | 63 | 79% |
| `satgonetem_gui/state.py` | 152 | 91% |
| `satgonetem_gui/storage.py` | 29 | 95% |
| **Total** | **895** | **77%** |

Branch coverage is enabled. No coverage threshold is enforced yet; Phase 3 will
gate new domain and service modules.

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

Phase 3 extracts the app factory, routers, services, and `satgonetem` adapters,
and removes the global mutable state. See issue #1 for the full phased plan.
