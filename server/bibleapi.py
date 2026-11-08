"""Verse of the day from API.Bible (the American Bible Society's service).

It has a free plan for non-commercial use. A key from your account goes in the API_BIBLE_KEY
environment variable (a Railway variable), never in the code. The service gives any passage you ask
for but has no "verse of the day", so the day's verse is picked from verse_refs.json by date, the
same one all day, and the text comes back in whichever translation the key can use.

What the key can use depends on the account: open-access Bibles (KJV and others) are free on every
plan; copyrighted ones (NIV, ESV, NLT and so on) are added from the account's dashboard.
Copyrighted text comes with a copyright notice, which the tile shows in small print.

"Translations to offer" (a setting) names the Bibles to put in the menu. Each name can be the Bible's
abbreviation (NLT), its short name as people say it (NIV, which finds "New International Version 2011"
when that is the only Bible whose name has those initials), or its Bible ID from the dashboard.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re

import requests

from sources import UA_BOT, Cached

BASE = "https://api.scripture.api.bible/v1"
REFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verse_refs.json")
POPULAR = ["NIV", "ESV", "NLT", "NKJV", "CSB", "NASB", "KJV", "WEB", "ASV"]     # listed first when no list is set

_bibles = Cached(24 * 3600)
_allowed: list = []


def key() -> str:
    return os.environ.get("API_BIBLE_KEY", "").strip()


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _initials(name: str) -> str:
    """'New International Version 2011' -> 'NIV' (words only; numbers and little words are skipped)."""
    return "".join(w[0] for w in re.findall(r"[A-Za-z]+", name or "") if w.lower() not in ("the", "of", "and")).upper()


def _get(path: str, params: dict | None = None):
    r = requests.get(BASE + path, params=params, timeout=20,
                     headers={"api-key": key(), "User-Agent": UA_BOT, "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise RuntimeError(f"API.Bible refused the key (HTTP {r.status_code}): {r.text[:100]}")
    if not r.ok:
        raise RuntimeError(f"API.Bible HTTP {r.status_code}: {r.text[:100]}")
    return r.json()


def bibles(force: bool = False) -> list:
    """The English Bibles this key can use: [{"id", "abbr", "name"}], refreshed daily. [] without a key."""
    if not key():
        return []

    def fetch():
        out, seen = [], set()
        for b in _get("/bibles", {"language": "eng"}).get("data", []):
            abbr = b.get("abbreviation") or b.get("abbreviationLocal") or ""
            if b.get("id") and abbr and b["id"] not in seen:
                seen.add(b["id"])
                out.append({"id": b["id"], "abbr": abbr, "name": b.get("nameLocal") or b.get("name") or abbr})
        if not out:
            raise RuntimeError("the key can use no English Bibles (add some in the API.Bible dashboard)")
        return out
    fetch.__name__ = "api_bible_list"
    return _bibles.get(fetch, force) or []


def cached_bibles() -> list:
    """What is already known, without making a request (safe to call from the settings page)."""
    return _bibles.value or []


def set_allowed(names) -> None:
    """The translations to offer, in the order to list them, from the settings page."""
    global _allowed
    if isinstance(names, str):
        names = names.split(",")
    _allowed = [str(n).strip() for n in (names or []) if str(n).strip()]


def _find(name: str, bl: list):
    """The Bible a name refers to: its abbreviation, its ID, or (only if exactly one Bible fits) the
    initials of its full name. None if nothing fits."""
    n = _norm(name)
    b = next((x for x in bl if _norm(x["abbr"]) == n), None)
    if b is None:
        b = next((x for x in bl if x["id"].lower() == name.strip().lower()), None)
    if b is None:
        cands = [x for x in bl if _initials(x["name"]) == n]
        if len(cands) == 1:
            b = cands[0]
    return b


def resolved(bl: list | None = None) -> list:
    """[(menu key, Bible)] for the menu: the 'translations to offer' that the key can use, in that order.
    If none of them match, everything the key can use, popular ones first, so there is always a choice."""
    bl = cached_bibles() if bl is None else bl
    out, seen = [], set()
    for a in _allowed:
        b = _find(a, bl)
        if b and b["id"] not in seen:
            seen.add(b["id"])
            out.append((b["abbr"] if a.strip().lower() == b["id"].lower() else a, b))
    if out:
        return out
    order = {_norm(a): i for i, a in enumerate(POPULAR)}
    return [(b["abbr"], b) for b in sorted(bl, key=lambda b: (order.get(_norm(b["abbr"]), 99), b["abbr"].upper()))]


def menu() -> dict:
    """{menu key: label} for the translation menu. Empty without a usable key."""
    return {k: f'{k} · {b["name"]}'[:60] for k, b in resolved()[:60]}


def diagnose() -> dict:
    """What the key can use, and which 'translations to offer' names matched nothing (with close matches
    to try). Makes no request, so it is safe to call from the settings page."""
    bl = cached_bibles()
    if not bl:
        return {}
    missing = []
    for a in _allowed:
        if _find(a, bl):
            continue
        n = _norm(a)
        similar = [f'{b["abbr"]} · {b["name"]} · ID {b["id"]}'[:90] for b in bl
                   if n in _norm(b["abbr"]) or _norm(b["abbr"]) in n or _initials(b["name"]).startswith(n)]
        missing.append({"asked": a, "similar": similar[:5]})
    return {"all": [f'{b["abbr"]} · {b["name"]} · ID {b["id"]}'[:90] for b in sorted(bl, key=lambda b: b["abbr"].upper())],
            "missing": missing}


def _verse_id(day: dt.date) -> str:
    with open(REFS_PATH, encoding="utf-8") as f:
        refs = json.load(f)
    return refs[day.toordinal() % len(refs)]["id"]


def verse_of_the_day(version: str, today: dt.date | None = None) -> dict:
    """{"text", "ref", "version", "copyright"} in the chosen translation, or raises with a plain reason."""
    if not key():
        raise RuntimeError("API_BIBLE_KEY is not set on the server")
    bl = bibles()
    if not bl:                              # say what actually went wrong (a refused key, no network...)
        raise RuntimeError(f"could not get the list of Bibles: {_bibles.error or 'no answer yet'}")
    ok = resolved(bl)
    want = _norm(version)
    hit = next(((k, b) for k, b in ok if _norm(k) == want), None)
    substituted = ""
    if hit is None:                         # a saved choice that is no longer on offer: use NIV if offered, else the first
        hit = next(((k, b) for k, b in ok if _norm(k) == "NIV"), ok[0])
        if any(_norm(a) == want for a in _allowed) and _find(version, bl) is None:
            substituted = (f"{version} is on your list but your API.Bible key has no Bible that matches it "
                           f"(see the list below), so {hit[0]} is shown instead")
        else:
            substituted = f"{version} is not on your list of translations, so {hit[0]} is shown instead"
    label, b = hit
    pid = _verse_id(today or dt.date.today())
    d = _get(f"/bibles/{b['id']}/passages/{pid}",
             {"content-type": "text", "include-notes": "false", "include-titles": "false",
              "include-chapter-numbers": "false", "include-verse-numbers": "false", "include-verse-spans": "false"}).get("data", {})
    raw = d.get("content") or ""
    raw = re.sub(r'<span[^>]*(?:class="v"|data-number)[^>]*>.*?</span>', " ", raw, flags=re.S)   # verse numbers, if any
    text = re.sub(r"<[^>]+>", " ", html.unescape(raw))
    text = re.sub(r"[¶¶]|\[\d+\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^\d+\s+(?=[A-Za-z“\"'])", "", text)           # a stray leading verse number
    text = text.strip()
    if not text:
        raise RuntimeError("API.Bible returned an empty passage")
    cr = re.sub(r"\s+", " ", html.unescape(d.get("copyright") or "")).strip()
    return {"text": text, "ref": d.get("reference") or pid, "version": label, "copyright": cr, "note_extra": substituted}
