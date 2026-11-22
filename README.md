# SatGoNetem GUI

A web-based control panel for the [SatGoNetem](https://github.com/satcomprojects/satgonetem) satellite constellation network emulation framework. This GUI lets you design, visualise, and interact with emulated LEO/MEO satellite topologies using GoNetem containers.

## Features

| Feature | Description |
|---------|-------------|
| **Project Builder** | Define Walker orbit shells and ground stations through a guided form. |
| **3D World View** | Interactive CesiumJS globe showing satellites, ground stations, links, and coverage in real time. |
| **Simulation Controls** | Play, pause, step, reset, seek, and change the playback speed of the emulated constellation. |
| **Node Explorer** | Browse all satellites and ground stations with detailed status and per-node links. |
| **Link Metrics** | Inspect link delay, capacity, and active state; Globe link width scales with capacity. |
| **Readiness Checks** | Preflight storage, Docker, image, and GoNetEm checks plus a rough container/memory estimate. |
| **Project Workspace** | List, reopen, save in place, duplicate, and delete projects under the configured save root. |
| **Usage Link Colors** | Opt-in World View link coloring from green (idle) to red (at/above capacity). |
| **Connectivity Matrix** | Ping every ordered pair of addressable nodes with a loss/RTT heatmap and CSV/JSON export. |
| **Coverage Analytics** | Snapshot Earth coverage at a chosen elevation mask, per shell and per ground station. |
| **Experiment Runs** | Run v0.3.2 YAML scenarios and keep manifests, metrics, results, and reports on the server. |
| **Forwarding Paths** | Trace a diagnostic hop-by-hop path between nodes and highlight it on the globe. |
| **Traffic Generator** | Run `iperf3`, `ping`, and `hping3` flows between ground stations and opt-in satellite endpoints with a queued job system. |
| **Experiment History** | Reopen, compare, and export recent completed runs from browser-local storage. |
| **Routing Control** | Apply Static/Dijkstra, OSPF, IS-IS, or SR-MPLS routing across the emulated topology. |
| **GoNetem Integration** | Start and stop Dockerised network nodes directly from the web UI. |
| **Save / Load** | Export and import projects as JSON files. |

## Requirements

- Python >= 3.10 (CI runs 3.12)
- Node >= 24 for the frontend tooling and test suites
- SatGoNetEm **v0.3.2** (pinned Git tag)
- A modern web browser with WebGL support (for the 3D globe; unsupported
  browsers get a fallback message)

## Installation

The supported development path uses [uv](https://github.com/astral-sh/uv) with
the committed lock file:

```bash
uv sync --locked --extra dev
```

SatGoNetEm enters through a PEP 508 direct URL pinned to the `v0.3.2` tag in
`pyproject.toml`; `uv.lock` records the resolved commit.

For a plain virtual environment, `pip` resolves the same direct Git URL, which
requires `git` and network access:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Running the Application

Start the web server with:

```bash
python -m satgonetem_gui.main
```

or 

```bash
python satgonetem_gui/main.py
```



The GUI will be available at **http://localhost:8000**.

FastAPI auto-generated API documentation can be found at **http://localhost:8000/docs**.

## Project Structure

```
satgonetem_gui/
├── app.py              # create_app factory and composition root
├── main.py             # Entry point (uvicorn runner + settings)
├── dependencies.py     # FastAPI service injection
├── config.py           # Host, port, and save-root settings
├── schemas.py          # Pydantic request/response models
├── errors.py           # Shared API error envelope
├── state.py            # Per-application project/runtime state
├── routes/             # Page, project, topology, routing, simulation, traffic APIs
├── services/           # Use-case orchestration and job registry
├── adapters/           # SatGoNetem topology (including simulation) and traffic adapters
├── ground_stations.py  # Ground-station CSV parsing/writing
├── serializers.py      # Traffic result shaping
├── storage.py          # Data-file and save-path policy
├── data/               # Bundled presets and sample GoNetem config
├── static/             # ES modules, CSS, and shared JS models
├── templates/          # Jinja2 HTML templates
│   └── base.html       # Shared layout with navigation
tests/                  # pytest suite (10x10 in-process topology)
js-tests/               # Vitest unit tests for pure frontend models
e2e/                    # Playwright page smoke tests
docs/                   # Architecture notes and test baseline
package.json            # Frontend test/tooling manifest
```

## Pages

| Path | Page |
|------|------|
| `/` | Dashboard — constellation statistics, simulation playback, GoNetem status, routing controls |
| `/world` | 3D Globe — real-time satellite and ground station visualisation with simulation playback and path highlighting |
| `/nodes` | Node Explorer — list, inspect, and trace paths between all topology nodes |
| `/traffic` | Traffic Generator — create and queue traffic jobs, review history and comparisons |
| `/new_project` | New Project — build a constellation from scratch |
| `/projects` | Projects — list, reopen, save, duplicate, and delete workspace projects |
| `/connectivity` | Connectivity Matrix — full-mesh loss/RTT heatmap with exports |
| `/coverage` | Coverage Analytics — elevation-mask coverage, shells, and station visibility |
| `/experiments` | Experiments — run scenarios and download server-side artifacts |
| `/ground_stations` | Ground Station Editor — manage ground station presets |
| `/docs` | API Documentation — auto-generated Swagger UI |

## Simulation Controls

The Dashboard and World View expose transport controls for the core simulation
loop: start/pause, single step, reset to the first step, seek to an absolute
step, and faster/slower playback. Step, reset, and seek require the loop to be
paused. Playback still updates satellite positions with containers stopped;
routing and traffic changes require GoNetEm to be running. A failed loop tick
is shown in the panel without stopping the loop.

## Satellite Traffic Endpoints

Satellites are not traffic endpoints by default. On the Traffic page, enable
**Include satellites as traffic endpoints** to expose every satellite as a
source or destination; the Nodes page can toggle one satellite at a time. The
setting is session-scoped for normal Walker projects because SatGoNetEm
v0.3.2 persists the addressable flag only in runtime-state projects. Re-enable
it after loading or replacing a Walker project. If addressing and routing are
already applied, re-apply them before running traffic so the new endpoints
receive routes.

## Experiment History

Completed traffic runs are copied into a compact browser-local ledger. Open
**History** in the floating Job Queue to reopen a result, delete a run, export
one run or the whole ledger as JSON/CSV, or compare two same-kind runs. The
comparison shows a summary table with Run B minus Run A deltas and a primary
series chart (iperf3 throughput or hping3 RTT).

Only successful runs are recorded. History is per-browser, retains at most 20
runs (about 2 MB), and samples long iperf3 interval arrays. It is lost if
browser storage is cleared; it is not a substitute for server-side provenance
or cross-machine sharing.

## Forwarding Paths

The Nodes page can trace a diagnostic path between any two topology nodes. The
hop table shows the link type and direction, distance, propagation delay, and
cumulative totals, plus the active routing method and preference. World View
has a matching Path control that highlights the route and dims unrelated links.

This is a **routing-graph snapshot, not the live forwarding table**: it is
computed from the public routing graph, and dynamic routing or an SR-MPLS
explicit path can install different forwarding state. Re-trace after changing
the topology, simulation step, or routing configuration.

## Link Metrics

`/api/links` includes propagation delay, capacity, and active state. Expand a
node in Node Explorer to see its Links table; on World View, line width scales
logarithmically with capacity and inactive links are red.

Utilization is not included yet: the pinned core's link monitor reads
`/tmp/interfaces` files, and that contract has not been verified against the
net-logger output. Capacity comes from the public `get_capacity()` value
(peer1/downlink for satellite-to-ground links); a zero or unavailable value is
shown as “Unknown”.

## Readiness Checks and Build Phases

The Dashboard and New Project pages run a bounded preflight check covering
project storage, the Docker daemon, required container images, and GoNetEm
server reachability. New Project also shows a rough estimate of satellites,
ground stations, containers, and memory (128 MB per container). Storage errors
block creation; Docker and GoNetEm problems are warnings because a project can
still be built in-process without running containers.

GoNetEm component images are published with version tags (for example
`0.6.0`). The image check matches repository-only entries in the bundled config
against any locally present tag, and the hint points at `gonetem-console pull`
rather than an untagged `docker pull`.

Project creation reports real lifecycle phases (`validating`, `building`,
`loading`, `finalizing`, `ready`, `error`) and elapsed time. When a phase has no
meaningful percentage, the progress bar is indeterminate instead of showing a
made-up number.

## Project Workspace

The Projects page lists JSON project files under `SATGONETEM_GUI_SAVE_ROOT`.
Projects are addressed by opaque IDs; the browser never sends a filesystem path.
From the page you can reopen a project, save the current project to the
workspace, update the current workspace file in place, duplicate a project file,
or delete one. Saving in place requires a project that was opened from or saved
to the workspace. Malformed JSON files are skipped with a visible warning.

## Connectivity Matrix

The Connectivity page runs a full-mesh ping check over selected addressable
ground stations and satellites. It requires GoNetEm containers and applied
addressing/routing. Runs are capped at 32 nodes and 2,000 ordered pairs, run in
the background, and render an N×N heatmap of packet loss and average RTT.
Completed jobs can be exported as CSV or JSON. The matrix is a snapshot; rerun
after topology or routing changes.

## Coverage Analytics

The Coverage page computes a snapshot of the current topology at a chosen
minimum elevation (0–90°, default 10°) and grid resolution (0.25–10°, default
1°). It reports the overall covered percentage, per-shell contributions, and
the best satellite and elevation for each ground station. Requests are bounded
at 100,000,000 satellite-cells and 1,200,000 grid cells; a finer grid over a
large constellation is rejected with a request to use a coarser resolution.
Results are cached per project generation, simulation step, elevation,
resolution, and section toggles.

## Experiment Runs

The Experiments page runs a v0.3.2 YAML scenario in validate-only, offline, or
live mode. Each run is stored under
`SATGONETEM_GUI_SAVE_ROOT/.satgonetem/experiments/` with its scenario, manifest,
metrics (`metrics.jsonl`), flows, errors, summary, report, optional connectivity
matrix, and a provenance record. Live runs require GoNetEm containers to be
stopped; the GUI reserves the network operation for the duration so project and
routing controls cannot race the experiment. Concurrent runs are bounded to two,
with one live run.

The run list opens a detail view with a live metrics chart, report text,
scenario YAML, and artifact actions. While a run is active the chart refreshes
from `GET /api/experiments/{id}/metrics?tail=N`; completed runs can be selected
(two to four) and compared by summary values, an overlaid metric series over
simulation time, and a line diff of their scenario documents.

Artifacts are downloadable from the run list. Interactive traffic history remains
browser-local; scenario runs are the server-backed experiment record.

## Usage Link Colors

Enable **Color links by usage** in World View's Links controls to color active
links from green (no usage) through amber to red (at or above capacity). The
page samples `/api/links/usage` every five seconds only while the control is
enabled. Inactive links remain red; unknown capacity or unavailable usage data
is gray. Usage depends on the core interface monitor and may be unavailable
when GoNetEm is stopped or the monitor files are absent.

## Configuration

The server and project storage are configured through environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SATGONETEM_GUI_HOST` | `127.0.0.1` | Bind address; loopback by default. |
| `SATGONETEM_GUI_PORT` | `8000` | HTTP port. |
| `SATGONETEM_GUI_SAVE_ROOT` | `~/satgonetem-projects` | Only project save paths inside this directory are accepted. |

Set `SATGONETEM_GUI_HOST=0.0.0.0` only on a trusted network. The machine's
hostname and local interface addresses are accepted automatically in that mode;
add any DNS alias or reverse-proxy name to `SATGONETEM_GUI_ALLOWED_HOSTS`. The
form's `Save to` field is optional; when used, its target must stay inside the
configured save root.

## Security

The GUI has no authentication and is intended for trusted local use. It binds
`127.0.0.1` by default, constrains project saves to `SATGONETEM_GUI_SAVE_ROOT`,
and does not expose a public API. Requests with a non-loopback `Host` header and
browser mutations from another origin are rejected. If a deliberate reverse
proxy or non-loopback hostname is used, add it to
`SATGONETEM_GUI_ALLOWED_HOSTS` (comma-separated). Do not bind it to a public
interface without placing it behind an authenticating reverse proxy.

## Development

To run the application in development mode with auto-reload:

```bash
uvicorn "satgonetem_gui.app:create_app" --factory --reload --host 127.0.0.1 --port 8000
```

Install the development tools and run the Python suite:

```bash
uv sync --locked --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check tests
```

Install the frontend tooling and run the JS tests:

```bash
npm ci
npm run test:js
```

Run the browser smoke tests (the Playwright web server starts the app itself):

```bash
npx playwright install chromium
npm run test:e2e
```

The default Python suite builds a 10x10 Walker constellation in-process and
does not require Docker or a running GoNetem server. See
[`docs/architecture.md`](docs/architecture.md) for the test strategy, target
module boundaries, and the current coverage baseline.

## License

See the project's `pyproject.toml` for dependency licenses.
