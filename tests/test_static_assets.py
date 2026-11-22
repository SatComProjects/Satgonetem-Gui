"""Static asset URLs stay identical between templates and module imports."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
BASE_TEMPLATE = PACKAGE / "templates" / "base.html"
TRAFFIC_MODULE = PACKAGE / "static" / "traffic.js"
QUEUE_MODULE = PACKAGE / "static" / "queue.js"

QUEUE_SCRIPT = "/static/queue.js?v=23"
QUEUE_IMPORT = "./queue.js?v=23"
QUEUE_MODEL_IMPORT = "./queue_model.js?v=3"
HISTORY_MODEL_IMPORT = "./history_model.js?v=1"
PATH_MODEL_IMPORT = "./path_model.js?v=1"
WORLD_TEMPLATE = PACKAGE / "templates" / "world.html"
SIMULATION_CONTROLS = PACKAGE / "static" / "simulation_controls.js"
SIMULATION_MODEL_IMPORT = "./simulation_model.js?v=1"
ADDRESSABILITY_MODEL_IMPORT = "./addressability_model.js?v=1"
NODES_MODULE = PACKAGE / "static" / "nodes.js"
WORLD_MODULE = PACKAGE / "static" / "world.js"


def test_path_controllers_import_the_versioned_model() -> None:
    """Node Explorer and World View share one cache-busted path model."""
    for path in (NODES_MODULE, WORLD_MODULE):
        assert f'"{PATH_MODEL_IMPORT}"' in path.read_text(encoding="utf-8")


def test_queue_imports_the_versioned_history_and_queue_models() -> None:
    """Queue module changes stay cache-busted alongside their pure models."""
    content = QUEUE_MODULE.read_text(encoding="utf-8")

    assert f'from "{HISTORY_MODEL_IMPORT}"' in content
    assert f'from "{QUEUE_MODEL_IMPORT}"' in content


def test_addressability_controls_import_the_versioned_model() -> None:
    """The traffic controller and its pure model share one cache-busted URL."""
    content = TRAFFIC_MODULE.read_text(encoding="utf-8")

    assert f'from "{ADDRESSABILITY_MODEL_IMPORT}"' in content


def test_simulation_controls_imports_the_versioned_model() -> None:
    """The transport page controllers share one cache-busted model URL."""
    content = SIMULATION_CONTROLS.read_text(encoding="utf-8")

    assert f'from "{SIMULATION_MODEL_IMPORT}"' in content


def test_base_template_loads_the_versioned_queue_module() -> None:
    """The shared page shell loads the same queue.js URL traffic.js imports."""
    content = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert QUEUE_SCRIPT in content


def test_traffic_module_imports_the_same_versioned_queue_module() -> None:
    """A bare import would create a second module instance on /traffic."""
    content = TRAFFIC_MODULE.read_text(encoding="utf-8")

    assert f'from "{QUEUE_IMPORT}"' in content


def test_cdn_assets_have_subresource_integrity() -> None:
    """CDN scripts and styles are pinned to an integrity hash."""
    base = BASE_TEMPLATE.read_text(encoding="utf-8")
    world = WORLD_TEMPLATE.read_text(encoding="utf-8")

    assert 'integrity="sha384-' in base
    assert 'crossorigin="anonymous"' in base
    assert world.count('integrity="sha384-') == 2
    assert world.count('crossorigin="anonymous"') == 2
