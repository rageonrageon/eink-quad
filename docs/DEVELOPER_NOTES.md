# Developer notes: how this board is built and how we work on it

Written so a fresh session (or a person) can pick the project up without the original conversation.
Nothing private belongs in this file: no keys, admin links, schedule data, or personal details.

## 1. How it works

- A **Python server** (`server/`, runs on Railway) renders every pixel of the 800x480 screen with Pillow
  (`render.py`) and serves it to a **dumb tablet** (Seeed reTerminal E1001, ESP32-S3, firmware in `firmware/`).
  The tablet only copies bytes and picks refresh modes.
- **Two tablet modes**, decided by the server from the battery voltage (`device_poll` in `app.py`):
  - *awake* (battery above `awake_above_v`, default 4.10 V, i.e. charging): Wi-Fi on, long-polls, updates fast.
  - *sleep* (on battery): deep sleep, wakes every `sleep_min` minutes (default 30), any button wakes it at once.
- The server keeps a **snapshot** of each tile's data (`Board.snap`), refreshed on the "main beat" every
  `interval_min` minutes (default 10) by `Board.take(name)`; then `redraw()` composes the screen and only
  commits a new version if something visible changed. The tablet picks up new versions at its next check-in.
- **Settings** live in `config.json` on the Railway volume (`/data`). Only values that differ from `DEFAULTS` in
  `app.py` are saved. The settings page is `server/web/dashboard.html` (one file, plain JS), opened with
  `/?k=<admin token>`.
- **Layouts**: `quad` (2x2, 4 slots) or `five` (2 on top, 3 across the bottom, 5 slots). `slots` lists the panel for
  each position. Bottom-row cells are about 267 px wide, the top row 400 px.

## 2. File map

| File | What it does |
|---|---|
| `server/app.py` | HTTP server, `Board` (snapshots, scheduling, redraw), settings (`DEFAULTS`, `set_config`), state for the page, API routes |
| `server/render.py` | Every tile (`panel_*`), the header/bar, layouts (`slot_boxes`, `compose_quad`), `Ctx` (what a frame needs) |
| `server/sources.py` | Weather, news, quotes, sports (ESPN), odds, the AI brief (`brief`, providers), verse backups, `Cached` helper |
| `server/lunch.py`, `lunch.json` | School lunch menu (data in the repo, updated monthly) |
| `server/agenda.py`, `ical.py` | Family calendar: hand-entered events plus calendar feeds (iCal links from env vars) |
| `server/countdown.py` | Holidays (tick boxes) plus custom countdowns |
| `server/history.py` | This day in history (Wikipedia), with the family-friendly filter |
| `server/bibleapi.py` | Verse of the day from API.Bible, `verse_refs.json` (verse list), `verses_kjv.json` (offline backup) |
| `server/localtv.py` | Which weekend CBS/FOX games are on the local TV stations (TV Passport station pages) |
| `server/hearings.py` + `tools/import_hearings.py` | Private schedule tile; data is posted to the server, never committed |
| `server/netcheck.py` | Connectivity test shown in the Health panel |
| `server/web/dashboard.html` | The settings page (cards, Health table, pickers) |

## 3. How to add a tile (checklist)

1. **Data**: put the fetching in its own module (or `sources.py`). Wrap network calls in `sources.Cached(ttl)`;
   it keeps the last good value if a fetch fails and retries at most every 2 minutes.
2. **Draw**: in `render.py` add a field to `Ctx`, write `panel_<name>(ctx, size)`, and register it in `PANELS`.
   House style: header text `F("cb", 18)` at (12, 3) with a 2 px line at y=25, content from y=28, rows about
   44-59 px, empty state ("Nothing coming up" plus a hint), dotted dividers (`dotted`), `ellipsize` for long text.
   Draw to whatever `size` you are given (top row 400 wide, bottom row about 267).
3. **Wire** in `app.py`: import the module; a `take()` branch that fills `self.snap[...]`; pass it in `ctx()`;
   add the name to the **three** `for name in (...)` loops and the `due = [...]` list (search for an existing
   tile such as `"hearings"` to find all of them); add any settings to `DEFAULTS` (type decides how the page's
   value is coerced); expose status in `state()` if the page should show it.
4. **Settings page**: add a label to `PANEL_LABELS` in `dashboard.html`. Inputs that have a `name` matching a
   `DEFAULTS` key are saved automatically (checkboxes, numbers, text, selects). Lists are comma separated text.
   Add a Health row in `render()` in the same file if useful.
5. **Mock first, then build**: render a mock with a scratch script that imports `render` and uses the real helpers
   and real data; look at it enlarged; only then edit the code.
6. **Test on a local server** (section 5), including the settings page, then push.

## 4. The custom tiles and what we learned

- **School lunch**: `lunch.json` maps ISO dates to a list of main entrees (first is the main one, the rest are "or"
  options), `{"items": [...], "from": "Restaurant"}` for a catered day, or `{"closed": "No School"}`.
  Monthly: read the menu image, add the days, show the list for checking, push. From `lunch_switch_hour`
  (default 13) the tile shows tomorrow first.
- **Calendar**: hand-entered events (settings page, `agenda.json` on the volume, weekly repeat) plus iCal feeds
  from `QUAD_ICAL_URL` (a calendar's private "secret address"). Google Tasks and Reminders are NOT in such a
  feed; recreate them as events. Only the next few events are shown, soonest first, with the date always shown.
- **Volleyball**: a team calendar feed (`QUAD_ICAL_URL_VOLLEYBALL`). Titles lose the team-name prefix; games are
  guessed from words like "vs" and "game".
- **Countdown**: built-in holidays (tick boxes) plus custom ones (name, start, optional end for a break, yearly
  repeat). Stored in `countdowns.json`; changes apply at once, no Save button.
- **Verse of the day**: API.Bible (key in `API_BIBLE_KEY`). The service has no "verse of the day", so a verse is
  picked from `verse_refs.json` by date. "Translations to offer" accepts an abbreviation, a Bible ID, or the
  initials of the full name (only if exactly one Bible fits). Backups: OurManna (NIV), then a built-in KJV list.
  Copyrighted translations show their notice in small print.
- **This day in history**: Wikipedia "On this day". An event must avoid morbid words (always), optionally avoid
  politics, and is ranked tech first, then culture, then the rest. Two events at a time, changing every 4 hours.
- **Weekend TV check** (`localtv.py`): Saturday and Sunday from 6 AM the server reads the two local stations'
  schedule pages (CBS and FOX) and records which of the family's games are really on. Unreadable or empty pages
  mean "cannot tell", never "not on". The brief then adds the network after the time.
- **Hearing calendar** (private): data is loaded with `tools/import_hearings.py` (needs `pdfplumber`, `requests`),
  which sends only dates, an "in person" flag and a count to `POST /api/hearings`. The in-person code prefix is
  supplied at run time and is not in the repo. Always show the diff and ask the owner before sending.
- **SMART tile**: rotates through up to three chosen tiles that are not already on the board. The step moves once
  per update the tablet receives: on each main beat while awake, on each wake-up while asleep (throttled).
- **Weather tile**: a big HIGH / LOW row under the description; the rain chart shows only when rain is possible
  (it is an empty frame on dry days).
- **The brief** (one line in the top bar): provider is a setting (Claude program, Claude API, or DeepSeek). It
  leaves sports out when the sports tile is on screen. DeepSeek needs thinking turned off or it returns an empty
  answer. The Health panel shows the provider, model, last result and the last prompt sent.

## 5. Working method

- **Local test server** (use temp paths so nothing lands in the repo):
  `QUAD_PORT=87xx QUAD_ADMIN=localtest QUAD_TOKEN=devtok QUAD_CONFIG=<tmp>/config.json QUAD_STATE=<tmp>/state.json
  QUAD_AGENDA=<tmp>/agenda.json python app.py`. Then open `/?k=localtest`, drive the page with the browser pane or
  scripts, and fetch `/api/preview.png?k=localtest` to see the board. Stop the server afterwards.
- **Before every push**: scan everything git would commit for private data (links, keys, personal schedule data),
  then `git add`, commit with the co-author line, push to `origin main`. Railway redeploys by itself.
- **Ask before pushing, and before sending anything to the live server.** Show mock-ups before building.
- **Private runtime files are git-ignored** (`config.json`, `state.json`, `agenda.json`, `countdowns.json`,
  `tv_local.json`, `hearings.json`). Keep it that way.
- **Environment variables** (names only; values live in Railway): `QUAD_TOKEN`, `QUAD_ADMIN`, `QUAD_BIND`,
  `QUAD_PORT`, `QUAD_CONFIG`, `QUAD_STATE`, `QUAD_CONTACT`, `TZ` (a POSIX string such as `CST6CDT,M3.2.0,M11.1.0`,
  because the container has no tz database), `QUAD_ICAL_URL`, `QUAD_ICAL_URL_VOLLEYBALL`, `DEEPSEEK_API_KEY`,
  `ANTHROPIC_API_KEY`, `API_BIBLE_KEY`, and optional path overrides (`QUAD_AGENDA`, `QUAD_COUNTDOWNS`,
  `QUAD_TVLOCAL`, `QUAD_HEARINGS`, `QUAD_LUNCH`).

## 6. Gotchas (all learned the hard way)

- **Some sites refuse Railway's IP address** (403 "Forbidden", often Cloudflare). Bible Gateway and 506sports did.
  Check with the Health panel's connectivity test before building on a new source, and prefer official APIs.
- **A refused or failing source must degrade quietly**: keep the last good value, show a reason on the Health
  panel, never claim "not available" without evidence.
- **Windows dev machine**: `time.tzset` does not exist, so `cases.py` crashes there (use your own preview script);
  git prints harmless LF/CRLF warnings; the Read tool cannot render PDFs (use `pdfplumber` for text and tables).
- **Editing**: patch scripts that embed backslashes (regexes) inside Python strings corrupt them; make exact
  edits with the editor tool instead. Double-check file paths in tool calls (typos in folder names happened).
- **rate limits**: bible-api.com allows about 15 requests per 30 seconds; back off when bulk-fetching.
- **The tablet only sees a new screen when it checks in** (up to `sleep_min` minutes on battery); a button press
  forces an update.
- **Quiet hours** pause scheduled updates (and the SMART rotation); the screen keeps its last image.
