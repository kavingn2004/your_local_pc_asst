# Plan — Google Tasks two-way sync

**Status:** planned, not yet implemented
**Date:** 2026-07-18
**Goal:** reminders created on your phone/web appear on the laptop (Spider-Man
announces them), and reminders created with `spiderman remind` appear in Google
Tasks on your phone.

---

## 1. Decisions

| Decision | Choice |
|---|---|
| Source | **Google Tasks API v1** |
| Direction | **Two-way** (pull + push) |
| Auth | **OAuth 2.0 only** — installed-app flow, no API key |
| Scope | `https://www.googleapis.com/auth/tasks` (read/write) |
| Completion sync | Only for tasks we announce (prevents re-firing loops) |

### Why Google Tasks and not "Google Reminders"

Google retired Reminders as a separate product and migrated them into Google
Tasks — Assistant reminders and Calendar reminders all live there now. There is
no Reminders API. Google Tasks API is the correct and only official target.

---

## 2. Credential model — OAuth only, no API key

Google Cloud offers three credential types. Only one can do this job:

| Credential | Purpose | Used here |
|---|---|---|
| **API key** | Identifies an app for **public** data (e.g. Maps tiles). Cannot read private user data. | ❌ **No — do not create one** |
| **OAuth client ID** | Acts **on behalf of a user** after their consent. | ✅ **Yes — the only credential we use** |
| **Service account** | Server-to-server with no user. Cannot reach a personal Gmail account's Tasks (needs Workspace domain-wide delegation). | ❌ No |

Your tasks are private user data, so an API key would be rejected by Google
regardless of configuration. **OAuth is not optional and an API key adds
nothing.** During setup, skip anything labelled "API key".

`credentials.json` therefore contains a **client ID + client secret** — not an
API key. It identifies *the application*; the **token** (obtained after you
consent) identifies *you*.

---

## 3. Known limitation: the API discards time-of-day

From the Google Tasks API reference, the `due` field:

> "only records date information; the time portion of the timestamp is discarded
> when setting the due date. It isn't possible to read or write the time that a
> task is due via the API."

This breaks time-accurate reminders, so the design works around it.

**Workaround — encode the time in `notes`.**

- On **push**: write `due` as the date, and prepend a marker line to `notes`:
  `⏰ 14:30` followed by any user notes.
- On **pull**: parse a leading `⏰ HH:MM` out of `notes`; combine with the `due`
  date to reconstruct the exact moment. If absent (task made in the Google UI),
  fall back to `DEFAULT_TIME` (configurable, default `09:00`).

Round-trips full precision for tasks we create, degrades gracefully for tasks
Google created, and stays readable in Google's own UI.

---

## 4. Architecture

### 4.1 Component overview

```
┌──────────────────────────── your laptop ────────────────────────────┐
│                                                                     │
│   ┌──────────────┐         writes/reads        ┌────────────────┐   │
│   │  spiderman   │ ──────────────────────────► │  tasks.json    │   │
│   │    (CLI)     │                             │  state.json    │   │
│   └──────────────┘                             └────────────────┘   │
│      user types                                    ▲       ▲        │
│   `spiderman remind`                               │       │        │
│                                                    │       │        │
│   ┌───────────────────────────────────────────┐    │       │        │
│   │      spiderman-overlay  (long-running)    │    │       │        │
│   │                                           │    │       │        │
│   │   ┌───────────────┐   ┌───────────────┐   │    │       │        │
│   │   │ GTK character │   │  _tick loop   │───┼────┘       │        │
│   │   │ bubble+voice  │◄──│   (15 s)      │   │            │        │
│   │   └───────────────┘   └───────┬───────┘   │            │        │
│   │                               │ every     │            │        │
│   │                               │ 120 s     │            │        │
│   │                       ┌───────▼────────┐  │            │        │
│   │                       │ google_sync.py │──┼────────────┘        │
│   │                       └───────┬────────┘  │                     │
│   └───────────────────────────────┼───────────┘                     │
│                                   │                                 │
│   ┌────────────────────────┐      │ OAuth token                     │
│   │ ~/.config/spiderman/   │      │                                 │
│   │   google/              │◄─────┘                                 │
│   │     credentials.json   │  (client id+secret, you download once) │
│   │     token.json         │  (refresh token, chmod 600)            │
│   └────────────────────────┘                                        │
└───────────────────────────────────┼─────────────────────────────────┘
                                    │ HTTPS
                                    ▼
                        ┌───────────────────────┐
                        │  Google Tasks API v1  │
                        └───────────┬───────────┘
                                    │
                                    ▼
                         📱 your phone's Tasks
```

**Key property:** the CLI and the sync layer never talk to each other directly.
`tasks.json` is the single source of truth on the laptop; every component reads
and writes only that. This keeps the pieces independently testable and means a
broken sync can never stop local reminders from firing.

### 4.2 Modules

| File | Responsibility | Depends on |
|---|---|---|
| `bin/spiderman` | CLI: parse commands, edit `tasks.json`, control the service, zenity GUI. Gains a `google` subcommand group. | `tasks.json` |
| `bin/spiderman-overlay` | GTK character, speech bubble, voice, `_tick` alert loop. Calls sync on a timer. | `tasks.json`, `google_sync` |
| `lib/google_sync.py` **(new)** | Auth, token refresh, pull, push, mapping, dedup. Exposes `login()`, `logout()`, `status()`, `sync()`. | Google API client, `tasks.json` |
| `.venv/` **(new)** | Isolated Google client libraries (PEP-668 requires it). | — |

`google_sync.py` is the only module that knows Google exists. Everything else
treats synced tasks as ordinary tasks with two extra fields.

### 4.3 Authentication flow (one time)

```
you            spiderman google login        browser            Google
 │                      │                       │                  │
 ├─ run command ───────►│                       │                  │
 │                      ├─ read credentials.json│                  │
 │                      ├─ start local server   │                  │
 │                      │   on 127.0.0.1:PORT   │                  │
 │                      ├─ open consent URL ───►│                  │
 │                      │                       ├─ sign in ───────►│
 │◄─────────────────────┼─── "unverified app" ──┤                  │
 ├─ click Advanced → Continue ─────────────────►│                  │
 ├─ grant Tasks access ────────────────────────►│                  │
 │                      │◄── redirect w/ code ──┤◄── auth code ────┤
 │                      ├─ exchange code for tokens ──────────────►│
 │                      │◄──── access + refresh token ─────────────┤
 │                      ├─ write token.json (chmod 600)            │
 │◄─ "connected as …" ──┤                                          │
```

Afterwards the refresh token silently mints new access tokens; you never log in
again (provided the consent screen is **published**, see §6 Phase 0).

### 4.4 Sync cycle (every 120 s)

```
                    ┌──────────────────┐
                    │  sync() called   │
                    └────────┬─────────┘
                             ▼
                  ┌─────────────────────┐   no token / offline
                  │ ensure valid token  ├──────────────► log + return
                  └────────┬────────────┘                (local unaffected)
                           ▼
         ╔═══════════════ PULL ═══════════════╗
         ║ tasks.list(showCompleted=false)    ║
         ║   for each remote task with a due: ║
         ║     • rebuild exact time from      ║
         ║       "⏰ HH:MM" in notes          ║
         ║     • known gid  → update if       ║
         ║       remote.updated > gupdated    ║
         ║     • new gid    → insert locally  ║
         ║   local gid missing remotely       ║
         ║       → delete locally             ║
         ╚════════════════╤═══════════════════╝
                          ▼
         ╔═══════════════ PUSH ═══════════════╗
         ║ local source="local", no gid       ║
         ║       → tasks.insert, store gid    ║
         ║ local dirty=true                   ║
         ║       → tasks.patch / delete       ║
         ╚════════════════╤═══════════════════╝
                          ▼
                 ┌────────────────────┐
                 │ write tasks.json   │
                 └────────────────────┘
```

**Conflict rule:** last-write-wins by timestamp (remote `updated` vs local
`modified`). Single-user, so this is sufficient and predictable.

**Loop prevention:** when Spider-Man announces a synced task it is marked
`status: completed` in Google, so the next pull won't resurrect it.

### 4.5 Data model

Local task records gain four fields:

```json
{
  "id": 7, "type": "reminder", "text": "call mom",
  "due": 1784400000, "fired": false,

  "source": "google",          // "google" | "local"  — where it came from
  "gid": "MTIzNDU2",           // Google task id, the dedup key
  "glist": "@default",         // Google task list id
  "gupdated": "2026-07-18T09:00:00Z",
  "dirty": false               // local edit awaiting push
}
```

`gid` is the **only** dedup key. A task that has a `gid` is never re-created
remotely; a task without one is never assumed to exist in Google.

### 4.6 Process & failure model

- **One long-running process** (`spiderman-overlay`, under systemd). Sync runs
  inside its existing timer — no second daemon, no cron.
- **Sync is fully wrapped in try/except.** Any failure (offline, expired token,
  API error) is logged and skipped; the local reminder loop keeps running.
- **The CLI never blocks on network.** `spiderman remind` writes locally and
  returns instantly; the push happens on the next sync tick.
- **Idempotent by design.** Running `sync()` repeatedly with no changes produces
  no writes and no duplicates.

---

## 5. New CLI surface

```
spiderman google login | logout | status
spiderman google sync                  # force a sync now
spiderman google list                  # show remote tasks
spiderman remind "text" 30m --google   # create locally + in Google
```

---

## 6. Phases

### Phase 0 — Google Cloud setup *(user, browser, ~10 min)*
1. Create a project at console.cloud.google.com
2. Enable **Google Tasks API**
3. OAuth consent screen → External → add your email as a test user
4. **Publish the app** ("In production"). Accept the unverified-app warning.
   *Required:* in Testing mode refresh tokens expire after 7 days.
5. Credentials → **OAuth client ID → Desktop app**.
   **Do not create an API key** (§2).
6. Download JSON → `~/.config/spiderman/google/credentials.json` (chmod 600)

**Done when:** the credentials file exists and is valid JSON.

### Phase 1 — Dependencies
- `python3 -m venv ~/spider-asst/.venv`
- install `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`
- **Verify they import on Python 3.14** (very new; pin versions if needed)

**Done when:** `from googleapiclient.discovery import build` succeeds.

### Phase 2 — Auth
- Implement `login()` / `logout()` / `status()` per §4.3
- Token written chmod 600; automatic refresh; clear error if refresh fails

**Done when:** `spiderman google status` prints your account after one login,
and still works after a reboot without re-consenting.

### Phase 3 — Pull sync
- Implement the PULL half of §4.4 including `⏰` notes parsing
- Remote tasks appear in `spiderman list` marked `[G]`

**Done when:** a reminder created on the phone announces on the laptop at the
correct time.

### Phase 4 — Push sync
- Implement the PUSH half; add `--google` flag
- Announced tasks marked complete remotely

**Done when:** a reminder made on the laptop shows on the phone with the right
time, and completes after firing.

---

## 7. Security & privacy

- `credentials.json` and `token.json` live in `~/.config/spiderman/google/`
  (dir `chmod 700`, files `chmod 600`) and are **gitignored**.
- Add `.gitignore`: `.venv/`, `**/token.json`, `**/credentials.json`.
- Scope limited to **Tasks only** — no Gmail, Drive, Calendar, or contacts.
- No API key exists to leak (§2).
- All data stays local; the only network destination is Google's own API.
- `spiderman google logout` deletes the token locally.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| API discards time-of-day | Encode `⏰ HH:MM` in `notes` (§3) |
| Testing-mode tokens expire in 7 days | Publish the consent screen (Phase 0) |
| Python 3.14 library incompatibility | Verify in Phase 1 before building on top; pin versions |
| Duplicate tasks from sync bugs | Dedup strictly on `gid` (§4.5) |
| Sync loop re-announcing tasks | Mark complete in Google after firing (§4.4) |
| Network offline / API down | Sync wrapped in try/except; local reminders unaffected (§4.6) |
| Timezone drift | Store epochs locally; convert only at the API boundary |

---

## 9. Testing

- **Phase 2:** login, reboot, confirm token refresh without re-consent.
- **Phase 3:** create a task on the phone → appears locally within 2 min with
  correct time; delete on phone → disappears locally.
- **Phase 4:** create with `--google` → appears on phone; let it fire → marked
  complete remotely.
- **Offline:** disconnect network → local reminders still fire, no crashes,
  sync resumes on reconnect.
- **Idempotency:** run `google sync` 10× → no duplicates, no writes.

---

## 10. Estimate

| Phase | Work |
|---|---|
| 0 | ~10 min (you, in browser) |
| 1 | ~15 min |
| 2 | ~45 min |
| 3 | ~1.5 h |
| 4 | ~1 h |

Roughly **3–4 hours**, staged so Phase 3 is independently useful — stop there
and you still get phone → laptop reminders.
