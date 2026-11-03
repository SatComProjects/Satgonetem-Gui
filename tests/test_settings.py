"""Tests for environment-backed server settings."""

from pathlib import Path

from satgonetem_gui.config import load_settings


def _clear_env(monkeypatch) -> None:
    for name in (
        "SATGONETEM_GUI_HOST",
        "SATGONETEM_GUI_PORT",
        "SATGONETEM_GUI_SAVE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_bind_is_loopback(monkeypatch) -> None:
    """The development server must not listen on all interfaces by default."""
    _clear_env(monkeypatch)

    settings = load_settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.save_root.name == "satgonetem-projects"


def test_environment_overrides_settings(monkeypatch, tmp_path: Path) -> None:
    """Operators can opt into another bind, port, and save root."""
    monkeypatch.setenv("SATGONETEM_GUI_HOST", "0.0.0.0")
    monkeypatch.setenv("SATGONETEM_GUI_PORT", "9000")
    monkeypatch.setenv("SATGONETEM_GUI_SAVE_ROOT", str(tmp_path / "projects"))

    settings = load_settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.save_root == (tmp_path / "projects").resolve()


def test_main_uses_loaded_settings(monkeypatch) -> None:
    """The entry point passes the configured host and port to uvicorn."""
    import satgonetem_gui.main as main_module

    captured = {}
    monkeypatch.setenv("SATGONETEM_GUI_HOST", "127.0.0.2")
    monkeypatch.setenv("SATGONETEM_GUI_PORT", "8123")
    monkeypatch.setattr(
        main_module.uvicorn,
        "run",
        lambda app, host, port: captured.update(app=app, host=host, port=port),
    )

    main_module.main()

    assert captured["host"] == "127.0.0.2"
    assert captured["port"] == 8123
