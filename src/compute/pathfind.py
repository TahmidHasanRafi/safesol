"""Least-cost paths over the DEM with Dijkstra's algorithm.

Edge cost = travel time (s) x (1 + penalty * slope / limit). Steps steeper than the limit are blocked.
Runs on a block-averaged copy of the DEM so a full search takes well under a second.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from affine import Affine
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from src.compute.terrain import Terrain, apply

NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def block_mean(values: np.ndarray, factor: int) -> np.ndarray:
    """Average factor x factor blocks; any NaN in a block makes the block NaN."""
    rows, cols = values.shape[0] // factor, values.shape[1] // factor
    v = values[: rows * factor, : cols * factor].reshape(rows, factor, cols, factor)
    return v.mean(axis=(1, 3))


@dataclass
class RoutingGrid:
    elev: np.ndarray
    transform: Affine
    res: float

    @classmethod
    def from_terrain(cls, terrain: Terrain, max_cells: int) -> "RoutingGrid":
        factor = max(1, math.ceil(max(terrain.shape) / max_cells))
        elev = block_mean(terrain.elev, factor)
        t = terrain.transform
        # Same as transform * Affine.scale(factor), written out so no affine version warns.
        coarse = Affine(t.a * factor, t.b * factor, t.c, t.d * factor, t.e * factor, t.f)
        return cls(elev, coarse, terrain.res * factor)

    @property
    def shape(self):
        return self.elev.shape

    def cell_at(self, x, y) -> int:
        col, row = apply(~self.transform, x, y)
        r, c = int(math.floor(row)), int(math.floor(col))
        rows, cols = self.shape
        if r < 0 or c < 0 or r >= rows or c >= cols:
            return -1
        return r * cols + c

    def center(self, idx: int):
        r, c = divmod(int(idx), self.shape[1])
        return apply(self.transform, c + 0.5, r + 0.5)

    def corners(self):
        rows, cols = self.shape
        return [apply(self.transform, c, r) for c, r in [(0, 0), (cols, 0), (cols, rows), (0, rows)]]


def build_graph(rg: RoutingGrid, slope_limit_deg: float, speed_m_s: float, penalty: float = 1.0):
    """Sparse directed graph of allowed 8-neighbour moves weighted by travel time."""
    rows, cols = rg.shape
    z = rg.elev
    idx = np.arange(rows * cols).reshape(rows, cols)
    src, dst, cost = [], [], []
    for dr, dc in NEIGHBOURS:
        r0, r1 = max(0, -dr), rows - max(0, dr)
        c0, c1 = max(0, -dc), cols - max(0, dc)
        a = z[r0:r1, c0:c1]
        b = z[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
        d = rg.res * (math.sqrt(2) if dr and dc else 1.0)
        slope = np.degrees(np.arctan(np.abs(b - a) / d))
        ok = np.isfinite(slope) & (slope <= slope_limit_deg)
        src.append(idx[r0:r1, c0:c1][ok])
        dst.append(idx[r0 + dr:r1 + dr, c0 + dc:c1 + dc][ok])
        # Tiny epsilon keeps zero-slope edges strictly positive for scipy.
        cost.append((d / speed_m_s) * (1 + penalty * slope[ok] / slope_limit_deg) + 1e-9)
    n = rows * cols
    return coo_matrix((np.concatenate(cost), (np.concatenate(src), np.concatenate(dst))), shape=(n, n)).tocsr()


def travel_times(graph, start: int):
    """Dijkstra from start. Returns (time to every cell in s, predecessor array)."""
    times, pred = dijkstra(graph, directed=True, indices=start, return_predecessors=True)
    return times, pred


def trace(pred: np.ndarray, end: int) -> list[int]:
    path = []
    i = int(end)
    while i >= 0:
        path.append(i)
        i = int(pred[i])
    return path[::-1]


def least_cost_route(rg: RoutingGrid, graph, a_xy, b_xy):
    """List of (x, y) from a to b over allowed terrain, or None if no safe route exists."""
    s, t = rg.cell_at(*a_xy), rg.cell_at(*b_xy)
    if s < 0 or t < 0 or not np.isfinite(rg.elev.flat[s]) or not np.isfinite(rg.elev.flat[t]):
        return None
    times, pred = travel_times(graph, s)
    if not np.isfinite(times[t]):
        return None
    cells = trace(pred, t)
    return [tuple(a_xy)] + [rg.center(i) for i in cells[1:-1]] + [tuple(b_xy)]