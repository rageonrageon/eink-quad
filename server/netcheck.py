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

PAGE = "https://506sports.com/nfl.php"
TARGETS = [
    # (label, address, what to look for)
    ("506sports.com (NFL maps page)", PAGE, "text"),
    ("506sports.com (a map image)", None, "image"),           # address read from the page above
    ("Bible Gateway (known to refuse cloud servers)", "https://www.biblegateway.com/votd/get/?format=json&version=NIV", "text"),
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
    if ok and kind == "image" and not (r.headers.get("content-type", "").startswith("image/")):
        ok, note = False, "answered, but it was not an image · " + note
    if not ok and r.status_code == 403:
        note = "refused (403 Forbidden)" + (f" · served by {server}" if server else "")
    elif not ok and r.status_code:
        note = f"HTTP {r.status_code}" + (f" · {note}" if note else "")
    return {"label": label, "url": url, "ok": ok, "status": r.status_code, "ms": ms, "detail": note}, (r.text if kind == "text" else "")


def _run():
    results, page_html = [], ""
    for label, url, kind in TARGETS:
        if url is None:                                        # the map image: find one on the page above
            m = re.search(r'src=["\'](20\d\d/[^"\']+\.png)["\']', page_html)
            if not m:
                results.append({"label": label, "url": "", "ok": False, "status": None, "ms": 0,
                                "detail": "skipped: could not read the page first"})
                continue
            url = "https://506sports.com/" + m.group(1)
        res, body = _try(label, url, kind)
        if url == PAGE:
            page_html = body
        results.append(res)
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
