# Plan — Slack messages announced by Spider-Man

**Status:** planned, not yet implemented
**Date:** 2026-07-18
**Goal:** when a Slack message arrives that you'd normally be notified about,
Spider-Man announces it — speech bubble + voice.

---

## 1. Two ways to do this

| | **A. Notification bridge** (recommended) | **B. Slack API (Socket Mode)** |
|---|---|---|
| How | Listen on D-Bus for Slack's own desktop notifications | Our own Slack app connects over WebSocket |
| Setup | **None** — works immediately | Create Slack app, tokens, **admin approval** |
| Admin approval | ❌ not needed | ⚠️ almost certainly needed on `stacx24.com` |
| Respects your Slack notification prefs | ✅ automatically | ❌ we'd re-implement the rules |
| Needs Slack desktop running | ✅ yes | ❌ no |
| Message metadata (channel, thread, sender id) | limited — whatever's in the notification | full |
| Can filter by channel/keyword server-side | ❌ | ✅ |

### Recommendation: **A**

You've already hit admin walls twice (Calendar sensitive scope, secret iCal
disabled). Slack app installation on a company workspace is
**admin-gated in the same way**, and getting it approved may not be quick.

Option A sidesteps that entirely: Slack already decides what deserves a
notification (DMs, mentions, keywords — exactly your existing preferences), and
we simply relay those to Spider-Man. If you later want channel filtering or
Slack-without-the-desktop-app, Option B can be added on top.

---

## 2. Architecture (Option A)

```
┌──────────────┐   posts desktop      ┌────────────────────────┐
│ Slack (snap) │   notification ────► │ org.freedesktop.       │
│  desktop app │                      │   Notifications (D-Bus)│
└──────────────┘                      └───────────┬────────────┘
                                                  │ (we monitor)
                                                  ▼
                                    ┌───────────────────────────┐
                                    │  slack_bridge.py          │
                                    │   • filter app == Slack   │
                                    │   • parse sender / text   │
                                    │   • throttle + de-dupe    │
                                    │   • privacy mode          │
                                    └───────────┬───────────────┘
                                                │ writes
                                                ▼
                                    ┌───────────────────────────┐
                                    │  slack_inbox.json         │
                                    └───────────┬───────────────┘
                                                │ reads (existing 15s tick)
                                                ▼
                                    ┌───────────────────────────┐
                                    │  spiderman-overlay        │
                                    │   bubble + voice          │
                                    └───────────────────────────┘
```

**Why a queue file instead of calling the overlay directly?** It matches the
existing design — the CLI, Google sync and calendar sync all communicate with
the overlay through files, never directly. The bridge can crash or restart
without affecting the character, and messages that arrive while Spider-Man is
muted simply wait.

### Module

| File | Responsibility |
|---|---|
| `lib/slack_bridge.py` **(new)** | D-Bus monitor, filtering, throttling, writes `slack_inbox.json` |
| `bin/spiderman-overlay` | reads the inbox on its existing tick, announces, clears |
| `bin/spiderman` | `spiderman slack on\|off\|status\|test` |

Runs as a second systemd user service (`spiderman-slack.service`) because a
D-Bus monitor is a long-lived blocking loop and must not sit inside the GTK
main loop.

---

## 3. The two hard problems

### 3.1 Spam

Slack is chatty. Speaking every message aloud would be unusable.

- **Throttle:** at most one spoken announcement per `SLACK_COOLDOWN` (default
  60 s).
- **Batch:** messages arriving inside the cooldown are counted, then announced
  as *"3 more messages from Slack"* rather than read individually.
- **Cap:** never announce more than N per 10 minutes; beyond that, go quiet and
  show a count only.

### 3.2 Privacy — this one matters

Message content spoken **out loud** in an office is a real problem: DMs, salary
talk, client names. Three modes, and the **default is the safe one**:

| Mode | Bubble shows | Voice says |
|---|---|---|
| `sender` **(default)** | `💬 Priya sent a message` | "Priya messaged you on Slack" |
| `preview` | `💬 Priya: can you review…` | sender + first ~60 chars |
| `full` | full text | full text |

Set with `spiderman slack mode sender|preview|full`.

---

## 4. Phases

### Phase 1 — Confirm which D-Bus interface Slack uses ⚠️
Snap apps often post through the **portal** (`org.gtk.Notifications`) rather
than `org.freedesktop.Notifications`. **This must be verified before anything
else is built** — if Slack uses the portal, the monitor match rule changes (and
if it uses neither, Option A is dead and we fall back to B).

**Done when:** a real Slack message is captured on D-Bus and printed.

### Phase 2 — The bridge
`lib/slack_bridge.py`: monitor, filter `app_name == "Slack"`, extract summary +
body, de-dupe (Slack re-issues notifications on edit), throttle, append to
`slack_inbox.json`.

**Done when:** sending yourself a Slack DM appends exactly one inbox entry.

### Phase 3 — Announcement
Overlay reads `slack_inbox.json` on its existing 15 s tick, announces with a
💬 marker in the chosen privacy mode, clears what it announced. Honours the
existing mute (`spiderman off`).

**Done when:** a Slack DM makes Spider-Man speak, and `spiderman off` silences it.

### Phase 4 — Controls & polish
```
spiderman slack on | off              # enable/disable Slack announcements
spiderman slack mode sender|preview|full
spiderman slack status                # running? mode? counts?
spiderman slack test                  # inject a fake message
```
Plus quiet hours and the systemd service with autostart.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| **Slack posts via the portal, not the notification bus** | Verify in Phase 1 before building; monitor both interfaces if needed |
| Snap confinement hides Slack's notifications | Phase 1 will reveal it; fallback is Option B |
| Announcement spam | Throttle + batch + hard cap (§3.1) |
| Reading private messages aloud | `sender` mode is the default (§3.2) |
| Slack desktop app not running | Nothing to relay — documented limitation of Option A |
| D-Bus monitor dies silently | systemd `Restart=always`; `slack status` shows liveness |
| Notification text format changes | Parsing is best-effort; falls back to "a message from Slack" |

---

## 6. Testing

- **Phase 1:** send yourself a DM → confirm it appears on D-Bus.
- **Phase 2:** one DM → exactly one inbox entry; edit the message → no duplicate.
- **Phase 3:** DM → Spider-Man announces; `spiderman off` → silent.
- **Spam:** paste 10 messages quickly → one announcement + a batched count.
- **Privacy:** in `sender` mode, confirm the body is **never** spoken or shown.
- **Resilience:** kill the bridge → systemd restarts it; Slack closed → no errors.

---

## 7. Estimate

| Phase | Work |
|---|---|
| 1 — verify D-Bus interface | ~20 min |
| 2 — bridge | ~1 h |
| 3 — announcement | ~30 min |
| 4 — controls & polish | ~45 min |

Roughly **2.5–3 hours**, and Phase 1 is the go/no-go gate: if Slack's
notifications aren't visible on the bus, we switch to Option B and the plan
changes substantially (Slack app + admin approval).

---

## 8. If we need Option B later

1. Create an app at `api.slack.com/apps` → enable **Socket Mode**
2. App-level token (`xapp-`) + bot token (`xoxb-`)
3. Scopes: `im:history`, `channels:history`, `app_mentions:read`, `users:read`
4. **Workspace admin must approve the install**
5. `pip install slack_sdk`, run a `SocketModeClient` in the same bridge process
   and write to the same `slack_inbox.json` — so Phases 3 and 4 are reused
   unchanged. Only the source of messages differs.
