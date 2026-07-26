# 🕷️ your_local_pc_asst

A local desktop assistant for Ubuntu / GNOME. A small Spider-Man character lives
on your screen, and delivers **reminders, alarms and battery alerts** through a
speech bubble (typed out) plus a spoken voice.

Everything runs **locally** and **user-level** — no sudo, no cloud, no accounts.

---

## Features

- **Live character** — a small draggable Spider-Man floats above your desktop
  (rendered through XWayland so it works on a Wayland session).
- **Drag him anywhere** with the mouse; he remembers where you put him.
- **Left-click** → a random action: a quip, the time, battery status, your next
  task, or a greeting.
- **Right-click** → menu: Add reminder, Next task, Mute/Unmute, Quit.
- **Reminders & alarms** — set from the terminal or a small GUI. When one fires,
  the text **types out** in the bubble together with its time, and is spoken.
- **Battery alerts** — low (≤20%), critical (≤10%), and a battery-care nudge at
  ≥85% while charging (helps an ageing battery).
- **Autostarts on login**, and can be muted or stopped at any time.
- **Web control panel + REST API** (`spiderman ui`) with Swagger docs, for
  managing everything from a browser.

---

## Install

```bash
cd ~/your_local_pc_asst
./install.sh
```

Installs symlinks into `~/.local/bin`, copies assets to `~/.config/spiderman`,
and enables the systemd user service. Open a new terminal afterwards so
`~/.local/bin` is on your `PATH`.

To remove it:

```bash
./uninstall.sh            # keeps your tasks/settings
./uninstall.sh --purge    # also deletes ~/.config/spiderman
```

---

## Usage

```bash
spiderman remind "call mom" 30m      # in 30 minutes
spiderman remind "standup" 9:00      # at 09:00
spiderman alarm 14:30 "meeting"      # alarm at 2:30 PM
spiderman list                       # show everything pending
spiderman cancel 3                   # remove task #3

spiderman gui                        # click-to-add window (zenity)

spiderman start | stop               # bring the character back / send away
spiderman on | off                   # unmute / mute all alerts
spiderman status                     # running? battery? tasks?
spiderman enable | disable           # autostart on login on/off
```

**Time formats:** `30m`, `1h`, `90s`, `1h30m`, `14:30`, `9am`, `7pm`.

### Google Tasks sync (two-way)

```bash
spiderman google login                  # one-time browser consent
spiderman google status                 # connected? which lists?
spiderman google tasks                  # dated tasks currently in Google
spiderman google sync                   # sync now (push + pull)
spiderman google auto on|off            # push every new reminder automatically
spiderman google logout

spiderman remind "call mom" 30m --google   # also create it in Google Tasks
spiderman remind "private note" 1h --local # never push this one
```

- Tasks you create **on your phone** appear here within ~2 minutes and are
  announced by Spider-Man.
- Once announced, the task is **marked complete in Google** so it never repeats.
- Completing or deleting a task on your phone removes it here on the next sync.
- Local-only tasks are never sent anywhere.

**The time-of-day workaround.** The Google Tasks API silently discards the time
portion of a due date — it stores dates only. To keep exact times, Spider-Man
writes a `⏰ HH:MM` marker into the task's notes and reads it back on sync. So:

| Task created in… | Fires at |
|---|---|
| Spider-Man (`--google`) | the exact time you set |
| Google's own app/website | **09:00** on the due date (no marker present) |

Change that fallback via `DEFAULT_HH`/`DEFAULT_MM` in `lib/google_sync.py`.

**Known limitation:** cancelling a task locally (`spiderman cancel`) does not
delete it from Google — complete it on your phone, or it will sync back.

### Calendar (via GNOME Online Accounts)

```bash
spiderman calendar calendars          # which calendars were found
spiderman calendar events             # upcoming events
spiderman calendar sync               # merge events into tasks now
spiderman calendar exclude <id>       # ignore a calendar (e.g. holidays)
spiderman calendar show               # settings
```

**Setup:** Settings → Online Accounts → Google → sign in → enable **Calendar**.
Nothing else to configure — Spider-Man reads the calendar GNOME already syncs.

Spider-Man announces each event **10 minutes before it starts**.

**Why not the Google Calendar API?** `calendar.readonly` is a *sensitive* scope
that Google refuses for unverified apps, and Workspace admins commonly disable
the secret iCal address. GNOME's OAuth client is verified and trusted, so adding
the account there sidesteps both problems — and no calendar data is ever shared
publicly. We read the local Evolution cache (`~/.cache/evolution/calendar/`,
read-only); there are no network calls and no tokens of our own.

Recurring events are expanded properly, cancelled occurrences are skipped, and
all-day entries (holidays, birthdays) are ignored since they have no useful
time. Because the calendar is read-only, announced events are recorded in
`gcal_seen.json` rather than marked done.

Tunables at the top of `lib/ical_sync.py`:

```python
LOOKAHEAD_H  = 24     # how far ahead to look
LEAD_MINUTES = 10     # how early to announce
SKIP_ALLDAY  = True   # ignore all-day entries
```

**If he disappears** (you clicked Quit, or he crashed): `spiderman start`.
He also returns automatically at your next login.

---

## Control panel & API

```bash
spiderman ui              # start the server and open the browser
spiderman ui --no-browser
```

- **Control panel** — <http://127.0.0.1:8777>
- **API docs (Swagger UI)** — <http://127.0.0.1:8777/docs>

The panel is a React app (vendored — no build step, no `node_modules`) that
shows the assistant, battery, Google Tasks, calendars, Slack availability and
your task list, and lets you change all of them.

> ⚠️ **Security.** The server binds to `127.0.0.1` only and has **no
> authentication** — the loopback binding *is* the boundary. It controls your
> assistant and exposes your task list, so never put it behind a public proxy
> or bind it to `0.0.0.0`.
>
> ⚠️ In Swagger, **“Try it out” executes for real.** There is no sandbox:
> `POST /api/assistant/stop` really stops the character.

### API reference

Base URL `http://127.0.0.1:8777`. All requests and responses are JSON.

**Assistant**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/assistant` | running / autostart / muted |
| `PATCH` | `/api/assistant` | `{"muted":true}` or `{"autostart":false}` |
| `POST` | `/api/assistant/start` | start the character |
| `POST` | `/api/assistant/stop` | stop it |
| `GET` | `/api/battery` | percent, status, health |

**Tasks**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tasks` | queued reminders, alarms and events |
| `POST` | `/api/tasks` | create — `{"text":"call mom","when":"30m"}` → **201** |
| `DELETE` | `/api/tasks/{id}` | cancel one |

`when` accepts `30m`, `1h30m`, `90s`, `14:30`, `9am`. Add `"google": true` to
push it to Google Tasks, or `"kind": "alarm"` for an alarm.

**Google Tasks**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/google` | connection state, lists, scopes, auto-push |
| `PATCH` | `/api/google` | `{"auto_push":true}` |
| `POST` | `/api/google/login` | opens the browser for consent → **202** |
| `POST` | `/api/google/logout` | delete the local token |
| `POST` | `/api/google/sync` | push pending + pull |
| `GET` | `/api/google/tasks` | what Google currently holds |

**Google Calendar**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/calendar` | detected calendars (with `writable` flags) |
| `GET` | `/api/calendar/events` | upcoming, next 24h |
| `POST` | `/api/calendar/events` | **create a real event** → **201** |
| `DELETE` | `/api/calendar/events/{uid}` | delete an event |
| `POST` | `/api/calendar/sync` | queue events for announcement |
| `POST` | `/api/calendar/refresh` | force Evolution to re-poll Google |
| `PATCH` | `/api/calendar/calendars/{id}` | `{"included":false}` to ignore one |

Creating an event writes to the calendar Evolution holds a **writable** CalDAV
connection to, so it syncs up to Google and appears on your phone. `start`
accepts ISO (`2026-07-20T14:30`), a clock time (`14:30`, next occurrence), or a
relative offset (`+45m`, `+2h`); `minutes` sets the duration (default 30).

```bash
curl -s -X POST localhost:8777/api/calendar/events \
     -H 'Content-Type: application/json' \
     -d '{"summary":"Coffee with Priya","start":"+45m","minutes":30}'
```

> This deliberately does **not** use the Google Calendar API — that scope is
> blocked for unverified apps. It goes through the same local route the GNOME
> Calendar app uses, so it needs no extra tokens or permissions.
>
> Only calendars reporting `writable: true` accept events; subscribed ones
> (holidays, birthdays) are read-only and will be refused.

**Slack** — returns **501**; see [the integration plan](docs/slack-integration-plan.md).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/slack` | availability + why it isn't working |
| `POST` | `/api/slack/connect` | reserved — **501 Not Implemented** |
| `GET` | `/api/slack/messages` | reserved — **501 Not Implemented** |

**Aggregate**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/status` | everything at once (the UI polls this) |
| `POST` | `/api/action` | legacy dispatcher, kept for the UI |

**Status codes:** `200` ok · `201` task created · `202` OAuth started ·
`400` bad/missing fields · `404` unknown route or task · `409` credentials
missing · `501` Slack unavailable · `502` Google/Evolution unreachable.

### Examples

```bash
curl -s localhost:8777/api/status | jq .

curl -s -X POST localhost:8777/api/tasks \
     -H 'Content-Type: application/json' \
     -d '{"text":"call mom","when":"30m","google":true}'

curl -s -X PATCH localhost:8777/api/assistant \
     -H 'Content-Type: application/json' -d '{"muted":true}'

curl -s -X POST localhost:8777/api/google/sync
curl -s -X DELETE localhost:8777/api/tasks/3
```

---

## Project layout

```
your_local_pc_asst/
├── bin/
│   ├── spiderman            # CLI: reminders, alarms, control, zenity GUI
│   └── spiderman-overlay    # GTK3 overlay character + alert loop
├── assets/
│   ├── spiderman.png        # notification icon (spider on a web)
│   └── spiderman-hero.png   # transparent character sprite
├── tools/
│   ├── make_icon.py         # regenerates the notification icon
│   └── make_sprite.py       # turns artwork into a transparent sprite
├── lib/
│   ├── google_sync.py       # Google Tasks: OAuth, two-way sync
│   └── ical_sync.py         # Calendar: reads Evolution's local cache
├── ui/
│   ├── index.html           # control panel shell + styles
│   ├── app.js               # the React app (htm, no build step)
│   ├── docs.html            # Swagger UI page
│   ├── openapi.json         # API specification
│   └── vendor/              # react, react-dom, htm, swagger-ui
├── docs/
│   ├── google-tasks-integration-plan.md
│   └── slack-integration-plan.md
├── .venv/                   # Python deps (gitignored)
├── systemd/spiderman.service
├── desktop/spiderman-gui.desktop
├── install.sh
├── uninstall.sh
└── README.md
```

The commands in `~/.local/bin` are **symlinks** into `bin/`, so editing a file
here changes the installed app directly. After editing the overlay, reload it:

```bash
spiderman stop && spiderman start
```

### Runtime data (not in this folder)

| Path | What |
|---|---|
| `~/.config/spiderman/tasks.json` | your reminders & alarms |
| `~/.config/spiderman/state.json` | mute flag + saved character position |
| `~/.config/spiderman/*.png` | assets copied here by `install.sh` |

---

## Customising

**Character size, voice speed, typing speed** — edit the constants at the top of
`bin/spiderman-overlay`:

```python
SPRITE_H   = 120     # character height in pixels
VOICE_RATE = "-18"   # spd-say rate: lower = slower
TYPE_MS    = 38      # ms per character in the speech bubble
```

**A different character image:**

```bash
python3 tools/make_sprite.py /path/to/artwork.png assets/spiderman-hero.png
cp assets/spiderman-hero.png ~/.config/spiderman/
spiderman stop && spiderman start
```

**Quips and voice lines** — the `QUIPS` and `LEADS` lists in `bin/spiderman-overlay`.

**Battery thresholds** — the `_tick` method in `bin/spiderman-overlay` (`cap <= 20`,
`cap <= 10`, `cap >= 85`).

---

## How it works

- `spiderman` (CLI) reads/writes `tasks.json`; it never talks to the overlay
  directly.
- `spiderman-overlay` is the long-running process: it draws the character, and
  every 15 s checks `tasks.json` for anything due plus the battery level, then
  fires a bubble + voice.
- systemd (`spiderman.service`, `WantedBy=default.target`) starts the overlay at
  login and restarts it if it crashes.
- Voice uses `spd-say` (speech-dispatcher → espeak-ng); notifications use
  `notify-send`; the GUI uses `zenity`.

## Requirements

Already present on a standard Ubuntu GNOME install: Python 3 with PyGObject
(GTK 3), Pillow (for the tools only), `spd-say`, `notify-send`, `zenity`,
and XWayland.
