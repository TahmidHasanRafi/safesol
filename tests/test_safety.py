"""Safe stops and most exposed point on a straight synthetic route."""

import numpy as np

from src.compute.safety import route_safety


def test_safe_stops_and_most_exposed_point():
    pts = np.column_stack([np.arange(0, 10001, 100.0), np.zeros(101)])   # 10 km due east
    dist = pts[:, 0]
    shelters = [
        {"id": "habitat", "name": "Habitat", "type": "habitat", "x": 0.0, "y": 0.0, "shielding": 1.0},
        {"id": "T1", "name": "Wall", "type": "terrain", "x": 8000.0, "y": 500.0, "shielding": 0.3},
        {"id": "T2", "name": "Far", "type": "terrain", "x": 5000.0, "y": 4000.0, "shielding": 0.4},
    ]
    s = route_safety(pts, dist, shelters, stop_radius_m=1000)
    assert [x["id"] for x in s["safe_stops"]] == ["habitat", "T1"]        # T2 is 4 km off the route
    assert s["safe_stops"][1]["at_m"] == 8000 and s["safe_stops"][1]["off_route_m"] == 500
    # Farthest from any shelter: around x = 4 km, 4 km from the habitat and ~4.03 km from the wall
    me = s["most_exposed"]
    assert 3800 <= me["at_m"] <= 4100 and me["distance_m"] > 3900
