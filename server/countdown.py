"""Days-until countdowns: built-in holidays you can tick on or off, plus your own.

Everything is kept in countdowns.json next to config.json (on Railway that is the /data
volume, so it survives redeploys):
    {"holidays": ["thanksgiving", "christmas", ...],
     "items": [{"id", "name", "date": "YYYY-MM-DD", "end": "" or "YYYY-MM-DD", "yearly": bool}]}

A custom item with an end date (a school break) counts down to its start, then, while the
break is on, counts down to its end. Yearly items (birthdays) roll over by themselves; a
one-off item disappears once it is over.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from dataclasses import dataclass

PATH = os.environ.get("QUAD_COUNTDOWNS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "countdowns.json")
_lock = threading.Lock()
D = dt.date


def _nth(y, mo, wd, n):
    """n-th weekday (Mon=0) of a month."""
    d = D(y, mo, 1)
    return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return D(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)


# key -> (label, date in a given year). Listed in the order they appear on the settings page.
HOLIDAYS = {
    "newyear": ("New Year's Day", lambda y: D(y, 1, 1)),
    "valentines": ("Valentine's Day", lambda y: D(y, 2, 14)),
    "easter": ("Easter", _easter),
    "mothers": ("Mother's Day", lambda y: _nth(y, 5, 6, 2)),
    "fathers": ("Father's Day", lambda y: _nth(y, 6, 6, 3)),
    "july4": ("July 4th", lambda y: D(y, 7, 4)),
    "halloween": ("Halloween", lambda y: D(y, 10, 31)),
    "thanksgiving": ("Thanksgiving", lambda y: _nth(y, 11, 3, 4)),
    "christmas": ("Christmas", lambda y: D(y, 12, 25)),
}
DEFAULT_HOLIDAYS = ["thanksgiving", "christmas", "easter", "july4"]


@dataclass
class Item:
    name: str
    date: dt.date            # start
    end: dt.date | None      # last day, for a break
    number: int              # the big number: days to the start, or to the end while a break is on
    state: str               # future | today | now


def _load(path=None) -> dict:
    try:
        with open(path or PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict, path=None):
    p = path or PATH
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)


def settings(path=None) -> dict:
    d = _load(path)
    hol = d.get("holidays")
    hol = [h for h in hol if h in HOLIDAYS] if isinstance(hol, list) else list(DEFAULT_HOLIDAYS)
    items = [i for i in d.get("items", []) if isinstance(i, dict) and i.get("id")]
    return {"holidays": hol, "items": sorted(items, key=lambda i: i.get("date", "")),
            "all_holidays": {k: v[0] for k, v in HOLIDAYS.items()}}


def set_holidays(keys: list, path=None):
    with _lock:
        d = _load(path)
        d["holidays"] = [k for k in HOLIDAYS if k in keys]       # keep the page's order
        _save(d, path)


def add(name: str, date: str, end: str = "", yearly: bool = False, path=None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Give the countdown a name")
    try:
        start = D.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("Pick a date")
    end = (end or "").strip()
    if end:
        try:
            if D.fromisoformat(end) < start:
                raise ValueError("The end date is before the start date")
        except TypeError:
            raise ValueError("Bad end date")
    item = {"id": uuid.uuid4().hex[:8], "name": name[:40], "date": date, "end": end, "yearly": bool(yearly)}
    with _lock:
        d = _load(path)
        d.setdefault("items", []).append(item)
        _save(d, path)
    return item


def delete(item_id: str, path=None) -> bool:
    with _lock:
        d = _load(path)
        items = d.get("items", [])
        keep = [i for i in items if i.get("id") != item_id]
        if len(keep) == len(items):
            return False
        d["items"] = keep
        _save(d, path)
    return True


def _shift(d: dt.date, year: int) -> dt.date:
    try:
        return d.replace(year=year)
    except ValueError:                       # Feb 29 in a non-leap year
        return d.replace(year=year, day=28)


def upcoming(today: dt.date, path=None) -> list:
    """The countdowns to show, soonest first. Breaks that are on right now come first."""
    st = settings(path)
    out = []
    for key in st["holidays"]:
        label, fn = HOLIDAYS[key]
        d = fn(today.year)
        if d < today:
            d = fn(today.year + 1)
        out.append(Item(label, d, None, (d - today).days, "today" if d == today else "future"))
    for i in st["items"]:
        try:
            s0 = D.fromisoformat(i["date"])
            e0 = D.fromisoformat(i["end"]) if i.get("end") else None
        except ValueError:
            continue
        span = (e0 - s0) if e0 else None
        years = (today.year - 1, today.year, today.year + 1) if i.get("yearly") else (s0.year,)
        best = None
        for y in years:
            s = _shift(s0, y) if i.get("yearly") else s0
            e = (s + span) if span is not None else None
            if s >= today or (e is not None and s < today <= e):
                if best is None or s < best[0]:
                    best = (s, e)
        if best is None:
            continue
        s, e = best
        if s > today:
            out.append(Item(i["name"], s, e, (s - today).days, "future"))
        elif s == today:
            out.append(Item(i["name"], s, e, (e - today).days if e else 0, "today"))
        else:
            out.append(Item(i["name"], s, e, (e - today).days, "now"))
    out.sort(key=lambda x: (today if x.state != "future" else x.date, x.name))
    return out
