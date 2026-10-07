"""Solar Energetic Particle (SEP) events from NASA DONKI.

    python -m src.acquire.donki --start 2017-09-01 --end 2017-09-30
    python -m src.acquire.donki --from-file sep.json      # a DONKI SEP response saved elsewhere

Since 30 September 2026 the DONKI API lives at https://ccmc.gsfc.nasa.gov/DONKI-API/get/...
and needs no API key. The previous CCMC host and the api.nasa.gov gateway (needs --key) are kept
as fallbacks. If your network cannot reach NASA, download the JSON on another machine (for example
your VPS) and import it with --from-file.

Writes cache/storms.json (merged across runs). Copy it to demo_fixtures/ with `make fixtures`.
DONKI detections come mostly from spacecraft near Earth; SafeSol replays them as Mars scenarios.
"""

import argparse
import json
import os

import requests

from src.config import CACHE

CCMC_URL = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/SEP"   # current official endpoint, no key
KAUAI_URL = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP"  # previous CCMC host, no key
LEGACY_URL = "https://api.nasa.gov/DONKI/SEP"              # older gateway, needs an API key


def normalise(raw, source_url):
    out = []
    for e in raw or []:
        if not e.get("sepID"):
            continue
        out.append({
            "id": e["sepID"],
            "time": e.get("eventTime"),
            "instruments": [i.get("displayName") for i in e.get("instruments") or [] if i.get("displayName")],
            "link": e.get("link"),
            "dataset": "NASA DONKI SEP",
            "source_url": source_url,
        })
    return out


def fetch(start, end, key, timeout):
    """Try the CCMC endpoint first, then the api.nasa.gov gateway. Returns (events, url used)."""
    attempts = [(CCMC_URL, {"startDate": start, "endDate": end}),
                (KAUAI_URL, {"startDate": start, "endDate": end})]
    if key:
        attempts.append((LEGACY_URL, {"startDate": start, "endDate": end, "api_key": key}))
    errors = []
    for url, params in attempts:
        try:
            print(f"Requesting {url} ...")
            r = requests.get(url, params=params, timeout=(20, timeout))  # 20 s to connect, then wait for data
            r.raise_for_status()
            data = r.json() if r.text.strip() else []
            if not isinstance(data, list):
                raise ValueError(f"unexpected response: {str(data)[:120]}")
            raw_dump = CACHE / f"donki_sep_{start}_{end}.json"
            raw_dump.write_text(json.dumps(data))
            return normalise(data, url), url
        except Exception as exc:  # network error, timeout, HTML page instead of JSON...
            errors.append(f"{url}: {exc}")
            print(f"  failed: {exc}")
    raise SystemExit("Could not reach DONKI.\n  " + "\n  ".join(errors) +
                     "\nCheck the link in a browser, try again later, or run this command on your VPS.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="YYYY-MM-DD")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--from-file", help="import a DONKI SEP JSON response saved on another machine")
    ap.add_argument("--key", default=os.getenv("NASA_API_KEY"), help="only needed for the api.nasa.gov fallback")
    ap.add_argument("--timeout", type=int, default=90, help="seconds to wait for each server (default 90)")
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    if args.from_file:
        raw = json.loads(open(args.from_file, encoding="utf-8-sig").read() or "[]")
        if not isinstance(raw, list):
            raise SystemExit("That file is not a DONKI SEP list. Save the raw response of /DONKI-API/get/SEP.")
        events, url = normalise(raw, CCMC_URL), args.from_file
    elif args.start and args.end:
        events, url = fetch(args.start, args.end, args.key, args.timeout)
    else:
        ap.error("give --start and --end, or --from-file")

    target = CACHE / "storms.json"
    existing = json.loads(target.read_text()) if target.exists() else []
    merged = {e["id"]: e for e in existing + events}
    result = sorted(merged.values(), key=lambda e: e.get("time") or "")
    target.write_text(json.dumps(result, indent=2))
    print(f"{len(events)} events from {url}; {len(result)} saved in {target}")


if __name__ == "__main__":
    main()