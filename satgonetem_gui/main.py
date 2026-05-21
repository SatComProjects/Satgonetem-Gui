"""Entry point for the SatGoNetem GUI server."""

import uvicorn

from satgonetem_gui.app import app


def main() -> None:
    """Start the Uvicorn development server on port 8000."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
