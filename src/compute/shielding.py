"""Terrain shielding from the sky view factor, and terrain shelter selection.

shielding = 1 - SVF,  SVF = 1 - mean over azimuths of sin(horizon angle)

Assumes particles arrive equally from every direction of the sky. This is a RELATIVE index of how
much open sky the terrain blocks. It is not a radiation dose.
"""

from __future__ import annotations

import math

import numpy as np


def sky_view_shielding(elev: np.ndarray, res: float, radius_m: float = 1500.0, n_azimuths: int = 16) -> np.ndarray:
    rows, cols = elev.shape
    steps = max(1, int(radius_m / res))
    filled = np.where(np.isfinite(elev), elev, -1e9)
    sin_sum = np.zeros(elev.shape)
    for k in range(n_azimuths):
        a = 2 * math.pi * k / n_azimuths
        dx, dy = math.sin(a), -math.cos(a)  # azimuth 0 = north = decreasing row
        best = np.zeros(elev.shape)         # tangent of the horizon angle, floored at 0
        for s in range(1, steps + 1):
            ox, oy = int(round(dx * s)), int(round(dy * s))
            if ox == 0 and oy == 0:
                continue
            dist = math.hypot(ox, oy) * res
            shifted = np.full(elev.shape, -1e9)
            shifted[max(0, -oy):min(rows, rows - oy), max(0, -ox):min(cols, cols - ox)] = \
                filled[max(0, oy):min(rows, rows + oy), max(0, ox):min(cols, cols + ox)]
            best = np.maximum(best, (shifted - filled) / dist)
        sin_sum += np.sin(np.arctan(best))
    shielding = sin_sum / n_azimuths
    shielding[~np.isfinite(elev)] = np.nan
    return shielding


def pick_shelters(shielding, slope_deg, cell_center, limit_deg=20.0, count=12, min_sep_m=700.0, threshold=0.08):
    """Highest-shielding cells that are not steeper than the slope limit, spaced apart.
    cell_center(row, col) -> (x, y) in projected metres."""
    cand = np.where(np.isfinite(shielding) & (slope_deg <= limit_deg) & (shielding >= threshold), shielding, -1.0)
    m = 3
    cand[:m, :] = cand[-m:, :] = -1
    cand[:, :m] = cand[:, -m:] = -1
    chosen = []
    for flat in np.argsort(cand, axis=None)[::-1]:
        v = cand.flat[flat]
        if v < 0 or len(chosen) >= count:
            break
        r, c = divmod(int(flat), cand.shape[1])
        x, y = cell_center(r, c)
        if all(math.hypot(x - p["x"], y - p["y"]) >= min_sep_m for p in chosen):
            chosen.append({"x": float(x), "y": float(y), "shielding": round(float(v), 3)})
    return chosen
