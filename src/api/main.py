"""SafeSol API. Reads only local data (cache/ or demo_fixtures/): it never calls NASA during a demo.

Run:  uvicorn src.api.main:app --reload
"""

from __future__ import annotations

import base64
import io
import json
from functools import lru_cache

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from src.acquire.safe import read_local_json
from src.compute.escape import escape_plan
from src.compute.pathfind import RoutingGrid, block_mean, build_graph, least_cost_route
from src.compute.route import PRESETS, Rover, analyze_route
from src.compute.safety import route_safety
from src.compute.terrain import Terrain
from src.config import PLANNING_MARGIN, ROUTING_MAX_CELLS, WEB, terrain_dir


# ---------- data loaded once at start-up ----------
class Data:
    def __init__(self):
        folder, self.source = terrain_dir()
        if not (folder / "meta.json").exists():
            raise RuntimeError("No terrain data. Run: python -m src.acquire.dem --synthetic (or --dem your_dem.tif)")
        self.folder = folder
        self.terrain = Terrain.load(folder)
        self.meta = self.terrain.meta
        self.slope = self.terrain.slope_raster()
        self.rg = RoutingGrid.from_terrain(self.terrain, ROUTING_MAX_CELLS)
        factor = round(self.rg.res / self.terrain.res)
        import rasterio
        with rasterio.open(folder / "shielding.tif") as src:
            shield = src.read(1).astype("float64")
        self.shield_coarse = block_mean(shield, factor)
        self.shelters = json.loads((folder / "shelters.json").read_text())
        storms, label = read_local_json("storms")
        self.storms = storms or []
        self.storms_source = label or "none"


DATA = Data()
app = FastAPI(title="SafeSol API", version="1.0.0")


@lru_cache(maxsize=16)
def graph_for(limit: float, speed: float):
    return build_graph(DATA.rg, limit, speed)


# ---------- request models ----------
class RoverIn(BaseModel):
    mass_kg: float = Field(4000, gt=0)
    speed_m_s: float = Field(2.0, gt=0)
    slope_limit_deg: float = Field(20, gt=0, le=60)
    base_power_w: float = Field(3000, ge=0)
    energy_per_sol_wh: float = Field(60000, gt=0)
    drive_hours_per_sol: float = Field(8, gt=0, le=24.7)

    def rover(self) -> Rover:
        return Rover(**self.model_dump())


class RouteIn(BaseModel):
    points: list[list[float]] = Field(..., description="[[lon, lat], ...] in Mars degrees")
    rover: RoverIn = RoverIn()
    spacing_m: float = Field(25, ge=1, le=500)


class EscapeIn(BaseModel):
    position: list[float] = Field(..., description="[lon, lat]")
    warning_min: float = Field(30, gt=0, le=1440)
    rover: RoverIn = RoverIn()


# ---------- helpers ----------
def to_xy(points):
    pts = np.asarray(points, dtype="float64")
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise HTTPException(422, "points must be [[lon, lat], ...]")
    x, y = DATA.terrain.lonlat_to_xy(pts[:, 0], pts[:, 1])
    return np.column_stack([x, y])


def to_ll(xy):
    xy = np.asarray(xy, dtype="float64").reshape(-1, 2)
    lon, lat = DATA.terrain.xy_to_lonlat(xy[:, 0], xy[:, 1])
    return [[round(float(a), 7), round(float(b), 7)] for a, b in zip(lon, lat)]


def png_data_url(rgba: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def serialise_analysis(a: dict) -> dict:
    if not a["ok"]:
        return a
    ll = to_ll(a["points"])
    safety = route_safety(a["points"], a["dist_m"], DATA.shelters)
    if safety.get("most_exposed"):
        me = safety["most_exposed"]
        me["lon"], me["lat"] = to_ll([(me["x"], me["y"])])[0]
    failed = []
    for f in a["failed"]:
        i = f["index"]
        failed.append({**f, "line": [ll[i - 1], ll[i]]})
    out = {k: v for k, v in a.items() if k not in ("points", "dist_m", "elev_m", "segment_slope_deg", "failed")}
    out["failed"] = failed
    out["safety"] = safety
    over = {f["index"] for f in a["failed"]}  # segment i ends at sample i
    out["profile"] = [
        {"d_km": round(float(d) / 1000, 4), "z_m": round(float(z), 2), "lon": p[0], "lat": p[1], "over": i in over}
        for i, (d, z, p) in enumerate(zip(a["dist_m"], a["elev_m"], ll))
    ]
    return out


def shelter_out(s):
    return {k: v for k, v in s.items() if k not in ("cell",)} if s else None


# ---------- endpoints ----------
@app.get("/api/meta")
def meta():
    return {
        **DATA.meta,
        "data_source": DATA.source,
        "routing_res_m": DATA.rg.res,
        "routing_corners_lonlat": to_ll(DATA.rg.corners()),
        "presets": {k: v.as_dict() for k, v in PRESETS.items()},
        "planning_margin": PLANNING_MARGIN,
    }


@app.get("/api/shelters")
def shelters():
    return DATA.shelters


@app.get("/api/storms")
def storms():
    return {"source": DATA.storms_source, "events": DATA.storms}


@app.get("/api/tiles/{name}.png")
def tiles(name: str):
    if name not in ("basemap", "shielding"):
        raise HTTPException(404)
    return FileResponse(DATA.folder / f"{name}.png", media_type="image/png")


@lru_cache(maxsize=8)
def hazard_png(limit: float) -> bytes:
    mask = np.nan_to_num(DATA.slope) > limit
    rgba = np.zeros(mask.shape + (4,), dtype="uint8")
    rgba[mask] = (240, 80, 63, 150)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@app.get("/api/overlay/hazard.png")
def hazard(limit: float = Query(20, gt=0, le=60)):
    return Response(hazard_png(round(limit, 1)), media_type="image/png")


@app.post("/api/route/analyze")
def route_analyze(body: RouteIn):
    a = analyze_route(DATA.terrain, to_xy(body.points), body.rover.rover(), body.spacing_m)
    return serialise_analysis(a)


@app.post("/api/route/contingency")
def route_contingency(body: RouteIn):
    rover = body.rover.rover()
    xy = to_xy(body.points)
    limit = rover.slope_limit_deg * PLANNING_MARGIN
    path = least_cost_route(DATA.rg, graph_for(round(limit, 2), rover.speed_m_s), xy[0], xy[-1])
    if path is None:
        return {"ok": False, "error": f"No route between these points stays under {limit:.1f}° "
                                      f"at {DATA.rg.res:.0f} m routing resolution."}
    a = analyze_route(DATA.terrain, np.asarray(path), rover, body.spacing_m)
    return {"ok": True, "path": to_ll(path), "analysis": serialise_analysis(a),
            "routing_res_m": DATA.rg.res, "planning_limit_deg": limit}


@app.post("/api/storm/escape")
def storm_escape(body: EscapeIn):
    rover = body.rover.rover()
    start = to_xy([body.position])[0]
    plan = escape_plan(DATA.rg, graph_for(round(rover.slope_limit_deg, 2), rover.speed_m_s),
                       DATA.shield_coarse, DATA.shelters, start, body.warning_min * 60)
    if not plan["ok"]:
        return plan
    zone = plan["zone"]
    rgba = np.zeros(zone.shape + (4,), dtype="uint8")
    rgba[zone] = (194, 38, 143, 80)
    path = plan["path"]
    length = float(np.sum(np.hypot(*np.diff(np.asarray(path), axis=0).T))) if len(path) > 1 else 0.0
    best = shelter_out(plan["best"])
    if best and "lon" not in best:
        best["lon"], best["lat"] = to_ll([(best["x"], best["y"])])[0]
    return {
        "ok": True, "mode": plan["mode"], "best": best, "fastest": shelter_out(plan["fastest"]),
        "path": to_ll(path) if path else [], "path_length_m": length,
        "warning_s": body.warning_min * 60, "speed_m_s": rover.speed_m_s,
        "zone": {"image": png_data_url(rgba), "corners": to_ll(DATA.rg.corners())},
    }


@app.get("/api/provenance")
def provenance():
    """Raw source records behind every figure, for the interface's provenance drawer."""
    return {
        "terrain": {"name": DATA.meta.get("name"), "synthetic": DATA.meta.get("synthetic"),
                    "attribution": DATA.meta.get("attribution"), "source": DATA.meta.get("source"),
                    "provenance": DATA.meta.get("provenance"), "crs": DATA.meta.get("crs"),
                    "res_m": DATA.meta.get("res_m"), "generated_utc": DATA.meta.get("generated_utc"),
                    "read_from": DATA.source},
        "storms": {"read_from": DATA.storms_source, "count": len(DATA.storms),
                   "api": "https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP"},
        "method": {"routing_res_m": DATA.rg.res, "planning_margin": PLANNING_MARGIN,
                   "shielding": DATA.meta.get("svf")},
    }


@app.get("/api/health")
def health():
    return {"ok": True, "terrain": DATA.meta.get("name"), "data_source": DATA.source}


# The static frontend is mounted last so /api/* takes priority.
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
