# Architecture and test baseline

Status: Phase 6 complete. The refactor is tracked in
[issue #1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1);
completed phases are
[#2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2),
[#3](https://github.com/SatComProjects/Satgonetem-Gui/issues/3),
[#4](https://github.com/SatComProjects/Satgonetem-Gui/issues/4),
[#5](https://github.com/SatComProjects/Satgonetem-Gui/issues/5),
[#6](https://github.com/SatComProjects/Satgonetem-Gui/issues/6),
[#7](https://github.com/SatComProjects/Satgonetem-Gui/issues/7), and
[#8](https://github.com/SatComProjects/Satgonetem-Gui/issues/8).

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

## Phase 4 changes

- Added a traffic strategy registry keyed by `iperf3`, `ping`, and `hping3`.
  Each strategy carries its typed request model and starter.
- The service and adapter each use one start/status dispatch path keyed by the
  job kind; no if/elif chain over concrete flow classes remains.
- Replaced the simple job dictionary with a bounded `JobRegistry`:
  - per-job locks;
  - immutable terminal transitions (`done`, `error`, `cancelled`);
  - TTL cleanup of finished jobs;
  - a maximum job count, with 429 when only running jobs remain.
- Cancel now calls `TrafficGateway.stop()`; finished jobs return 409, failed
  stops return 500, and cancelled jobs are never polled again.
- A flow rejected by the capacity limit is stopped rather than leaked.
- Added tests for strategy registration, terminal transitions, TTL cleanup,
  capacity eviction, cancel success/failure, and API cancel behavior.

## Phase 5 changes

- Added explicit `addressing_applied` state to the project session. It resets
  when a new project is installed and is cleared by routing delete and
  container stop.
- Split the network controller into addressing, routing-init, delete, start,
  stop, and status operations.
- Negative dependency return codes now raise `NetworkOperationError` in the
  topology adapter; routing service maps them to API 500 responses.
- Routing status no longer equates `addressing_applied` with container state.
- Removed the `set_status(True)` workaround after container stop. The dashboard
  reports `constellation_loaded` from the project session, not the container
  status.
- Added fake-controller failure tests and an opt-in real-container contract test
  (`SATGONETEM_RUN_CONTAINER_TESTS=1`).

## Phase 6 changes

- Converted page scripts to ES modules with a shared `api.js` client and a
  quote-safe `escape.js` helper.
- Removed inline `onclick`/`onchange` handlers and the inline load/save script;
  project actions now live in `project_actions.js`.
- Queue items use stable queue IDs. Removal clears the matching poll timer, and
  `Clear` cancels every tracked timer.
- Ground-station selections are keyed by `preset:index`, so equal indexes in
  different presets no longer collide.
- Extracted pure `queue_model.js`, `ground_stations_model.js`, and
  `traffic_model.js` modules with Vitest coverage.
- Added Playwright smoke coverage for all non-WebGL pages, absence of inline
  handlers, and queue add/remove behavior.
- World View remains a manual WebGL check; the smoke test only verifies the
  page shell.

## Test strategy

- The integration fixture is a **10x10 Walker delta** constellation (100
  satellites) with one Berlin ground station.
- The fixture builds in-process with `TopologyManager.from_satcom`; no Docker,
  no GoNetem server, and no containers are required for the default suite.
- API tests use `create_app()` per test with an isolated save root.
- Unit tests cover serializers, storage, traffic-flow normalization, routing
  guards, project lifecycle transitions, the job registry, and cancellation.
- A structural test asserts `TopologyManager` and concrete flow classes appear
  only in their adapters, private dependency hooks appear only in adapters, and
  route handlers stay small.
- Docker-backed routing and traffic happy paths are not part of the default
  suite. The fake traffic gateway exercises start/status/cancel without
  containers.
- The real-container routing contract test is marked `slow` and skipped unless
  `SATGONETEM_RUN_CONTAINER_TESTS=1`.
- Vitest covers the pure queue, ground-station selection, traffic payload, API
  wrapper, and escaping modules.
- Playwright covers page navigation, runtime page errors, absence of inline
  handlers, queue add/remove, cross-preset station selection, edit-form prefill,
  node expansion, and dashboard counts. World View WebGL rendering is excluded.

## Current measurements

Measured on 2026-11-03 with Python 3.15.0, pytest 9.2.0, and coverage 7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **146 passed, 1 skipped** in about 1.8 s. Frontend: **14 Vitest tests**, **9 Playwright smoke tests**.

| Module | Statements | Coverage |
|---|---:|---:|
| `adapters/satgonetem_topology.py` | 166 | 88% |
| `adapters/satgonetem_traffic.py` | 76 | 76% |
| `services/project_service.py` | 73 | 86% |
| `services/routing_service.py` | 63 | 82% |
| `services/topology_service.py` | 37 | 98% |
| `services/traffic_service.py` | 155 | 88% |
| `state.py` | 123 | 95% |
| `schemas.py` | 120 | 98% |
| `storage.py` | 29 | 95% |
| **Total** | **1193** | **90%** |

Branch coverage is enabled. No coverage threshold is enforced yet. Phase 7
covers packaging, resources, and documentation cleanup.

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
- CI runs on pushes and pull requests to `main` and `develop`, installs Python
  and npm dependencies, runs Python/Vitest/Playwright tests, and verifies that
  the wheel contains the application modules, templates, and static assets.
- `node_modules/`, `.npm-cache/`, and Playwright browser/artifacts are ignored.

## Next phase

Phase 7 moves bundled resources into the package, fixes installed-package
resource discovery, and cleans up documentation and repository debt. See
issue #1 for the full plan.
