"""Verse of the day from API.Bible (the American Bible Society's service).

It has a free plan for non-commercial use. A key from your account goes in the API_BIBLE_KEY
environment variable (a Railway variable), never in the code. The service gives any passage you ask
for but has no "verse of the day", so the day's verse is picked from verse_refs.json by date, the
same one all day, and the text comes back in whichever translation the key can use.

What the key can use depends on the account: open-access Bibles (KJV and others) are free on every
plan; copyrighted ones (NIV, ESV, NLT and so on) are added from the account's dashboard.
Copyrighted text comes with a copyright notice, which the tile shows in small print.
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
POPULAR = ["NIV", "ESV", "NLT", "NKJV", "CSB", "NASB", "KJV", "WEB", "ASV"]     # listed first in the menu

_bibles = Cached(24 * 3600)


def key() -> str:
    return os.environ.get("API_BIBLE_KEY", "").strip()


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


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
            if b.get("id") and abbr and _norm(abbr) not in seen:
                seen.add(_norm(abbr))
                out.append({"id": b["id"], "abbr": abbr, "name": b.get("nameLocal") or b.get("name") or abbr})
        if not out:
            raise RuntimeError("the key can use no English Bibles (add some in the API.Bible dashboard)")
        return out
    fetch.__name__ = "api_bible_list"
    return _bibles.get(fetch, force) or []


def cached_bibles() -> list:
    """What is already known, without making a request (safe to call from the settings page)."""
    return _bibles.value or []


_allowed: list = []


def set_allowed(names) -> None:
    """The translations to offer (abbreviations, in the order to list them), from the settings page."""
    global _allowed
    if isinstance(names, str):
        names = names.split(",")
    _allowed = [str(n).strip() for n in (names or []) if str(n).strip()]


def usable(bl: list | None = None) -> list:
    """The key's Bibles limited to the allowed list, in that order. If none of the allowed names match
    what the key can use (a different abbreviation, say), everything the key can use, so there is always a choice."""
    bl = cached_bibles() if bl is None else bl
    if _allowed:
        order = {_norm(a): i for i, a in enumerate(_allowed)}
        picked = sorted((b for b in bl if _norm(b["abbr"]) in order), key=lambda b: order[_norm(b["abbr"])])
        if picked:
            return picked
    order = {_norm(a): i for i, a in enumerate(POPULAR)}
    return sorted(bl, key=lambda b: (order.get(_norm(b["abbr"]), 99), b["abbr"].upper()))


def menu() -> dict:
    """{abbreviation: label} for the translation menu. Empty without a usable key."""
    return {b["abbr"]: f'{b["abbr"]} · {b["name"]}'[:60] for b in usable()[:60]}


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
    want = _norm(version)
    ok = usable(bl)
    b = next((x for x in ok if _norm(x["abbr"]) == want), None)
    substituted = ""
    if b is None:                           # a saved choice that is no longer on offer: use NIV if offered, else the first
        b = next((x for x in ok if _norm(x["abbr"]) == "NIV"), ok[0])
        substituted = f"{version} is not on your list of translations, so {b['abbr']} is shown instead"
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
    return {"text": text, "ref": d.get("reference") or pid, "version": b["abbr"], "copyright": cr, "note_extra": substituted}
