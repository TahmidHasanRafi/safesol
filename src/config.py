"""Paths and settings shared by every layer."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"                 # gitignored: downloaded and processed NASA data
FIXTURES = ROOT / "demo_fixtures"      # committed: the exact bytes the demo needs
WEB = ROOT / "web"

MARS_DIR_NAME = "mars"                 # processed terrain lives in cache/mars/ or demo_fixtures/mars/
OFFLINE = os.getenv("OFFLINE") == "1"

# Mars sphere used by NASA/USGS equirectangular products (IAU 2000).
MARS_RADIUS_M = 3_396_190.0
MARS_G = 3.72  # m/s^2

# Routing grid is a block-averaged copy of the DEM, capped at this many cells per side.
ROUTING_MAX_CELLS = 450
# Automatic routes keep this fraction of the slope limit as their own limit.
PLANNING_MARGIN = 0.8


def terrain_dir() -> tuple[Path, str]:
    """cache/mars when it has been prepared, otherwise the committed fixture."""
    cached = CACHE / MARS_DIR_NAME
    if (cached / "meta.json").exists():
        return cached, "cache"
    return FIXTURES / MARS_DIR_NAME, "fixture"
