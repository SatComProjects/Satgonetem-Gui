"""Static asset URLs stay identical between templates and module imports."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
BASE_TEMPLATE = PACKAGE / "templates" / "base.html"
TRAFFIC_MODULE = PACKAGE / "static" / "traffic.js"

QUEUE_SCRIPT = "/static/queue.js?v=5"
QUEUE_IMPORT = "./queue.js?v=5"


def test_base_template_loads_the_versioned_queue_module() -> None:
    """The shared page shell loads the same queue.js URL traffic.js imports."""
    content = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert QUEUE_SCRIPT in content


def test_traffic_module_imports_the_same_versioned_queue_module() -> None:
    """A bare import would create a second module instance on /traffic."""
    content = TRAFFIC_MODULE.read_text(encoding="utf-8")

    assert f'from "{QUEUE_IMPORT}"' in content
