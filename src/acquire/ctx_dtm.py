"""Download real Jezero terrain: a CTX digital terrain model and its orthoimage.

Source: NASA Mars Reconnaissance Orbiter Context Camera (CTX) stereo images, processed into
controlled DTMs by the USGS Astrogeology Science Center and published as Cloud Optimized
GeoTIFFs in the Astrogeology Analysis Ready Data STAC catalog. No login or API key needed.

    python -m src.acquire.ctx_dtm --list                 # show the DTMs covering Jezero
    python -m src.acquire.ctx_dtm                        # download the best one (20 x 20 km)
    python -m src.acquire.ctx_dtm --item <ITEM_ID>       # download a specific one
    python -m src.acquire.ctx_dtm --lon 77.45 --lat 18.45 --half-size-km 8

Only the requested window is downloaded (HTTP range requests), not the whole strip.
Writes cache/raw/jezero_dem.tif, cache/raw/jezero_ortho.tif and cache/raw/source.json,
then prints the command that prepares them for the app.
"""

from __future__ import annotations

import argparse
import json
import math

import requests

from src.config import CACHE

STAC_SEARCH = "https://stac.astrogeology.usgs.gov/api/search"
COLLECTION = "mro_ctx_controlled_usgs_dtms"
JEZERO = (77.58, 18.38)  # lon, lat (degrees east, planetocentric north)
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
            "GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_RETRY_DELAY": "2"}


# ---------- geometry helpers (no extra dependencies) ----------
def _ring_contains(ring, x, y):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(geometry, lon, lat) -> bool:
    if not geometry:
        return False
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry.get("coordinates", [])
    return any(_ring_contains([tuple(p[:2]) for p in poly[0]], lon, lat) for poly in polys)


def rank(features, lon, lat):
    """Footprints containing the point first, then those whose centre is closest to it."""
    def key(f):
        b = f.get("bbox") or [0, 0, 0, 0]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return (not contains(f.get("geometry"), lon, lat), math.hypot(cx - lon, cy - lat))
    return sorted(features, key=key)


# ---------- STAC ----------
def search(lon, lat, pad_deg=0.3, max_pages=5):
    params = {"collections": COLLECTION, "bbox": f"{lon - pad_deg},{lat - pad_deg},{lon + pad_deg},{lat + pad_deg}", "limit": 100}
    url, features = STAC_SEARCH, []
    for _ in range(max_pages):
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        page = r.json()
        features += page.get("features", [])
        nxt = next((l for l in page.get("links", []) if l.get("rel") == "next"), None)
        if not nxt:
            break
        url, params = nxt["href"], None
    return features


def asset(feature, *keys):
    assets = feature.get("assets", {})
    for k in keys:
        if k in assets and assets[k].get("href"):
            return assets[k]["href"]
    return None


# ---------- download a window ----------
def download_window(href, out_path, lon, lat, half_size_m):
    import rasterio
    from pyproj import CRS, Transformer
    from rasterio.windows import Window, from_bounds

    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        crs = CRS.from_wkt(src.crs.to_wkt())
        to_src = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        radius = crs.ellipsoid.semi_major_metre
        dlat = math.degrees(half_size_m / radius)
        dlon = dlat / math.cos(math.radians(lat))
        xs, ys = to_src.transform([lon - dlon, lon + dlon, lon - dlon, lon + dlon],
                                  [lat - dlat, lat - dlat, lat + dlat, lat + dlat])
        win = from_bounds(min(xs), min(ys), max(xs), max(ys), transform=src.transform)
        win = win.round_offsets().round_lengths()
        full = Window(0, 0, src.width, src.height)
        win = win.intersection(full)
        data = src.read(1, window=win)
        profile = src.profile.copy()
        profile.update(driver="GTiff", width=win.width, height=win.height,
                       transform=src.window_transform(win), tiled=True, blockxsize=256, blockysize=256,
                       compress="deflate")
        for k in ("photometric", "interleave"):
            profile.pop(k, None)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data, 1)
        return win.width, win.height, abs(src.transform.a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lon", type=float, default=JEZERO[0])
    ap.add_argument("--lat", type=float, default=JEZERO[1])
    ap.add_argument("--half-size-km", type=float, default=10.0, help="half the side of the square to download (default 10 km)")
    ap.add_argument("--item", help="STAC item id to use instead of the best match")
    ap.add_argument("--list", action="store_true", help="only list matching DTMs")
    ap.add_argument("--no-ortho", action="store_true", help="skip the orthoimage")
    args = ap.parse_args()

    print("Searching the USGS Astrogeology STAC catalog for CTX DTMs...")
    feats = rank(search(args.lon, args.lat), args.lon, args.lat)
    if not feats:
        raise SystemExit("No CTX DTMs found near that point. Try a different --lon/--lat.")

    for i, f in enumerate(feats[:15]):
        mark = "covers point" if contains(f.get("geometry"), args.lon, args.lat) else "nearby"
        print(f"  {i + 1:2d}. {f['id']}  ({mark})")
    if args.list:
        return

    chosen = next((f for f in feats if f["id"] == args.item), None) if args.item else feats[0]
    if chosen is None:
        raise SystemExit(f"Item {args.item} not found in the search results. Use --list to see the ids.")
    if not contains(chosen.get("geometry"), args.lon, args.lat):
        print("Warning: the chosen DTM does not cover the exact point; part of the area may be empty.")

    dtm = asset(chosen, "dtm")
    ortho = asset(chosen, "orthoimage")
    if not dtm:
        raise SystemExit(f"Item {chosen['id']} has no 'dtm' asset.")

    raw = CACHE / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    half = args.half_size_km * 1000
    print(f"Downloading DTM window from {chosen['id']} ...")
    w, h, px = download_window(dtm, raw / "jezero_dem.tif", args.lon, args.lat, half)
    print(f"  saved cache/raw/jezero_dem.tif ({w} x {h} px at {px:.1f} m)")
    have_ortho = False
    if ortho and not args.no_ortho:
        print("Downloading orthoimage window ...")
        w, h, px = download_window(ortho, raw / "jezero_ortho.tif", args.lon, args.lat, half)
        print(f"  saved cache/raw/jezero_ortho.tif ({w} x {h} px at {px:.1f} m)")
        have_ortho = True

    source = {
        "dataset": "MRO CTX controlled DTM (USGS Astrogeology Analysis Ready Data)",
        "collection": COLLECTION,
        "item_id": chosen["id"],
        "stac_search": STAC_SEARCH,
        "dtm_href": dtm,
        "orthoimage_href": ortho,
        "mission": "NASA Mars Reconnaissance Orbiter, Context Camera (CTX)",
        "center_lonlat": [args.lon, args.lat],
        "half_size_km": args.half_size_km,
    }
    (raw / "source.json").write_text(json.dumps(source, indent=2))

    cmd = 'python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --name "Jezero Crater"'
    if have_ortho:
        cmd += " --ortho cache/raw/jezero_ortho.tif"
    print("\nNext step, prepare the data for the app:\n  " + cmd)


if __name__ == "__main__":
    main()
