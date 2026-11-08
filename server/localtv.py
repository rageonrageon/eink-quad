"""Which of the family's games are on local (Omaha) broadcast TV?

ESPN only says a game is on "CBS" or "FOX", which is the national assignment. On a Sunday the
networks show different games in different cities, so a game can be "on CBS" and still not be on
the CBS station in Omaha. This asks the two Omaha stations' schedule pages (TV Passport has a
plain-text page per station and per day) whether the game is really there.

It runs on Saturday and Sunday mornings, not every hour, and saves its answers in a small file
so a restart does not lose them. A game's answer is one of:
    "CBS" / "FOX"  - found on that Omaha station
    "none"         - the station's page loaded and the game is not on it
    None           - could not tell (page unreadable or empty); nothing is claimed either way
Only games ESPN lists on CBS or FOX are checked; other networks are national, not regional.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import threading
import time

import requests

from sources import UA_BOT

PATH = os.environ.get("QUAD_TVLOCAL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "tv_local.json")

# network -> the Omaha station's schedule page (add /YYYY-MM-DD for a day)
STATIONS = {"CBS": "https://www.tvpassport.com/tv-listings/stations/cbs-kmtv-omaha-ne/1243",
            "FOX": "https://www.tvpassport.com/tv-listings/stations/fox-kptm-omaha-ne/1244"}
SPORT_WORDS = ("football", "basketball", "baseball", "hockey", "soccer")
_lock = threading.Lock()


def network(game) -> str:
    """'CBS' or 'FOX' if ESPN says the game is on one of them, else ''."""
    tv = (getattr(game, "tv", "") or "").upper()
    return "CBS" if tv.startswith("CBS") else "FOX" if tv.startswith("FOX") else ""


def _game_date(game) -> dt.date:
    import render                                   # for the US Central conversion
    return render.central(game.start).date()


def key(game) -> str:
    return f"{_game_date(game).isoformat()}|{game.our_full}|{game.opp_full}"


def _load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, PATH)


def lookup(game):
    """The saved answer for this game, or None if there isn't one (never checked, or unknown)."""
    if not (network(game) and game.our_full and game.opp_full):
        return None
    r = _load().get("games", {}).get(key(game))
    return r.get("result") if r else None


def ran_on(day: str) -> bool:
    return _load().get("day") == day


def _page_text(net: str, date: dt.date):
    """A station's plain schedule text for a day, or None if it could not be read as a schedule."""
    try:
        r = requests.get(f"{STATIONS[net]}/{date.isoformat()}", headers={"User-Agent": UA_BOT}, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code != 200 or "TV listings for" not in r.text:
        return None
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def on_page(text: str, a: str, b: str) -> bool:
    """Are both teams named close together, in a listing that is the game itself (a sport word just
    before them), and not in a studio show that merely talks about it?"""
    tl, a, b = text.lower(), a.lower(), b.lower()
    for name, other in ((a, b), (b, a)):
        i = tl.find(name)
        while i >= 0:
            near = tl[i + len(name): i + len(name) + 140]
            before = tl[max(0, i - 90): i]
            if other in near and any(w in before for w in SPORT_WORDS):
                return True
            i = tl.find(name, i + len(name))
    return False


def games_to_check(teams, now: float) -> list:
    """The family's next games on CBS or FOX that fall today or tomorrow (Central)."""
    import render
    today = render.central(now).date()
    out = []
    for r in teams or []:
        g = r.next
        if not g or not network(g) or not (g.our_full and g.opp_full):
            continue
        d = _game_date(g)
        if today <= d <= today + dt.timedelta(days=1):
            out.append(g)
    return out


def refresh(teams, now: float, when: str = "") -> dict:
    """Check every game due, save the answers, and return a summary."""
    games = games_to_check(teams, now)
    pages = {}
    for g in games:
        k = (network(g), _game_date(g))
        if k not in pages:
            pages[k] = _page_text(*k)
    results = {}
    for g in games:
        net, d = network(g), _game_date(g)
        text = pages[(net, d)]
        if text is None or not any(w in text.lower() for w in SPORT_WORDS):
            ans = None                                   # page missing or empty: do not claim anything
        else:
            ans = net if on_page(text, g.our_full, g.opp_full) else "none"
        results[key(g)] = {"label": f"{g.team} vs {g.opp_name}", "net": net, "date": d.isoformat(), "result": ans}
    out = {"at": now, "day": dt.datetime.fromtimestamp(now).strftime("%Y-%m-%d"), "when": when, "games": results}
    with _lock:
        _save(out)
    return {**out, "summary": summarize(out)}


def summarize(d: dict) -> str:
    games = d.get("games") or {}
    if not games:
        return "no CBS or FOX games for the family's teams today or tomorrow"
    bits = []
    for g in games.values():
        r = g.get("result")
        bits.append(f"{g['label']} ({g['net']}): " + (f"ON {r} in Omaha" if r in ("CBS", "FOX")
                                                    else "not on Omaha TV" if r == "none" else "could not tell"))
    return "; ".join(bits)


def summary() -> dict:
    d = _load()
    return {"at": d.get("at"), "when": d.get("when", ""), "day": d.get("day"), "summary": summarize(d) if d else ""}
