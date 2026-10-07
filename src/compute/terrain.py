"""Terrain: a DEM in a projected Mars CRS (metres), with Mars longitude/latitude conversion.

All distances and slopes are computed in the DEM's projected metres, never in degrees.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import CRS, Transformer

def apply(t: Affine, col, row):
    """Pixel (col, row) -> projected (x, y). Written out so it works on every affine version."""
    return t.a * col + t.b * row + t.c, t.d * col + t.e * row + t.f


# Equirectangular on the Mars IAU 2000 sphere: the projection used by Mars Trek / USGS products.
MARS_EQC = CRS.from_proj4("+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs")


@dataclass
class Terrain:
    elev: np.ndarray            # (rows, cols) float64, NaN = nodata, row 0 = north
    transform: Affine           # pixel -> projected metres
    crs: CRS
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.elev = np.asarray(self.elev, dtype="float64")
        self.res_x = abs(self.transform.a)
        self.res_y = abs(self.transform.e)
        self.res = (self.res_x + self.res_y) / 2
        geo = self.crs.geodetic_crs
        self._to_xy = Transformer.from_crs(geo, self.crs, always_xy=True)
        self._to_ll = Transformer.from_crs(self.crs, geo, always_xy=True)
        self._inv = ~self.transform

    # ---------- construction ----------
    @classmethod
    def load(cls, folder: Path) -> "Terrain":
        import rasterio

        with rasterio.open(folder / "dem.tif") as src:
            data = src.read(1, masked=True).astype("float64")
            elev = data.filled(np.nan)
            return cls(elev, src.transform, CRS.from_wkt(src.crs.to_wkt()),
                       json.loads((folder / "meta.json").read_text()))

    @classmethod
    def from_array(cls, elev, res, origin_xy=(0.0, 0.0), crs=MARS_EQC) -> "Terrain":
        """origin_xy is the top-left corner in projected metres."""
        x0, y0 = origin_xy
        return cls(np.asarray(elev, dtype="float64"), Affine(res, 0, x0, 0, -res, y0), crs)

    @property
    def shape(self):
        return self.elev.shape

    # ---------- coordinates ----------
    def lonlat_to_xy(self, lon, lat):
        return self._to_xy.transform(lon, lat)

    def xy_to_lonlat(self, x, y):
        return self._to_ll.transform(x, y)

    def xy_to_rowcol(self, x, y):
        """Fractional (row, col) of cell centres."""
        col, row = apply(self._inv, np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64"))
        return row - 0.5, col - 0.5

    def cell_center_xy(self, row, col):
        x, y = apply(self.transform, np.asarray(col) + 0.5, np.asarray(row) + 0.5)
        return x, y

    def corners_lonlat(self):
        """[top-left, top-right, bottom-right, bottom-left] as [lon, lat] — MapLibre image source order."""
        rows, cols = self.shape
        pts = [(0, 0), (cols, 0), (cols, rows), (0, rows)]
        out = []
        for c, r in pts:
            x, y = apply(self.transform, c, r)
            lon, lat = self.xy_to_lonlat(x, y)
            out.append([float(lon), float(lat)])
        return out

    # ---------- sampling ----------
    def sample(self, x, y):
        """Bilinear elevation at projected points. NaN outside coverage or next to nodata."""
        x = np.atleast_1d(np.asarray(x, dtype="float64"))
        y = np.atleast_1d(np.asarray(y, dtype="float64"))
        fr, fc = self.xy_to_rowcol(x, y)
        rows, cols = self.shape
        out = np.full(x.shape, np.nan)
        ok = (fr >= 0) & (fc >= 0) & (fr <= rows - 1) & (fc <= cols - 1)
        if not ok.any():
            return out
        r0 = np.floor(fr[ok]).astype(int)
        c0 = np.floor(fc[ok]).astype(int)
        r1 = np.minimum(r0 + 1, rows - 1)
        c1 = np.minimum(c0 + 1, cols - 1)
        ty = fr[ok] - r0
        tx = fc[ok] - c0
        e = self.elev
        top = e[r0, c0] * (1 - tx) + e[r0, c1] * tx
        bot = e[r1, c0] * (1 - tx) + e[r1, c1] * tx
        out[ok] = top * (1 - ty) + bot * ty
        return out

    def ground_slope(self, x, y):
        """Steepest slope in any direction (degrees) from central differences."""
        x = np.atleast_1d(np.asarray(x, dtype="float64"))
        y = np.atleast_1d(np.asarray(y, dtype="float64"))
        hx, hy = self.res_x, self.res_y
        dzdx = (self.sample(x + hx, y) - self.sample(x - hx, y)) / (2 * hx)
        dzdy = (self.sample(x, y + hy) - self.sample(x, y - hy)) / (2 * hy)
        return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))

    def slope_raster(self):
        gy, gx = np.gradient(self.elev, self.res_y, self.res_x)
        return np.degrees(np.arctan(np.hypot(gx, gy)))


def mars_distance_check(lon1, lat1, lon2, lat2):
    """Great-circle distance on the Mars sphere (m). Used only to sanity-check projected distances."""
    r = 3_396_190.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
