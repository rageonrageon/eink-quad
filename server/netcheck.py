"""Connectivity check: can this server actually reach a few websites?

Some sites turn away requests that come from cloud data centers (Railway, GitHub and so on),
even though the same address opens fine in a browser at home. This tries a short, fixed list of
addresses from the server itself and reports what came back, so we know before building
something that depends on a site. It runs once at startup and again when asked from the
settings page. Nothing here changes any setting or stores anything beyond the latest result.
"""
from __future__ import annotations

import re
import threading
import time

import requests

from sources import UA_BOT

_lock = threading.Lock()
_state = {"at": 0.0, "running": False, "results": []}

# TV Passport: each local station has a plain-text schedule page, and /YYYY-MM-DD on the end picks the day.
# The two Omaha stations that can carry a Sunday NFL game are CBS (KMTV) and FOX (KPTM).
TVP_STATIONS = {"CBS (KMTV) Omaha": "https://www.tvpassport.com/tv-listings/stations/cbs-kmtv-omaha-ne/1243",
                "FOX (KPTM) Omaha": "https://www.tvpassport.com/tv-listings/stations/fox-kptm-omaha-ne/1244"}
TARGETS = [
    # (label, address, what to look for)
    ("TV Passport schedule: CBS (KMTV) Omaha", TVP_STATIONS["CBS (KMTV) Omaha"], "tvp"),
    ("TV Passport schedule: FOX (KPTM) Omaha", TVP_STATIONS["FOX (KPTM) Omaha"], "tvp"),
    ("API.Bible (verse of the day)", "https://api.scripture.api.bible/v1/bibles", "apibible"),
    ("ESPN (for comparison, works today)", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", "text"),
]


def _try(label: str, url: str, kind: str) -> tuple:
    t0 = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": UA_BOT}, timeout=20)
    except requests.RequestException as e:
        return {"label": label, "url": url, "ok": False, "status": None, "ms": round((time.time() - t0) * 1000),
                "detail": f"{type(e).__name__}: {str(e)[:120]}"}, ""
    ms = round((time.time() - t0) * 1000)
    server = (r.headers.get("server") or "").strip()
    note = f"{len(r.content):,} bytes" + (f" · served by {server}" if server else "")
    ok = r.status_code == 200
    if not ok and r.status_code == 403:
        note = "refused (403 Forbidden)" + (f" · served by {server}" if server else "")
    elif not ok and r.status_code:
        note = f"HTTP {r.status_code}" + (f" · {note}" if note else "")
    return {"label": label, "url": url, "ok": ok, "status": r.status_code, "ms": ms, "detail": note}, (r.text if kind == "text" else "")


def _try_tvp(label: str, url: str) -> dict:
    """Read one station's schedule page and report the day it shows and how many NFL games are on it."""
    t0 = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": UA_BOT}, timeout=20)
    except requests.RequestException as e:
        return {"label": label, "url": url, "ok": False, "status": None, "ms": round((time.time() - t0) * 1000),
                "detail": f"{type(e).__name__}: {str(e)[:120]}"}
    ms = round((time.time() - t0) * 1000)
    server = (r.headers.get("server") or "").strip()
    if r.status_code != 200:
        why = "refused (403 Forbidden)" if r.status_code == 403 else f"HTTP {r.status_code}"
        return {"label": label, "url": url, "ok": False, "status": r.status_code, "ms": ms,
                "detail": why + (f" · served by {server}" if server else "")}
    day = re.search(r'caret-down"></i>\s*([^<]+?)\s*</span>', r.text)
    ok = "TV listings for" in r.text and day is not None
    nfl = r.text.count("NFL Football")
    return {"label": label, "url": url, "ok": ok, "status": 200, "ms": ms,
            "detail": (f"schedule for {day.group(1)}: {nfl} NFL game{'s' if nfl != 1 else ''} listed" if ok
                       else "answered, but it does not look like a schedule page (page changed?)")}


def _try_apibible(label: str, url: str) -> dict:
    """Ask without a key. A service that is reachable answers 'Missing API key' (401); a refusal is a block."""
    t0 = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": UA_BOT}, timeout=20)
    except requests.RequestException as e:
        return {"label": label, "url": url, "ok": False, "status": None, "ms": round((time.time() - t0) * 1000),
                "detail": f"{type(e).__name__}: {str(e)[:120]}"}
    ms = round((time.time() - t0) * 1000)
    if r.status_code == 401 and "key" in r.text.lower():
        return {"label": label, "url": url, "ok": True, "status": 401, "ms": ms, "detail": "reachable (it asks for a key, as expected)"}
    server = (r.headers.get("server") or "").strip()
    why = "refused (403 Forbidden)" if r.status_code == 403 else f"HTTP {r.status_code}"
    return {"label": label, "url": url, "ok": False, "status": r.status_code, "ms": ms,
            "detail": why + (f" · served by {server}" if server else "")}


def _run():
    results = []
    for label, url, kind in TARGETS:
        if kind == "apibible":
            results.append(_try_apibible(label, url))
        elif kind == "tvp":
            results.append(_try_tvp(label, url))
        else:
            results.append(_try(label, url, kind)[0])
    with _lock:
        _state.update(at=time.time(), running=False, results=results)


def run_async():
    """Start a check in the background (ignored if one is already running)."""
    with _lock:
        if _state["running"]:
            return
        _state["running"] = True
    threading.Thread(target=_run, daemon=True).start()


def snapshot() -> dict:
    with _lock:
        return {"at": _state["at"], "running": _state["running"], "results": [dict(r) for r in _state["results"]]}
