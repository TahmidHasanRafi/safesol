"""Route cost from terrain: one module, all assumptions visible.

Deterministic science only. No language model computes anything here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from src.config import MARS_G
from src.compute.terrain import Terrain


@dataclass
class Rover:
    """Every field is a modelling assumption and is shown in the interface."""
    mass_kg: float = 4000.0
    speed_m_s: float = 2.0
    slope_limit_deg: float = 20.0
    base_power_w: float = 3000.0
    energy_per_sol_wh: float = 60000.0
    drive_hours_per_sol: float = 8.0

    def as_dict(self):
        return asdict(self)


PRESETS = {
    "crewed": Rover(4000, 2.0, 20, 3000, 60000, 8),
    "robotic": Rover(900, 0.04, 20, 120, 2000, 4),
}


def sample_polyline(xy: np.ndarray, spacing_m: float):
    """Resample a polyline every spacing_m metres, keeping both ends.
    Returns (points (n, 2), cumulative distance (n,))."""
    xy = np.asarray(xy, dtype="float64")
    if len(xy) < 2:
        return np.empty((0, 2)), np.empty(0)
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total == 0:
        return np.empty((0, 2)), np.empty(0)
    d = np.arange(0.0, total, spacing_m)
    if total - d[-1] > 1e-9:
        d = np.append(d, total)
    x = np.interp(d, cum, xy[:, 0])
    y = np.interp(d, cum, xy[:, 1])
    return np.column_stack([x, y]), d


def route_profile(elevations_m, distances_m, rover: Rover) -> dict:
    """Profile metrics from elevations at known along-route distances (the Build Guide's route_profile,
    generalised to uneven spacing)."""
    z = np.asarray(elevations_m, dtype="float64")
    d = np.asarray(distances_m, dtype="float64")
    dz = np.diff(z)
    dd = np.diff(d)
    slope = np.degrees(np.arctan2(dz, dd))
    climb = float(dz[dz > 0].sum())
    distance = float(d[-1])
    time_s = distance / rover.speed_m_s
    base_j = rover.base_power_w * time_s
    climb_j = rover.mass_kg * MARS_G * climb
    total_wh = (base_j + climb_j) / 3600
    driving_sols = time_s / 3600 / rover.drive_hours_per_sol
    wh_per_sol = total_wh / driving_sols if driving_sols > 1 else total_wh
    max_slope = float(np.abs(slope).max()) if slope.size else 0.0
    return {
        "distance_m": distance,
        "total_climb_m": climb,
        "max_slope_deg": max_slope,
        "slope_deg": slope,
        "time_s": time_s,
        "time_hours": time_s / 3600,
        "base_wh": base_j / 3600,
        "climb_wh": climb_j / 3600,
        "energy_wh": total_wh,
        "driving_sols": driving_sols,
        "wh_per_sol": wh_per_sol,
        "energy_ok": bool(wh_per_sol <= rover.energy_per_sol_wh),
        "passes_slope_limit": bool(max_slope <= rover.slope_limit_deg),
    }


def analyze_route(terrain: Terrain, xy, rover: Rover, spacing_m: float = 25.0) -> dict:
    """Full analysis of a route given in projected metres."""
    pts, dist = sample_polyline(xy, spacing_m)
    if len(pts) < 2:
        return {"ok": False, "error": "Draw at least two points to make a route."}

    z = terrain.sample(pts[:, 0], pts[:, 1])
    bad = np.flatnonzero(~np.isfinite(z))
    if bad.size:
        km = dist[bad[0]] / 1000
        return {"ok": False, "error": f"The route leaves the terrain data at {km:.2f} km. Keep the route inside the map."}

    prof = route_profile(z, dist, rover)
    ground = terrain.ground_slope(pts[:, 0], pts[:, 1])
    slope = prof.pop("slope_deg")
    exceed = np.abs(slope) - rover.slope_limit_deg
    failed = [
        {"index": int(i + 1), "from_m": float(dist[i]), "to_m": float(dist[i + 1]),
         "slope_deg": float(slope[i]), "exceed_deg": float(exceed[i])}
        for i in np.flatnonzero(exceed > 0)
    ]
    return {
        "ok": True,
        "status": "PASS" if not failed else "FAIL",
        **prof,
        "max_ground_slope_deg": float(np.nanmax(ground)) if np.isfinite(ground).any() else None,
        "failed": failed,
        "worst": max(failed, key=lambda f: f["exceed_deg"]) if failed else None,
        "points": pts,
        "dist_m": dist,
        "elev_m": z,
        "segment_slope_deg": slope,
    }
