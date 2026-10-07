# CLAUDE.md

This is a NASA Space Apps 2026 project built at a Bangladesh Local Event.
Challenge 11: Interplanetary Survival Guide: Martian Map. Project: SafeSol.

## Non-negotiables
- Offline-first. Read from cache/. Wrap live calls with a fixture fallback (src/acquire/safe.py).
  Support OFFLINE=1.
- Deterministic science — statistics, geometry, routing, physics — lives in
  src/compute and is never performed by the model.
- Cite every dataset with an id and a URL.
- Record every AI tool and key prompt in docs/AI_USE.md.
- Apache-2.0 license. Public repository. No under-18 likenesses anywhere.

## Commands
- make cache   # pre-fetch every demo input (CTX DTM -> cache/raw -> cache/mars, DONKI -> cache/storms.json)
- make demo    # run the app with OFFLINE=1
- make test    # pytest for the science and the API

## Style
- Python: type hints, small pure functions in src/compute, pytest for the science.
- Frontend: no build step you cannot rerun on a laptop with no internet (web/ uses vendored MapLibre and Chart.js).
- Every vehicle assumption must stay visible in the interface.
