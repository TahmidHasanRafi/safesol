"""End-to-end API checks against the committed demo fixture."""

from fastapi.testclient import TestClient

from src.api.main import DATA, app

client = TestClient(app)


def corner_route():
    (lon0, lat0), (lon1, _), _, (_, lat1) = DATA.meta["corners_lonlat"]
    a = [lon0 + (lon1 - lon0) * 0.2, lat0 + (lat1 - lat0) * 0.5]
    b = [lon0 + (lon1 - lon0) * 0.6, lat0 + (lat1 - lat0) * 0.5]
    return [a, b]


def test_meta_and_health():
    assert client.get("/api/health").json()["ok"]
    m = client.get("/api/meta").json()
    assert len(m["corners_lonlat"]) == 4 and "crewed" in m["presets"]


def test_analyze_route():
    r = client.post("/api/route/analyze", json={"points": corner_route()}).json()
    assert r["ok"] and r["status"] in ("PASS", "FAIL") and r["distance_m"] > 1000
    assert len(r["profile"]) > 10


def test_contingency_and_escape():
    pts = corner_route()
    c = client.post("/api/route/contingency", json={"points": pts}).json()
    assert "ok" in c
    e = client.post("/api/storm/escape", json={"position": pts[0], "warning_min": 30}).json()
    assert e["ok"] and e["mode"] in ("shelter", "spot", "none")
    assert e["zone"]["image"].startswith("data:image/png;base64,")


def test_route_outside_is_rejected():
    r = client.post("/api/route/analyze", json={"points": [[0, 0], [0.1, 0.1]]}).json()
    assert r["ok"] is False


def test_static_frontend_served():
    assert client.get("/").status_code == 200
