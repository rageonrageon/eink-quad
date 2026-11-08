"""Hearing Calendar: the days that have hearings, and whether any of them is in person.

The data is private. It lives in hearings.json next to config.json (on Railway, the /data volume), it is
never committed to the repository (see .gitignore), and it is loaded by posting it to the server from the
importer in tools/import_hearings.py, not by pushing code. Only dates and two facts per day are kept:
    {"2030-01-15": {"in_person": true, "count": 5, "other": []}, ...}      (an example date, not real data)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from dataclasses import dataclass

PATH = os.environ.get("QUAD_HEARINGS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "hearings.json")
MAX_DAYS = 500
_lock = threading.Lock()


@dataclass
class Day:
    date: dt.date
    in_person: bool
    count: int


def load(path: str | None = None) -> dict:
    try:
        with open(path or PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def replace(days: dict, path: str | None = None) -> dict:
    """Validate and store a whole new schedule (each import is the full list of future hearings)."""
    if not isinstance(days, dict) or len(days) > MAX_DAYS:
        raise ValueError(f"expected a list of at most {MAX_DAYS} days")
    clean = {}
    for k, v in days.items():
        try:
            dt.date.fromisoformat(k)
        except (TypeError, ValueError):
            raise ValueError(f"not a date: {str(k)[:20]!r}")
        if not isinstance(v, dict) or not isinstance(v.get("in_person"), bool):
            raise ValueError(f"{k}: needs in_person true or false")
        count = v.get("count", 0)
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 100:
            raise ValueError(f"{k}: count must be a whole number")
        other = [str(c)[:30] for c in (v.get("other") or [])][:10]
        clean[k] = {"in_person": v["in_person"], "count": count, "other": other}
    clean = dict(sorted(clean.items()))
    p = path or PATH
    with _lock:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=1)
        os.replace(tmp, p)
    return clean


def upcoming(today: dt.date, n: int = 3, path: str | None = None) -> list:
    """The next n hearing days, today included."""
    out = []
    for k, v in sorted(load(path).items()):
        try:
            d = dt.date.fromisoformat(k)
        except ValueError:
            continue
        if d >= today:
            out.append(Day(d, bool(v.get("in_person")), int(v.get("count", 0))))
        if len(out) >= n:
            break
    return out


def summary(today: dt.date, path: str | None = None) -> dict:
    """What the settings page may show: counts and the next day, never the whole list."""
    data = load(path)
    future = [k for k in data if k >= today.isoformat()]
    nxt = upcoming(today, 1, path)
    return {"loaded": len(data), "future": len(future),
            "next": (f"{nxt[0].date:%a %b} {nxt[0].date.day} ({'in person' if nxt[0].in_person else 'remote'})" if nxt else "")}
