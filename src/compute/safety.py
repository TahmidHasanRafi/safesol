"""Survival-card safety facts for a route: where the safe stops are and what to do if something fails.

Distances here are straight-line distances in projected metres (a conservative lower bound on
walking or driving distance). They answer "how far is help" at every point of the route.
"""

from __future__ import annotations

import numpy as np


def route_safety(points_xy, dist_m, shelters: list[dict], stop_radius_m: float = 1000.0) -> dict:
    """points_xy: (n, 2) route samples, dist_m: (n,) along-route distance of each sample,
    shelters: [{"id","name","type","x","y","shielding"}]."""
    pts = np.asarray(points_xy, dtype="float64")
    d = np.asarray(dist_m, dtype="float64")
    if len(pts) == 0 or not shelters:
        return {"safe_stops": [], "most_exposed": None}

    sx = np.array([s["x"] for s in shelters], dtype="float64")
    sy = np.array([s["y"] for s in shelters], dtype="float64")
    # distance from every sample to every shelter: (n_samples, n_shelters)
    gap = np.hypot(pts[:, 0:1] - sx[None, :], pts[:, 1:2] - sy[None, :])

    # Safe stops: shelters that come within stop_radius_m of the route, in the order they are passed.
    stops = []
    for j, s in enumerate(shelters):
        i = int(np.argmin(gap[:, j]))
        if gap[i, j] <= stop_radius_m:
            stops.append({"id": s["id"], "name": s["name"], "type": s["type"], "shielding": s["shielding"],
                          "at_m": float(d[i]), "off_route_m": float(gap[i, j])})
    stops.sort(key=lambda s: s["at_m"])

    # Most exposed point: the sample whose nearest shelter is farthest away.
    nearest_j = gap.argmin(axis=1)
    nearest_m = gap[np.arange(len(pts)), nearest_j]
    i = int(np.argmax(nearest_m))
    s = shelters[int(nearest_j[i])]
    most_exposed = {"at_m": float(d[i]), "x": float(pts[i, 0]), "y": float(pts[i, 1]),
                    "nearest_shelter": s["name"], "nearest_type": s["type"], "distance_m": float(nearest_m[i])}
    return {"safe_stops": stops, "most_exposed": most_exposed, "stop_radius_m": stop_radius_m}
