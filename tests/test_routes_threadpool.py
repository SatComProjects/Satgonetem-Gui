"""Route handlers must not run blocking service work on the event loop.

FastAPI runs plain ``def`` handlers in its threadpool and ``async def`` handlers
on the event loop. Blocking endpoints therefore stay synchronous; the handlers
that await non-blocking async service methods stay coroutines.
"""

import inspect

import pytest

from satgonetem_gui.routes import (
    addressability,
    projects,
    routing,
    topology,
    traffic,
)

BLOCKING_ENDPOINTS = [
    addressability.api_satellite_addressability,
    addressability.api_set_satellite_addressability,
    addressability.api_set_node_addressability,
    projects.api_ground_station_presets,
    projects.api_project_create,
    projects.api_project_status,
    projects.api_project_exists,
    projects.api_project_config,
    topology.api_satellites,
    topology.api_ground_stations,
    topology.api_status,
    topology.api_links,
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
