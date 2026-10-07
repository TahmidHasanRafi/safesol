"""Route maths against synthetic terrain with known answers."""

import math

import numpy as np
import pytest

from src.compute.route import Rover, analyze_route, sample_polyline
from src.compute.terrain import Terrain
from src.config import MARS_G

ROVER = Rover(mass_kg=900, speed_m_s=0.04, slope_limit_deg=20, base_power_w=120,
              energy_per_sol_wh=2000, drive_hours_per_sol=4)


def ramp(grade, cols=200, rows=10, res=1.0):
    """Elevation rises to the east: z = grade * x."""
    x = (np.arange(cols) + 0.5) * res
    return Terrain.from_array(np.tile(grade * x, (rows, 1)), res, origin_xy=(0.0, rows * res))


def test_sampling_keeps_both_ends():
    _, d = sample_polyline([(0, 0), (25, 0)], 10)
    assert d.tolist() == [0, 10, 20, 25]


def test_synthetic_ramp_slope_distance_climb():
    a = analyze_route(ramp(0.1), [(10, 5), (110, 5)], ROVER, 5)
    assert a["ok"] and a["status"] == "PASS"
    assert a["distance_m"] == pytest.approx(100)
    assert a["max_slope_deg"] == pytest.approx(math.degrees(math.atan(0.1)), abs=0.01)  # 5.71 deg
    assert a["total_climb_m"] == pytest.approx(10, abs=1e-6)


def test_flat_terrain_has_zero_slope():
    a = analyze_route(ramp(0.0), [(10, 5), (110, 5)], ROVER, 5)
    assert a["max_slope_deg"] == pytest.approx(0)


def test_downhill_adds_no_climb():
    a = analyze_route(ramp(0.1), [(110, 5), (10, 5)], ROVER, 5)
    assert a["total_climb_m"] == pytest.approx(0)


def test_slope_limit_failure_and_exceedance():
    rover = Rover(**{**ROVER.as_dict(), "slope_limit_deg": 5})
    a = analyze_route(ramp(0.1), [(10, 5), (110, 5)], rover, 5)
    assert a["status"] == "FAIL"
    assert a["worst"]["exceed_deg"] == pytest.approx(0.71, abs=0.01)


def test_time_and_energy_model():
    a = analyze_route(ramp(0.1), [(10, 5), (110, 5)], ROVER, 5)
    assert a["time_s"] == pytest.approx(2500)          # 100 m / 0.04 m/s
    expected_j = 120 * 2500 + 900 * MARS_G * 10
    assert a["energy_wh"] == pytest.approx(expected_j / 3600)


def test_route_outside_dem_is_rejected():
    a = analyze_route(ramp(0.1), [(10, 5), (400, 5)], ROVER, 5)
    assert a["ok"] is False


def test_lonlat_roundtrip():
    t = ramp(0.1)
    lon, lat = t.xy_to_lonlat(50.0, 5.0)
    x, y = t.lonlat_to_xy(lon, lat)
    assert (x, y) == pytest.approx((50.0, 5.0), abs=1e-6)
