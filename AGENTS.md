# AGENTS.md

Agents may: search catalogues (PDS, Treks), fetch data (Mars Trek, DONKI), orchestrate steps,
and explain or narrate results.
Agents may not: compute statistics, geometry, routing or physics themselves.
Call the functions in src/compute instead:
- src/compute/route.py      route sampling, slope, climb, time, energy, slope-limit check
- src/compute/pathfind.py   Dijkstra least-cost routes on the DEM
- src/compute/shielding.py  sky-view shielding index, terrain shelters
- src/compute/escape.py     solar storm escape plan
Every claim needs a source_url and a dataset_id.
SafeSol ships with no agent at runtime; this file applies to coding agents working on the repo.
