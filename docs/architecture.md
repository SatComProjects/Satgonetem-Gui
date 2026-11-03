# Architecture and test baseline

Status: Phase 3 complete. The refactor is tracked in
[issue #1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1);
completed phases are
[#2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2),
[#3](https://github.com/SatComProjects/Satgonetem-Gui/issues/3),
[#4](https://github.com/SatComProjects/Satgonetem-Gui/issues/4), and
[#5](https://github.com/SatComProjects/Satgonetem-Gui/issues/5).

## Current shape

The dependency direction is now:

```text
app.py (create_app + composition)
  -> routes/*        (HTTP translation only)
  -> services/*      (use-case orchestration)
      -> services/ports (narrow protocols)
  -> adapters/*      (satgonetem integration)

state.py / config.py / schemas.py / errors.py / storage.py / serializers.py
```

Per-application runtime state lives in `RuntimeState`; there is no module-level
`app_state` singleton. `create_app()` builds a fresh state, service container,
and adapter graph for each app.

- `app.py` - `create_app()`, service composition, routers, static mount.
- `dependencies.py` - injects `ApplicationServices` from `app.state`.
- `routes/` - pages, projects, topology, routing, traffic routers.
- `services/` - project lifecycle, topology views, routing, traffic jobs.
- `adapters/` - the only modules importing `TopologyManager` or concrete flow
  classes.
- `state.py` - `ProjectSession`, `ProjectTaskManager`, `RuntimeState`.
- `schemas.py` - Pydantic request/response models.
- `errors.py` - API exceptions and the common error envelope.
- `config.py` - host, port, and save-root settings.
- `storage.py` - path resolution and save-root containment.
- `ground_stations.py` - CSV parsing and safe temporary output.
- `serializers.py` - traffic result shaping.

## Dependency rules

Routes translate HTTP. Services coordinate use cases. Adapters own the external
dependency. Domain/runtime modules depend on nothing external and are tested
without Docker.

The topology adapter wraps private operations (`_sync_node_positions`,
`_apply_network_config`) and the raw iperf interval data. Routes and services do
not import those dependency internals.

## Phase 1 changes

- Added `ProjectSession`/`ProjectTaskManager` with single-flight reservation,
  explicit states, and a preserved previous project on failure.
- Added `GET /api/project/status`; the New Project page stops polling on
  `error` and shows the failure message.
- Fixed `/api/project/config` and the edit-form round-trip.
- Load preserves the user-facing project name; save/download uses it.

## Phase 2 changes

- Added Pydantic request/response models and `response_model` for every JSON
  route.
- Added one error envelope for 400/404/409/422/500, including framework 404s and
  unexpected exceptions.
- Moved ground-station CSV handling and traffic serializers into pure modules.
- Added loopback defaults, environment-backed settings, save-root containment,
  and unique temporary station files.

## Phase 3 changes

- Added `create_app(settings, services)`; every test gets an isolated app and
  runtime state.
- Removed the global `app_state` singleton. Services are injected through
  `Depends(get_services)` and stored on `app.state`.
- Split the monolithic route module into pages, projects, topology, routing, and
  traffic routers. Handlers are thin translation layers.
- Added `ProjectService`, `TopologyService`, `RoutingService`, and
  `TrafficService`.
- Added `SatGoNetemTopologyAdapter` and `SatGoNetemTrafficAdapter` behind narrow
  protocols in `services/ports.py`.
- Added structural tests for adapter boundaries, absence of the global
  singleton, and route-handler size.
- Added an app-factory isolation test and a real topology-adapter contract test.

## Test strategy

- The integration fixture is a **10x10 Walker delta** constellation (100
  satellites) with one Berlin ground station.
- The fixture builds in-process with `TopologyManager.from_satcom`; no Docker,
  no GoNetem server, and no containers are required for the default suite.
- API tests use `create_app()` per test with an isolated save root.
- Unit tests cover serializers, storage, traffic-flow normalization, routing
  guards, and project lifecycle transitions.
- A structural test asserts `TopologyManager` and concrete flow classes appear
  only in their adapters, private dependency hooks appear only in adapters, and
  route handlers stay small.
- Docker-backed routing and traffic happy paths are not part of the default
  suite. They will be covered by optional contract tests.

## Current measurements

Measured on 2026-11-03 with Python 3.15.0, pytest 9.2.0, and coverage 7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **119 passed** in about 1.7 s.

| Module | Statements | Coverage |
|---|---:|---:|
| `adapters/satgonetem_topology.py` | 154 | 86% |
| `adapters/satgonetem_traffic.py` | 77 | 77% |
| `services/project_service.py` | 73 | 86% |
| `services/routing_service.py` | 45 | 68% |
| `services/topology_service.py` | 37 | 98% |
| `services/traffic_service.py` | 80 | 85% |
| `state.py` | 117 | 95% |
| `schemas.py` | 120 | 98% |
| `storage.py` | 29 | 95% |
| **Total** | **1075** | **89%** |

Branch coverage is enabled. No coverage threshold is enforced yet; Phase 4
will add the job-registry guarantees and traffic cancellation tests.

## Tooling decisions

- `uv.lock` is the source of truth and is committed.
- `requirements.txt` is generated from the lock for pip users. Regenerate it
  with:

  ```bash
  uv export --no-hashes --no-emit-project --format requirements-txt
  ```

  Keep the two-line warning header at the top of the file.
- Ruff checks `E9`, `F`, and `I` across the repository. Formatting is checked
  for the test suite; production files are formatted as they are touched.
- CI runs on pushes and pull requests to `main` and `develop`, installs from the
  lockfile, runs lint and tests, and verifies that the wheel contains the
  application modules, templates, and static assets.

## Next phase

Phase 4 adds the flow-strategy registry, a bounded job repository with
per-job synchronization, and real traffic cancellation. See issue #1 for the
full plan.
