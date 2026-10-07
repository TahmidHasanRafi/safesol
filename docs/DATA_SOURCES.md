# NASA data sources

| Dataset | Dataset id | Source URL | Used for |
|---|---|---|---|
| MRO CTX controlled DTM, Jezero (USGS Astrogeology Analysis Ready Data) | STAC collection `mro_ctx_controlled_usgs_dtms`, item `G14_023524_1985_XN_18N282W__G13_023379_1985_XN_18N282W` | https://stac.astrogeology.usgs.gov/api/ | Elevation, slope, routing, shielding |
| MRO CTX orthoimage, same item | asset `orthoimage` of the item above | https://stac.astrogeology.usgs.gov/api/ | Basemap |
| MRO CTX source images (stereo pair) in the NASA Planetary Data System | `G14_023524_1985_XN_18N282W`, `G13_023379_1985_XN_18N282W` (CTX EDR product ids) | https://pds.nasa.gov/ (PDS Imaging Node) | Citable origin of the terrain model |
| DONKI Solar Energetic Particle events | `DONKI-API/get/SEP`, event ids in `demo_fixtures/storms.json` (Sep 2017, May 2024) | https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP | Storm drill scenarios |

The CTX images come from NASA's Mars Reconnaissance Orbiter Context Camera. The USGS Astrogeology
Science Center turns stereo pairs into controlled digital terrain models and publishes them as Cloud
Optimized GeoTIFFs (Astrogeology Analysis Ready Data). The exact item id, file links and download area
are saved in `cache/raw/source.json` and copied into `meta.json` under `provenance`.

## Getting the terrain (recommended)

```bash
python -m src.acquire.ctx_dtm --list     # see which DTMs cover Jezero
python -m src.acquire.ctx_dtm            # download a 20 x 20 km window of the best one
python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --ortho cache/raw/jezero_ortho.tif --name "Jezero Crater"
```

Only the requested window is downloaded. Use `--lon`, `--lat` and `--half-size-km` to move or resize it,
and `--item <id>` to pick a different DTM from the list.

## Alternative: NASA Mars Trek by hand

1. Open https://trek.nasa.gov/mars/ and search for Jezero.
2. Choose an elevation (DEM) layer covering the crater and note its exact name.
3. Export the area as a GeoTIFF and save it as `cache/raw/jezero_dem.tif`.
4. Run `python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --product "<layer name>"`.

## Storm events

```bash
python -m src.acquire.donki --start 2017-09-01 --end 2017-09-30
```

Since 30 September 2026 NASA's Community Coordinated Modeling Center serves the DONKI API at
`https://ccmc.gsfc.nasa.gov/DONKI-API/get/...` with no API key
([announcement](https://ccmc.gsfc.nasa.gov/news/major-updates/)). The script tries that first and falls back to
the older `https://api.nasa.gov/DONKI/SEP` gateway when you pass `--key`.

**How we obtained the storm data.** `ccmc.gsfc.nasa.gov` was unreachable from our networks in Bangladesh
(connection timed out from both a home connection and a Bangladesh-hosted server). The team therefore downloaded
the two monthly SEP responses from a temporary US-hosted server with the command below, copied the files to our
laptop and imported them unchanged with `--from-file`:

| File | Request | Events |
|---|---|---|
| `demo_fixtures/donki_raw/sep.json` | `DONKI-API/get/SEP?startDate=2017-09-01&endDate=2017-09-30` | 10 |
| `demo_fixtures/donki_raw/sep_2024.json` | `DONKI-API/get/SEP?startDate=2024-05-01&endDate=2024-05-31` | 14 |

The raw files are kept so anyone can compare them with a fresh request to the same URL.

If your network cannot reach `ccmc.gsfc.nasa.gov`, download the response on another machine (for example a VPS)
and import it:

```bash
curl -s "https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP?startDate=2017-09-01&endDate=2017-09-30" -o sep.json
python -m src.acquire.donki --from-file sep.json
```

## Other sources

- Mars Global Cave Candidate Catalog (USGS Astrogeology): checked for cave entrances in the region.
- Software: MapLibre GL JS (BSD-3-Clause), Chart.js (MIT), FastAPI, NumPy, SciPy, rasterio, pyproj, Pillow.
