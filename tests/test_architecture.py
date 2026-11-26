"""Structural checks for the dependency boundaries.

These are contracts, not style checks: routes translate HTTP, services own use
cases, and only the adapters may import the SatGoNetem core. The checks parse
imports with :mod:`ast` so aliased imports and dynamic string-based imports are
caught instead of relying on substring matches.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "satgonetem_gui"
ADAPTERS = PACKAGE / "adapters"

CORE_PACKAGES = (
    "satgonetem",
    "sat_com_builder",
    "sat_com_connectivity",
    "sat_com_model",
)
CORE_CONTRACT_SYMBOLS = frozenset({"TopologyManager", "Iperf3Flow", "PingFlow", "Hping3Flow"})
PRIVATE_HOOKS = frozenset(
    {"_sync_node_positions", "_apply_network_config", "_active_flows", "_data"}
)


def _module_name(path: Path) -> str:
    """Return the absolute import name of a package source file."""
    relative = path.relative_to(PACKAGE.parent).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_import(module: str, level: int, module_name: str) -> str:
    """Resolve a possibly relative import to an absolute module name."""
    if level == 0:
        return module
    package_parts = module_name.split(".")[:-1]
    base = package_parts[: len(package_parts) - (level - 1)]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _imported_modules(source: str, module_name: str) -> list[str]:
    """Return every absolute module imported by the given source."""
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(_resolve_import(node.module or "", node.level, module_name))
    return modules


def _imported_symbols(source: str) -> list[str]:
    """Return every symbol imported by name from an ``ImportFrom``."""
    tree = ast.parse(source)
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            symbols.extend(alias.name for alias in node.names)
    return symbols


def _string_constants(source: str) -> list[str]:
    """Return every string literal in the source."""
    tree = ast.parse(source)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _non_adapter_sources() -> list[Path]:
    return [path for path in _sources() if ADAPTERS not in path.parents]


def _is_core_module(module: str) -> bool:
    return module.split(".")[0] in CORE_PACKAGES


def _forbidden_core_imports(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    return [
        module
        for module in _imported_modules(source, _module_name(path))
        if _is_core_module(module)
    ]


def _adapter_imports(path: Path) -> list[str]:
    adapter_package = _module_name(ADAPTERS / "__init__.py")
    source = path.read_text(encoding="utf-8")
    return [
        module
        for module in _imported_modules(source, _module_name(path))
        if module == adapter_package or module.startswith(f"{adapter_package}.")
    ]


def test_only_adapters_import_the_satgonetem_core() -> None:
    """Routes, services, and pure modules never import the core packages."""
    offenders = {
        str(path.relative_to(PACKAGE)): _forbidden_core_imports(path)
        for path in _non_adapter_sources()
        if _forbidden_core_imports(path)
    }
    assert offenders == {}


def test_routes_and_services_do_not_import_adapters() -> None:
    """The dependency direction is routes -> services -> ports; adapters plug in."""
    offenders = {}
    for path in _non_adapter_sources():
        if path.parent.name not in {"routes", "services"}:
            continue
        imports = _adapter_imports(path)
        if imports:
            offenders[str(path.relative_to(PACKAGE))] = imports
    assert offenders == {}


def test_core_contract_symbols_are_confined_to_adapters() -> None:
    """Concrete core classes are imported by name only inside adapters."""
    offenders = {}
    for path in _non_adapter_sources():
        symbols = set(_imported_symbols(path.read_text(encoding="utf-8")))
        concrete = sorted(symbols & CORE_CONTRACT_SYMBOLS)
        if concrete:
            offenders[str(path.relative_to(PACKAGE))] = concrete
    assert offenders == {}


def test_private_core_hooks_are_confined_to_adapters() -> None:
    """Private satgonetem attributes never leak outside the adapter package."""
    offenders = {}
    for path in _non_adapter_sources():
        constants = set(_string_constants(path.read_text(encoding="utf-8")))
        hooks = sorted(constants & PRIVATE_HOOKS)
        if hooks:
            offenders[str(path.relative_to(PACKAGE))] = hooks
    assert offenders == {}


def test_route_handlers_stay_small() -> None:
    """Route modules remain translation layers, not orchestration modules."""
    for path in sorted((PACKAGE / "routes").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                assert length <= 60, f"{path.name}:{node.name} is {length} lines"


def test_detector_flags_aliased_core_imports() -> None:
    """The import detector catches aliased and relative adapter imports."""
    source = "import satgonetem as core\nfrom ..adapters.core import initialize_core\n"
    module_name = "satgonetem_gui.services.example"
    modules = _imported_modules(source, module_name)
    assert "satgonetem" in modules
    assert [module for module in modules if module.startswith("satgonetem_gui.adapters")] == [
        "satgonetem_gui.adapters.core"
    ]


def test_detector_allows_adapter_imports() -> None:
    """The project adapter contract is explicitly allowed to import the core."""
    project_adapter = ADAPTERS / "project_adapter.py"
    symbols = set(_imported_symbols(project_adapter.read_text(encoding="utf-8")))
    assert "TopologyManager" in symbols
