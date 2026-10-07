"""Prepare the regional terrain cache from a NASA Mars Trek DEM (run before the event).

    python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --name "Jezero Crater"
    python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --ortho cache/raw/jezero_ortho.tif
    python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --bbox 77.2 18.2 77.8 18.7
    python -m src.acquire.dem --synthetic            # test terrain, clearly flagged in the app

Real terrain is easiest to get with `python -m src.acquire.ctx_dtm` (USGS Astrogeology CTX DTM),
or download a GeoTIFF from NASA Mars Trek by hand.

Steps:
 1. Reproject the DEM into a local equirectangular projection centred on the region, so one
    projected metre is one metre on the ground (a global equirectangular grid stretches
    east-west distances by 1/cos(latitude), about 5% at Jezero).
 2. Resample by area averaging to the target cell size and save as a Cloud Optimized GeoTIFF.
 3. Compute the sky-view shielding index and pick terrain shelters.
 4. Render the basemap (Mars Trek orthoimage if given, otherwise a hillshade) and overlays.

Output: cache/mars/  dem.tif  shielding.tif  basemap.png  shielding.png  shelters.json  meta.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS
from pyproj.crs import ProjectedCRS
from pyproj.crs.coordinate_operation import EquidistantCylindricalConversion
from rasterio.crs import CRS as RioCRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds

from src.compute.shielding import pick_shelters, sky_view_shielding
from src.compute.terrain import Terrain
from src.config import CACHE, MARS_DIR_NAME

JEZERO_LON, JEZERO_LAT = 77.58, 18.38


def local_crs(geodetic: CRS, lon_c: float, lat_c: float) -> CRS:
    return ProjectedCRS(
        conversion=EquidistantCylindricalConversion(latitude_first_parallel=lat_c, longitude_natural_origin=lon_c),
        geodetic_crs=geodetic,
        name=f"Local equirectangular {lat_c:.3f}N {lon_c:.3f}E",
    )


def warp_to_local(path: Path, res: float, bbox_lonlat=None, resampling=Resampling.average, grid=None):
    """Reproject a raster to the local grid. Returns (array, transform, crs, info)."""
    with rasterio.open(path) as src:
        if src.crs is None:
            raise SystemExit(f"{path} has no coordinate reference system. Download a georeferenced GeoTIFF.")
        src_crs = CRS.from_wkt(src.crs.to_wkt())
        geo = src_crs.geodetic_crs
        if grid is None:
            ll = transform_bounds(src.crs, RioCRS.from_wkt(geo.to_wkt()), *src.bounds)
            if bbox_lonlat:
                ll = (max(ll[0], bbox_lonlat[0]), max(ll[1], bbox_lonlat[1]),
                      min(ll[2], bbox_lonlat[2]), min(ll[3], bbox_lonlat[3]))
                if ll[0] >= ll[2] or ll[1] >= ll[3]:
                    raise SystemExit("The --bbox does not overlap the DEM.")
            lon_c, lat_c = (ll[0] + ll[2]) / 2, (ll[1] + ll[3]) / 2
            dst_crs = local_crs(geo, lon_c, lat_c)
            left, bottom, right, top = transform_bounds(RioCRS.from_wkt(geo.to_wkt()),
                                                        RioCRS.from_wkt(dst_crs.to_wkt()), *ll)
            width, height = math.ceil((right - left) / res), math.ceil((top - bottom) / res)
            transform = from_origin(left, top, res, res)
        else:
            transform, dst_crs, width, height = grid
        out = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=out,
            src_nodata=src.nodata, dst_nodata=np.nan,
            dst_transform=transform, dst_crs=RioCRS.from_wkt(dst_crs.to_wkt()),
            resampling=resampling,
        )
        info = {"file": Path(path).name, "crs": src_crs.name,
                "native_pixel_m": [round(abs(src.transform.a), 3), round(abs(src.transform.e), 3)]}
    return out, transform, dst_crs, info


def synthetic_raw(path: Path, res: float = 20.0):
    """Write a synthetic crater GeoTIFF in a GLOBAL Mars equirectangular grid near Jezero,
    the way a downloaded product would look. NOT real Mars data."""
    size = 20_000
    n = int(size / res)
    y, x = np.mgrid[0:n, 0:n].astype("float64") * res
    cx, cy = size * 0.55, size * 0.5
    r = np.hypot(x - cx, y - cy)
    R = 7_000
    t = np.clip((R - r) / 1_200, 0, 1)
    z = (-400 + 0.02 * r) * 0.4 * t * t * (3 - 2 * t)
    z += 160 * np.exp(-((r - R) / 500) ** 2) - 200 * np.clip((R - r) / 900, 0, 1) * (r < R)
    z += 120 * np.exp(-(((x - 4_500) / 2_200) ** 2 + ((y - 9_500) / 1_600) ** 2))
    rng = np.random.default_rng(7)
    for _ in range(25):
        kx, ky = rng.uniform(1_000, size - 1_000, 2)
        kr = rng.uniform(150, 600)
        d = np.hypot(x - kx, y - ky)
        z += -0.25 * kr * np.clip(1 - (d / kr) ** 2, 0, 1) + 0.08 * kr * np.exp(-((d - kr) / (0.25 * kr)) ** 2)
    z += rng.normal(0, 0.6, z.shape)

    geo = CRS("IAU_2015:49900")  # Mars (2015) sphere
    gcrs = ProjectedCRS(conversion=EquidistantCylindricalConversion(latitude_first_parallel=0, longitude_natural_origin=0),
                        geodetic_crs=geo, name="Mars global equirectangular")
    radius = geo.ellipsoid.semi_major_metre
    x0 = math.radians(JEZERO_LON) * radius - size / 2 / math.cos(math.radians(JEZERO_LAT))
    y0 = math.radians(JEZERO_LAT) * radius + size / 2
    px = res / math.cos(math.radians(JEZERO_LAT))  # global grid cells are wider than they look on the ground
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32",
                       crs=RioCRS.from_wkt(gcrs.to_wkt()), transform=from_origin(x0, y0, px, res), nodata=-9999) as dst:
        dst.write(z.astype("float32"), 1)


def write_cog(path: Path, arr: np.ndarray, transform, crs: CRS):
    profile = dict(driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype="float32",
                   crs=RioCRS.from_wkt(crs.to_wkt()), transform=transform, nodata=np.nan,
                   tiled=True, blockxsize=256, blockysize=256, compress="deflate")
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)
    try:  # convert to a true COG when the GDAL build supports it
        from rasterio.shutil import copy as rio_copy
        rio_copy(tmp, path, driver="COG", compress="DEFLATE")
        tmp.unlink()
    except Exception:
        tmp.replace(path)


def hillshade(elev, res, az=315.0, alt=35.0):
    gy, gx = np.gradient(elev, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, b = math.radians(az), math.radians(alt)
    return np.clip(math.sin(b) * np.cos(slope) + math.cos(b) * np.sin(slope) * np.cos(a - aspect), 0, 1)


def dust_tint(gray01, valid):
    lo, hi = np.array([58, 40, 32]), np.array([236, 196, 150])
    rgb = (lo + (hi - lo) * np.nan_to_num(gray01)[..., None]).astype("uint8")
    return np.dstack([rgb, np.where(valid, 255, 0).astype("uint8")])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dem", type=Path, help="DEM GeoTIFF downloaded from NASA Mars Trek")
    ap.add_argument("--ortho", type=Path, help="optional orthoimage GeoTIFF from Mars Trek for the basemap")
    ap.add_argument("--synthetic", action="store_true", help="build from a synthetic test crater instead")
    ap.add_argument("--name", default="Jezero Crater")
    ap.add_argument("--product", default="", help="Mars Trek product name, recorded in meta.json for citation")
    ap.add_argument("--res", type=float, default=25.0, help="cell size in metres (default 25)")
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("LONMIN", "LATMIN", "LONMAX", "LATMAX"))
    ap.add_argument("--max-cells", type=int, default=1200)
    ap.add_argument("--slope-limit", type=float, default=20.0)
    ap.add_argument("--svf-radius", type=float, default=1500.0)
    ap.add_argument("--azimuths", type=int, default=16)
    ap.add_argument("--shelters", type=int, default=12)
    ap.add_argument("--min-sep", type=float, default=700.0)
    ap.add_argument("--threshold", type=float, default=0.08)
    ap.add_argument("--habitat", type=float, nargs=2, metavar=("LON", "LAT"), help="habitat position (default: centre)")
    ap.add_argument("--out", type=Path, default=CACHE / MARS_DIR_NAME)
    args = ap.parse_args()

    if args.synthetic:
        args.dem = CACHE / "raw" / "synthetic_dem.tif"
        synthetic_raw(args.dem)
        args.name = "Synthetic test crater (not real Mars data)"
    elif not args.dem:
        ap.error("give --dem path/to/dem.tif or --synthetic")

    provenance = {}
    src_json = args.dem.parent / "source.json"
    if not args.synthetic and src_json.exists():
        provenance = json.loads(src_json.read_text())   # written by src.acquire.ctx_dtm
        args.product = args.product or provenance.get("item_id", "")

    elev, transform, crs, info = warp_to_local(args.dem, args.res, args.bbox)
    rows, cols = elev.shape
    if max(rows, cols) > args.max_cells:
        raise SystemExit(f"Grid would be {cols}x{rows}. Use a larger --res or a smaller --bbox "
                         f"(limit {args.max_cells} cells per side).")
    if np.isnan(elev).mean() > 0.3:
        print("Warning: more than 30% of the area has no elevation data. Consider a tighter --bbox.")
    print(f"Grid {cols} x {rows} at {args.res:g} m = {cols * args.res / 1000:.1f} x {rows * args.res / 1000:.1f} km")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    terrain = Terrain(elev, transform, crs)
    slope = terrain.slope_raster()

    print("Sky-view shielding (about a minute)...")
    shield = sky_view_shielding(elev, args.res, args.svf_radius, args.azimuths)

    write_cog(out / "dem.tif", elev, transform, crs)
    write_cog(out / "shielding.tif", shield, transform, crs)

    valid = np.isfinite(elev)
    if args.ortho:
        img, *_ = warp_to_local(args.ortho, args.res, grid=(transform, crs, cols, rows))
        lo, hi = np.nanpercentile(img, [2, 98])
        gray = np.clip((img - lo) / max(hi - lo, 1e-9), 0, 1)
        basemap_source = f"Orthoimage {args.ortho.name}"
    else:
        gray = hillshade(np.where(valid, elev, np.nanmean(elev)), args.res)
        basemap_source = "Hillshade computed from the DEM"
    Image.fromarray(dust_tint(gray, valid), "RGBA").save(out / "basemap.png", optimize=True)

    s = np.nan_to_num(shield)
    overlay = np.zeros((rows, cols, 4), dtype="uint8")
    overlay[..., 0], overlay[..., 1], overlay[..., 2] = 194, 38, 143
    overlay[..., 3] = (np.clip(s / 0.4, 0, 1) * 200).astype("uint8")
    Image.fromarray(overlay, "RGBA").save(out / "shielding.png", optimize=True)

    if args.habitat:
        hx, hy = terrain.lonlat_to_xy(*args.habitat)
    else:
        hx, hy = terrain.cell_center_xy(rows / 2 - 0.5, cols / 2 - 0.5)
    shelters = [{"id": "habitat", "name": "Habitat storm shelter", "type": "habitat",
                 "x": float(hx), "y": float(hy), "shielding": 1.0,
                 "note": "Assumed full storm shelter at a position chosen by the team."}]
    picked = pick_shelters(shield, slope, terrain.cell_center_xy, args.slope_limit, args.shelters,
                           args.min_sep, args.threshold)
    for i, p in enumerate(picked, start=1):
        shelters.append({"id": f"T{i}", "name": f"Terrain shelter T{i}", "type": "terrain", **p})
    for s_ in shelters:
        lon, lat = terrain.xy_to_lonlat(s_["x"], s_["y"])
        s_["lon"], s_["lat"] = round(float(lon), 6), round(float(lat), 6)
    (out / "shelters.json").write_text(json.dumps(shelters, indent=2))

    lon_c, lat_c = terrain.xy_to_lonlat(*terrain.cell_center_xy(rows / 2, cols / 2))
    meta = {
        "name": args.name,
        "synthetic": bool(args.synthetic),
        "width": cols, "height": rows, "res_m": args.res,
        "center_lonlat": [float(lon_c), float(lat_c)],
        "corners_lonlat": terrain.corners_lonlat(),
        "elevation_range_m": [float(np.nanmin(elev)), float(np.nanmax(elev))],
        "crs": crs.name,
        "source": {**info, "product": args.product or ("SYNTHETIC" if args.synthetic else "")},
        "provenance": provenance,
        "attribution": ("Synthetic test terrain" if args.synthetic else
                        f"Terrain: {provenance.get('dataset', 'NASA Mars Trek / PDS')} "
                        f"({args.product or info['file']})"),
        "basemap": basemap_source,
        "svf": {"radius_m": args.svf_radius, "azimuths": args.azimuths},
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Done: habitat + {len(picked)} terrain shelters -> {out}")


if __name__ == "__main__":
    main()
