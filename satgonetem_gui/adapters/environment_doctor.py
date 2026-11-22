"""Local environment readiness checks for preflight diagnostics.

The checks are best-effort probes. Every probe is bounded and converts an
unexpected failure into an explicit ``warning``, ``error``, or ``unknown``
check so the preflight panel never crashes the API.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import tempfile
from pathlib import Path
from typing import Any, Callable

import docker
import yaml

from ..config import Settings
from ..resources import GONETEM_CONFIG_PATH

logger = logging.getLogger(__name__)

MIN_FREE_BYTES = 1024**3
MAX_MESSAGE_LENGTH = 300
DEFAULT_LISTEN = "localhost:10110"
DOCKER_TIMEOUT_SECONDS = 2.0
GONETEM_TIMEOUT_SECONDS = 1.0

STORAGE_HINT = (
    "Set SATGONETEM_GUI_SAVE_ROOT to a writable directory with at least 1 GB free."
)
DOCKER_HINT = (
    "Start Docker and confirm the current user can access the Docker socket."
)
GONETEM_HINT = (
    "Start the GoNetEm server and confirm the bundled listen address."
)
DOCKER_UNAVAILABLE_IMAGES_MESSAGE = "Cannot check images until Docker is reachable."


def _short_text(value: object) -> str:
    """Collapse whitespace and cap user-facing text to a readable length."""
    text = " ".join(str(value).split())
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text
    return text[: MAX_MESSAGE_LENGTH - 3].rstrip() + "..."


def _check(
    check_id: str,
    label: str,
    status: str,
    message: str,
    hint: str | None = None,
) -> dict[str, Any]:
    """Build one preflight check dictionary with bounded text."""
    result: dict[str, Any] = {
        "id": check_id,
        "label": label,
        "status": status,
        "message": _short_text(message),
    }
    if hint:
        result["hint"] = _short_text(hint)
    return result


def required_images(config: object) -> list[str]:
    """Return the deduplicated images the bundled GoNetEm config references."""
    images: list[str] = []
    if not isinstance(config, dict):
        return images
    docker_config = config.get("docker")
    if not isinstance(docker_config, dict):
        return images

    candidates: list[object] = []
    nodes = docker_config.get("nodes")
    if isinstance(nodes, dict):
        candidates.extend(nodes.values())
    extra_nodes = docker_config.get("extraNodes")
    if isinstance(extra_nodes, list):
        candidates.extend(extra_nodes)

    for node in candidates:
        if not isinstance(node, dict):
            continue
        image = node.get("image")
        if not isinstance(image, str) or not image.strip():
            continue
        image = image.strip()
        if image not in images:
            images.append(image)
    return images


def listen_address(config: object) -> tuple[str, int]:
    """Return the GoNetEm listen host and port, falling back to the default."""
    address = DEFAULT_LISTEN
    if isinstance(config, dict):
        configured = config.get("listen")
        if isinstance(configured, str) and configured.strip():
            address = configured.strip()

    host, _, port_text = address.rpartition(":")
    if not host:
        host = "localhost"
    try:
        port = int(port_text)
    except ValueError:
        return "localhost", 10110
    return host.strip("[]") or "localhost", port


def _nearest_existing_directory(path: Path) -> Path | None:
    """Return the closest existing ancestor of a not-yet-created save root."""
    for candidate in (path, *path.parents):
        if candidate.is_dir():
            return candidate
    return None


def _is_writable(directory: Path) -> bool:
    """Probe writability with a temporary file that is always removed."""
    try:
        handle, name = tempfile.mkstemp(
            prefix=".satgonetem-preflight-",
            dir=str(directory),
        )
    except OSError:
        return False
    try:
        os.close(handle)
    except OSError:
        pass
    try:
        Path(name).unlink()
    except OSError:
        pass
    return True


def check_storage(
    save_root: str | Path,
    disk_usage: Callable[..., Any] | None = None,
    min_free_bytes: int = MIN_FREE_BYTES,
) -> dict[str, Any]:
    """Check that the project save root is writable and has enough free space."""
    read_disk_usage = disk_usage or shutil.disk_usage
    root = Path(save_root)
    directory = _nearest_existing_directory(root)
    if directory is None or not _is_writable(directory):
        return _check(
            "storage",
            "Project storage",
            "error",
            f"The project save directory {root} is not writable.",
            STORAGE_HINT,
        )

    try:
        free_bytes = int(read_disk_usage(directory).free)
    except (OSError, TypeError, ValueError, AttributeError) as exc:
        logger.info("Could not read free disk space: %s", exc)
        return _check(
            "storage",
            "Project storage",
            "error",
            f"Could not read free space for {root} ({exc.__class__.__name__}).",
            STORAGE_HINT,
        )

    free_gib = free_bytes / 1024**3
    if free_bytes < min_free_bytes:
        return _check(
            "storage",
            "Project storage",
            "error",
            (
                f"The project save directory {root} has {free_gib:.1f} GiB free; "
                "at least 1 GiB is required."
            ),
            STORAGE_HINT,
        )

    return _check(
        "storage",
        "Project storage",
        "ok",
        f"{root} is writable with {free_gib:.1f} GiB free.",
    )


class LocalEnvironmentDoctor:
    """Best-effort checks for Docker, images, storage, and the GoNetEm server."""

    def __init__(
        self,
        settings: Settings,
        docker_factory: Callable[..., Any] | None = None,
        socket_factory: Callable[..., Any] | None = None,
        disk_usage: Callable[..., Any] | None = None,
        config_path: str | Path = GONETEM_CONFIG_PATH,
    ) -> None:
        self.settings = settings
        self._docker_factory = docker_factory
        self._socket_factory = socket_factory or socket.create_connection
        self._disk_usage = disk_usage or shutil.disk_usage
        self._config_path = Path(config_path)

    def environment_checks(self) -> list[dict[str, Any]]:
        """Return the four preflight checks in a stable order."""
        config, config_error = self._load_config()
        checks = [check_storage(self.settings.save_root, self._disk_usage)]

        docker_check, client = self._check_docker()
        checks.append(docker_check)
        try:
            checks.append(self._check_images(config, config_error, client))
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    logger.debug("Could not close the Docker client.", exc_info=True)

        checks.append(self._check_gonetem(config))
        return checks

    def _load_config(self) -> tuple[dict[str, Any], str | None]:
        """Load the bundled GoNetEm config; a parse failure is not fatal."""
        try:
            with self._config_path.open("r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            logger.warning("Could not read the bundled GoNetEm config: %s", exc)
            return {}, f"Could not read the bundled GoNetEm config ({exc.__class__.__name__})."
        if not isinstance(config, dict):
            logger.warning("The bundled GoNetEm config is not a mapping.")
            return {}, "The bundled GoNetEm config is not a mapping."
        return config, None

    def _check_docker(self) -> tuple[dict[str, Any], Any | None]:
        """Ping Docker with a bounded timeout and return the client when usable."""
        factory = self._docker_factory or docker.from_env
        try:
            client = factory(timeout=DOCKER_TIMEOUT_SECONDS)
            client.ping()
        except Exception as exc:
            logger.info("Docker is not reachable: %s", exc)
            return (
                _check(
                    "docker",
                    "Docker daemon",
                    "warning",
                    (
                        "Docker is not reachable "
                        f"({exc.__class__.__name__}). Docker is required to run "
                        "the emulated containers but not to build a project."
                    ),
                    DOCKER_HINT,
                ),
                None,
            )
        return (
            _check("docker", "Docker daemon", "ok", "Docker is reachable."),
            client,
        )

    def _check_images(
        self,
        config: dict[str, Any],
        config_error: str | None,
        client: Any | None,
    ) -> dict[str, Any]:
        """Compare the bundled config images with the local Docker image store."""
        if client is None:
            return _check(
                "images",
                "Container images",
                "unknown",
                DOCKER_UNAVAILABLE_IMAGES_MESSAGE,
            )

        if config_error is not None:
            return _check(
                "images",
                "Container images",
                "warning",
                config_error,
            )

        images = required_images(config)
        if not images:
            return _check(
                "images",
                "Container images",
                "warning",
                "The bundled GoNetEm config declares no container images.",
            )

        missing: list[str] = []
        try:
            for image in images:
                try:
                    client.images.get(image)
                except docker.errors.ImageNotFound:
                    missing.append(image)
        except Exception as exc:
            logger.info("Could not inspect Docker images: %s", exc)
            return _check(
                "images",
                "Container images",
                "warning",
                f"Could not inspect the local Docker images ({exc.__class__.__name__}).",
            )

        if missing:
            listed = ", ".join(missing[:5])
            if len(missing) > 5:
                listed += f", and {len(missing) - 5} more"
            return _check(
                "images",
                "Container images",
                "warning",
                (
                    f"{len(missing)} of {len(images)} required images are missing: "
                    f"{listed}."
                ),
                f"Pull a missing image with: docker pull {missing[0]}",
            )

        return _check(
            "images",
            "Container images",
            "ok",
            f"All {len(images)} required container images are available locally.",
        )

    def _check_gonetem(self, config: dict[str, Any]) -> dict[str, Any]:
        """Attempt a short TCP connection to the configured GoNetEm server."""
        host, port = listen_address(config)
        connection = None
        try:
            connection = self._socket_factory((host, port), GONETEM_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.info("GoNetEm is not reachable at %s:%s: %s", host, port, exc)
            return _check(
                "gonetem",
                "GoNetEm server",
                "warning",
                f"No GoNetEm server answered at {host}:{port}.",
                GONETEM_HINT,
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    logger.debug("Could not close the GoNetEm probe socket.")

        return _check(
            "gonetem",
            "GoNetEm server",
            "ok",
            f"GoNetEm is reachable at {host}:{port}.",
        )
