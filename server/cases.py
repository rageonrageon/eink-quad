"""Render every screen with live data to PNGs for eyeballing.
python3 cases.py  ->  case_*.png"""
import os, time
os.environ.setdefault("TZ", "America/New_York"); time.tzset()
import render as R, sources as S

CFG = {"lat": 27.9506, "lon": -82.4572, "feeds": ["world", "us", "markets"],
       "tickers": ["^GSPC", "^DJI", "^IXIC", "SOXL"], "teams": ["bucs", "lightning", "rays", "gators_fb", "gators_bb"],
       "slots": ["weather", "news", "sports", "lunch"]}
now = time.time()
wx = S.weather(CFG); heads = S.headlines(CFG); qs = S.quotes(CFG); teams, _ = S.sports(CFG)
base = dict(now=now, cfg=CFG, weather=wx, heads=heads, quotes=qs, teams=teams,
            brief="Treasury yields keep climbing as stocks slip; Rays open the ALDS Saturday and rain chances jump Thursday.",
            indoor_f=74.3, indoor_rh=52, updated=now, cycle=0)
cases = {
    "quad": R.Ctx(**base),
    "quad_message": R.Ctx(**base, sticky="Dinner at 7 — bring the charger!"),
}
for p in ("weather", "news", "sports"):
    cases["page_" + p] = R.Ctx(**base, page=p)
# a synthetic line on the first next game and a covered final, so both layouts are exercised
for r in teams:
    if r.next and r.next.odds is None and r.next.opp != "TBD":
        r.next.odds = S.Odds("DraftKings", f"{r.next.abbr} -3.5", -3.5, 44.5, -180, 150, 62)
        break
import logos
logos.prefetch([r.logo for r in teams] + [g.opp_logo for r in teams for g in (r.live, r.last, r.next) if g])
for k, ctx in cases.items():
    R.compose(ctx).save(f"case_{k}.png")
    if k in ("quad", "page_sports"):
        R.compose_gray(ctx).save(f"case_{k}_gray.png")
print("ok", list(cases))
