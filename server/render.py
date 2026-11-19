"""Draws the board. Pure functions of data -> PIL images; no I/O here.

Everything is drawn on an 8-bit "L" canvas and thresholded to 1-bit at the
very end. Text uses FreeType's monochrome rasteriser (fontmode "1"), which is
hinted for exactly this and is much crisper than thresholding anti-aliased
glyphs. Icons are drawn 4x oversize and shrunk, so their edges are smooth
before the threshold.

Layout (800x480):
    header    y 0..38     date | sticky message | indoor + updated time
    strip     y 38..66    Claude's one-line brief (or a weather alert)
    grid      y 66..480   2x2 slots, each 400x207; any panel in any slot
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H = 800, 480
HEAD_H = 38
STRIP_H = 28
GRID_Y = HEAD_H + STRIP_H
CELL_W, CELL_H = W // 2, (H - GRID_Y) // 2      # 400 x 207
BODY = (W, H - GRID_Y)                            # detail pages: 800 x 414

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
INK, PAPER = 0, 255

_fonts = {}


def F(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _fonts:
        path = os.path.join(FONT_DIR, {
            "r": "Barlow-Regular.ttf", "m": "Barlow-Medium.ttf", "sb": "Barlow-SemiBold.ttf",
            "b": "Barlow-Bold.ttf", "cr": "BarlowCondensed-Regular.ttf", "cm": "BarlowCondensed-Medium.ttf",
            "csb": "BarlowCondensed-SemiBold.ttf", "cb": "BarlowCondensed-Bold.ttf",
            "hand": "PatrickHand-Regular.ttf",
        }[name])
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


# True while rendering the 4-level grey version: text is anti-aliased then,
# because the panel can actually show the in-between shades.
AA = False


def canvas(size):
    img = Image.new("L", size, PAPER)
    d = ImageDraw.Draw(img)
    d.fontmode = "L" if AA else "1"
    return img, d


def tw(d, s, f):
    return d.textlength(s, font=f)


def text(d, xy, s, f, fill=INK, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def ellipsize(d, s, f, width):
    if tw(d, s, f) <= width:
        return s
    while s and tw(d, s + "…", f) > width:
        s = s[:-1]
    return s.rstrip(" ,.;:-") + "…"


def wrap(d, s, f, width, max_lines):
    words = s.split()
    lines, cur = [], ""
    for i, w in enumerate(words):
        t = (cur + " " + w).strip()
        if tw(d, t, f) <= width:
            cur = t
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    used = " ".join(lines).split()
    if len(used) < len(words):
        lines[-1] = ellipsize(d, lines[-1] + " " + words[len(used)] + "…", f, width)
        if not lines[-1].endswith("…"):
            lines[-1] += "…"
    return lines


def fit_font(d, s, name, width, sizes):
    for sz in sizes:
        f = F(name, sz)
        if tw(d, s, f) <= width:
            return f
    return F(name, sizes[-1])


def to1(img: Image.Image, invert=False) -> Image.Image:
    out = img.point(lambda v: 255 if v >= 128 else 0).convert("1")
    if invert:
        out = ImageChops.invert(out)
    return out


def pill(d, x, y, s, f, pad=5, fill=INK, fg=PAPER, h=None):
    """Inverted label. Returns right edge."""
    wd = tw(d, s, f)
    asc, desc = f.getmetrics()
    hh = h or (asc + desc // 2 + 2)
    d.rounded_rectangle((x, y, x + wd + 2 * pad, y + hh), radius=4, fill=fill)
    d.text((x + pad, y + hh / 2), s, font=f, fill=fg, anchor="lm")
    return x + wd + 2 * pad


def dotted(d, x0, x1, y, step=4):
    for x in range(int(x0), int(x1), step):
        d.point((x, y), fill=INK)


def tri(d, x, y, size, up, fill=INK):
    if up:
        d.polygon([(x, y + size), (x + size, y + size), (x + size / 2, y)], fill=fill)
    else:
        d.polygon([(x, y), (x + size, y), (x + size / 2, y + size)], fill=fill)


# ------------------------------------------------------------------ icons

_icon_cache = {}


def icon(kind: str, size: int, night=False) -> Image.Image:
    key = (kind, size, night)
    if key in _icon_cache:
        return _icon_cache[key]
    S = size * 4
    img = Image.new("L", (S, S), PAPER)
    d = ImageDraw.Draw(img)
    lw = max(4, S // 22)

    def sun(cx, cy, r, rays=True):
        if night:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
            o = r * 0.55
            d.ellipse((cx - r + o, cy - r - o * 0.3, cx + r + o, cy + r - o * 0.3), fill=PAPER)
            return
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
        if rays:
            for i in range(8):
                a = i * math.pi / 4
                r0, r1 = r * 1.35, r * 1.8
                d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a),
                        cx + r1 * math.cos(a), cy + r1 * math.sin(a)), fill=INK, width=lw)

    def cloud(x0, y0, x1, y1, fill=PAPER):
        w, h = x1 - x0, y1 - y0
        parts = [(x0, y0 + h * 0.45, x0 + w * 0.45, y1),
                 (x0 + w * 0.2, y0 + h * 0.15, x0 + w * 0.65, y0 + h * 0.85),
                 (x0 + w * 0.45, y0, x1 - w * 0.05, y0 + h * 0.85),
                 (x1 - w * 0.4, y0 + h * 0.4, x1, y1)]
        base = (x0 + w * 0.2, y0 + h * 0.6, x1 - w * 0.2, y1)
        for (a, b, c, e) in parts:
            d.ellipse((a - lw, b - lw, c + lw, e + lw), fill=INK)
        d.rectangle((base[0], base[1] - lw, base[2], base[3] + lw), fill=INK)
        for (a, b, c, e) in parts:
            d.ellipse((a, b, c, e), fill=fill)
        d.rectangle(base, fill=fill)

    if kind == "sun":
        sun(S / 2, S / 2, S * 0.22)
    elif kind == "partly":
        sun(S * 0.36, S * 0.36, S * 0.17)
        cloud(S * 0.22, S * 0.38, S * 0.96, S * 0.84)
    elif kind in ("cloud", "fog"):
        cloud(S * 0.06, S * 0.2, S * 0.94, S * 0.74)
        if kind == "fog":
            for i, y in enumerate((0.82, 0.93)):
                d.line((S * (0.12 + 0.08 * i), S * y, S * (0.88 - 0.08 * i), S * y), fill=INK, width=lw)
    elif kind in ("rain", "showers", "storm", "snow"):
        if kind == "showers":
            sun(S * 0.33, S * 0.3, S * 0.15)
        cloud(S * 0.08, S * 0.12, S * 0.92, S * 0.62)
        if kind == "storm":
            d.polygon([(S * .52, S * .6), (S * .36, S * .82), (S * .5, S * .82), (S * .42, S * .99),
                       (S * .66, S * .74), (S * .52, S * .74), (S * .6, S * .6)], fill=INK)
        elif kind == "snow":
            for (x, y) in ((.3, .76), (.5, .86), (.7, .76), (.4, .96), (.6, .96)):
                r = S * 0.04
                d.ellipse((S * x - r, S * y - r, S * x + r, S * y + r), fill=INK)
        else:
            for x in (0.3, 0.5, 0.7):
                d.line((S * x, S * 0.7, S * (x - 0.07), S * 0.92), fill=INK, width=lw + 2)
    out = img.resize((size, size), Image.LANCZOS)
    _icon_cache[key] = out
    return out


def paste_icon(c, kind, x, y, size, night=False):
    ic = icon(kind, size, night)
    c.paste(ImageChops.darker(c.crop((x, y, x + size, y + size)), ic), (x, y))


def paste_logo(c, url, x, y, size, cfg=None):
    """Team logo, or False if we have none (caller falls back to text).
    Grey render keeps its shading; the 1-bit render gets it dithered so the
    fast partial updates still show a logo rather than a blob."""
    if cfg is not None and not cfg.get("sports_logos", True):
        return False
    import logos
    img = logos.get(url, size)
    if img is None:
        return False
    if not AA:
        img = img.convert("1").convert("L")
    x, y = int(x), int(y)
    c.paste(ImageChops.darker(c.crop((x, y, x + size, y + size)), img), (x, y))
    return True


# ------------------------------------------------------------------ helpers for time

def hm(ts, ampm=True):
    t = time.localtime(ts)
    s = f"{t.tm_hour % 12 or 12}:{t.tm_min:02d}"
    return s + (" AM" if t.tm_hour < 12 else " PM") if ampm else s


def when(ts, tbd=False):
    """Friendly game time: 'Tonight 7:00', 'Tomorrow 1:00 PM', 'Sun 1:00 PM', 'Oct 12'."""
    now = time.localtime()
    t = time.localtime(ts)
    days = (time.mktime(t[:3] + (0, 0, 0, 0, 0, -1)) - time.mktime(now[:3] + (0, 0, 0, 0, 0, -1))) / 86400
    days = round(days)
    clock = "" if tbd else " " + hm(ts)
    if days == 0:
        return ("Tonight" if t.tm_hour >= 17 else "Today") + (clock if not tbd else " · time TBD")
    if days == 1:
        return "Tomorrow" + clock
    if 1 < days < 7:
        return time.strftime("%a", t) + clock
    return time.strftime("%b ", t) + str(t.tm_mday) + clock


def ago(ts):
    m = int((time.time() - ts) // 60)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    return f"{m // 60}h {m % 60:02d}m ago"


# ================================================================== panels

@dataclass
class Ctx:
    """Everything a frame needs. Built by app.py; render never fetches."""
    now: float
    cfg: dict
    weather: object = None
    heads: list = field(default_factory=list)
    quotes: list = field(default_factory=list)
    teams: list = field(default_factory=list)
    brief: str = ""
    sticky: str = ""
    indoor_f: float | None = None
    indoor_rh: float | None = None
    battery: int | None = None
    on_usb: bool = True
    cycle: int = 0                # increments every scheduled update (rotations)
    updated: float = 0.0
    page: str = "quad"
    notes_new: int = 0
    stale: dict = field(default_factory=dict)
    lunch: list = field(default_factory=list)    # lunch.LunchDay rows
    lunch_week: list = field(default_factory=list)   # 5 consecutive days from today
    activities: dict = field(default_factory=dict)   # {date: [("8:00 AM", "Volleyball practice"), ...]}
    agenda: list = field(default_factory=list)       # agenda.Occurrence rows for the calendar panel
    volleyball: list = field(default_factory=list)   # agenda.Occurrence rows from the volleyball feed
    volleyball_name: str = ""                        # the team calendar's own name, e.g. "Power 14 - 2027"
    volleyball_on: bool = False                      # is a volleyball feed configured at all
    countdowns: list = field(default_factory=list)   # countdown.Item rows, soonest first
    hearings: list = field(default_factory=list)     # hearings.Day rows: the next hearing days
    todos: list = field(default_factory=list)        # todo.Item rows: open tasks, in the order added
    smart_step: int = 0                              # which of the SMART tile's panels is up (see panel_smart)
    verse: dict | None = None                        # {"text", "ref", "version"} from sources.votd
    history: list = field(default_factory=list)      # [{"year", "text"}] from history.pick


def _deg(v):
    return f"{v:.0f}°"


WIND = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def panel_weather(ctx: Ctx, size):
    from sources import wmo
    c, d = canvas(size)
    w, h = size
    wx = ctx.weather
    if wx is None:
        text(d, (w / 2, h / 2), "Weather unavailable", F("m", 18), anchor="mm")
        return c
    y0 = 8
    if wx.alerts:
        ev = wx.alerts[0][0].upper()
        more = f" +{len(wx.alerts) - 1}" if len(wx.alerts) > 1 else ""
        d.rectangle((0, 0, w, 26), fill=INK)
        tri(d, 10, 5, 15, True, fill=PAPER)
        d.text((18, 16), "!", font=F("b", 11), fill=INK, anchor="mm")
        text(d, (34, 13), ellipsize(d, ev + more, F("csb", 19), w - 44), F("csb", 19), fill=PAPER, anchor="lm")
        y0 = 32
    desc, kind = wmo(wx.code)
    night = not wx.is_day and kind in ("sun", "partly")
    isz = 76 if y0 < 20 else 64
    paste_icon(c, kind, 10, y0 + 2, isz, night)
    big = F("sb", 66 if y0 < 20 else 56)
    tx = 16 + isz
    text(d, (tx, y0 - 8), _deg(wx.temp), big)
    today = wx.days[0] if wx.days else None
    cy = y0 + (66 if y0 < 20 else 56)
    # description with "Feels" beside it, then a big HIGH / LOW row in the space under them
    feels = f"Feels {_deg(wx.feels)}"
    fdesc, ffeels = F("sb", 19), F("m", 16)
    if tw(d, desc, fdesc) + 12 + tw(d, feels, ffeels) > 214:          # a long description: a touch smaller
        fdesc = F("sb", 17)
    text(d, (14, cy + 6), ellipsize(d, desc, fdesc, 214 - 12 - tw(d, feels, ffeels)), fdesc)
    text(d, (14 + min(tw(d, desc, fdesc), 214 - 12 - tw(d, feels, ffeels)) + 12, cy + 9), feels, ffeels)
    if today and not (wx.alerts and wx.rain_note):                     # (an alert banner plus a rain pill leaves no room, as before)
        sz = 22 if wx.rain_note else 30                                # smaller when the rain pill needs the room under it
        ry = cy + (26 if wx.rain_note else 28)
        x = 14
        for lab, val in (("HIGH", f"{today.hi:.0f}°"), ("LOW", f"{today.lo:.0f}°")):
            text(d, (x, ry + sz * 0.5), lab, F("cb", 15), anchor="lm")
            x += tw(d, lab, F("cb", 15)) + 5
            text(d, (x, ry + sz * 0.5), val, F("b", sz), anchor="lm")
            x += tw(d, val, F("b", sz)) + 18

    # right column of small facts
    rx = 238
    facts = []                         # (today's rain % is the chart below)
    facts.append(("Wind", f"{WIND[int((wx.wind_dir + 22.5) // 45) % 8]} {wx.wind:.0f}"
                  + (f"–{wx.gust:.0f}" if wx.gust - wx.wind >= 8 else "")))
    facts.append(("Humid", f"{wx.humidity}%"))
    if today and today.sunset:
        # after sunset, show tomorrow's sunrise instead
        tm = time.localtime(ctx.now)
        if tm.tm_hour >= 12:
            facts.append(("Sunset", today.sunset.replace(" PM", "p").replace(" AM", "a")))
        else:
            facts.append(("Sunrise", today.sunrise.replace(" AM", "a").replace(" PM", "p")))
    fy = y0 + 2
    for k, v in facts[:2 if wx.alerts else 3]:
        text(d, (rx, fy), k, F("cm", 16))
        text(d, (w - 12, fy), v, F("csb", 18), anchor="ra")
        dotted(d, rx + tw(d, k, F("cm", 16)) + 5, w - 14 - tw(d, v, F("csb", 18)) - 4, fy + 14)
        fy += 23
    # rain: nowcast pill under "Feels" + next-12h chance-of-rain bars under the facts column.
    # Both live in fixed space, so the 3-day row never moves (the pill used to push it off the bottom).
    top = h - 56                       # 3-day row
    if wx.rain_note:
        f = F("csb", 17)
        py = cy + 30 if wx.alerts else cy + 50   # under an alert banner the pill replaces "Feels"
        pill(d, 12, py, ellipsize(d, wx.rain_note, f, rx - 34), f, h=21)
    _rain_bars(d, wx.hourly, ctx.now, rx, w - 12, fy + 4, top - 7)
    # 3-day row
    days = wx.days[1:4]
    if days:
        d.line((10, top - 4, w - 10, top - 4), fill=INK, width=1)
        cw = (w - 20) / len(days)
        for i, day in enumerate(days):
            x = 10 + i * cw
            t = time.strptime(day.date, "%Y-%m-%d")
            dn, dk = wmo(day.code)
            text(d, (x + 4, top), time.strftime("%a", t).upper(), F("cb", 18))
            text(d, (x + cw - 8, top + 2), f"{day.pop}%", F("cm", 16), anchor="ra")
            paste_icon(c, dk, int(x + 4), int(top + 21), 32)
            hs = f"{day.hi:.0f}°"
            text(d, (x + 44, top + 24), hs, F("sb", 20))
            text(d, (x + 44 + tw(d, hs, F("sb", 20)) + 4, top + 28), f"{day.lo:.0f}°", F("m", 16))
            if i:
                d.line((x - 2, top + 4, x - 2, h - 6), fill=INK, width=1)
    return c


def _rain_bars(d, hourly, now, x0, x1, y0, y1):
    """Next 12 hours of precipitation probability as bars, 50% dotted guide, hour ticks every 3h."""
    hrs = [hh for hh in hourly if hh[0] >= now - 1800][:12]
    if len(hrs) < 2 or x1 - x0 < 60:
        return
    fl = F("cm", 13)
    by1 = y1 - 13                      # bar baseline; hour labels below it
    bh = by1 - y0 - 13                 # headroom above for the peak label
    n = len(hrs)
    cw = (x1 - x0) / n
    dotted(d, x0, x1, int(by1 - bh / 2), 3)
    d.line((x0, by1, x1, by1), fill=INK)
    peak = max(range(n), key=lambda i: hrs[i][2])
    for i, (ts, _, pop, _) in enumerate(hrs):
        bx = x0 + i * cw
        hgt = pop / 100 * bh
        if hgt >= 1:
            d.rectangle((bx + 1, by1 - hgt, bx + cw - 2, by1), fill=INK)
        if i % 3 == 0:
            lt = time.localtime(ts)
            lab = "now" if i == 0 else f"{lt.tm_hour % 12 or 12}{'a' if lt.tm_hour < 12 else 'p'}"
            text(d, (bx + 1, by1 + 1), lab, fl)
    pk = hrs[peak][2]
    if pk >= 10:
        # label the peak just above its bar
        px = x0 + peak * cw + cw / 2
        s = f"{pk}%"
        hgt = pk / 100 * bh
        lx = min(max(px, x0 + tw(d, s, fl) / 2), x1 - tw(d, s, fl) / 2)
        text(d, (lx, by1 - hgt - 2), s, fl, anchor="md")


def _quote_cell(d, x, y, cw, q, spark_h=0, c=None):
    fname = F("cm", 15)
    text(d, (x + cw / 2, y), ellipsize(d, q.name, fname, cw - 4), fname, anchor="ma")
    pct = q.chg_pct
    s = f"{abs(pct):.2f}%"
    f = F("cb", 20)
    wv = tw(d, s, f) + 13
    sx = x + (cw - wv) / 2
    if abs(pct) >= 0.005:
        tri(d, sx, y + 23, 9, pct > 0)
    text(d, (sx + 13, y + 17), s, f)
    p = q.price
    ps = f"{p:,.0f}" if p >= 1000 else f"{p:,.2f}"
    text(d, (x + cw / 2, y + 40), ps, F("cr", 15), anchor="ma")
    if spark_h and q.spark and len(q.spark) > 2:
        sy0, sy1 = y + 60, y + 60 + spark_h
        lo, hi = min(q.spark + [q.prev]), max(q.spark + [q.prev])
        rng = (hi - lo) or 1
        n = 78   # a full session is 78 five-minute bars

        def P(i, v):
            return (x + 6 + (cw - 12) * i / (n - 1), sy1 - (v - lo) / rng * (sy1 - sy0))
        py = P(0, q.prev)[1]
        dotted(d, x + 6, x + cw - 6, py, 3)
        d.line([P(i, v) for i, v in enumerate(q.spark[:n])], fill=INK, width=2)


def panel_news(ctx: Ctx, size):
    c, d = canvas(size)
    w, h = size
    y = 6
    qs = ctx.quotes[:6]
    if qs:
        cw = w / len(qs)
        for i, q in enumerate(qs):
            _quote_cell(d, i * cw, y, cw, q)
            if i:
                d.line((i * cw, y + 2, i * cw, y + 54), fill=INK, width=1)
        y += 60
        d.line((8, y, w - 8, y), fill=INK, width=2)
        y += 7
    heads = ctx.heads
    f = F("m", 17)
    lh = 19
    if not heads:
        text(d, (w / 2, (y + h) / 2), "No headlines", F("m", 17), anchor="mm")
        return c
    # rotate through the list, one page per scheduled update
    avail = h - y + 2
    pages, cur, used = [], [], 0
    for hd in heads[:30]:
        lines = wrap(d, hd.title, f, w - 34, 2)
        need = len(lines) * lh + 5
        if used + need > avail and cur:
            pages.append(cur)
            cur, used = [], 0
        cur.append(lines)
        used += need
    if cur:
        pages.append(cur)
    pages = pages[:ctx.cfg.get("news_pages", 4)]
    pg = pages[ctx.cycle % len(pages)]
    for lines in pg:
        d.rectangle((12, y + 7, 18, y + 13), fill=INK)
        for ln in lines:
            text(d, (28, y), ln, f)
            y += lh
        y += 5
    # page dots
    if len(pages) > 1 and not qs:
        cx = w - 12 - (len(pages) - 1) * 10
        dy = 63 if qs else 6
        d.rectangle((cx - 8, dy - 5, w - 4, dy + 5), fill=PAPER)
        for i in range(len(pages)):
            r = 3
            box = (cx + i * 10 - r, dy - r, cx + i * 10 + r, dy + r)
            if i == ctx.cycle % len(pages):
                d.ellipse(box, fill=INK)
            else:
                d.ellipse(box, outline=INK)
    return c


def _odds_bits(g, abbr, cfg, sport, full=False):
    o = g.odds if g else None
    if not o or not cfg.get("odds", True):
        return []
    style = cfg.get("odds_style", "spread")
    main = o.line(abbr, style, sport)
    bits = [main]
    if full:
        if o.ml_us is not None and f"{o.ml_us:+d}" not in main:
            bits.append(f"ML {o.ml_us:+d}")
        if o.win_pct is not None and "to win" not in main:
            bits.append(f"{o.win_pct}% to win")
    if o.total:
        bits.append(f"O/U {o.total:g}")
    return bits


def _sport(r):
    import sources
    return sources.TEAMS.get(r.key, ("", ""))[1]


def _team_lines(r, cfg=None):
    """(badge, primary, secondary) for one TeamRow."""
    cfg = cfg or {}

    def score(g):
        return f"{g.us}–{g.them}"

    def vs(g, name=True):
        who = g.opp_name if name else g.opp
        rk = f"#{g.opp_rank} " if g.opp_rank else ""
        return ("vs " if g.home else "at ") + rk + who
    if r.live:
        g = r.live
        bits = [g.detail] + ([g.tv] if g.tv else []) + _odds_bits(g, g.abbr, cfg, _sport(r))[:1]
        return "LIVE", f"{score(g)} {vs(g)}", " · ".join(bits)
    if r.fresh_result:
        g = r.last
        bits = []
        if g.ats and cfg.get("odds", True):
            bits.append(f"{g.ats} {g.odds.spread_us:+g}".replace("+0", "PK")
                        if _sport(r) not in ("hockey", "baseball") else ("won as " if g.result == "W" else "lost as ")
                        + ("fav" if (g.odds.ml_us or 0) < 0 else "dog"))
        if r.next:
            bits.append("Next: " + when(r.next.start, r.next.time_tbd) + " " + vs(r.next, False))
        elif g.note:
            bits.append(g.note)
        return g.result, f"{score(g)} {vs(g)}", " · ".join(bits)
    if r.next:
        g = r.next
        prim = when(g.start, g.time_tbd) + " " + vs(g)
        bits = []
        if g.note:
            bits.append(g.note.replace(" - ", " "))
        if g.tv:
            bits.append(g.tv)
        odds = _odds_bits(g, g.abbr, cfg, _sport(r))
        bits += odds
        if r.last and not g.note and not odds:
            bits.append(f"last {r.last.result} {score(r.last)} {r.last.opp}")
        return None, prim, " · ".join(bits)
    return None, "No games scheduled", ""


def central(ts):
    """A game's start in US Central (CST/CDT), whatever the server's own TZ is."""
    import datetime as dt
    u = dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None)

    def nth_sunday(month, n):
        d = dt.datetime(u.year, month, 1)
        return d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    dst_on = nth_sunday(3, 2) + dt.timedelta(hours=8)     # 2:00 CST, 2nd Sunday of March
    dst_off = nth_sunday(11, 1) + dt.timedelta(hours=7)   # 2:00 CDT, 1st Sunday of November
    return u + dt.timedelta(hours=-5 if dst_on <= u < dst_off else -6)


def _ct_when(g):
    """'Sun 3:25 PM CT' (adds the date when the game is more than a week out)."""
    t = central(g.start)
    day = t.strftime("%a") + (f" {t:%b} {t.day}" if g.start - time.time() > 6 * 86400 else "")
    if g.time_tbd:
        return day + " · time TBD"
    return f"{day} {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'} CT"


def _sports_narrow(ctx: Ctx, size):
    """Compact sports block for a third-width cell: logo vs/at logo, records under the
    logos, then game time (Central), then TV and spread. Two teams per page."""
    c, d = canvas(size)
    w, h = size
    teams = ctx.teams
    if not teams:
        text(d, (w / 2, h / 2), "No games in the next few weeks", F("m", 16), anchor="mm")
        return c
    per = 2 if h >= 150 else 1
    pages = [teams[i:i + per] for i in range(0, len(teams), per)]
    pg = pages[ctx.cycle % len(pages)]
    bh = (h - 6) / per
    L = 40 if bh >= 104 else 36
    cx = w / 2
    off = min(66, w / 2 - L / 2 - 8)          # logo centres sit this far either side of the middle
    for i, r in enumerate(pg):
        y = 3 + i * bh
        g = r.live or (r.last if r.fresh_result else None) or r.next
        if g is None:
            text(d, (cx, y + bh / 2), f"{r.label}: no games scheduled", F("m", 16), anchor="mm")
        else:
            for url, abbr, mid in ((r.logo, g.abbr, cx - off), (g.opp_logo, g.opp, cx + off)):
                if not paste_logo(c, url, mid - L / 2, y + 2, L, ctx.cfg):
                    text(d, (mid, y + 2 + L / 2), abbr, F("cb", 24), anchor="mm")
            text(d, (cx, y + 2 + L / 2), "vs" if g.home else "at", F("sb", 20), anchor="mm")
            ry = y + L + 3
            if r.record:
                text(d, (cx - off, ry), r.record, F("cm", 14), anchor="ma")
            if g.opp_record:
                text(d, (cx + off, ry), g.opp_record, F("cm", 14), anchor="ma")
            ly = ry + 17
            odds = _odds_bits(g, g.abbr, ctx.cfg, _sport(r))[:1]
            tvline = " · ".join(([g.tv] if g.tv else []) + odds)
            if r.live:
                l3 = f"LIVE {g.us}–{g.them} · {g.detail}"
            elif g is r.last:
                l3 = f"{g.result} {g.us}–{g.them} · Final"
                tvline = ("Next " + _ct_when(r.next)) if r.next else (g.note or "")
            else:
                l3 = _ct_when(g)
            f3 = fit_font(d, l3, "sb", w - 12, [17, 16, 15, 14])
            text(d, (cx, ly), ellipsize(d, l3, f3, w - 12), f3, anchor="ma")
            if tvline:
                f4 = fit_font(d, tvline, "m", w - 12, [16, 15, 14])
                text(d, (cx, ly + 21), ellipsize(d, tvline, f4, w - 12), f4, anchor="ma")
        if i < len(pg) - 1:
            dotted(d, 10, w - 10, int(y + bh - 2), 3)
    if len(pages) > 1:
        text(d, (w - 6, h - 3), f"{ctx.cycle % len(pages) + 1}/{len(pages)}", F("cm", 13), anchor="rd")
    return c


def panel_sports(ctx: Ctx, size, rows=None):
    if size[0] < 320:
        return _sports_narrow(ctx, size)
    c, d = canvas(size)
    w, h = size
    teams = ctx.teams
    if not teams:
        text(d, (w / 2, h / 2), "No games in the next few weeks", F("m", 17), anchor="mm")
        return c
    per = rows or max(1, min(4, len(teams)))
    pages = [teams[i:i + per] for i in range(0, len(teams), per)]
    pg = pages[ctx.cycle % len(pages)]
    rh = (h - 6) / per
    y = 3
    for i, r in enumerate(pg):
        badge, prim, sec = _team_lines(r, ctx.cfg)
        g = r.live or (r.last if r.fresh_result else None) or r.next
        lsz = int(min(42, rh - 8))
        if paste_logo(c, r.logo, 10, y + (rh - 6 - lsz) / 2 + 1, lsz, ctx.cfg):
            tx = 10 + lsz + 10
            sec = " · ".join(b for b in (r.record, sec) if b)
        else:
            text(d, (12, y + 4), r.label.upper(), F("cb", 21))
            if r.record:
                text(d, (12, y + 27), r.record, F("cm", 15))
            tx = 108
        right = w - 10
        osz = 30
        if g and g.opp_logo and paste_logo(c, g.opp_logo, w - 10 - osz, y + (rh - 6 - osz) / 2 + 1, osz, ctx.cfg):
            right = w - 10 - osz - 8
        x = tx
        if badge:
            fb = F("cb", 17)
            x = pill(d, x, y + 4, badge, fb, pad=5, h=24) + 7
        text(d, (x, y + 3), ellipsize(d, prim, F("sb", 19), right - x), F("sb", 19))
        if sec:
            text(d, (tx, y + 27), ellipsize(d, sec, F("cm", 16), right - tx), F("cm", 16))
        y += rh
        if i < len(pg) - 1:
            dotted(d, 10, w - 10, int(y - 3), 3)
    if len(pages) > 1:
        text(d, (w - 8, h - 4), f"{ctx.cycle % len(pages) + 1}/{len(pages)}", F("cm", 13), anchor="rd")
    return c


def panel_lunch(ctx: Ctx, size):
    c, d = canvas(size)
    w, h = size
    rows = ctx.lunch[:2]
    if not rows:
        text(d, (w / 2, h / 2 - 12), "No lunch menu loaded", F("sb", 20), anchor="mm")
        text(d, (w / 2, h / 2 + 14), "Add next month to lunch.json", F("m", 15), anchor="mm")
        return c
    rh = (h - 6) / 2
    for i, r in enumerate(rows):
        y = 3 + i * rh
        x = pill(d, 12, y + 4, r.label, F("cb", 17), pad=6, h=22) + 8
        dtxt = f"{r.date:%b} {r.date.day}"
        if r.label in ("TODAY", "TOMORROW"):
            dtxt = f"{r.date:%a} " + dtxt
        text(d, (x, y + 15), dtxt, F("cm", 17), anchor="lm")
        if r.source:
            text(d, (w - 12, y + 15), ellipsize(d, "from " + r.source, F("csb", 17), w - x - 90),
                 F("csb", 17), anchor="rm")
        ty = y + 32
        if r.closed:
            text(d, (12, ty + 4), r.closed, F("sb", 24))
        else:
            fm = F("sb", 21)
            lines = wrap(d, r.items[0], fm, w - 24, 2)
            for ln in lines:
                text(d, (12, ty), ln, fm)
                ty += 23
            for alt in r.items[1:2]:
                fa = fit_font(d, "or " + alt, "m", w - 24, [17, 16, 15])
                text(d, (12, ty + 1), ellipsize(d, "or " + alt, fa, w - 24), fa)
        if i == 0 and len(rows) > 1:
            dotted(d, 10, w - 10, int(y + rh - 2), 3)
    return c


def panel_calendar(ctx: Ctx, size):
    """Upcoming family events, soonest first: day and time on one line, title under it."""
    c, d = canvas(size)
    w, h = size
    evs = ctx.agenda
    text(d, (12, 3), "CALENDAR", F("cb", 18))              # same header as the other tiles
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    if not evs:
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), "Nothing coming up", F("sb", 19), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), "Add events on the settings page", F("m", 14), anchor="mm")
        return c
    today = time.localtime(ctx.now)
    import datetime as _dt
    t0 = _dt.date(today.tm_year, today.tm_mon, today.tm_mday)
    rh = 44                                  # row pitch: date line, title, then room before the divider
    rows = max(1, int((h - 28) // rh))
    shown = evs[:rows]
    hidden = len(evs) - len(shown)
    y = 28
    for i, e in enumerate(shown):
        delta = (e.date - t0).days
        date = f"{e.date:%a %b} {e.date.day}"            # always the date: "Mon Nov 9"
        day = ("Today · " if delta == 0 else "Tomorrow · " if delta == 1 else "") + date
        head = day + (" · " + e.clock if e.clock else "")
        fh = fit_font(d, head, "csb", w - 24, [16, 15, 14])
        text(d, (12, y + 2), ellipsize(d, head, fh, w - 24), fh)
        ft = fit_font(d, e.title, "sb", w - 24, [18, 17, 16, 15])
        text(d, (12, y + 18), ellipsize(d, e.title, ft, w - 24), ft)
        y += rh
        if i < len(shown) - 1:
            dotted(d, 10, w - 10, int(y - 2), 3)
    if hidden > 0:                           # the count sits in the header, so it costs no row
        text(d, (w - 12, 5), f"+{hidden} more", F("cm", 15), anchor="ra")
    return c


def panel_volleyball(ctx: Ctx, size):
    """The team's next games and practices: a date/time line (GAME badge for games), the
    title, then the venue. Falls back to a plain message when nothing is scheduled."""
    import datetime as _dt
    c, d = canvas(size)
    w, h = size
    name = ctx.volleyball_name.split(" - ")[0] if ctx.volleyball_name else ""
    text(d, (12, 3), "VOLLEYBALL", F("cb", 18))
    if name:
        text(d, (w - 12, 5), ellipsize(d, name, F("cm", 15), w - 130), F("cm", 15), anchor="ra")
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    evs = ctx.volleyball
    if not evs:
        msg = "No volleyball scheduled" if ctx.volleyball_on else "Volleyball not connected"
        sub = "Games and practices appear here" if ctx.volleyball_on else "Set the feed link on the server"
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), msg, F("sb", 18), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), sub, F("m", 14), anchor="mm")
        return c
    tm = time.localtime(ctx.now)
    t0 = _dt.date(tm.tm_year, tm.tm_mon, tm.tm_mday)
    rh = 59
    rows = max(1, int((h - 28) // rh))
    y = 28
    for i, e in enumerate(evs[:rows]):
        delta = (e.date - t0).days
        when = ("Today · " if delta == 0 else "Tomorrow · " if delta == 1 else "") + f"{e.date:%a %b} {e.date.day}"
        if e.time:
            when += " · " + e.clock
        x = 12
        if e.kind in ("game", "tournament"):
            x = pill(d, 12, y + 1, "GAME" if e.kind == "game" else "TOURNEY", F("cb", 14), pad=5, h=18) + 7
        fh = fit_font(d, when, "csb", w - 12 - x, [16, 15, 14])
        text(d, (x, y + 10), ellipsize(d, when, fh, w - 12 - x), fh, anchor="lm")
        ft = fit_font(d, e.title, "sb", w - 24, [18, 17, 16, 15])
        text(d, (12, y + 18), ellipsize(d, e.title, ft, w - 24), ft)
        if e.place:
            text(d, (12, y + 38), ellipsize(d, e.place, F("m", 14), w - 24), F("m", 14))
        y += rh
        if i < rows - 1 and i < len(evs) - 1:
            dotted(d, 10, w - 10, int(y - 2), 3)
    return c


def panel_todo(ctx: Ctx, size):
    """Open tasks in the order they were added: an empty tick box, the task, and a small due date on the right."""
    c, d = canvas(size)
    w, h = size
    items = ctx.todos
    text(d, (12, 3), "TO-DO LIST", F("cb", 18))
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    if not items:
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), "All done!", F("sb", 19), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), "Add tasks on the settings page", F("m", 14), anchor="mm")
        return c
    rh = 29
    rows = max(1, int((h - 28) // rh))
    shown = items[:rows]
    hidden = len(items) - len(shown)
    y = 28
    for i, t in enumerate(shown):
        d.rectangle((12, y + 6, 26, y + 20), outline=INK, width=2)              # empty tick box
        due = f"{t.due:%a %b} {t.due.day}" if t.due else ""
        dw = 0
        if due:
            fd = F("cm", 14)
            dw = tw(d, due, fd)
            text(d, (w - 12, y + 14), due, fd, anchor="rm")
        avail = w - 40 - (dw + 10 if due else 0)
        ft = fit_font(d, t.title, "sb", avail, [18, 17, 16, 15])
        text(d, (36, y + 14), ellipsize(d, t.title, ft, avail), ft, anchor="lm")
        y += rh
        if i < len(shown) - 1:
            dotted(d, 10, w - 10, int(y - 1), 3)
    if hidden > 0:                           # the count sits in the header, so it costs no row
        text(d, (w - 12, 5), f"+{hidden} more", F("cm", 15), anchor="ra")
    return c


def panel_countdown(ctx: Ctx, size):
    """Days until: a big number, the name, and the date. A break that is on shows days left."""
    c, d = canvas(size)
    w, h = size
    text(d, (12, 3), "COUNTDOWN", F("cb", 18))
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    items = ctx.countdowns
    if not items:
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), "Nothing to count down to", F("sb", 18), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), "Pick holidays on the settings page", F("m", 14), anchor="mm")
        return c
    rh = 44
    rows = max(1, int((h - 28) // rh))
    y = 28
    for i, it in enumerate(items[:rows]):
        last_day = it.state == "now" and it.number == 0
        if it.state == "today" or last_day:
            pill(d, 8, y + 9, "LAST DAY" if last_day else "TODAY", F("cb", 14 if last_day else 18), pad=6, h=26)
        else:
            text(d, (60, y + 1), str(it.number), F("b", 30), anchor="ra")
            text(d, (60, y + 29), "day" if it.number == 1 else "days", F("cm", 13), anchor="ra")
        fn = fit_font(d, it.name, "sb", w - 86, [19, 18, 17, 16])
        text(d, (74, y + 5), ellipsize(d, it.name, fn, w - 86), fn)
        dm = lambda x: f"{x:%b} {x.day}"
        if it.state == "now":
            sub = f"Now · ends {it.end:%a} {dm(it.end)}"
        elif it.end and it.end != it.date:
            sub = f"{dm(it.date)} – {dm(it.end)}"
        else:
            sub = f"{it.date:%a} {dm(it.date)}"
        text(d, (74, y + 26), ellipsize(d, sub, F("cm", 14), w - 86), F("cm", 14))
        y += rh
        if i < rows - 1 and i < len(items) - 1:
            dotted(d, 10, w - 10, int(y - 1), 3)
    return c


def panel_verse(ctx: Ctx, size):
    """Verse of the day. The text takes the biggest size that fits and is cut with an
    ellipsis only if even the smallest does not."""
    c, d = canvas(size)
    w, h = size
    text(d, (12, 3), "VERSE OF THE DAY", F("cb", 18))
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    v = ctx.verse
    if not v or not v.get("text"):
        text(d, (w / 2, 30 + (h - 30) / 2), "Verse unavailable right now", F("sb", 17), anchor="mm")
        return c
    ref = f'{v["ref"]} · {v["version"]}'
    cr = (v.get("copyright") or "").strip()
    if cr and "public domain" in cr.lower():
        cr = ""
    ry = h - 24 - (12 if cr else 0)
    if cr:                                    # copyrighted translations show their notice, in small print
        text(d, (12, h - 13), ellipsize(d, cr, F("cm", 11), w - 24), F("cm", 11))
    text(d, (w - 12, ry + 2), ellipsize(d, ref, F("cb", 17), w - 24), F("cb", 17), anchor="ra")
    body = "\u201c" + v["text"] + "\u201d"
    top, avail = 32, ry - 34
    for sz in (22, 20, 19, 18, 17, 16, 15, 14):
        f = F("cm", sz)
        lh = sz + 3
        lines = wrap(d, body, f, w - 24, 40)
        if len(lines) * lh <= avail:
            break
    else:
        lines = wrap(d, body, f, w - 24, max(1, int(avail // lh)))
    y = top + max(0, (avail - len(lines) * lh) // 2) if len(lines) * lh < avail * 0.6 else top
    for ln in lines:
        text(d, (12, y), ln, f)
        y += lh
    return c


def panel_history(ctx: Ctx, size):
    """This day in history: two events, each a big year with the event under it."""
    c, d = canvas(size)
    w, h = size
    tm = time.localtime(ctx.now)
    text(d, (12, 3), "THIS DAY IN HISTORY", F("cb", 18))
    text(d, (w - 12, 5), time.strftime("%b ", tm) + str(tm.tm_mday), F("cm", 15), anchor="ra")
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    evs = ctx.history
    if not evs:
        text(d, (w / 2, 30 + (h - 30) / 2), "No history for today", F("sb", 17), anchor="mm")
        return c
    n = min(2, len(evs))
    ih = (h - 28) / n                         # height of one item
    for i, e in enumerate(evs[:n]):
        y = 28 + i * ih
        text(d, (12, y + 1), str(e["year"]), F("b", 26))
        avail = int(ih - 33 - (4 if i < n - 1 else 0))
        for sz in (17, 16, 15, 14):
            f = F("cm", sz)
            lh = sz + 3
            lines = wrap(d, e["text"], f, w - 24, 10)
            if len(lines) * lh <= avail:
                break
        else:
            lines = wrap(d, e["text"], f, w - 24, max(1, avail // lh))
        ty = y + 31
        for ln in lines:
            text(d, (12, ty), ln, f)
            ty += lh
        if i < n - 1:
            dotted(d, 10, w - 10, int(y + ih - 3), 3)
    return c


def panel_hearings(ctx: Ctx, size):
    """Hearing Calendar: the next four hearing days, each with its weekday, date, and a badge that says
    whether any hearing that day is in person (solid) or all are phone/video (outlined)."""
    c, d = canvas(size)
    w, h = size
    text(d, (12, 3), "HEARING CALENDAR", F("cb", 18))
    d.line((10, 25, w - 10, 25), fill=INK, width=2)
    days = ctx.hearings
    if not days:
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), "No upcoming hearings", F("sb", 18), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), "Load a schedule to see them", F("m", 14), anchor="mm")
        return c
    rh = 44
    y = 28
    rows = max(1, min(4, int((h - 28) // rh)))
    for i, day in enumerate(days[:rows]):
        text(d, (12, y + (rh - 30) // 2 - 2), day.date.strftime("%a").upper(), F("cb", 28))
        text(d, (72, y + (rh - 23) // 2 + 1), f"{day.date:%b} {day.date.day}", F("sb", 23))
        label = "IN PERSON" if day.in_person else "REMOTE"
        f = F("cb", 15)
        bw = tw(d, label, f) + 16
        x0, y0 = w - 12 - bw, y + (rh - 24) // 2
        if day.in_person:
            d.rounded_rectangle((x0, y0, w - 12, y0 + 24), radius=4, fill=INK)
            d.text((x0 + 8, y0 + 12), label, font=f, fill=PAPER, anchor="lm")
        else:
            d.rounded_rectangle((x0, y0, w - 12, y0 + 24), radius=4, outline=INK, width=2)
            d.text((x0 + 8, y0 + 12), label, font=f, fill=INK, anchor="lm")
        y += rh
        if i < rows - 1 and i < len(days) - 1:
            dotted(d, 10, w - 10, int(y - 2), 3)
    return c


def smart_names(cfg: dict) -> list:
    """The panels the SMART tile rotates through: up to five it was given, leaving out any that is already
    showing in another slot (it would only repeat what the board shows) and anything unknown."""
    n = 5 if cfg.get("layout") == "five" else 4
    used = set((cfg.get("slots") or [])[:n]) - {"smart"}
    out = []
    for name in cfg.get("smart_tiles") or []:
        if name in PANELS and name != "smart" and name not in used and name not in out:
            out.append(name)
    return out[:5]


def smart_current(cfg: dict, step: int):
    names = smart_names(cfg)
    return (names[step % len(names)] if names else None), names


def panel_smart(ctx: Ctx, size):
    """SMART: one tile that shows a different panel each time the board updates, so the other tiles can
    stay put while this one brings in extra information. It draws whichever panel is up, at its own size."""
    name, names = smart_current(ctx.cfg, ctx.smart_step)
    if name is None:
        c, d = canvas(size)
        w, h = size
        text(d, (12, 3), "SMART", F("cb", 18))
        d.line((10, 25, w - 10, 25), fill=INK, width=2)
        text(d, (w / 2, 30 + (h - 30) / 2 - 8), "Nothing chosen yet", F("sb", 18), anchor="mm")
        text(d, (w / 2, 30 + (h - 30) / 2 + 14), "Pick its tiles in the settings", F("m", 14), anchor="mm")
        return c
    return PANELS[name](ctx, size)


def panel_lunch_week(ctx: Ctx, size):
    """The whole right half: five consecutive days, one row each."""
    c, d = canvas(size)
    w, h = size
    rows = ctx.lunch_week[:5]
    if not rows:
        text(d, (w / 2, h / 2), "No lunch menu loaded", F("sb", 20), anchor="mm")
        return c
    rh = (h - 4) / 5
    x0 = 92                                  # text column
    for i, r in enumerate(rows):
        y = 2 + i * rh
        if r.label == "TODAY":
            pill(d, 12, y + 9, "TODAY", F("cb", 19), pad=6, h=24)
        else:
            text(d, (12, y + 9), r.label, F("cb", 22))
        dtxt = f"{r.date:%b} {r.date.day}"
        text(d, (12, y + 40), (f"{r.date:%a} " + dtxt) if r.label == "TODAY" else dtxt, F("cm", 16))
        tw_ = w - x0 - 12
        acts = ctx.activities.get(r.date, [])
        ty = y + 8
        if r.closed:
            text(d, (x0, y + 10), r.closed, F("sb", 21))
            ty = y + 40
        elif r.items:
            fm = F("sb", 18)
            for ln in wrap(d, r.items[0], fm, tw_, 2):
                text(d, (x0, ty), ln, fm)
                ty += 21
            # keep room for the activity lines: drop the "or" option if they would not fit
            if len(r.items) > 1 and ty + 19 + 19 * len(acts) <= y + rh:
                fa = fit_font(d, "or " + r.items[1], "m", tw_, [16, 15, 14])
                text(d, (x0, ty + 1), ellipsize(d, "or " + r.items[1], fa, tw_), fa)
                ty += 19
            if r.source:
                text(d, (w - 12, y + 10), r.source, F("csb", 15), anchor="ra")
        elif not r.weekend:
            text(d, (x0, y + 10), "Menu not loaded", F("m", 16))
            ty = y + 34
        for tm, title in acts:
            tf, nf = F("cb", 17), F("m", 17)
            text(d, (x0, ty), tm, tf)
            text(d, (x0 + tw(d, tm, tf) + 8, ty), ellipsize(d, title, nf, tw_ - tw(d, tm, tf) - 8), nf)
            ty += 20
        if i < len(rows) - 1:
            dotted(d, 10, w - 10, int(y + rh - 1), 3)
    return c


PANELS = {"weather": panel_weather, "news": panel_news, "sports": panel_sports,
          "lunch": panel_lunch, "calendar": panel_calendar, "hearings": panel_hearings, "smart": panel_smart,
          "volleyball": panel_volleyball, "countdown": panel_countdown, "verse": panel_verse,
          "history": panel_history, "todo": panel_todo}


# ================================================================== chrome

def header(ctx: Ctx):
    c, d = canvas((W, HEAD_H))
    d.rectangle((0, 0, W, HEAD_H), fill=INK)
    t = time.localtime(ctx.now)
    date = time.strftime("%A, %B ", t) + str(t.tm_mday)
    text(d, (14, HEAD_H / 2), date, F("sb", 22), fill=PAPER, anchor="lm")
    # right side, laid out right-to-left: updated time, battery, indoor
    f = F("m", 17)
    sep = "   ·   "
    x = W - 14
    s = f"Updated {hm(ctx.updated or ctx.now)}"
    text(d, (x, HEAD_H / 2), s, f, fill=PAPER, anchor="rm")
    x -= tw(d, s, f)
    if ctx.battery is not None:
        x -= tw(d, sep, f)
        text(d, (x, HEAD_H / 2), sep, f, fill=PAPER, anchor="lm")
        pct = f"{ctx.battery}%" + ("  plug me in" if ctx.battery <= 20 else "")
        x -= tw(d, pct, f)
        text(d, (x, HEAD_H / 2), pct, f, fill=PAPER, anchor="lm")
        # battery glyph: outline, nub, fill proportional to charge
        bw, bh = 26, 13
        x -= bw + 9
        y0 = HEAD_H / 2 - bh / 2
        d.rounded_rectangle((x, y0, x + bw, y0 + bh), radius=2, outline=PAPER, width=2)
        d.rectangle((x + bw + 1, y0 + 4, x + bw + 3, y0 + bh - 4), fill=PAPER)
        fillw = max(1, round((bw - 6) * min(100, ctx.battery) / 100))
        d.rectangle((x + 3, y0 + 3, x + 3 + fillw, y0 + bh - 3), fill=PAPER)
    if ctx.indoor_f is not None:
        x -= tw(d, sep, f)
        text(d, (x, HEAD_H / 2), sep, f, fill=PAPER, anchor="lm")
        s = f"Inside {ctx.indoor_f:.0f}°" + (f" {ctx.indoor_rh:.0f}%" if ctx.indoor_rh is not None else "")
        text(d, (x, HEAD_H / 2), s, f, fill=PAPER, anchor="rm")
    if ctx.notes_new:
        f = F("csb", 17)
        s = f"{ctx.notes_new} new note{'s' if ctx.notes_new > 1 else ''}"
        x = 14 + tw(d, date, F("sb", 22)) + 18
        pill(d, x, 8, s, f, fill=PAPER, fg=INK, h=22)
    return c


def _severe_alert(ctx):
    return ctx.weather is not None and ctx.weather.alerts and ctx.weather.alerts[0][2] in ("Extreme", "Severe")


def has_strip(ctx: Ctx) -> bool:
    """The bar under the date. With headline_bar off it only appears for a posted
    message or a severe weather alert, and the panels use the space otherwise."""
    return bool(ctx.cfg.get("headline_bar", True) or ctx.sticky or _severe_alert(ctx))


def strip(ctx: Ctx):
    """The one line under the header: sticky message > severe alert > brief."""
    c, d = canvas((W, STRIP_H))
    msg, bold = "", False
    if ctx.sticky:
        msg, bold = ctx.sticky, True
    elif _severe_alert(ctx):
        msg, bold = ctx.weather.alerts[0][1], True
    elif ctx.brief and ctx.cfg.get("headline_bar", True):
        msg = ctx.brief
    if not msg and ctx.cfg.get("headline_bar", True):
        up = _next_up(ctx)
        msg = up or ""
    if bold:
        d.rectangle((0, 0, W, STRIP_H - 1), fill=INK)
        tri(d, 12, 6, 15, True, fill=PAPER)
        d.text((19.5, 17), "!", font=F("b", 11), fill=INK, anchor="mm")
        text(d, (36, STRIP_H / 2), ellipsize(d, msg, F("sb", 18), W - 50), F("sb", 18), fill=PAPER, anchor="lm")
    else:
        text(d, (14, STRIP_H / 2 - 1), ellipsize(d, msg, F("m", 18), W - 28), F("m", 18), anchor="lm")
        d.line((0, STRIP_H - 1, W, STRIP_H - 1), fill=INK, width=2)
    return c


def strip_source(ctx: Ctx) -> str:
    """Plain words for where the bar's text is coming from, mirroring strip() above."""
    if ctx.sticky:
        return "your posted message"
    if _severe_alert(ctx):
        return "a severe weather alert"
    if not ctx.cfg.get("headline_bar", True):
        return "nothing (headline bar is off)"
    if ctx.brief:
        return "the AI brief"
    for r in ctx.teams:
        if r.live:
            return "a live game (no AI brief available)"
    for r in ctx.teams:
        if r.next and r.next.start - ctx.now < 12 * 3600:
            return "a game within 12 hours (no AI brief available)"
    return "the top headline (no AI brief available)" if ctx.heads else "nothing"


def _next_up(ctx):
    for r in ctx.teams:
        if r.live:
            return f"{r.label} playing now: {r.live.us}–{r.live.them} {r.live.detail}"
    for r in ctx.teams:
        if r.next and r.next.start - ctx.now < 12 * 3600:
            return f"{r.label} {when(r.next.start, r.next.time_tbd).lower()} vs {r.next.opp_name}"
    if ctx.heads:
        return ctx.heads[0].title
    return ""


def grid_geom(bar: bool = True):
    """(top of the panel grid, height of one cell). Without the bar the grid grows."""
    gy = GRID_Y if bar else HEAD_H
    return gy, (H - gy) // 2


def visible_panels(cfg: dict) -> set:
    """The panels on the main screen right now: the first 4 or 5 of the slots, or the fixed week layout."""
    layout = cfg.get("layout")
    if layout == "week":
        return {"weather", "sports", "lunch"}
    n = 5 if layout == "five" else 4
    return set((cfg.get("slots") or [])[:n])


def slot_boxes(bar: bool = True, layout: str = "quad"):
    """Panel boxes in slot order. quad: 2x2. five: two on top, three across the bottom."""
    gy, ch = grid_geom(bar)
    top = [(0, gy, CELL_W, gy + ch), (CELL_W, gy, W, gy + ch)]
    if layout == "five":
        xs = [0, W // 3 + 1, 2 * W // 3 + 1, W]
        return top + [(xs[i], gy + ch, xs[i + 1], H) for i in range(3)]
    return top + [(0, gy + ch, CELL_W, H), (CELL_W, gy + ch, W, H)]


def compose_quad(ctx: Ctx, panels: dict | None = None) -> Image.Image:
    """panels: optional {name: prerendered L image} to reuse (not re-render)."""
    c = Image.new("L", (W, H), PAPER)
    c.paste(header(ctx), (0, 0))
    bar = has_strip(ctx)
    gy, ch = grid_geom(bar)
    if bar:
        c.paste(strip(ctx), (0, HEAD_H))
    if ctx.cfg.get("layout") == "week":
        # weather and sports on the left, five days of lunch down the whole right side
        bx = slot_boxes(bar)
        c.paste(panel_weather(ctx, (CELL_W, ch)), bx[0][:2])
        c.paste(panel_sports(ctx, (CELL_W, ch)), bx[2][:2])
        c.paste(panel_lunch_week(ctx, (CELL_W, 2 * ch)), bx[1][:2])
        d = ImageDraw.Draw(c)
        d.line((CELL_W - 1, gy + 6, CELL_W - 1, H - 6), fill=INK, width=2)
        d.line((6, gy + ch, CELL_W - 6, gy + ch), fill=INK, width=2)
        return c
    layout = ctx.cfg.get("layout")
    slots = ctx.cfg.get("slots", ["weather", "news", "sports", "lunch"])
    boxes = slot_boxes(bar, layout)
    for name, box in zip(slots, boxes):
        img = (panels or {}).get(name)
        if img is None:
            img = PANELS[name](ctx, (box[2] - box[0], box[3] - box[1]))
        c.paste(img, box[:2])
    d = ImageDraw.Draw(c)
    d.line((6, gy + ch, W - 6, gy + ch), fill=INK, width=2)
    if layout == "five":
        d.line((CELL_W - 1, gy + 6, CELL_W - 1, gy + ch - 6), fill=INK, width=2)
        for b in boxes[3:]:
            if b[0]:
                d.line((b[0] - 1, gy + ch + 6, b[0] - 1, H - 6), fill=INK, width=2)
    else:
        d.line((CELL_W - 1, gy + 6, CELL_W - 1, H - 6), fill=INK, width=2)
    return c


# ================================================================== detail pages

def detail_weather(ctx, size):
    from sources import wmo
    c, d = canvas(size)
    w, h = size
    left = panel_weather(ctx, (400, 207))
    c.paste(left, (0, 0))
    wx = ctx.weather
    if wx is None:
        return c
    # 24h chart on the right
    x0, x1, y0, y1 = 430, w - 20, 26, 190
    text(d, (x0, 4), "NEXT 24 HOURS", F("cb", 17))
    hrs = [hh for hh in wx.hourly if hh[0] >= ctx.now - 1800][:24]
    if len(hrs) > 2:
        temps = [t for _, t, _, _ in hrs]
        lo, hi = min(temps) - 2, max(temps) + 2
        n = len(hrs)

        def X(i):
            return x0 + (x1 - x0) * i / (n - 1)

        def Y(t):
            return y1 - 48 - (t - lo) / (hi - lo) * (y1 - 48 - y0 - 14)
        for i, (_, _, pop, _) in enumerate(hrs):
            bh = pop / 100 * 40
            if bh >= 1:
                d.rectangle((X(i) - 4, y1 - bh, X(i) + 4, y1), fill=INK)
        d.line((x0, y1, x1, y1), fill=INK)
        d.line([(X(i), Y(t)) for i, t in enumerate(temps)], fill=INK, width=3)
        for i in range(0, n, 3):
            ts, t, pop, code = hrs[i]
            text(d, (X(i), Y(t) - 6), f"{t:.0f}°", F("csb", 15), anchor="md")
            lt = time.localtime(ts)
            text(d, (X(i), y1 + 3), f"{lt.tm_hour % 12 or 12}{'a' if lt.tm_hour < 12 else 'p'}", F("cm", 14), anchor="ma")
        text(d, (x1, 4), "bars: chance of rain", F("cr", 14), anchor="ra")
    # 5-day strip
    days = wx.days[:5]
    top = 222
    d.line((10, top - 6, w - 10, top - 6), fill=INK, width=2)
    cw = (w - 20) / max(1, len(days))
    for i, day in enumerate(days):
        x = 10 + i * cw
        t = time.strptime(day.date, "%Y-%m-%d")
        dn, dk = wmo(day.code)
        text(d, (x + cw / 2, top + 4), "TODAY" if i == 0 else time.strftime("%A", t).upper(), F("cb", 19), anchor="ma")
        paste_icon(c, dk, int(x + cw / 2 - 30), top + 30, 60)
        text(d, (x + cw / 2, top + 96), f"{day.hi:.0f}°  {day.lo:.0f}°", F("sb", 24), anchor="ma")
        text(d, (x + cw / 2, top + 126), dn, F("m", 16), anchor="ma")
        text(d, (x + cw / 2, top + 148), f"{day.pop}% rain · UV {day.uv:.0f}", F("cm", 15), anchor="ma")
        if i:
            d.line((x, top + 4, x, h - 10), fill=INK, width=1)
    return c


def detail_news(ctx, size):
    c, d = canvas(size)
    w, h = size
    qs = ctx.quotes[:6]
    y = 6
    if qs:
        cw = w / len(qs)
        for i, q in enumerate(qs):
            _quote_cell(d, i * cw, y, cw, q, spark_h=28)
            if i:
                d.line((i * cw, y + 2, i * cw, y + 90), fill=INK, width=1)
        y += 98
        state = "Market open" if any(q.state == "open" for q in qs) else "Market closed"
        text(d, (w - 12, y - 8), state, F("cm", 13), anchor="rd")
        d.line((8, y, w - 8, y), fill=INK, width=2)
        y += 8
    f = F("m", 18)
    lh = 22
    colw = (w - 40) / 2
    cols = [(16, y), (16 + colw + 12, y)]
    ci = 0
    for hd in ctx.heads[:16]:
        x, cy = cols[ci]
        lines = wrap(d, hd.title, f, colw - 20, 2)
        need = len(lines) * lh + 8
        if cy + need > h - 4:
            ci += 1
            if ci >= 2:
                break
            x, cy = cols[ci]
        d.rectangle((x, cy + 8, x + 6, cy + 14), fill=INK)
        for ln in lines:
            text(d, (x + 14, cy), ln, f)
            cy += lh
        cols[ci] = (x, cy + 8)
    return c


def detail_sports(ctx, size):
    c, d = canvas(size)
    w, h = size
    teams = ctx.teams
    if not teams:
        text(d, (w / 2, h / 2), "No games in the next few weeks", F("m", 20), anchor="mm")
        return c
    n = min(6, len(teams))
    rh = (h - 10) / n
    y = 6
    for i, r in enumerate(teams[:n]):
        lsz = int(min(56, rh - 10))
        if paste_logo(c, r.logo, 12, y + 2, lsz, ctx.cfg):
            text(d, (22 + lsz, y + 4), r.label.upper(), F("cb", 24))
            text(d, (22 + lsz, y + 32), r.record, F("cm", 17))
        else:
            text(d, (16, y + 4), r.label.upper(), F("cb", 28))
            text(d, (16, y + 36), r.record, F("cm", 17))
        x = 190
        if r.live:
            g = r.live
            xx = pill(d, x, y + 4, "LIVE", F("cb", 20), h=28) + 10
            text(d, (xx, y + 2), f"{g.us}–{g.them} " + ("vs " if g.home else "at ") + g.opp_name, F("sb", 24))
            text(d, (x, y + 38), g.detail + (f" · {g.tv}" if g.tv else ""), F("m", 17))
        else:
            if r.last:
                g = r.last
                if paste_logo(c, g.opp_logo, x, y + 4, 28, ctx.cfg):
                    x += 36
                xx = pill(d, x, y + 6, g.result or "–", F("cb", 18), h=24) + 8
                s = f"{g.us}–{g.them} " + ("vs " if g.home else "at ") + g.opp_name
                text(d, (xx, y + 4), s, F("sb", 21))
                dt = time.strftime("%a %b ", time.localtime(g.start)) + str(time.localtime(g.start).tm_mday)
                if g.ats and ctx.cfg.get("odds", True) and g.odds.spread_us is not None and _sport(r) not in ("hockey", "baseball"):
                    dt += f" · {g.ats} {g.odds.spread_us:+g}"
                text(d, (xx, y + 30), dt, F("cm", 16))
            if r.next:
                g = r.next
                nx = 500
                text(d, (nx, y + 4), "NEXT", F("cb", 15))
                if paste_logo(c, g.opp_logo, w - 12 - 28, y + 2, 28, ctx.cfg):
                    pass
                s = when(g.start, g.time_tbd) + (" vs " if g.home else " at ") + g.opp_name
                text(d, (nx, y + 22), ellipsize(d, s, F("sb", 19), w - nx - 12), F("sb", 19))
                sub = " · ".join(b for b in (g.note, g.tv) if b)
                ob = _odds_bits(g, g.abbr, ctx.cfg, _sport(r), full=True)
                if ob:
                    sub = " · ".join(b for b in (sub, " · ".join(ob)) if b)
                if sub:
                    text(d, (nx, y + 44), ellipsize(d, sub, F("cm", 16), w - nx - 12), F("cm", 16))
                if ob and g.odds.book:
                    text(d, (nx, y + 63), g.odds.book, F("cr", 13))
            if r.news:
                # under the last result, stopping short of the NEXT column; no result yet = use its slot
                fn = F("cm", 16)
                hy = y + 52 if r.last else y + 6
                for j, ln in enumerate(wrap(d, "» " + r.news, fn, 300, 2 if rh - (hy - y) >= 42 or not r.last else 1)):
                    text(d, (190 + (12 if j else 0), hy + j * 18), ln, fn)
        y += rh
        if i < n - 1:
            dotted(d, 12, w - 12, int(y - 4), 3)
    return c


def detail_lunch(ctx, size):
    c, d = canvas(size)
    w, h = size
    rows = ctx.lunch[:5]
    if not rows:
        text(d, (w / 2, h / 2 - 14), "No lunch menu loaded", F("sb", 26), anchor="mm")
        text(d, (w / 2, h / 2 + 18), "Add next month to lunch.json", F("m", 18), anchor="mm")
        return c
    rh = (h - 4) / 5
    for i, r in enumerate(rows):
        y = 2 + i * rh
        lab = r.label if r.label in ("TODAY", "TOMORROW") else r.label[:3]
        pill(d, 14, y + 10, lab, F("cb", 20), pad=7, h=26)
        text(d, (14, y + 48), f"{r.date:%a} {r.date:%b} {r.date.day}", F("cm", 18))
        x = 170
        if r.closed:
            text(d, (x, y + rh / 2), r.closed, F("sb", 28), anchor="lm")
        else:
            fm = fit_font(d, r.items[0], "sb", w - x - 14, [28, 26, 24, 22])
            text(d, (x, y + 8), ellipsize(d, r.items[0], fm, w - x - 14), fm)
            ty = y + 8 + fm.size + 6
            for alt in r.items[1:2]:
                fa = fit_font(d, "or " + alt, "m", w - x - 14, [20, 18, 16])
                text(d, (x, ty), ellipsize(d, "or " + alt, fa, w - x - 14), fa)
            if r.source:
                text(d, (x, y + rh - 14), "from " + r.source, F("csb", 17), anchor="ls")
        if i < len(rows) - 1:
            dotted(d, 10, w - 10, int(y + rh - 2), 3)
    return c


DETAILS = {"weather": detail_weather, "news": detail_news, "sports": detail_sports, "lunch": detail_lunch}


def compose_page(ctx: Ctx, name: str) -> Image.Image:
    c = Image.new("L", (W, H), PAPER)
    c.paste(header(ctx), (0, 0))
    # the strip becomes a page title bar with position dots
    s, d = canvas((W, STRIP_H))
    titles = {"weather": "Weather", "news": "News & markets", "sports": "Scores & schedule", "lunch": "School lunch"}
    text(d, (14, STRIP_H / 2 - 1), titles.get(name, name).upper(), F("cb", 19), anchor="lm")
    text(d, (W - 14, STRIP_H / 2 - 1), "middle: back  ·  right: next  ·  left: home", F("cm", 15), anchor="rm")
    d.line((0, STRIP_H - 1, W, STRIP_H - 1), fill=INK, width=2)
    c.paste(s, (0, HEAD_H))
    c.paste(DETAILS[name](ctx, BODY), (0, GRID_Y))
    return c


def _compose_l(ctx: Ctx) -> Image.Image:
    return compose_page(ctx, ctx.page) if ctx.page in DETAILS else compose_quad(ctx)


def compose_gray(ctx: Ctx) -> Image.Image:
    """The same frame in 4 grey levels (L image holding only 0/85/170/255)."""
    global AA
    AA = True
    try:
        img = _compose_l(ctx)
    finally:
        AA = False
    # Snap to the 4 levels. The midpoints are skewed dark a little: e-paper
    # greys read lighter than they are on a monitor, and thin anti-aliased
    # strokes otherwise fade.
    q = img.point(lambda v: 0 if v < 60 else 85 if v < 140 else 170 if v < 215 else 255)
    if ctx.cfg.get("dark", False):
        q = q.point(lambda v: 255 - v)
    return q


def pack2(gray: Image.Image) -> bytes:
    """L image of 0/85/170/255 -> 2bpp, 4 px per byte, MSB first, 0=black..3=white."""
    v = gray.point(lambda p: p // 85).tobytes()
    return bytes((v[i] << 6) | (v[i + 1] << 4) | (v[i + 2] << 2) | v[i + 3] for i in range(0, len(v), 4))


def compose(ctx: Ctx) -> Image.Image:
    if ctx.page in DETAILS:
        img = compose_page(ctx, ctx.page)
    else:
        img = compose_quad(ctx)
    return to1(img, invert=ctx.cfg.get("dark", False))


# ================================================================== wire format

def encode_reel(frames) -> bytes:
    """REEL v1 -- identical to the note box firmware's format.

    b"REEL" u8 version u16 nframes, then per frame:
      u16 x0 y0 x1 y1 (x multiple of 8, exclusive ends), u16 delay_ms, u8 flags,
      then (x1-x0)/8 * (y1-y0) bytes of region rows. flags bit0 = full refresh.
    """
    out = bytearray(b"REEL")
    out += bytes([1])
    out += len(frames).to_bytes(2, "little")
    prev = None
    for fr in frames:
        img, delay, full = fr[:3]
        gray = fr[3] if len(fr) > 3 else None
        if prev is None or full or gray is not None:
            box = (0, 0, W, H)
        else:
            box = ImageChops.logical_xor(prev, img).getbbox() or (0, 0, 8, 1)
        x0 = box[0] & ~7
        x1 = min(W, (box[2] + 7) & ~7)
        y0, y1 = box[1], box[3]
        for v in (x0, y0, x1, y1, delay):
            out += int(v).to_bytes(2, "little")
        if gray is not None:
            # flags bit1: full-screen grey frame, 1-bit rows then 2bpp rows
            out += bytes([3])
            out += img.tobytes()
            out += pack2(gray)
        else:
            out += bytes([1 if full else 0])
            out += img.crop((x0, y0, x1, y1)).tobytes()
        prev = img
    return bytes(out)


def region_frames(prev: Image.Image, new: Image.Image, bar: bool = True, layout: str = "quad"):
    """Split one update into per-region partial refreshes (header, strip, each
    slot), so a change in two corners refreshes two small windows instead of
    one window spanning the whole screen. Each partial costs ~1s whatever its
    size, but a smaller window ghosts less."""
    boxes = [(0, 0, W, HEAD_H)] + ([(0, HEAD_H, W, GRID_Y)] if bar else []) + slot_boxes(bar, layout)
    frames = []
    cur = prev.copy()
    for b in boxes:
        a, n = prev.crop(b), new.crop(b)
        if ImageChops.logical_xor(a, n).getbbox() is None:
            continue
        cur = cur.copy()
        cur.paste(n, b[:2])
        frames.append(cur)
    if ImageChops.logical_xor(cur, new).getbbox() is not None:   # anything outside the boxes
        frames.append(new)
    return frames
