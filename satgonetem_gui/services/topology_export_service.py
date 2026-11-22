"""Topology health and export use cases."""

from ..errors import APIError
from ..topology_export import serialize_topology
from ..topology_health import build_health
from .topology_service import TopologyService

MAX_EXPORT_CHARS = 10_000_000


class TopologyExportService:
    """Analyze and serialize the currently loaded topology."""

    def __init__(self, topology: TopologyService) -> None:
        self.topology = topology

    def health(self) -> dict:
        """Return every structural health check for the loaded topology."""
        return build_health(self.topology.nodes(), self.topology.links())

    def export(self, fmt: str) -> dict:
        """Serialize one topology snapshot or reject an oversized export."""
        nodes = self.topology.nodes()
        links = self.topology.links()
        filename, content, content_type = serialize_topology(fmt, nodes, links)
        if len(content) > MAX_EXPORT_CHARS:
            raise APIError(422, "Topology export is too large; reduce the project size.")
        return {
            "ok": True,
            "filename": filename,
            "content": content,
            "content_type": content_type,
        }
