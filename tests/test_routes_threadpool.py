"""Route handlers must not run blocking service work on the event loop.

FastAPI runs plain ``def`` handlers in its threadpool and ``async def`` handlers
on the event loop. Blocking endpoints therefore stay synchronous; the handlers
that await non-blocking async service methods stay coroutines.
"""

import inspect

import pytest

from satgonetem_gui.routes import (
    addressability,
    connectivity,
    coverage,
    diagnostics,
    experiments,
    projects,
    routing,
    topology,
    traffic,
    workspace,
)

BLOCKING_ENDPOINTS = [
    addressability.api_satellite_addressability,
    addressability.api_set_satellite_addressability,
    addressability.api_set_node_addressability,
    diagnostics.api_preflight,
    connectivity.api_connectivity_start,
    connectivity.api_connectivity_status,
    connectivity.api_connectivity_export,
    coverage.api_coverage,
    experiments.api_experiment_start,
    experiments.api_experiment_list,
    experiments.api_experiment_status,
    experiments.api_experiment_artifact,
    experiments.api_experiment_metrics,
    projects.api_ground_station_presets,
    projects.api_project_create,
    projects.api_project_status,
    projects.api_project_exists,
    projects.api_project_config,
    workspace.api_projects,
    workspace.api_duplicate_project,
    workspace.api_delete_project,
    topology.api_satellites,
    topology.api_ground_stations,
    topology.api_status,
    topology.api_links,
    topology.api_link_usage,
    topology.api_nodes,
    topology.api_node_detail,
    routing.api_routing_status,
    routing.api_routing_path,
    traffic.api_traffic_nodes,
    traffic.api_traffic_iperf3,
    traffic.api_traffic_ping,
    traffic.api_traffic_hping3,
    traffic.api_traffic_status,
    traffic.api_traffic_cancel,
]

ASYNC_ENDPOINTS = [
    projects.api_project_load,
    projects.api_project_save,
    workspace.api_load_project,
    workspace.api_save_to,
    workspace.api_save_in_place,
    routing.api_routing_apply,
    routing.api_routing_delete,
    routing.api_gonetem_start,
    routing.api_gonetem_stop,
]


@pytest.mark.parametrize("endpoint", BLOCKING_ENDPOINTS, ids=lambda endpoint: endpoint.__name__)
def test_blocking_endpoints_are_plain_functions(endpoint) -> None:
    """Blocking handlers are sync so FastAPI offloads them to the threadpool."""
    assert not inspect.iscoroutinefunction(endpoint)


@pytest.mark.parametrize("endpoint", ASYNC_ENDPOINTS, ids=lambda endpoint: endpoint.__name__)
def test_async_service_endpoints_remain_coroutines(endpoint) -> None:
    """Handlers that await async services stay coroutines on the event loop."""
    assert inspect.iscoroutinefunction(endpoint)
