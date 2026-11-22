"""Static asset URLs stay identical between templates and module imports."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
BASE_TEMPLATE = PACKAGE / "templates" / "base.html"
TRAFFIC_MODULE = PACKAGE / "static" / "traffic.js"

QUEUE_SCRIPT = "/static/queue.js?v=11"
QUEUE_IMPORT = "./queue.js?v=11"
WORLD_TEMPLATE = PACKAGE / "templates" / "world.html"


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
