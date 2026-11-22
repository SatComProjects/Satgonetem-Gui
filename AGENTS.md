# Development Guide

SatGoNetem GUI is a FastAPI + Jinja2 + vanilla JavaScript control panel for the
[SatGoNetem](https://github.com/satcomprojects/satgonetem) satellite network
emulation framework. Python source lives in `satgonetem_gui/`, pytest tests in
`tests/`, Vitest tests in `js-tests/`, Playwright tests in `e2e/`, and
architecture notes in `docs/`. Development uses `uv`, `pytest`, `ruff`, `npm`,
Vitest, and Playwright, and targets the `develop` branch.

This guide adapts the SatGoNetem development guide to this repository. It is the
working agreement for humans and AI agents and applies to every change,
including refactors. Phased specifications live in
[docs/specs/](docs/specs/README.md), architecture decisions are recorded in
[docs/adr/](docs/adr/README.md), and the current structure and test baseline are
documented in [docs/architecture.md](docs/architecture.md). The GUI consumes
SatGoNetem as a pinned Git dependency; work that needs new core capability
follows the cross-repository rules below.

## Non-negotiables

1. **Specification first.** Do not guess requirements. Restate the request,
   acceptance criteria, edge cases, and constraints before writing code. Ask
   when a requirement is ambiguous.
2. **Test-driven development.** Write a failing test before implementation.
   Verify it fails for the expected reason, then make the smallest change that
   passes. Refactor only with tests green.
3. **Small, incremental changes.** One concern per change. Do not mix behavior
   changes, refactors, formatting, and dependency updates.
4. **Preserve behavior unless explicitly asked to change it.** Refactors must
   be behavior-preserving and covered by tests before and after.
5. **Never weaken tests to get green.** Do not delete assertions, loosen
   tolerances, add skips, or over-mock to make a test pass. Fix the cause.
6. **Never claim a check passed without running it.** Report the exact command,
   exit status, and any relevant failure output.
7. **Report unverified assumptions.** If something could not be executed
   locally (Docker, WebGL, a real browser, external services), say so
   explicitly.
8. **Review the complete diff before declaring completion.** Include
   architecture tradeoffs and known limitations in the final report.

## Branch and pull-request policy

- `develop` is the integration branch. All work starts from an up-to-date
  `develop` and targets `develop` in a pull request.
- `main` is release-only. Do not commit feature work to `main`.
- Use short-lived branches:
  `feat/<topic>`, `fix/<topic>`, `refactor/<topic>`, `test/<topic>`,
  `docs/<topic>`, `chore/<topic>`.
- A pull request description states: the specification, the RED evidence
  (failing test and command), the implementation summary, validation commands
  and results, architectural tradeoffs, unverified assumptions, and screenshots
  or recordings for visible UI changes where practical.
- The `CI` workflow must pass before merge on `develop` and `main`. It runs the
  Vitest suite, Ruff lint and format checks, pytest with the 85% coverage gate,
  Playwright browser smoke tests, and the wheel build plus installed-wheel
  check. Do not bypass or disable a gate to land a change.

## Six-stage workflow

### 1. Understand

- Restate the requirement and acceptance criteria.
- List edge cases and error paths: first load, no active project, failed
  project build/load, stopped containers, routing not applied, traffic
  capacity limits, stale or cancelled jobs, and unavailable WebGL.
- List explicit non-goals.
- Identify affected routes, services, adapters, schemas, templates, static
  modules, and documentation.
- Name constraints: Python 3.10+ (CI runs 3.12), Node 24, browser/WebGL
  support, loopback-only trusted use with no authentication, the default suite
  requiring no Docker, and the pinned SatGoNetem version.

### 2. Design

- Identify responsibilities, interfaces, and dependency direction before
  coding.
- Design the API first: request/response schemas, status codes, and the common
  error envelope before the page that consumes them.
- Design page state explicitly: loading, empty, success, and error. Separate
  pure frontend state from DOM wiring.
- Check the change against the architecture rules below and SOLID
  responsibilities.
- Prefer the simplest design that satisfies the specification. Avoid a
  frontend framework, build step, speculative abstraction, or new layer
  without a demonstrated need.
- For cross-module, public-API, or page-behavior changes, discuss alternatives
  and the tradeoff before implementation.
- Write a specification in `docs/specs/` when the work spans phases or changes
  a public contract, and an ADR in `docs/adr/` when a decision is costly to
  reverse or chooses between credible alternatives.

### 3. Test (RED)

- Add the smallest tests that express the new behavior: pytest unit/API tests
  for backend logic and contracts, Vitest tests for pure frontend models, and
  Playwright tests for page wiring or regressions that only appear in a
  browser.
- Run the tests and confirm they fail for the expected reason (not an import
  error, missing fixture, or typo).
- A bug fix starts with a test that reproduces the bug.
- For behavior that cannot be automated (for example real WebGL globe
  rendering), state the manual check and why automation is not feasible. Do
  not claim an automated pass for it.

### 4. Implement (GREEN)

- Write the smallest production change that makes the failing tests pass.
- Do not add unrelated refactors, renames, or formatting churn in the same
  change.
- Keep dependencies explicit and injected where a boundary is involved. Do not
  add a runtime dependency, CDN asset, or frontend tool without justification.

### 5. Refactor

- With tests green, remove duplication, clarify names, and simplify
  abstractions.
- Re-check SOLID responsibilities, especially SRP and DIP, without introducing
  indirection for its own sake.
- Refactoring commits must not change behavior. If behavior must change, go
  back to stage 3 and add a test.

### 6. Validate

- Run the narrowest relevant tests first, then the full Python suite. Run the
  Vitest and Playwright suites when frontend behavior changes.
- Run lint and format checks. Run `uv lock --check` when dependencies change,
  and keep `package-lock.json` consistent with `package.json`.
- Build and inspect the wheel when packaging, bundled data, templates, or
  static assets change.
- Inspect the complete `git diff`, including generated or untracked files.
- Report: commands run, exit statuses, architectural tradeoffs, and anything
  unverified.

## Design principles

These are requirements, not preferences. Each principle names how it is
enforced; when a change cannot satisfy one, the specification or ADR must say
why and the deviation is reviewed explicitly.

1. **Boundaries before convenience.** A route translates HTTP, a service
   orchestrates one use case, and an adapter owns the external dependency.
   Never reach across a boundary to save a call, share a mutable object, or
   import core types into routes or services. Enforced in part by
   `tests/test_architecture.py`; the rest by review.
2. **One composition root.** `create_app()` builds a fresh runtime state,
   service container, and adapter graph for each application instance. Do not
   add module-level mutable state, hidden caches, or global singletons.
   Enforced by `tests/test_app_factory.py` and the isolated-app test rule.
3. **Explicit state over inferred state.** Model lifecycle with explicit states
   and legal transitions (`ProjectSession`, `ProjectTaskManager`, the job
   registry) instead of booleans derived from unrelated values. Pages mirror
   the same states: loading, empty, success, and error. Enforced by the
   lifecycle and job-registry tests.
4. **Depend on narrow protocols and inject the boundary.** Services depend on
   `services/ports.py`; tests inject fakes rather than patching private
   internals. A new external capability enters through a protocol and an
   adapter, never as a direct call from a service or route. Enforced by the
   structural tests and the fake-based service tests.
5. **Extend by registration, not by branching.** A new traffic kind is a typed
   request schema, a strategy, and an adapter operation registered with the
   existing registry; a new routing method belongs in the core daemon contract
   behind the adapter. Do not add `if`/`elif` chains over kinds or methods in
   callers, adapters, or templates. Enforced by the strategy-registry tests
   and review.
6. **Fail at the boundary with one error shape.** Validate input with Pydantic
   models, raise the shared exceptions in `errors.py`, and return the common
   error envelope. Never invent an ad hoc JSON error, return a bare string for
   failure, or leak a traceback to the browser. Enforced by the API, error,
   and OpenAPI contract tests.
7. **Separate pure logic from effects.** Parsing, selection, queue transitions,
   and payload shaping live in pure, testable modules (`*_model.js`,
   `serializers.py`, `ground_stations.py`). HTTP, DOM, filesystem, and core
   calls stay at the edges. Enforced by Vitest and pytest unit tests.
8. **Secure by default within the trust boundary.** Bind to `127.0.0.1`, keep
   project paths inside `SATGONETEM_GUI_SAVE_ROOT`, treat project JSON,
   ground-station CSV files, and traffic output as untrusted input, and escape
   before rendering. Enforced by the save-path, storage, and API tests.
9. **Degrade gracefully and surface failure.** A missing browser capability
   must not break the page (World View falls back when WebGL is absent), and a
   failed request must produce a visible message rather than a silent console
   error. Enforced by the Playwright fallback test and `ApiError` handling.
10. **Rule of three before abstraction.** Do not add a layer, factory, plugin
    system, framework, or build step without a concrete second use case and a
    specification. Prefer deleting code to generalizing it; review-only.

## Architecture rules

### Boundaries

- `satgonetem_gui/app.py` — the composition root. `create_app()` builds a
  fresh runtime state, service container, and adapter graph for each
  application instance. Do not introduce module-level mutable singletons.
- `satgonetem_gui/dependencies.py` — injects `ApplicationServices` from
  `app.state`.
- `satgonetem_gui/routes/` — HTTP translation only: validate input, call one
  service operation, and shape the response. No orchestration, no core imports,
  and no direct adapter imports. Structural tests enforce that handlers stay
  translation-sized (60 lines or fewer).
- `satgonetem_gui/services/` — use-case orchestration for project lifecycle,
  topology views, routing, and traffic jobs. Depend on the narrow protocols in
  `satgonetem_gui/services/ports.py`, not on FastAPI or SatGoNetem types.
- `satgonetem_gui/adapters/` — the only modules allowed to import SatGoNetem
  APIs (`TopologyManager`, concrete traffic-flow classes) and private core
  hooks. New core integration enters here behind a protocol.
- `satgonetem_gui/state.py` — per-application runtime state
  (`RuntimeState`, `ProjectSession`, `ProjectTaskManager`). Every test creates
  an isolated app; do not share state through globals.
- `satgonetem_gui/schemas.py` — Pydantic request/response models. Every JSON
  route declares a response model and appears in the OpenAPI contract.
- `satgonetem_gui/errors.py` — the shared API exception types and error
  envelope. Do not invent ad hoc error shapes.
- `satgonetem_gui/storage.py` — path resolution and save-root containment. All
  project save/load paths pass through it.
- `satgonetem_gui/ground_stations.py`, `serializers.py`, and `resources.py` —
  pure parsing, result shaping, and packaged-resource access. Keep them free of
  request handling.
- `satgonetem_gui/static/` — browser ES modules. `api.js` owns HTTP, `escape.js`
  owns HTML escaping, pure state/transform logic lives in `*_model.js`, and page
  modules wire the DOM to those pieces.
- `satgonetem_gui/templates/` — Jinja2 templates sharing `base.html`. Keep
  markup, not behavior, in templates: no inline event handlers and no inline
  scripts.
- `tests/` — pytest suite mirroring the Python module layout.
- `js-tests/` — Vitest tests for pure frontend modules.
- `e2e/` — Playwright smoke tests for page navigation and browser behavior.

### Dependency direction

```text
app.py (composition root)
  -> routes/*        (HTTP translation only)
  -> services/*      (use cases)
       -> services/ports.py (narrow protocols)
  -> adapters/*      (implement the protocols; only core integration point)

state.py / config.py / schemas.py / errors.py / storage.py / serializers.py
```

Routes and services must not import adapters or SatGoNetem. Adapters implement
the protocols and may import core types; they do not import routes. Static
modules communicate with the backend only through the HTTP API. Do not reach
into private SatGoNetem attributes or `_data` outside `adapters/`; the
structural test treats that as a contract violation. Do not introduce import
cycles.

### SOLID, pragmatically

- **Single responsibility:** one reason to change per module/class. Page
  controllers wire the DOM, pure models transform state, services own one use
  case, and adapters own the external dependency.
- **Open/closed:** extend through existing strategies and composition. A new
  traffic kind is a request schema, strategy, and adapter operation registered
  with the existing registry, not an `if`/`elif` chain in callers. A new
  routing method belongs in the core daemon contract and is exposed through the
  adapter, not branched into templates.
- **Liskov substitution:** protocol implementations honor the documented
  contract, including error behavior and return types.
- **Interface segregation:** keep protocols in `services/ports.py` narrow and
  capability-specific; do not force implementations to depend on operations
  they do not use.
- **Dependency inversion:** services depend on protocols for SatGoNetem,
  Docker/gRPC, filesystem, and other external boundaries. Inject fakes in tests
  instead of patching private internals.
- Apply the rule of three before extracting an abstraction. Do not add a layer,
  factory, or plugin system without a concrete second use case.

### Frontend rules

- Use browser-native ES modules. Do not add a build step or UI framework
  without a specification and maintainer agreement.
- Never use inline `onclick`, `onchange`, `onload`, or inline `<script>` blocks.
  Wire events with `addEventListener` from module scripts.
- Route HTTP calls through `static/api.js` and handle `ApiError` so failures
  produce a user-visible message instead of a silent console error.
- Escape untrusted values before inserting HTML. Prefer `textContent`; when
  markup is unavoidable, use `escapeHtml()` from `static/escape.js`.
- Keep pure state and data transforms in `*_model.js` modules with Vitest
  coverage. Page modules should mostly translate events and DOM state.
- Queue items keep stable IDs. Removing or clearing an item cancels its poll
  timer; no interval, timeout, or listener may leak across page use.
- Every async view has explicit loading, empty, success, and error states. Do
  not leave a spinner running or hide failures.
- Degrade gracefully where the browser lacks a capability. World View must
  show its fallback when WebGL is unavailable and must not break the rest of
  the page.
- Keep markup accessible: semantic elements, associated labels, keyboard
  reachability, and explicit `type="button"` on non-submit buttons.
- Bump the `?v=` query parameter when changing a static asset referenced by a
  template so browsers do not serve a stale file.

### Security and trust boundary

- The GUI has no authentication and is intended for trusted local use. Keep
  the default bind address on `127.0.0.1`; do not widen it, add permissive
  CORS, or disable a protection without an explicit requirement.
- Project save/load paths must remain inside `SATGONETEM_GUI_SAVE_ROOT`.
  Validate on read and write; never trust a client-supplied path.
- Treat project JSON, ground-station CSV files, and traffic output as
  untrusted input: validate at the schema boundary and escape when rendering.
- Do not log secrets, tokens, or full environment dumps. Do not interpolate
  user input into shell commands; call typed adapters instead.
- Pin dependencies and keep lock files committed. New dependencies need a
  concrete reason and a security/maintenance check.

### Cross-repository changes

- The GUI consumes SatGoNetem from the pinned Git tag in `pyproject.toml`
  (`v0.3.2`, resolved commit `b5a2f6eef93c8a1f57c0cfa031343f80b2eac535`) and
  records the resolved revision in `uv.lock`. The runtime dependency is a PEP
  508 direct URL so built wheel metadata carries the pin, and
  `[tool.uv.sources]` pins the same tag for `uv` resolution.
- If a GUI feature needs new core capability, land and test the core change in
  the `satgonetem` repository first, produce a release tag, then bump the pin
  and lock file here and update the adapter contract tests.
- Never vendor, copy, or patch SatGoNetem internals in this repository. Do not
  add new private-hook usage; the existing exceptions stay confined to
  `adapters/` and are covered by contract tests.
- Report the core version and commit that were actually tested.

## Coding practices

### Python

- Annotate public functions, service methods, and adapter boundaries with type
  hints; use built-in generics (`list[str]`, `dict[str, Any]`) because the
  package targets Python 3.10+.
- Use Pydantic models at the HTTP edge (`schemas.py`). Do not pass raw request
  dictionaries through routes or services when a schema exists.
- Inject dependencies through `ApplicationServices` and the protocols in
  `services/ports.py`. Do not create module-level clients, reach into
  `app.state` outside `dependencies.py`, or monkeypatch core internals.
- Do not block the event loop. Run synchronous core, Docker, or gRPC work
  through `asyncio.to_thread` in services, and long project builds through
  `ProjectTaskManager`.
- Catch the narrowest exception that can occur, convert it to the shared API
  error at the boundary, and log with `logger.exception`. Never swallow an
  exception with a bare `except` or `except Exception: pass`.
- Use `pathlib.Path`; resolve every project save/load path through
  `storage.py`, and create temporary files with `tempfile` and clean them up.
- Load bundled resources through `resources.py` and `importlib.resources`, not
  through `__file__` arithmetic.
- Use `logging.getLogger(__name__)` per module. Do not `print` from library
  code, log secrets or environment dumps, or interpolate user input into shell
  commands.

### Browser JavaScript

- Use browser-native ES modules. One concern per module: `api.js` owns HTTP,
  `escape.js` owns escaping, `*_model.js` owns pure state and transforms, and
  page modules wire events to them. No build step, framework, or global
  namespace.
- Route every request through `api.js` and handle `ApiError`; show the failure
  in the relevant status region and leave the page usable.
- Write text with `textContent`. When markup is unavoidable, build it with
  `escapeHtml()`; never interpolate untrusted values into an HTML string.
- Wire events with `addEventListener`; never add inline handlers or inline
  scripts. Give non-submit buttons an explicit `type="button"`.
- Keep item identity stable and clean up. Removing or clearing a queue item
  cancels its timers and listeners; no interval, timeout, or listener may
  outlive its element or page.
- Model every async view explicitly: loading, empty, success, and error. Do not
  leave a spinner running, hide a failure, or show stale success data.
- Prefer classes in `base.css` or the page stylesheet over new inline styles.
- Bump the template's `?v=` query parameter when a static asset changes.

### Templates

- Extend `base.html` and keep markup, not behavior, in templates.
- Do not use `|safe` on project data, request values, or traffic output. Jinja
  autoescaping stays enabled.
- Keep controls accessible: semantic elements, associated labels, keyboard
  reachability, and visible focus where the page overrides browser defaults.

### Tests

- Follow the testing rules below. Name each test for the behavior it protects,
  arrange data with the shared fixtures or factories, and keep tests
  deterministic: no real sleeps, network calls, or container starts in the
  default suite.
- Change a structural test only when the architectural contract changes on
  purpose, and record the reason in the specification or ADR.

### Documentation and commits

- Update `docs/architecture.md` when module boundaries, the dependency
  direction, or measured baselines change.
- Write a specification in `docs/specs/` for phased or public-contract work and
  an ADR in `docs/adr/` for a decision that is costly to reverse or trades off
  alternatives.
- Update `README.md` for user-facing behavior, requirements, or configuration,
  and keep this guide current when a rule changes.
- Write imperative, scoped commit subjects (`routes: validate save paths`) and
  one concern per commit. PR descriptions follow the branch policy above.

## Testing rules

- Python tests live under `tests/` and are named for the module or feature they
  cover (`tests/test_<module>.py`, `tests/test_<feature>.py`). Frontend unit
  tests live in `js-tests/<module>.test.js`; browser tests live in
  `e2e/*.spec.js`.
- Prefer deterministic unit tests. Mock at external boundaries (SatGoNetem,
  Docker, subprocess, network), not at internal domain logic.
- Use the fixtures in `tests/conftest.py`, `tests/factories.py`, and
  `tests/helpers.py`; do not add duplicate harness code.
- API tests create a fresh application with an isolated save root per test.
  Do not rely on process-global state or a shared server.
- The default Python suite builds a 10x10 Walker constellation in process and
  requires no Docker, GoNetEm server, or containers.
- Mark long-running tests `slow`; run them explicitly with `-m slow` when
  appropriate. Real-container tests are additionally gated by
  `SATGONETEM_RUN_CONTAINER_TESTS=1`. Their skip reason must state the
  prerequisite, and the report must say they were skipped or not run.
- Use Vitest for pure frontend models and Playwright for page behavior. Actual
  WebGL rendering remains a manual desktop check; report it as such.
- Test behavior and contracts, not implementation details or call sequences
  unless the interaction is the contract.
- Structural tests are contracts: keep `TopologyManager`, concrete flow
  classes, and private core hooks confined to adapters, and keep route handlers
  small. Do not weaken these checks.
- Every bug fix includes a regression test.
- Coverage is a diagnostic, not a target. Do not game it.

## Required commands

Run from the repository root with the locked environment:

```bash
uv sync --locked --extra dev                                  # install
uv run ruff check .                                           # lint
uv run ruff format --check tests                              # format (CI scope)
uv run pytest -q                                              # default Python suite
uv run pytest -q --cov=satgonetem_gui --cov-report=term-missing  # coverage gate (85%)
npm ci                                                        # frontend install
npm run test:js                                               # Vitest
npx playwright install chromium                               # browser install
npm run test:e2e                                              # Playwright smoke tests
uv build --wheel                                              # package build
uv lock --check                                               # dependencies changed
```

Targeted runs:

```bash
uv run pytest tests/test_storage.py -q
npx vitest run js-tests/queue_model.test.js
npx playwright test e2e/pages.spec.js
```

Notes:

- CI uses Node 24 and `uv sync --locked`; do not rely on a floating local
  environment.
- Ruff's `select` list is a deliberate ratchet (`E9`, `F`, `I`). Never narrow
  it; widen it as findings are fixed. CI checks formatting for `tests/`;
  production files are formatted as they are touched.
- The coverage gate is 85% with branch coverage enabled. Report the actual
  percentage; do not lower the gate to land a change.
- Docker-backed container checks are not part of the default suite. Report
  them explicitly when they were not run.
- When packaging, bundled data, templates, or static assets change, verify the
  wheel contains them and smoke-test the installed wheel.
- SatGoNetem is pinned to a Git tag; bumping it is a dependency change that
  requires `uv lock`, adapter contract tests, and a note in the PR.

## Definition of done

- [ ] Specification and acceptance criteria are stated.
- [ ] A specification or ADR was added or updated when the change spans
      phases, changes a public contract, or records a costly-to-reverse
      decision.
- [ ] For behavior changes, a RED test was added and observed failing for the
      expected reason (pytest, Vitest, or Playwright as appropriate);
      manual-only checks are identified.
- [ ] Implementation is the smallest change that satisfies the tests.
- [ ] Tests remain green; no test was weakened or skipped to achieve it.
- [ ] Targeted tests and the full Python suite were run; Vitest and Playwright
      were run when frontend behavior changed, with results reported.
- [ ] `ruff check .` and `ruff format --check tests` pass; other static
      analysis is run or explicitly reported as not run.
- [ ] Coverage meets the 85% gate and was not gamed.
- [ ] The wheel was built and verified when packaging, data, templates, or
      static assets changed.
- [ ] `uv lock --check` passes when dependencies changed, and npm lock files
      are consistent.
- [ ] Documentation is updated for public API, configuration, or behavior
      changes.
- [ ] The change satisfies the design principles and coding practices above,
      or the deviation is justified in the specification or ADR.
- [ ] The complete diff was reviewed; unrelated changes were removed.
- [ ] Architecture tradeoffs and unverified assumptions are reported.
