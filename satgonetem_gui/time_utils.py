"""Shared timestamp formatting for service and lifecycle records."""

from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
