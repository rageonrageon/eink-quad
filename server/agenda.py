"""The family calendar: a small list of events kept in a JSON file.

Events are added and removed from the settings page (no code or git needed). The
file lives next to config.json, so on Railway it sits on the /data volume and
survives redeploys.

Each event: {"id", "date": "YYYY-MM-DD", "time": "" or "HH:MM" (24h), "title",
"repeat": "" or "weekly"}.  A weekly event repeats on the same weekday from its date.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass

PATH = os.environ.get("QUAD_AGENDA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "agenda.json")
_lock = threading.Lock()


@dataclass
class Occurrence:
    id: str
    date: dt.date
    time: str          # "" for all-day, else "HH:MM"
    title: str
    repeat: str = ""

    @property
    def clock(self) -> str:
        if not self.time:
            return ""
        h, m = int(self.time[:2]), int(self.time[3:])
        return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def load(path: str | None = None) -> list:
    try:
        with open(path or PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [e for e in data if isinstance(e, dict) and e.get("id") and e.get("date")]
    except (OSError, ValueError):
        return []


def _save(events: list, path: str | None = None):
    p = path or PATH
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=1)
    os.replace(tmp, p)


def add(date: str, time: str, title: str, repeat: str = "", path: str | None = None) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("Give the event a title")
    try:
        dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("Pick a date")
    time = (time or "").strip()
    if time and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("Time should look like 08:00")
    ev = {"id": uuid.uuid4().hex[:8], "date": date, "time": time, "title": title[:80],
          "repeat": "weekly" if repeat == "weekly" else ""}
    with _lock:
        events = load(path)
        events.append(ev)
        _save(events, path)
    return ev


def delete(ev_id: str, path: str | None = None) -> bool:
    with _lock:
        events = load(path)
        keep = [e for e in events if e["id"] != ev_id]
        if len(keep) == len(events):
            return False
        _save(keep, path)
    return True


def listing(path: str | None = None) -> list:
    return sorted(load(path), key=lambda e: (e["date"], e.get("time") or ""))


def upcoming(now: float, days: int = 14, path: str | None = None) -> list:
    """Occurrences from now to `days` ahead, soonest first. An event that started
    more than an hour ago today is dropped."""
    n = dt.datetime.fromtimestamp(now)
    today, end = n.date(), n.date() + dt.timedelta(days=days)
    now_min = n.hour * 60 + n.minute
    out = []
    for e in load(path):
        try:
            d0 = dt.date.fromisoformat(e["date"])
        except ValueError:
            continue
        d = d0
        if e.get("repeat") == "weekly" and d0 < today:
            d = d0 + dt.timedelta(days=7 * -(-(today - d0).days // 7))
        while d <= end:
            if d >= today:
                t = e.get("time") or ""
                started_long_ago = d == today and t and int(t[:2]) * 60 + int(t[3:]) + 60 < now_min
                if not started_long_ago:
                    out.append(Occurrence(e["id"], d, t, e["title"], e.get("repeat", "")))
            if e.get("repeat") != "weekly":
                break
            d += dt.timedelta(days=7)
    out.sort(key=lambda o: (o.date, o.time or "00:00", o.title))
    return out
