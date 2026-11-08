"""Calendar feeds (iCal / .ics) -> the calendar and volleyball panels.

Each feed's link comes from an environment variable (a Railway variable), never from the
code or the repo, because these links are private:
    QUAD_ICAL_URL             family calendar (Google Calendar "secret address in iCal format")
    QUAD_ICAL_URL_VOLLEYBALL  the volleyball team feed (PlayMetrics "Sync Calendar" link)

A feed is fetched at most every 15 minutes and the last good copy is kept if a fetch
fails. Only calendar events are in such a feed; Google Tasks and Reminders are not.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import zoneinfo

import requests

import agenda
from sources import Cached

DEFAULT_TZ = "America/Chicago"
_GAME = re.compile(r"\b(vs\.?|v\.?|versus|game|match|scrimmage)\b|@", re.I)


def classify(title: str) -> str:
    """'game' | 'tournament' | 'practice' | '' from the event title (a best guess)."""
    t = title.lower()
    if "tournament" in t or "tourney" in t:
        return "tournament"
    if "practice" in t or "training" in t:
        return "practice"
    if _GAME.search(title):
        return "game"
    return ""


def _venue(loc: str) -> str:
    parts = [p.strip() for p in re.split(r",|\\,", loc) if p.strip()]
    if not parts:
        return ""
    if parts[0][:1].isdigit() and len(parts) > 1:      # a street address: keep the town too
        return f"{parts[0]}, {parts[1]}"
    return parts[0]


class Feed:
    def __init__(self, env: str, days: int):
        self.env, self.days = env, days
        self.cache = Cached(900)
        self.count = 0
        self.name = ""

    def url(self) -> str:
        return os.environ.get(self.env, "").strip()

    def _fetch(self, feed_url: str, now: float) -> list:
        import icalendar
        import recurring_ical_events
        r = requests.get(feed_url, timeout=20, headers={"User-Agent": "quad-board"})
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        tz = zoneinfo.ZoneInfo(str(cal.get("X-WR-TIMEZONE") or DEFAULT_TZ))
        self.name = str(cal.get("X-WR-CALNAME") or "")
        prefix = self.name + " - " if self.name else None
        today = dt.datetime.fromtimestamp(now, tz).date()
        start = dt.datetime.combine(today, dt.time.min, tz)
        end = dt.datetime.combine(today + dt.timedelta(days=self.days + 2), dt.time.min, tz)
        out = []
        for e in recurring_ical_events.of(cal).between(start, end):
            if str(e.get("STATUS", "")).upper() == "CANCELLED":
                continue
            title = str(e.get("SUMMARY", "")).strip()
            if prefix and title.startswith(prefix):       # "Power 14 - 2027 - Practice" -> "Practice"
                title = title[len(prefix):].strip()
            if not title:
                continue
            s = e["DTSTART"].dt
            if isinstance(s, dt.datetime):
                local = s.astimezone(tz) if s.tzinfo else s
                d, t = local.date(), local.strftime("%H:%M")
            else:                                   # all-day; a multi-day one already under way shows as today
                d, t = max(s, today), ""
            occ = agenda.Occurrence("g-" + str(e.get("UID", title))[:12], d, t, title, "")
            occ.place = _venue(str(e.get("LOCATION", "")))
            occ.kind = classify(title)
            out.append(occ)
        return out

    def upcoming(self, now: float) -> list:
        u = self.url()
        if not u:
            return []

        def fetch():
            return self._fetch(u, now)
        fetch.__name__ = "ical_" + self.env.lower()
        evs = self.cache.get(fetch) or []
        self.count = len(evs)
        n = dt.datetime.fromtimestamp(now)
        today, end = n.date(), n.date() + dt.timedelta(days=self.days)
        now_min = n.hour * 60 + n.minute
        keep = []
        for o in evs:
            if not (today <= o.date <= end):
                continue
            if o.date == today and o.time and int(o.time[:2]) * 60 + int(o.time[3:]) + 60 < now_min:
                continue
            keep.append(o)
        return keep

    def status(self) -> dict:
        st = self.cache.status()
        return {"configured": bool(self.url()), "age_s": st["age_s"], "error": st["error"],
                "count": self.count, "name": self.name}


CALENDAR = Feed("QUAD_ICAL_URL", days=14)
VOLLEYBALL = Feed("QUAD_ICAL_URL_VOLLEYBALL", days=60)     # games and tournaments are planned further out


def upcoming(now: float, days: int = 14) -> list:
    return CALENDAR.upcoming(now)


def status() -> dict:
    return CALENDAR.status()
