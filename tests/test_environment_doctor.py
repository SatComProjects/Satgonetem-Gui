"""Unit tests for the local preflight environment doctor."""

from types import SimpleNamespace

import docker
import pytest

from satgonetem_gui.adapters import environment_doctor
from satgonetem_gui.adapters.environment_doctor import (
    LocalEnvironmentDoctor,
    check_storage,
    listen_address,
    required_images,
)
from satgonetem_gui.config import Settings

CONFIG_YAML = """
listen: "127.0.0.1:12345"
docker:
  nodes:
    router:
      image: mroy31/gonetem-frr
    host:
      image: mroy31/gonetem-host
  extraNodes:
    - type: satellite
      image: jariassuarez/sgnt:satellite
    - type: duplicate
      image: mroy31/gonetem-frr
"""

GIB = 1024**3


class FakeImages:
    """Docker image collection with a set of missing image names."""

    def __init__(self, missing=()) -> None:
        self.missing = set(missing)

    def get(self, image):
        if image in self.missing:
            raise docker.errors.ImageNotFound(f"missing {image}")
        return object()


class FakeDockerClient:
    """Minimal Docker client for adapter tests."""

    def __init__(self, missing=(), ping_error: Exception | None = None) -> None:
        self.images = FakeImages(missing)
        self.ping_error = ping_error
        self.closed = False

    def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return True

    def close(self) -> None:
        self.closed = True


class FakeSocket:
    """Socket stand-in that records cleanup."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def config_path(tmp_path):
    """Write the representative bundled config to an isolated file."""
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_YAML, encoding="utf-8")
    return path


def _settings(tmp_path) -> Settings:
    return Settings("127.0.0.1", 8000, tmp_path / "projects")


def _doctor(
    tmp_path,
    config_path,
    *,
    docker_factory=None,
    socket_factory=None,
    disk_usage=None,
) -> LocalEnvironmentDoctor:
    return LocalEnvironmentDoctor(
        _settings(tmp_path),
        docker_factory=docker_factory or (lambda timeout: FakeDockerClient()),
        socket_factory=socket_factory or (lambda address, timeout: FakeSocket()),
        disk_usage=disk_usage or (lambda path: SimpleNamespace(free=10 * GIB)),
        config_path=config_path,
    )


def _by_id(checks) -> dict:
    return {check["id"]: check for check in checks}


def test_required_images_parses_nodes_and_deduplicates() -> None:
    """Images come from docker.nodes and docker.extraNodes without duplicates."""
    images = required_images(
        {
            "docker": {
                "nodes": {
                    "router": {"image": "mroy31/gonetem-frr"},
                    "host": {"image": "mroy31/gonetem-host"},
                },
                "extraNodes": [
                    {"type": "satellite", "image": "jariassuarez/sgnt:satellite"},
                    {"type": "duplicate", "image": "mroy31/gonetem-frr"},
                ],
            }
        }
    )

    assert images == [
        "mroy31/gonetem-frr",
        "mroy31/gonetem-host",
        "jariassuarez/sgnt:satellite",
    ]


def test_required_images_ignores_malformed_sections() -> None:
    """A config without a Docker section declares no images."""
    assert required_images({}) == []
    assert required_images({"docker": {"nodes": []}}) == []
    assert required_images("not-a-mapping") == []


def test_listen_address_uses_the_config_and_falls_back() -> None:
    """The GoNetEm listen address is parsed with a safe default."""
    assert listen_address({"listen": "0.0.0.0:10111"}) == ("0.0.0.0", 10111)
    assert listen_address({"listen": "[::1]:10112"}) == ("::1", 10112)
    assert listen_address({}) == ("localhost", 10110)
    assert listen_address({"listen": "not-an-address"}) == ("localhost", 10110)


def test_all_checks_pass_with_injected_fakes(tmp_path, config_path) -> None:
    """A healthy environment reports four ordered, successful checks."""
    docker_calls = []
    socket_calls = []
    sockets = []

    def docker_factory(timeout):
        docker_calls.append(timeout)
        return FakeDockerClient()

    def socket_factory(address, timeout):
        socket_calls.append((address, timeout))
        socket = FakeSocket()
        sockets.append(socket)
        return socket

    doctor = _doctor(
        tmp_path,
        config_path,
        docker_factory=docker_factory,
        socket_factory=socket_factory,
    )

    checks = doctor.environment_checks()

    assert [check["id"] for check in checks] == [
        "storage",
        "docker",
        "images",
        "gonetem",
    ]
    assert {check["status"] for check in checks} == {"ok"}
    assert docker_calls == [2.0]
    assert socket_calls == [(("127.0.0.1", 12345), 1.0)]
    assert sockets[0].closed is True


def test_missing_image_is_a_warning_with_a_pull_hint(tmp_path, config_path) -> None:
    """Missing images are reported with the first image to pull."""
    doctor = _doctor(
        tmp_path,
        config_path,
        docker_factory=lambda timeout: FakeDockerClient(missing={"mroy31/gonetem-frr"}),
    )

    images = _by_id(doctor.environment_checks())["images"]

    assert images["status"] == "warning"
    assert "mroy31/gonetem-frr" in images["message"]
    assert images["hint"] == "Pull a missing image with: docker pull mroy31/gonetem-frr"


def test_docker_unavailable_makes_image_checks_unknown(tmp_path, config_path) -> None:
    """Docker is optional for builds, so an unreachable daemon is a warning."""

    def docker_factory(_timeout):
        raise RuntimeError("daemon down")

    doctor = _doctor(tmp_path, config_path, docker_factory=docker_factory)
    checks = _by_id(doctor.environment_checks())

    assert checks["docker"]["status"] == "warning"
    assert "daemon down" not in checks["docker"]["message"]
    assert checks["images"]["status"] == "unknown"
    assert checks["images"]["message"] == ("Cannot check images until Docker is reachable.")


def test_low_disk_space_is_a_blocking_error(tmp_path, config_path) -> None:
    """The save root must have at least 1 GiB free."""
    doctor = _doctor(
        tmp_path,
        config_path,
        disk_usage=lambda path: SimpleNamespace(free=100),
    )

    checks = _by_id(doctor.environment_checks())

    assert checks["storage"]["status"] == "error"
    assert "1 GiB" in checks["storage"]["message"]
    assert checks["storage"]["hint"]


def test_unwritable_save_root_is_an_error(tmp_path, monkeypatch) -> None:
    """A save root the process cannot write to blocks the preflight."""
    monkeypatch.setattr(environment_doctor, "_is_writable", lambda path: False)

    check = check_storage(tmp_path, disk_usage=lambda path: SimpleNamespace(free=10 * GIB))

    assert check["status"] == "error"
    assert "not writable" in check["message"]


def test_storage_probe_leaves_no_temporary_file(tmp_path) -> None:
    """The writability probe cleans up its temporary file."""
    check = check_storage(
        tmp_path / "projects",
        disk_usage=lambda path: SimpleNamespace(free=10 * GIB),
    )

    assert check["status"] == "ok"
    assert list(tmp_path.iterdir()) == []


def test_config_parse_failure_returns_checks_instead_of_raising(
    tmp_path,
) -> None:
    """A broken bundled config is a warning, not an API failure."""
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("listen: [unterminated", encoding="utf-8")
    doctor = _doctor(tmp_path, config_path)

    checks = doctor.environment_checks()

    assert len(checks) == 4
    checks_by_id = _by_id(checks)
    assert checks_by_id["images"]["status"] == "warning"
    assert checks_by_id["gonetem"]["status"] == "ok"


def test_missing_gonetem_server_is_a_warning(tmp_path, config_path) -> None:
    """A stopped GoNetEm server does not block a project build."""

    def socket_factory(_address, _timeout):
        raise ConnectionRefusedError("refused")

    doctor = _doctor(tmp_path, config_path, socket_factory=socket_factory)

    gonetem = _by_id(doctor.environment_checks())["gonetem"]

    assert gonetem["status"] == "warning"
    assert "127.0.0.1:12345" in gonetem["message"]
    assert gonetem["hint"]
