"""Runtime settings loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_SAVE_ROOT = Path.home() / "satgonetem-projects"


@dataclass(frozen=True)
class Settings:
    """Server bind and filesystem policy."""

    host: str
    port: int
    save_root: Path


def load_settings() -> Settings:
    """Load server settings from the environment.

    Returns:
        Settings with loopback defaults and an optional save-root override.
    """
    host = os.getenv("SATGONETEM_GUI_HOST", DEFAULT_HOST)
    port_text = os.getenv("SATGONETEM_GUI_PORT", str(DEFAULT_PORT))
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"Invalid SATGONETEM_GUI_PORT: {port_text!r}") from exc

    save_root = Path(
        os.getenv("SATGONETEM_GUI_SAVE_ROOT", str(DEFAULT_SAVE_ROOT))
    ).expanduser()
    return Settings(host=host, port=port, save_root=save_root.resolve())
