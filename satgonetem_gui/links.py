"""Stable identities for topology links.

The security lab needs to name a link across HTTP requests without exposing
object identity. The key is derived only from fields that are stable for the
lifetime of a loaded topology.
"""

from typing import Any


def link_key(link: Any) -> str:
    """Return a stable, URL-safe key for a topology link."""
    source = getattr(getattr(link, "source", None), "name", "")
    target = getattr(getattr(link, "target", None), "name", "")
    link_type = getattr(link, "type", "")
    direction = getattr(link, "direction", "")
    return f"{source}|{target}|{link_type}|{direction}"
