"""Entry point for the SatGoNetem GUI server."""

import uvicorn

from satgonetem_gui.app import app
from satgonetem_gui.config import load_settings


def main() -> None:
    """Start the Uvicorn server using environment-backed settings."""
    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
