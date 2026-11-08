"""Load a hearing-calendar PDF into the Hearing Calendar tile on the quad server.

The PDF is a Monday-Friday grid for each month. A day with any entry beyond its date number is a hearing
day. An entry is "9:00a" (phone or video) or "9:00a: <code>" where a code that starts with the in-person
prefix means in person. The prefix is given at run time (see below) and is deliberately not written into this
file, because the repository is public. Any other code is reported and counted as NOT in person, so nothing
is guessed.

Only dates and, per day, "any in person?" plus a hearing count are sent. The PDF's header text and
everything else in it stay on this computer. The server keeps the result on its private storage; nothing
goes into git.

    pip install pdfplumber requests
    set QUAD_URL=https://your-server.example.com     (no secret in it)
    set QUAD_ADMIN=your admin token                  (the value after ?k= on the settings page)
    set HEARING_IN_PERSON_PREFIX=the code prefix     (or pass --prefix; entries starting with it are in person)
    python import_hearings.py "path\\to\\calendar.pdf"            (shows what would change, asks first)
    python import_hearings.py "path\\to\\calendar.pdf" --dry-run  (only reads and prints)
    python import_hearings.py "path\\to\\calendar.pdf" --yes      (no question)

Each PDF is treated as the complete list of future hearings: sending one replaces the previous list.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
ENTRY = re.compile(r"^(\d{1,2}:\d{2}\s*[ap]m?)\s*(?::\s*(.+))?$", re.I)
IN_PERSON_PREFIX = ""          # set from --prefix or HEARING_IN_PERSON_PREFIX in main(); never stored in the repo


def parse(path: str):
    """-> ({iso date: {"in_person", "count", "other"}}, [problems])"""
    import pdfplumber
    days, problems = {}, []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            title = " ".join(c for t in tables[:1] for row in t for c in row if c)
            m = re.search(r"(%s)\s+(\d{4})" % "|".join(MONTHS), title)
            if not m or len(tables) < 2:
                problems.append(f"page {pno}: could not find a month and a calendar grid")
                continue
            month, year = MONTHS.index(m.group(1)) + 1, int(m.group(2))
            for row in tables[1][1:]:                                   # skip the MONDAY..FRIDAY header row
                for cell in row:
                    lines = [ln.strip() for ln in (cell or "").split("\n") if ln.strip()]
                    if not lines:
                        continue
                    if not re.fullmatch(r"\d{1,2}", lines[0]):
                        problems.append(f"page {pno}: a cell does not start with a day number: {lines[0][:30]!r}")
                        continue
                    entries = lines[1:]
                    if not entries:
                        continue                                        # only the date: no hearings that day
                    d = dt.date(year, month, int(lines[0]))
                    in_person, other, bad = classify(entries)
                    problems += [f"{d}: unrecognised entry {e!r}" for e in bad]
                    days[d.isoformat()] = {"in_person": in_person, "count": len(entries), "other": other}
    return dict(sorted(days.items())), problems


def classify(entries):
    """The entries of one day -> (any in person?, [other codes], [entries that could not be read])."""
    in_person, other, bad = False, [], []
    for e in entries:
        em = ENTRY.match(e)
        if not em:
            bad.append(e)
            continue
        code = (em.group(2) or "").strip()
        if IN_PERSON_PREFIX and code.upper().startswith(IN_PERSON_PREFIX.upper()):
            in_person = True
        elif code:
            other.append(code)
    return in_person, other, bad


def describe(days: dict) -> str:
    return "\n".join(f"  {dt.date.fromisoformat(k):%a %Y-%m-%d}  {v['count']} hearings  "
                     f"{'IN PERSON' if v['in_person'] else 'remote'}" + (f"  (other codes: {v['other']})" if v["other"] else "")
                     for k, v in days.items())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--dry-run", action="store_true", help="read the PDF and print, send nothing")
    ap.add_argument("--yes", action="store_true", help="do not ask before sending")
    ap.add_argument("--prefix", help="the code prefix that means in person (or set HEARING_IN_PERSON_PREFIX)")
    args = ap.parse_args()

    global IN_PERSON_PREFIX
    IN_PERSON_PREFIX = (args.prefix or os.environ.get("HEARING_IN_PERSON_PREFIX", "")).strip()
    if not IN_PERSON_PREFIX:
        print("Tell me which code prefix means in person: --prefix CODE or set HEARING_IN_PERSON_PREFIX.")
        return 2

    days, problems = parse(args.pdf)
    print(f"{len(days)} hearing days found:\n{describe(days)}")
    if problems:
        print("\nPROBLEMS (fix or check these before trusting the result):")
        for p in problems:
            print("  -", p)
    if any(v["other"] for v in days.values()):
        print("\nNOTE: some entries have a code that does not start with the in-person prefix; they are counted as NOT in person.")
    if args.dry_run or not days:
        return 0 if days else 1

    import requests
    url, key = os.environ.get("QUAD_URL", "").rstrip("/"), os.environ.get("QUAD_ADMIN", "")
    if not url or not key:
        print("\nSet QUAD_URL and QUAD_ADMIN first (see the top of this file).")
        return 2
    hdr = {"Authorization": f"Bearer {key}"}
    old = requests.get(url + "/api/hearings", headers=hdr, timeout=30)
    if old.status_code != 200:
        print(f"\nThe server did not accept the request (HTTP {old.status_code}). Check QUAD_URL and QUAD_ADMIN.")
        return 2
    before = old.json().get("days", {})
    added = sorted(set(days) - set(before))
    removed = sorted(set(before) - set(days))
    changed = sorted(k for k in set(days) & set(before) if days[k]["in_person"] != before[k].get("in_person"))
    print(f"\nCompared with what the server has now: {len(added)} added, {len(removed)} removed, "
          f"{len(changed)} changed between in person and remote.")
    for label, ks in (("added", added), ("removed", removed), ("changed", changed)):
        if ks:
            print(f"  {label}: " + ", ".join(ks))
    if not args.yes and input("\nSend this to the server? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing sent.")
        return 0
    r = requests.post(url + "/api/hearings", headers=hdr, json={"days": days}, timeout=30)
    if r.status_code != 200:
        print(f"The server refused it (HTTP {r.status_code}): {r.text[:200]}")
        return 2
    print(f"Done. The server now has {len(r.json().get('days', {}))} hearing days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
