"""HTML page routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

PAGE_ROUTES = (
    ("/", "index.html"),
    ("/new_project", "new_project.html"),
    ("/projects", "projects.html"),
    ("/connectivity", "connectivity.html"),
    ("/coverage", "coverage.html"),
    ("/topology", "topology.html"),
    ("/monitor", "monitor.html"),
    ("/matrix", "matrix.html"),
    ("/link-budget", "link_budget.html"),
    ("/experiments", "experiments.html"),
    ("/ground_stations", "ground_stations.html"),
    ("/world", "world.html"),
    ("/nodes", "nodes.html"),
    ("/traffic", "traffic.html"),
)


def _page_handler(templates: Jinja2Templates, template: str):
    """Build one async HTML handler for a template."""

    async def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, template)

    return handler


def create_pages_router(templates: Jinja2Templates) -> APIRouter:
    """Build the page router around a template directory."""
    router = APIRouter()
    for path, template in PAGE_ROUTES:
        router.add_api_route(
            path,
            _page_handler(templates, template),
            response_class=HTMLResponse,
            name=template.removesuffix(".html"),
        )
    return router
