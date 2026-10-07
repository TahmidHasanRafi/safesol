---
name: challenge-11-martian-map
description: Build and maintain SafeSol for challenge 11, Interplanetary Survival Guide: Martian Map — a Mars traverse planner with a survival card and a solar storm shelter finder. Use for any change to routing, terrain, shelters or the storm drill.
license: Apache-2.0
---
# Challenge 11 — Interplanetary Survival Guide: Martian Map
Ask: interactive maps and survival tools for future Mars explorers.
Data: NASA MRO CTX controlled DTM + orthoimage for Jezero (USGS Astrogeology STAC), cached as a COG in
cache/mars/ and committed in demo_fixtures/mars/;
NASA DONKI SEP events in cache/storms.json.
Deterministic: route profile, slope limit, time and energy in src/compute/route.py;
Dijkstra in src/compute/pathfind.py; sky-view shielding in src/compute/shielding.py;
escape plan in src/compute/escape.py.
Killer demo: draw a route across the crater rim, watch it fail with the exact segment and excess;
suggest a safe route; trigger a replayed solar storm and watch the reachable zone and the path to
the best shelter appear; shorten the warning time until no shelter is reachable.
Cut when behind: drop the contingency route, then the shielding layer; keep draw -> profile ->
survival card -> storm escape.
