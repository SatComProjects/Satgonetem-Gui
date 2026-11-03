"""HTML page routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def create_pages_router(templates: Jinja2Templates) -> APIRouter:
    """Build the page router around a template directory."""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @router.get("/new_project", response_class=HTMLResponse)
    async def new_project(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "new_project.html")

    @router.get("/ground_stations", response_class=HTMLResponse)
    async def ground_stations_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "ground_stations.html")

    @router.get("/world", response_class=HTMLResponse)
    async def world_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "world.html")

    @router.get("/nodes", response_class=HTMLResponse)
    async def nodes_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "nodes.html")

    @router.get("/traffic", response_class=HTMLResponse)
    async def traffic_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "traffic.html")

    @router.get("/security", response_class=HTMLResponse)
    async def security_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "security.html")

    return router
