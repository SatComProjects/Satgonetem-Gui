"""Verify packaging metadata keeps the pinned SatGoNetEm dependency."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 gets tomli via pytest
    import tomli as tomllib

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
PINNED_TAG = "v0.3.2"
PINNED_URL = f"git+https://github.com/satcomprojects/satgonetem@{PINNED_TAG}"


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_runtime_dependency_is_a_direct_url_pin() -> None:
    """The wheel must not fall back to a floating satgonetem version range."""
    dependencies = _load_pyproject()["project"]["dependencies"]
    satgonetem = [dep for dep in dependencies if dep.split()[0] == "satgonetem"]

    assert len(satgonetem) == 1, satgonetem
    assert satgonetem[0] == f"satgonetem @ {PINNED_URL}"
    assert not any(
        dep.startswith(("satgonetem>=", "satgonetem==", "satgonetem~=")) for dep in dependencies
    )


def test_uv_source_pins_the_same_tag() -> None:
    """uv resolves the direct URL requirement from the same release tag."""
    source = _load_pyproject()["tool"]["uv"]["sources"]["satgonetem"]

    assert source["git"] == "https://github.com/satcomprojects/satgonetem"
    assert source["tag"] == PINNED_TAG
