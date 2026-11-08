"""This day in history: events from Wikipedia's "On this day" feed, picked to suit a family
kitchen, two at a time, with no one needing to curate anything.

How an event is judged (all keyword rules, so a good guide and not a guarantee):
  1. MORBID  - anything about killing, dying, crime or disaster is always left out. War
               starting or ending is fine as long as the text is not about the killing.
  2. POLITICS - elections, governments and diplomacy are left out unless the "skip
               political events" setting is turned off.
  3. TIERS   - what is left is ranked: tech and inventions first, then culture and
               exploration, then anything else. The tile draws only from the best tier
               that has at least four events that day, so it favours tech without ever
               running dry.
Length is capped to fit three lines; a sparse date allows longer text (shortened on screen).
The word lists below are plain text and safe to edit.
"""
from __future__ import annotations

import datetime as dt
import html
import random
import re
import zlib

import requests

from sources import Cached, UA_BOT

MAX_CHARS = 140          # what fits in three lines of the tile
MIN_POOL = 6             # events to rotate through, at least
LONG_CHARS = 200         # allowed on a sparse date; the tile cuts it with an ellipsis

MORBID = re.compile(
    r"\b(kill\w*|death|deaths|dead|die|dies|died|dying|perish\w*|massacre\w*|murder\w*|assassin\w*|execut\w*|"
    r"genocide|slaughter\w*|victims?|casualt\w*|torture\w*|suicide|hostages?|lynch\w*|rape\w*|shoot\w*|shot|"
    r"hang\w*|hanged|gallows|wound\w*|injur\w*|fatal\w*|bod(?:y|ies)|remains|martyr\w*|persecut\w*|"
    r"drown\w*|sacrific\w*|cult|bloody|holocaust|concentration camps?|famine|plague|epidemic|pandemic|"
    r"virus|outbreak|disease|cancer|tumou?r|surgery|surgical|operation|"
    r"crash\w*|disaster|explosion|bomb\w*|terror\w*|attack\w*|wreck\w*|collapse\w*|sink\w*|sank|sunk|"
    r"fire|burn\w*|wildfire|flood\w*|tsunami|volcan\w*|eruption|landslide|avalanche|drought|"
    r"earthquake|hurricane|typhoon|tornado|cyclone|"
    r"kidnap\w*|abduct\w*|hijack\w*|ransom\w*|prison\w*|captur\w*|spy|spies|disappear\w*|vanish\w*|missing|"
    r"slave\w*|slavery|enslav\w*|racis\w*|segregat\w*|nuclear|atomic|radiation|inquisition|crusade\w*|"
    r"tragedy|tragic|riot\w*|mob|nazi\w*|battle\w*|siege\w*|defeat\w*|routed|offensive|bombard\w*|"
    r"repulse\w*|crushing|conquer\w*|occupied|occupation)\b", re.I)

POLITICS = re.compile(
    r"\b(elect\w*|president\w*|prime minister|parliament\w*|congress\w*|senat\w*|governor|campaign\w*|"
    r"vote\w*|voting|referendum|republican|democrat\w*|party|legislat\w*|constitution\w*|supreme court|"
    r"chancellor|minister|cabinet|politic\w*|monarch\w*|king|queen|throne|empire|council|commissar\w*|soviet|"
    r"bolshevik\w*|communist\w*|revolution\w*|rebel\w*|independence|viceroy|duke|emperor|tsar\w*|royal|"
    r"kingdom|dynasty|sovereign\w*|republic|government\w*|nation\w*|regime|dictator\w*|coup|"
    r"impeach\w*|resign\w*|scandal|sanction\w*|embargo|treaty|protest\w*|strike|strikes|arrest\w*|trial|"
    r"convict\w*|sentenc\w*|abolish\w*|annex\w*|currency|bankrupt\w*|crisis|exile\w*|deport\w*|expel\w*|"
    r"refugee\w*|colony|colonial|colonies|pope|bishop|diocese)\b", re.I)

# tier 1: tech and inventions
TECH = re.compile(
    r"\b(invent\w*|patent\w*|discover\w*|computer\w*|internet|website|web|online|software|program\w*|robot\w*|"
    r"digital|technolog\w*|satellite|space\w*|nasa|astronaut\w*|rocket|telescope|planet\w*|comet|asteroid|probe|"
    r"shuttle|orbit\w*|moon|mars|airplane|aircraft|aviation|jet|engine|electric\w*|battery|radio|telephone|"
    r"phone|television|tv|camera|photograph\w*|microscope|x-ray|laser|transistor|chip|semiconductor|"
    r"apple|microsoft|google|amazon|facebook|youtube|twitter|iphone|nintendo|sony|atari|video game|"
    r"locomotive|railway|steamship|skyscraper|bridge|tunnel|canal|dam|experiment\w*|scientist\w*|physic\w*|"
    r"chemi\w*|dna|genome|launch\w*|first flight|first successful|first powered)\b", re.I)

# tier 2: culture, sport and exploration
CULTURE = re.compile(
    r"\b(album|song|concert|film|movie|premiere\w*|debut\w*|novel|book|publish\w*|opera|symphony|ballet|"
    r"orchestra|museum|library|zoo|olympic\w*|world series|super bowl|championship|champion\w*|cartoon|comic|"
    r"toy|theatre|theater|painting|sculpture|nobel|prize|expedition|explor\w*|archaeolog\w*|dinosaur\w*|"
    r"fossil\w*|pyramid|tomb|summit|performed|released|first (?:ever|televised|performed|person|woman|man|time))\b",
    re.I)

_cache: dict[tuple, Cached] = {}


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(t or "")).strip()


def _fetch(month: int, day: int) -> list:
    r = requests.get(f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{month:02d}/{day:02d}",
                     headers={"User-Agent": UA_BOT}, timeout=15)
    r.raise_for_status()
    out, seen = [], set()
    for e in r.json().get("events", []):
        t = _clean(e.get("text"))
        if t and t not in seen and isinstance(e.get("year"), int):
            seen.add(t)
            out.append((e["year"], t))
    if not out:
        raise ValueError("no events returned")
    return out


def raw_events(date: dt.date, force: bool = False) -> list:
    c = _cache.setdefault((date.month, date.day), Cached(6 * 3600))

    def fetch():
        return _fetch(date.month, date.day)
    fetch.__name__ = f"history_{date.month:02d}{date.day:02d}"
    return c.get(fetch, force) or []


def tier(text: str) -> int:
    """1 = tech or invention, 2 = culture or exploration, 3 = anything else."""
    return 1 if TECH.search(text) else 2 if CULTURE.search(text) else 3


def candidates(events: list, skip_politics: bool = True) -> list:
    """The events the tile may draw from. Never morbid (or political, if skipped) and short
    enough; ranked tech first, then culture, then the rest. The pool is every tech and culture
    event plus just enough of the rest to reach MIN_POOL, so a day with little tech still leads
    with it. A sparse date allows longer text. Morbid and politics rules are never relaxed."""
    def clean(t, limit):
        return len(t) <= limit and not MORBID.search(t) and not (skip_politics and POLITICS.search(t))
    for limit in (MAX_CHARS, LONG_CHARS):
        ok = [(y, t) for y, t in events if clean(t, limit)]
        ok.sort(key=lambda e: (tier(e[1]), zlib.crc32(e[1].encode())))      # best tier first, then a stable shuffle
        good = sum(1 for _, t in ok if tier(t) <= 2)
        pool = ok[:max(MIN_POOL, good)]
        if len(pool) >= 4:
            return pool
    return [(y, t) for y, t in events if clean(t, LONG_CHARS)]


def pick(now: float, n: int = 2, skip_politics: bool = True, hours: int = 4) -> list:
    """n events for this moment: stable within a `hours`-hour block, different the next block,
    and the same on every restart. [{"year", "text"}] (maybe fewer than n)."""
    date = dt.date.fromtimestamp(now)
    cands = candidates(raw_events(date), skip_politics)
    if not cands:
        return []
    random.Random(date.toordinal()).shuffle(cands)           # the day's own order
    block = int(now // (hours * 3600))
    start = (block * n) % len(cands)
    chosen = [cands[(start + i) % len(cands)] for i in range(min(n, len(cands)))]
    chosen.sort(key=lambda e: -e[0])                         # newest first
    return [{"year": y, "text": t} for y, t in chosen]


def status() -> dict:
    cs = list(_cache.values())
    if not cs:
        return {"age_s": None, "error": None}
    c = max(cs, key=lambda c: c.at)
    return c.status()
