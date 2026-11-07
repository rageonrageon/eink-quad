"""School lunch menu: reads lunch.json and picks the days to show.

lunch.json maps an ISO date to either a list of main entrees (first is the
main one, the rest are the "or" alternatives), {"items": [...], "from":
"Godfather's"} for a catered day, or {"closed": "No School"}.
Months are just more keys, so add each new month's days to the same file.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("QUAD_LUNCH") or os.path.join(HERE, "lunch.json")


@dataclass
class LunchDay:
    date: dt.date
    items: list = field(default_factory=list)
    closed: str = ""
    source: str = ""         # restaurant for catered days, e.g. "Godfather's"
    weekend: bool = False
    label: str = ""          # TODAY / TOMORROW / MONDAY, filled in by upcoming()


def load(path: str = PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[lunch] cannot read {path}: {e}", flush=True)
        return {}
    days = {}
    for k, v in raw.items():
        try:
            d = dt.date.fromisoformat(k)
        except ValueError:
            continue
        if isinstance(v, dict) and isinstance(v.get("items"), list) and v["items"]:
            days[d] = LunchDay(d, items=[str(x) for x in v["items"]], source=str(v.get("from") or ""))
        elif isinstance(v, dict):
            days[d] = LunchDay(d, closed=str(v.get("closed") or "No School"))
        elif isinstance(v, list) and v:
            days[d] = LunchDay(d, items=[str(x) for x in v])
    return days


def days_from(now: float, n: int = 5, path: str = PATH) -> list:
    """n consecutive calendar days starting today, weekends included.

    Weekends come back blank (items empty, closed empty, weekend=True); a weekday
    with no data comes back blank too, so the caller can say the menu is missing."""
    days = load(path)
    today = dt.date.fromtimestamp(now)
    out = []
    for i in range(n):
        d = today + dt.timedelta(days=i)
        r = days.get(d) or LunchDay(d)
        r.weekend = d.weekday() >= 5
        r.label = "TODAY" if i == 0 else d.strftime("%a").upper()
        out.append(r)
    return out


def upcoming(now: float, n: int = 2, horizon_days: int = 14, path: str = PATH) -> list:
    """Today (menu or closure) then the next school day(s), up to n rows."""
    days = load(path)
    today = dt.date.fromtimestamp(now)
    rows = []
    if today in days:
        rows.append(days[today])
    for d in sorted(k for k in days if k > today):
        if len(rows) >= n or (d - today).days > horizon_days:
            break
        if not days[d].closed:
            rows.append(days[d])
    for r in rows:
        delta = (r.date - today).days
        r.label = "TODAY" if delta == 0 else "TOMORROW" if delta == 1 else r.date.strftime("%A").upper()
    return rows
