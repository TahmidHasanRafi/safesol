# SafeSol: Mars Traverse & Solar Storm Shelter Planner

**NASA Space Apps Challenge 2026 · Challenge: Interplanetary Survival Guide: Martian Map · Team Cosmic84, Bangladesh**

- **2026 challenge:** #11 Interplanetary Survival Guide: Martian Map (2026 NASA Space Apps Challenges)
- **Live demo:** https://cosmic84.tahmid-hasan-rafi.com
- **240-second video:** _add the YouTube / Drive link here_

SafeSol plans a drive across real Mars terrain and answers the question every surface crew will face:
*if a solar storm alert arrives right now, where do we go, and can we get there in time?*

- **Route planner.** Draw a route on Jezero Crater. SafeSol samples the elevation model along it and
  reports distance, driving time, energy, total climb and slope. Any stretch steeper than the vehicle's
  slope limit turns red on the map and on the elevation profile, with the exact segment and excess.
- **Survival card.** Distance, time, driving sols, energy per sol, climb, maximum slope, side-slope
  warning, pass or fail with the reason, the safe stops along the route, what to do if something fails
  (including the most exposed point and the nearest shelter from it), and every vehicle assumption used.
- **Contingency route.** Dijkstra's algorithm finds a route that stays under the slope limit, re-checked
  on the full-resolution terrain and compared side by side with the drawn route.
- **Solar storm shelter finder.** Replays a real Solar Energetic Particle event from NASA DONKI. One
  Dijkstra search gives the travel time to every place on the map; SafeSol draws the zone reachable
  before the warning runs out and sends the crew to the best-protected shelter inside it. If no shelter
  is reachable, it finds the best-protected spot within reach.
- **Terrain shelters from the DEM.** Crater walls and depressions that hide part of the sky are scored
  with a sky-view-factor shielding index computed from the elevation model.

- **Provenance drawer.** "Data sources and raw records" shows the NASA product id, file links, the selected
  DONKI event and the raw JSON behind the figures.

Every number comes from deterministic, unit-tested code in `src/compute`. No AI model runs in the app.

## Team Cosmic84 (Bangladesh)

| Name | Role |
|---|---|
| Tahamid Hasan Rafi | Team lead, development, data collection |
| Abdul Aziz | Communication, video, presentation and script |
| Syed Estyak Hossain | Development, Data collection |
| Hasnain Ahmed | Frontend |
| MD Hasibul Hasan Shanto | Data collection |
| Md Kamrul Hasan | Development |

## Architecture

```
CTX DTM (USGS STAC) ─► src/acquire/ctx_dtm.py ─► cache/raw/
cache/raw DEM       ──► src/acquire/dem.py ──► cache/mars/ (COG + overlays + shelters)
NASA DONKI SEP     ──► src/acquire/donki.py ─► cache/storms.json
                        (live → cache → demo_fixtures, via src/acquire/safe.py)
                                   │
                                   ▼
                     src/compute/  (deterministic science, pytest)
         route.py · pathfind.py (Dijkstra) · shielding.py · escape.py
                                   │
                                   ▼
                      src/api/main.py  (FastAPI, reads local data only)
                                   │
                                   ▼
             web/  (MapLibre GL + Chart.js, static, vendored, offline)
```

```
safesol/
├─ LICENSE                 Apache-2.0
├─ README.md
├─ CLAUDE.md / AGENTS.md   rules for coding agents
├─ .claude/skills/         project and challenge skill files
├─ .env.example            NASA_API_KEY, OFFLINE
├─ Makefile                make cache / make demo / make test
├─ cache/                  gitignored: downloaded and processed NASA data
├─ demo_fixtures/          committed: the exact data the demo needs
├─ deploy/                 systemd service and nginx config
├─ docs/                   AI_USE, ASSUMPTIONS, DATA_SOURCES, DEPLOY
├─ src/acquire/            safe.py (offline safety net), ctx_dtm.py, dem.py, donki.py
├─ src/compute/            terrain.py, route.py, pathfind.py, shielding.py, escape.py, safety.py
├─ src/api/                main.py (FastAPI)
├─ tests/                  pytest: synthetic ramp, Dijkstra, escape, safe stops, API
└─ web/                    index.html, app.js, style.css, vendor/
```

## Run it (VS Code or any terminal)

Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python -m pytest                                   # 17 tests
python -m uvicorn src.api.main:app --reload        # open http://127.0.0.1:8000
```

The repository ships with **real NASA data** in `demo_fixtures/`, so the app starts immediately after
`pip install`, with no network and no API key:

- `demo_fixtures/mars/`: a 20 × 20 km window of the MRO CTX controlled DTM and orthoimage over Jezero
  Crater at 25 m, with the derived shielding layer and terrain shelters.
- `demo_fixtures/storms.json`: 24 real Solar Energetic Particle events from NASA DONKI
  (September 2017 and May 2024); the unchanged API responses are in `demo_fixtures/donki_raw/`.

To rebuild that data from the original sources yourself:

```bash
# 1. Jezero terrain: CTX elevation model + orthoimage (NASA MRO data, USGS Astrogeology)
python -m src.acquire.ctx_dtm
python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --ortho cache/raw/jezero_ortho.tif --name "Jezero Crater"

# 2. Storm events from NASA DONKI (CCMC DONKI-API, no key needed)
python -m src.acquire.donki --start 2017-09-01 --end 2017-09-30

# 3. Copy the prepared data into demo_fixtures/ so the demo never needs the network
make fixtures            # or copy cache/mars/* to demo_fixtures/mars/ and cache/storms.json to demo_fixtures/
```

If `ccmc.gsfc.nasa.gov` is unreachable from your network, see [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
for how we fetched the DONKI responses and imported them with `--from-file`.

Data is read from `cache/` first, then `demo_fixtures/`. The header shows which one is in use.
Run the stage version with `OFFLINE=1` (`make demo`, or the "offline" launch configuration in VS Code).

Deploying on a VPS: [docs/DEPLOY.md](docs/DEPLOY.md).

## Method

| Step | Method | Code |
|---|---|---|
| Projection | DEM reprojected to a local equirectangular projection on the Mars sphere, so distances are true metres | `acquire/dem.py` |
| Route sampling | Polyline resampled every *s* metres (default 25 m), ends included | `compute/route.py` |
| Elevation | Bilinear interpolation; a route leaving the DEM is rejected, not calculated | `compute/terrain.py` |
| Slope | θ = atan(Δh / d); sign kept for the profile, absolute value checked against the limit | `compute/route.py` |
| Total climb | Sum of positive Δh only | `compute/route.py` |
| Time and energy | t = D / v; E = P_base · t + m · g_Mars · H_climb, in Wh and per driving sol | `compute/route.py` |
| Contingency route | Dijkstra, 8 neighbours, cost = time × (1 + slope / limit), steps over 80% of the limit blocked, re-checked on the full DEM | `compute/pathfind.py` |
| Shielding index | 1 − SVF, SVF = 1 − mean over 16 azimuths of sin(horizon angle), horizon to 1.5 km | `compute/shielding.py` |
| Storm escape | One Dijkstra search from the vehicle; reachable zone = time ≤ warning; best shelter = highest shielding in the zone | `compute/escape.py` |

Assumptions and limitations: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## NASA data

| Dataset | Used for |
|---|---|
| NASA Mars Reconnaissance Orbiter CTX controlled DTM, item `G14_023524_1985_XN_18N282W__G13_023379_1985_XN_18N282W` (USGS Astrogeology STAC; source images in the NASA PDS) | Elevation, slope, routing, shelter shielding |
| MRO CTX orthoimage, same item | Basemap |
| NASA DONKI Solar Energetic Particle events (CCMC DONKI-API) | Solar storm drill scenarios |

Dataset ids and citations: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Use of AI

[docs/AI_USE.md](docs/AI_USE.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
