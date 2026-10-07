"""Every network fetch goes through here: live first, cache second, committed fixture last.

Matches the Build Guide's offline safety net. Set OFFLINE=1 to force cache/fixture mode.
"""

import hashlib
import json

import requests

from src.config import CACHE, FIXTURES, OFFLINE


def fetch_json(url, params=None, name=None, timeout=25):
    """Return (data, source) where source is "live", "cache" or "fixture". Never raises during a demo
    unless no copy of the data exists anywhere."""
    key = name or hashlib.md5(f"{url}{sorted((params or {}).items())}".encode()).hexdigest()
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / f"{key}.json"
    fixture = FIXTURES / f"{key}.json"
    if not OFFLINE:
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            cached.write_text(json.dumps(data))
            return data, "live"
        except Exception:
            pass
    if cached.exists():
        return json.loads(cached.read_text()), "cache"
    if fixture.exists():
        return json.loads(fixture.read_text()), "fixture"
    raise FileNotFoundError(f"No live, cache or fixture data for {key}")


def read_local_json(name):
    """Read cache/<name>.json, else demo_fixtures/<name>.json. Returns (data, source) or (None, None)."""
    for folder, label in ((CACHE, "cache"), (FIXTURES, "fixture")):
        path = folder / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text()), label
    return None, None
