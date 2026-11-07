"""Google Calendar (or any iCal feed) -> the calendar panel.

Point QUAD_ICAL_URL at a calendar's *secret address in iCal format*. The link is read
from the environment only (a Railway variable), so it never ends up in the code or the
repo. The feed is fetched at most every 15 minutes, and the last good copy is kept if
a fetch fails. Only calendar events are in such a feed; Google Tasks and Reminders are not.
"""
from __future__ import annotations

import datetime as dt
import os
import zoneinfo

import requests

import agenda
from sources import Cached

DEFAULT_TZ = "America/Chicago"
_cache = Cached(900)
_count = 0


def url() -> str:
    return os.environ.get("QUAD_ICAL_URL", "").strip()


def _fetch(feed_url: str, now: float, days: int) -> list:
    import icalendar
    import recurring_ical_events
    r = requests.get(feed_url, timeout=20, headers={"User-Agent": "quad-board"})
    r.raise_for_status()
    cal = icalendar.Calendar.from_ical(r.content)
    tz = zoneinfo.ZoneInfo(str(cal.get("X-WR-TIMEZONE") or DEFAULT_TZ))
    today = dt.datetime.fromtimestamp(now, tz).date()
    start = dt.datetime.combine(today, dt.time.min, tz)
    end = dt.datetime.combine(today + dt.timedelta(days=days + 1), dt.time.min, tz)
    out = []
    for e in recurring_ical_events.of(cal).between(start, end):
        if str(e.get("STATUS", "")).upper() == "CANCELLED":
            continue
        title = str(e.get("SUMMARY", "")).strip()
        s = e["DTSTART"].dt
        if not title:
            continue
        if isinstance(s, dt.datetime):
            local = s.astimezone(tz) if s.tzinfo else s
            d, t = local.date(), local.strftime("%H:%M")
        else:                                   # all-day; a multi-day one already under way shows as today
            d, t = max(s, today), ""
        out.append(agenda.Occurrence("g-" + str(e.get("UID", title))[:12], d, t, title, ""))
    return out


def upcoming(now: float, days: int = 14) -> list:
    """Occurrences from the feed, filtered the same way as the hand-entered events."""
    global _count
    u = url()
    if not u:
        return []

    def fetch():
        return _fetch(u, now, days + 1)
    fetch.__name__ = "ical"
    evs = _cache.get(fetch) or []
    _count = len(evs)
    n = dt.datetime.fromtimestamp(now)
    today, end = n.date(), n.date() + dt.timedelta(days=days)
    now_min = n.hour * 60 + n.minute
    keep = []
    for o in evs:
        if not (today <= o.date <= end):
            continue
        if o.date == today and o.time and int(o.time[:2]) * 60 + int(o.time[3:]) + 60 < now_min:
            continue
        keep.append(o)
    return keep


def status() -> dict:
    st = _cache.status()
    return {"configured": bool(url()), "age_s": st["age_s"], "error": st["error"], "count": _count}
