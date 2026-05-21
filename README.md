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
├── app.py              # FastAPI application (routes & API endpoints)
├── main.py             # Entry point (uvicorn runner)
├── state.py            # Global application state (TopologyManager, jobs, etc.)
├── static/             # CSS and JavaScript assets
├── static_back/        # Previous version of static assets (backup)
├── templates/          # Jinja2 HTML templates
│   └── base.html       # Shared layout with navigation
├── templates_back/     # Previous version of templates (backup)
satgonetem_gui.egg-info/
docs/                   # Project documentation (placeholder)
resources/              # Sample configuration and ground station data
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

## Development

To run the application in development mode with auto-reload:

```bash
uvicorn satgonetem_gui.app:app --reload --host 0.0.0.0 --port 8000
```

## License

See the project's `pyproject.toml` for dependency licenses.
