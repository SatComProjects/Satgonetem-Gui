"""FastAPI dependency providers."""

from fastapi import Request

from .services.container import ApplicationServices


def get_services(request: Request) -> ApplicationServices:
    """Return the service container attached to this app instance."""
    return request.app.state.services
