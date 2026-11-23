"""Static asset URLs stay identical between templates and module imports."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
BASE_TEMPLATE = PACKAGE / "templates" / "base.html"
TRAFFIC_MODULE = PACKAGE / "static" / "traffic.js"
QUEUE_MODULE = PACKAGE / "static" / "queue.js"

QUEUE_SCRIPT = "/static/queue.js?v=24"
QUEUE_IMPORT = "./queue.js?v=24"
QUEUE_MODEL_IMPORT = "./queue_model.js?v=4"
HISTORY_MODEL_IMPORT = "./history_model.js?v=1"
PATH_MODEL_IMPORT = "./path_model.js?v=1"
LINKS_MODEL_IMPORT = "./links_model.js?v=1"
WORLD_TEMPLATE = PACKAGE / "templates" / "world.html"
SIMULATION_CONTROLS = PACKAGE / "static" / "simulation_controls.js"
SIMULATION_MODEL_IMPORT = "./simulation_model.js?v=1"
ADDRESSABILITY_MODEL_IMPORT = "./addressability_model.js?v=1"
PREFLIGHT_MODEL_IMPORT = "./preflight_model.js?v=1"
PREFLIGHT_UI_IMPORT = "./preflight_ui.js?v=1"
DASHBOARD_MODULE = PACKAGE / "static" / "dashboard.js"
NEW_PROJECT_MODULE = PACKAGE / "static" / "new_project.js"
PROJECTS_MODULE = PACKAGE / "static" / "projects.js"
PROJECTS_MODEL_IMPORT = "./projects_model.js?v=1"
CONNECTIVITY_MODULE = PACKAGE / "static" / "connectivity.js"
CONNECTIVITY_MODEL_IMPORT = "./connectivity_model.js?v=1"
COVERAGE_MODULE = PACKAGE / "static" / "coverage.js"
COVERAGE_MODEL_IMPORT = "./coverage_model.js?v=1"
TOPOLOGY_HEALTH_MODULE = PACKAGE / "static" / "topology_health.js"
TOPOLOGY_HEALTH_MODEL_IMPORT = "./topology_health_model.js?v=1"
TRAFFIC_MODULE = PACKAGE / "static" / "traffic.js"
TRAFFIC_PRESETS_IMPORT = "./traffic_presets.js?v=1"
SHORTCUTS_MODULE = PACKAGE / "static" / "shortcuts.js"
SHORTCUTS_MODEL_IMPORT = "./shortcuts_model.js?v=1"
LINK_BUDGET_MODULE = PACKAGE / "static" / "link_budget.js"
LINK_BUDGET_MODEL_IMPORT = "./link_budget_model.js?v=1"
SCENARIO_BUILDER_MODULE = PACKAGE / "static" / "scenario_builder.js"
SCENARIO_BUILDER_MODEL_IMPORT = "./scenario_builder_model.js?v=1"
EXPERIMENTS_MODULE = PACKAGE / "static" / "experiments.js"
EXPERIMENTS_MODEL_IMPORT = "./experiments_model.js?v=2"
NODES_MODULE = PACKAGE / "static" / "nodes.js"
WORLD_MODULE = PACKAGE / "static" / "world.js"


def test_path_controllers_import_the_versioned_model() -> None:
    """Node Explorer and World View share one cache-busted path model."""
    for path in (NODES_MODULE, WORLD_MODULE):
        assert f'"{PATH_MODEL_IMPORT}"' in path.read_text(encoding="utf-8")


def test_link_controllers_import_the_versioned_model() -> None:
    """Node Explorer and World View share one cache-busted link model."""
    for path in (NODES_MODULE, WORLD_MODULE):
        assert f'"{LINKS_MODEL_IMPORT}"' in path.read_text(encoding="utf-8")


def test_experiments_page_imports_the_versioned_model() -> None:
    """The experiment page uses one cache-busted formatting model."""
    assert f'"{EXPERIMENTS_MODEL_IMPORT}"' in EXPERIMENTS_MODULE.read_text(encoding="utf-8")


def test_scenario_builder_imports_the_versioned_model() -> None:
    """The builder uses one cache-busted generation model."""
    assert f'"{SCENARIO_BUILDER_MODEL_IMPORT}"' in SCENARIO_BUILDER_MODULE.read_text(
        encoding="utf-8"
    )


def test_link_budget_page_imports_the_versioned_model() -> None:
    """The workbench uses one cache-busted formatting model."""
    assert f'"{LINK_BUDGET_MODEL_IMPORT}"' in LINK_BUDGET_MODULE.read_text(encoding="utf-8")


def test_shortcuts_module_imports_the_versioned_model() -> None:
    """The shell shortcuts use one cache-busted guard model."""
    assert f'"{SHORTCUTS_MODEL_IMPORT}"' in SHORTCUTS_MODULE.read_text(encoding="utf-8")


def test_traffic_page_imports_the_versioned_preset_model() -> None:
    """The traffic form uses one cache-busted preset model."""
    assert f'"{TRAFFIC_PRESETS_IMPORT}"' in TRAFFIC_MODULE.read_text(encoding="utf-8")


def test_topology_health_imports_the_versioned_model() -> None:
    """The health card uses one cache-busted formatting model."""
    assert f'"{TOPOLOGY_HEALTH_MODEL_IMPORT}"' in TOPOLOGY_HEALTH_MODULE.read_text(encoding="utf-8")


def test_coverage_page_imports_the_versioned_model() -> None:
    """The coverage page uses one cache-busted formatting model."""
    assert f'"{COVERAGE_MODEL_IMPORT}"' in COVERAGE_MODULE.read_text(encoding="utf-8")


def test_connectivity_page_imports_the_versioned_model() -> None:
    """The heatmap controller uses one cache-busted connectivity model."""
    assert f'"{CONNECTIVITY_MODEL_IMPORT}"' in CONNECTIVITY_MODULE.read_text(encoding="utf-8")


def test_projects_page_imports_the_versioned_model() -> None:
    """The workspace page shares one cache-busted formatting model."""
    assert f'"{PROJECTS_MODEL_IMPORT}"' in PROJECTS_MODULE.read_text(encoding="utf-8")


def test_preflight_pages_import_the_versioned_ui_and_model() -> None:
    """Dashboard and New Project share cache-busted preflight modules."""
    for path in (DASHBOARD_MODULE, NEW_PROJECT_MODULE):
        content = path.read_text(encoding="utf-8")
        assert f'"{PREFLIGHT_UI_IMPORT}"' in content
    assert f'"{PREFLIGHT_MODEL_IMPORT}"' in NEW_PROJECT_MODULE.read_text(encoding="utf-8")


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
