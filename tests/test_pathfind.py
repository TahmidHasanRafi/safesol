"""Dijkstra routing and storm escape on synthetic terrain."""

import numpy as np

from src.compute.escape import escape_plan
from src.compute.pathfind import RoutingGrid, build_graph, least_cost_route
from src.compute.terrain import Terrain


def walled(with_gap: bool) -> RoutingGrid:
    """Flat 60x60 plain (10 m cells) with a 300 m wall at x = 290..310 m, gap at y = 50..100 m."""
    z = np.zeros((60, 60))
    z[:, 29:31] = 300
    if with_gap:
        z[50:55, 29:31] = 0   # rows 50..54 from the top = y 50..100 m from the bottom
    t = Terrain.from_array(z, 10.0, origin_xy=(0.0, 600.0))
    return RoutingGrid.from_terrain(t, 1000)


def test_route_goes_through_the_gap():
    rg = walled(True)
    path = least_cost_route(rg, build_graph(rg, 20, 1.0), (50, 300), (550, 300))
    assert path is not None
    crossing = [p for p in path if 290 < p[0] < 310]
    assert crossing and all(50 <= p[1] <= 100 for p in crossing)


def test_no_gap_means_no_route():
    rg = walled(False)
    assert least_cost_route(rg, build_graph(rg, 20, 1.0), (50, 300), (550, 300)) is None


def test_escape_prefers_reachable_shelter_else_best_spot():
    t = Terrain.from_array(np.zeros((60, 60)), 10.0, origin_xy=(0.0, 600.0))
    rg = RoutingGrid.from_terrain(t, 1000)
    graph = build_graph(rg, 20, 1.0)               # 1 m/s
    shield = np.full(rg.shape, 0.1)
    shield[30, 33] = 0.5                           # protected spot about 30 m east of the start
    shelters = [{"id": "far", "name": "Far wall", "type": "terrain", "x": 555.0, "y": 305.0, "shielding": 0.6}]
    start = (305.0, 295.0)

    long_warning = escape_plan(rg, graph, shield, shelters, start, 3600)
    assert long_warning["mode"] == "shelter" and long_warning["best"]["id"] == "far"

    short_warning = escape_plan(rg, graph, shield, shelters, start, 60)
    assert short_warning["mode"] == "spot"
    assert short_warning["best"]["shielding"] == 0.5
