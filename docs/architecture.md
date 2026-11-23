# Architecture and test baseline

Status: Phase 7 complete; the refactor is done. The tracking issue is
[#1](https://github.com/SatComProjects/Satgonetem-Gui/issues/1) and the
completed phase issues are
[#2](https://github.com/SatComProjects/Satgonetem-Gui/issues/2),
[#3](https://github.com/SatComProjects/Satgonetem-Gui/issues/3),
[#4](https://github.com/SatComProjects/Satgonetem-Gui/issues/4),
[#5](https://github.com/SatComProjects/Satgonetem-Gui/issues/5),
[#6](https://github.com/SatComProjects/Satgonetem-Gui/issues/6),
[#7](https://github.com/SatComProjects/Satgonetem-Gui/issues/7),
[#8](https://github.com/SatComProjects/Satgonetem-Gui/issues/8), and
[#9](https://github.com/SatComProjects/Satgonetem-Gui/issues/9).

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
- `routes/` - pages, projects, topology, addressability, routing, simulation,
  traffic routers.
- `services/` - project lifecycle, topology views, satellite addressability,
  routing, simulation transport, traffic jobs.
- `adapters/` - the only modules importing `TopologyManager` or concrete flow
  classes.
- `state.py` - `ProjectSession`, `ProjectTaskManager`, `RuntimeState`.
- `schemas.py` - Pydantic request/response models.
- `errors.py` - API exceptions and the common error envelope.
- `config.py` - host, port, and save-root settings.
- `storage.py` - path resolution and save-root containment.
- `ground_stations.py` - CSV parsing and safe temporary output.
- `serializers.py` - traffic result shaping.
- `resources.py` - `importlib.resources` access to bundled presets/config.
- `data/` - packaged ground-station presets and sample GoNetem config.

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

## Phase 7 changes

- Moved ground-station presets and the sample GoNetEm config into
  `satgonetem_gui/data/`, included through package data, and loaded presets
  through `importlib.resources`.
- Removed the generated `requirements.txt`; `pyproject.toml` plus `uv.lock`
  are the only dependency manifests.
- Removed committed `.idea/` files and ignored the directory.
- Added an installed-wheel smoke test in CI and a package-data unit test.
- Added a WebGL-unavailable fallback for World View, covered by Playwright.
- Added an 85% coverage gate and completed the documentation/security notes.

## Phase 8 changes

- Added a `SimulationService` and a narrow `SimulationController` protocol for
  start/pause, single-step, reset, seek-to-step, and faster/slower playback.
- Added `POST /api/simulation/*` routes and extended `/api/status` with total
  steps, playback rate, and the last simulation tick error.
- Serialized simulation mutations with the existing session-level network
  operation gate and stopped the loop before project replacement and on
  application shutdown.
- Added a shared Dashboard/World View transport panel, Vitest coverage for the
  pure model, and Playwright coverage for the panel shell.

## Phase 9 changes

- Added an `AddressabilityService` and a narrow `AddressabilityController`
  protocol for global and per-node satellite traffic addressability.
- Added `GET/POST /api/satellites/addressable` and
  `POST /api/nodes/{name}/addressable`; node detail now exposes the satellite
  addressable flag.
- Kept addressability session-scoped for simulation-property (Walker) projects
  because the pinned core persists the flag only in runtime-state projects, and
  returned a routing-refresh flag when addressing is active.
- Added the Traffic page satellite-endpoint toggle, a per-node Node Explorer
  control, Vitest coverage for the pure formatting/rules, and a mocked
  Playwright flow that verifies endpoint refresh.

## Phase 10 changes

- Added a browser-local experiment ledger (`static/history_model.js`) that
  captures successful terminal runs, compacts long interval arrays, and caps
  the ledger by count and approximate bytes.
- Added a History view to the existing results modal with reopen, delete,
  per-run/all-run JSON export, CSV export, and same-kind comparison.
- Added queue `created_at`/`started_at` timestamps for run duration and bumped
  the queue module versions (`queue.js?v=23`, `queue_model.js?v=3`).
- Added Vitest coverage for compaction, normalization, export, and comparison,
  plus Playwright coverage for seeded history, live capture, exports, delete,
  compare, and a stubbed Chart.js contract.

## Phase 12 changes

- Added `PathReader` and `RoutingService.path` over the public
  `get_path_between_nodes`/`get_current_graph` APIs; added
  `GET /api/routing/path`.
- Added a diagnostic hop DTO with link type, direction, propagation delay, and
  cumulative totals, explicitly labeled as a routing-graph snapshot rather than
  the live forwarding table.
- Added the Node Explorer Forwarding Path card and World View path highlight,
  with shared pure formatting/link-identity helpers in `path_model.js`.
- Added Vitest coverage for path formatting/link keys and Playwright coverage
  for the Nodes path table and missing-path state.

## Phase 13 changes

- Extended `LinkResponse` with propagation delay, `get_capacity()` capacity, and
  active state.
- Added the Node Explorer per-node Links table with peer, type, direction,
  distance, delay, capacity, and state.
- Sized World View links logarithmically by capacity and colored inactive links
  red; the forwarding-path width override still takes precedence.
- Added `links_model.js`, Vitest coverage for formatting/filtering/width, and a
  Playwright node-link inspector flow.
- Deferred utilization until the core's `/tmp/interfaces` monitor contract is
  verified or replaced.

## Phase 14 changes

- Added a bounded environment doctor (`LocalEnvironmentDoctor`) for storage,
  Docker, required images, and GoNetEm server reachability.
- Added `POST /api/diagnostics/preflight` with a pure constellation estimate
  (satellites, inline stations, containers, rough memory) and explicit
  `blocking` semantics; only storage/configuration errors block creation.
- Replaced synthetic create percentages with session phase/progress fields
  (`validating`, `building`, `loading`, `finalizing`, `ready`, `error`) and
  monotonic elapsed time; UI phases without a percentage use an indeterminate
  bar.
- Added Dashboard/New Project readiness panels, Vitest formatting/model tests,
  and Playwright coverage for readiness, blocking creation, and indeterminate
  progress.
- Declared direct `docker` and `pyyaml` dependencies.

## Phase 15 changes

- Added a contained project workspace/catalog with opaque IDs, atomic writes,
  list/open/save-to/save-in-place/duplicate/delete, and malformed-file warnings.
- Added `/projects` with workspace listing and current-project save controls.
- Added `GET /api/links/usage` backed by the public core usage monitor, with a
  safe unavailable state and per-link utilization.
- Added opt-in World View usage coloring (green → amber → red), sampled every
  five seconds only while enabled.
- Added the workspace specification, ADR 0007, Vitest formatting/models, and
  Playwright workspace flows.

## Phase 16 changes

- Added a bounded background connectivity service over the public v0.3.2
  `build_connectivity_matrix()` API, with node resolution, generation guards,
  four-job capacity, and one-hour terminal TTL.
- Added connectivity start/status/CSV/JSON export routes and the
  `/connectivity` page with an N×N loss/RTT heatmap.
- Added the connectivity specification, Vitest matrix formatting, and
  Playwright start/heatmap/export coverage.

## Phase 17 changes

- Added a server-side experiment runner over v0.3.2 `Scenario` and
  `ExperimentRunner`, with validate-only/offline/live modes and a live network
  reservation.
- Persisted scenario, manifest, metrics, flows, errors, summary, report,
  connectivity, and provenance artifacts under the save root with bounded run
  capacity and allowlisted downloads.
- Added the `/experiments` page, experiment specification, Vitest formatting,
  and Playwright run/artifact coverage.

## Phase 18 changes

- Added `GET /api/experiments/{run_id}/metrics?tail=N` for bounded, parsed
  metric samples from running and completed runs.
- Added a run detail panel with a live chart, summary stats, report, scenario,
  and artifacts; added two-to-four-run comparison with a metric overlay and
  scenario line diff.
- Stripped the core report's absolute `run_dir` from stored and served
  summaries.
- Added the detail/compare specification, Vitest chart-data/table/diff tests,
  and Playwright detail/compare coverage.

## Phase 19 changes

- Added a coverage snapshot service and adapter over the public
  `get_coverage_percentage()` and `coverage_percentage_fast()` APIs, with
  per-shell grouping, per-ground-station best elevation, truncation flags, and
  a measured work cap.
- Added `POST /api/analysis/coverage` and a generation/step/options-scoped
  16-entry LRU cache.
- Added the `/coverage` page, coverage specification, Vitest formatting, and
  Playwright analyze/too-large-grid coverage.

## Phase 20 changes

- Added pure topology health checks (isolation, incomplete/duplicate positions,
  zero/negative capacity, negative delay, self-links, duplicate pairs) with
  bounded item previews.
- Added JSON/DOT/GraphML serializers and a protected export envelope with a
  10 MB cap.
- Added `GET /api/topology/health` and `GET /api/topology/export`, plus the
  Nodes page health/export card and its tests.

## Phase 21 changes

- Added browser-local traffic presets (versioned, capped, case-insensitive
  upsert), endpoint swap, and queue clone/history replay through the shared
  queue-item factory.
- Added pure preset and clone/replay models plus Vitest and Playwright coverage;
  bumped the queue/model and traffic controller cache versions.

## Phase 22 changes

- Added pure node search/type filtering, numeric-aware and city sorting, and
  browser-local favorite normalization/toggle helpers.
- Added the Node Explorer toolbar, live visible/total count, favorite stars,
  and an accessible row-toggle button while preserving polling and detail
  state.
- Added Vitest filter/sort/favorite tests and Playwright search/filter/sort/
  favorite-persistence coverage.

## Phase 23 changes

- Added pure link categorization/summaries, nearest-peer distance ordering, and
  deep-link parsing to `world_model.js`.
- Added the World View node inspector, ground-station selection, link
  isolation dimming, deep links, and the Node Explorer "Open in World" link.
- Added Vitest inspector tests and a WebGL-conditional Playwright deep-link
  panel test.

## Phase 24 changes

- Added the shared skip link/main landmark, active navigation, focus-visible
  ring, responsive header, and narrow-screen queue bottom sheet.
- Added the `?` shortcut dialog and guarded `g`-prefix navigation, with pure
  shortcut metadata/guards and readiness signalling for tests.
- Moved World View's inline CSS verbatim into `world.css`.
- Added Vitest shortcut-guard tests and Playwright shell/shortcut/responsive
  queue coverage.

## Phase 25 changes

- Added `POST /api/analysis/link-budget` using the public core antenna, budget,
  propagation, receiver, and capacity-strategy APIs, with atmospheric fallback
  and full breakdown.
- Added the `/link-budget` workbench page and pure formatting/summary model.
- Added adapter/API/Vitest/Playwright coverage; project application and
  persistence remain a later phase.

## Phase 26 changes

- Added a phase-1 scenario builder for the experiment header, Walker shells, and
  ground stations with deterministic YAML generation and validation.
- Added pure add/remove/validate/YAML helpers, builder e2e coverage, and a
  pytest check that the generated YAML parses with the core `Scenario` schema.
- Traffic, events, and topology-file authoring remain in YAML.

## Phase 27 changes

- Exposed satellite shell identifiers (via the simulation manager object ids)
  and link loss/jitter in the read models.
- Added the `/topology` deterministic SVG graph with shell/type/search filters,
  edge metrics, connected-component highlighting, routing-path trace, node
  inspector, caps, and polling.
- Added pure graph filter/layout/partition/tooltip models, Vitest coverage, and
  Playwright graph tests.

## Phase 28 changes

- Added the `/monitor` live traffic page: two-second usage/status/link polling,
  a 300-sample client ring, per-link and per-node aggregates, a total-throughput
  chart, pause/resume/clear, and CSV/JSON export.
- Added the pure monitor aggregation/serialization model, Vitest coverage, and
  Playwright pause/export/unavailable tests.
- Configured link metrics and measured usage are labelled separately; no
  backend changes were needed beyond the shell/loss/jitter read fields.

## Phase 29 changes

- Added a bounded in-memory topology snapshot history (240 steps / 100k link
  records) recorded on observed step changes and cleared on project generation
  changes.
- Added record/list/compare routes with added/removed/changed links, node
  changes, dedupe, and 404 semantics.
- Added automatic snapshot recording, step selects, a diff table, and
  added/removed/changed edge highlighting (including removed-link ghosts) to
  the topology page.
- Added service/API tests and Playwright comparison coverage.

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
- Package-data tests verify bundled presets/config, and CI installs the built
  wheel into a clean target before importing the app.
- Vitest covers the pure queue, ground-station selection, traffic payload, API
  wrapper, simulation formatting/action rules, addressability summaries/rules,
  experiment-history compaction/export/comparison, forwarding-path formatting,
  link formatting/filtering/width/usage colors, preflight/phase formatting,
  project-workspace formatting, connectivity matrix formatting, coverage
  formatting/sorting, topology health formatting, node filter/sort/favorites,
  world inspector link/peer helpers, shell shortcut guards, link-budget
  formatting, scenario builder generation/validation, topology graph
  filtering/layout/partitions, traffic monitor aggregation/export, topology
  history/compare, traffic preset and clone/replay models, experiment
  status/summary/artifact/detail formatting and diffing, and escaping modules.
- Playwright covers page navigation, runtime page errors, absence of inline
  handlers, queue add/remove, cross-preset station selection, edit-form prefill,
  node expansion, dashboard counts, simulation panel accessibility,
  addressability endpoint refresh, history reopen/capture/export/delete/compare,
  forwarding-path rendering, link-inspector rendering, readiness checks,
  blocking creation, indeterminate build progress, workspace list/open/save,
  connectivity start/heatmap/export, coverage analyze/too-large-grid,
  topology health/export, node search/filter/sort/favorites, world
  inspector/deep link/isolation, shell shortcuts/responsive queue, link-budget
  calculate/error, scenario builder generate/validate/collapse, topology graph
  filters/partitions/path/inspector, topology snapshot compare/diff, traffic
  monitor sample/pause/export, traffic preset/swap/clone/replay, experiment
  start/list/artifact download, detail/live metrics, comparison/diff, and the
  WebGL fallback. World View WebGL rendering itself remains a manual desktop
  check.

## Current measurements

Measured on 2026-11-22 with Python 3.12.16, pytest 9.2.0, and coverage
7.17.1:

```bash
uv run pytest --cov=satgonetem_gui --cov-report=term-missing
```

Result: **809 passed, 1 skipped** in about 63 s with coverage. Frontend:
**171 Vitest tests**, **54 Playwright tests**.

Branch coverage is enabled with an 85% minimum; the current suite is at
**89.88%** over 4901 statements.

## Tooling decisions

- `uv.lock` is the source of truth and is committed.
- Runtime data is packaged under `satgonetem_gui/data/` and loaded through
  `importlib.resources`; the wheel test verifies it is present.
- SatGoNetEm is pinned to the `v0.3.2` Git tag (commit `b5a2f6e`). The runtime
  dependency is a PEP 508 direct URL, so built wheel metadata carries the pin
  instead of a floating version range; `[tool.uv.sources]` pins the same tag
  for `uv` resolution. The 10x10 adapter contract tests pass against the tag.
- Ruff checks `E9`, `F`, and `I` across the repository. Formatting is checked
  for the test suite; production files are formatted as they are touched.
- CI runs on pushes and pull requests to `main` and `develop`, installs Python
  and npm dependencies, runs Python/Vitest/Playwright tests, and verifies the
  wheel contains application modules, data, templates, and static assets and
  that its metadata pins the SatGoNetEm `v0.3.2` direct URL.
- `node_modules/`, `.npm-cache/`, and Playwright browser/artifacts are ignored.

## Status

The refactor is complete. Tracking issue #1 is closed after the Phase 7 merge;
future work should use new scoped issues.
