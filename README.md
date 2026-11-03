# SatGoNetem GUI

A web-based control panel for the [SatGoNetem](https://github.com/satcomprojects/satgonetem) satellite constellation network emulation framework. This GUI lets you design, visualise, and interact with emulated LEO/MEO satellite topologies using GoNetem containers.

## Features

| Feature | Description |
|---------|-------------|
| **Project Builder** | Define Walker orbit shells and ground stations through a guided form. |
| **3D World View** | Interactive CesiumJS globe showing satellites, ground stations, links, and coverage in real time. |
| **Node Explorer** | Browse all satellites and ground stations with detailed status. |
| **Traffic Generator** | Run `iperf3`, `ping`, and `hping3` flows between nodes with a queued job system. |
| **Routing Control** | Apply Static/Dijkstra, OSPF, IS-IS, or SR-MPLS routing across the emulated topology. |
| **GoNetem Integration** | Start and stop Dockerised network nodes directly from the web UI. |
| **Save / Load** | Export and import projects as JSON files. |

## Requirements

- Python >= 3.10
- SatGoNetEm
- A modern web browser with WebGL support (for the 3D globe)

## Installation

It is recommended to work in a virtual environment.

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Or, if you use [uv](https://github.com/astral-sh/uv):

```bash
uv sync
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
├── routes/             # Page, project, topology, routing, traffic APIs
├── services/           # Use-case orchestration and job registry
├── adapters/           # SatGoNetem topology and traffic adapters
├── ground_stations.py  # Ground-station CSV parsing/writing
├── serializers.py      # Traffic result shaping
├── storage.py          # Data-file and save-path policy
├── static/             # ES modules, CSS, and shared JS models
├── templates/          # Jinja2 HTML templates
│   └── base.html       # Shared layout with navigation
tests/                  # pytest suite (10x10 in-process topology)
js-tests/               # Vitest unit tests for pure frontend models
e2e/                    # Playwright page smoke tests
docs/                   # Architecture notes and test baseline
resources/              # Sample configuration and ground station data
package.json            # Frontend test/tooling manifest
```

## Pages

| Path | Page |
|------|------|
| `/` | Dashboard — constellation statistics, GoNetem status, routing controls |
| `/world` | 3D Globe — real-time satellite and ground station visualisation |
| `/nodes` | Node Explorer — list and inspect all topology nodes |
| `/traffic` | Traffic Generator — create and queue traffic jobs |
| `/new_project` | New Project — build a constellation from scratch |
| `/ground_stations` | Ground Station Editor — manage ground station presets |
| `/docs` | API Documentation — auto-generated Swagger UI |

## Configuration

The server and project storage are configured through environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SATGONETEM_GUI_HOST` | `127.0.0.1` | Bind address; loopback by default. |
| `SATGONETEM_GUI_PORT` | `8000` | HTTP port. |
| `SATGONETEM_GUI_SAVE_ROOT` | `~/satgonetem-projects` | Only project save paths inside this directory are accepted. |

Set `SATGONETEM_GUI_HOST=0.0.0.0` only on a trusted network. The form's
`Save to` field is optional; when used, its target must stay inside the
configured save root.

## Development

To run the application in development mode with auto-reload:

```bash
uvicorn satgonetem_gui.app:app --reload --host 127.0.0.1 --port 8000
```

Install the development tools and run the Python suite:

```bash
uv sync --extra dev
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
