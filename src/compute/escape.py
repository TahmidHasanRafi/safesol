"""Solar storm escape planning.

One Dijkstra search from the vehicle gives the travel time to every cell. From that:
  - reachable zone = cells reachable before the warning time runs out
  - best shelter   = highest shielding among shelters inside the zone (ties: fastest)
  - fallback       = best-protected cell inside the zone when no shelter is reachable
"""

from __future__ import annotations

import numpy as np

from src.compute.pathfind import RoutingGrid, trace, travel_times


def escape_plan(rg: RoutingGrid, graph, shield_coarse: np.ndarray, shelters: list[dict], start_xy, warning_s: float):
    start = rg.cell_at(*start_xy)
    if start < 0 or not np.isfinite(rg.elev.flat[start]):
        return {"ok": False, "error": "The vehicle position is outside the terrain data."}

    times, pred = travel_times(graph, start)
    zone = times <= warning_s

    timed = []
    for s in shelters:
        cell = rg.cell_at(s["x"], s["y"])
        if cell >= 0 and np.isfinite(times[cell]):
            timed.append({**s, "cell": cell, "time_s": float(times[cell])})
    fastest = min(timed, key=lambda s: s["time_s"]) if timed else None
    reachable = sorted((s for s in timed if s["time_s"] <= warning_s),
                       key=lambda s: (-s["shielding"], s["time_s"]))

    def path_to(cell):
        return [tuple(start_xy)] + [rg.center(i) for i in trace(pred, cell)[1:]]

    if reachable:
        best = reachable[0]
        return {"ok": True, "mode": "shelter", "best": best, "fastest": fastest,
                "path": path_to(best["cell"]), "zone": zone.reshape(rg.shape)}

    sc = np.where(zone & np.isfinite(shield_coarse.ravel()), shield_coarse.ravel(), -1.0)
    cell = int(np.argmax(sc))
    if sc[cell] < 0 or cell == start:
        return {"ok": True, "mode": "none", "best": None, "fastest": fastest, "path": [],
                "zone": zone.reshape(rg.shape)}
    x, y = rg.center(cell)
    best = {"id": "spot", "name": "Best protected spot in reach", "type": "spot", "x": x, "y": y,
            "shielding": round(float(sc[cell]), 3), "cell": cell, "time_s": float(times[cell])}
    return {"ok": True, "mode": "spot", "best": best, "fastest": fastest,
            "path": path_to(cell), "zone": zone.reshape(rg.shape)}
