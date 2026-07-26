#!/usr/bin/env python3
"""Create events in a writable Evolution calendar (which syncs up to Google).

The Google Calendar API is not an option here — calendar.readonly is a
"sensitive" scope Google refuses for unverified apps. But GNOME already holds a
*writable* CalDAV connection to the account, so we create the event through
Evolution's D-Bus API and let it push to Google. Same route GNOME Calendar uses.

No new permissions, no tokens of our own, no extra packages.

Commands:
    writable                       list calendars we can write to
    create <summary> <start> [min] create an event (start = ISO or "HH:MM")
    find [text]                    list events matching text
    delete <ical-uid>              remove an event
"""
import sys, uuid, glob, os, sqlite3
from datetime import datetime, timedelta, timezone

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception as e:
    print(f"❌ PyGObject required: {e}", file=sys.stderr)
    sys.exit(2)

BUS_NAME  = "org.gnome.evolution.dataserver.Calendar8"
FACTORY   = "/org/gnome/evolution/dataserver/CalendarFactory"
IF_FACTORY = "org.gnome.evolution.dataserver.CalendarFactory"
IF_CAL     = "org.gnome.evolution.dataserver.Calendar"
CACHE_GLOB = os.path.expanduser("~/.cache/evolution/calendar/*/cache.db")


def _bus():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def writable_calendars():
    """Source ids of calendars Evolution reports as writable."""
    out = []
    for db in glob.glob(CACHE_GLOB):
        uid = os.path.basename(os.path.dirname(db))
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            keys = dict(con.execute("SELECT key,value FROM ECacheKeys"))
            con.close()
            if keys.get("user::ecmb::connected-writable") == "1":
                out.append(uid)
        except Exception:
            continue
    return out


def open_calendar(uid):
    """Returns (bus_name, object_path) for an opened calendar."""
    bus = _bus()
    res = bus.call_sync(BUS_NAME, FACTORY, IF_FACTORY, "OpenCalendar",
                        GLib.Variant("(s)", (uid,)), None,
                        Gio.DBusCallFlags.NONE, 15000, None)
    path, name = res.unpack()
    # the object must be Open()ed before it accepts writes
    bus.call_sync(name, path, IF_CAL, "Open", None, None,
                  Gio.DBusCallFlags.NONE, 20000, None)
    return name, path


def _ics(summary, start: datetime, minutes: int, description=""):
    """A bare VEVENT — CreateObjects wants components, not a VCALENDAR
    wrapper (see the backend's own DefaultObject property).

    Times are written as floating local time; Evolution applies the calendar's
    timezone, matching how the GNOME Calendar app writes events."""
    fmt = "%Y%m%dT%H%M%S"
    end = start + timedelta(minutes=minutes)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    desc = description.replace("\n", "\\n")
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uuid.uuid4()}\r\n"
        f"DTSTAMP:{now}\r\n"
        f"DTSTART:{start.strftime(fmt)}\r\n"
        f"DTEND:{end.strftime(fmt)}\r\n"
        f"SUMMARY:{summary}\r\n"
        + (f"DESCRIPTION:{desc}\r\n" if desc else "") +
        "STATUS:CONFIRMED\r\n"
        "END:VEVENT\r\n")


def parse_start(s):
    """Accept ISO ('2026-07-20T14:30'), 'HH:MM', or '+45m'."""
    s = s.strip()
    now = datetime.now()
    if s.startswith("+"):
        n = int("".join(c for c in s if c.isdigit()) or 0)
        unit = s.rstrip().lower()[-1]
        return now + timedelta(hours=n) if unit == "h" else now + timedelta(minutes=n)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for f in ("%H:%M", "%I:%M%p", "%I%p"):
        try:
            t = datetime.strptime(s.lower().replace(" ", ""), f)
            cand = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            return cand + timedelta(days=1) if cand <= now else cand
        except ValueError:
            continue
    raise ValueError(f"couldn't understand start time: '{s}'")


def create_event(summary, start, minutes=30, description="", uid=None):
    cals = writable_calendars()
    if not cals:
        return {"ok": False, "err": "no writable calendar — add a Google account "
                                    "in Settings → Online Accounts"}
    target = uid if uid in cals else cals[0]
    try:
        name, path = open_calendar(target)
        ics = _ics(summary, start, minutes, description)
        res = _bus().call_sync(name, path, IF_CAL, "CreateObjects",
                               GLib.Variant("(asu)", ([ics], 0)), None,
                               Gio.DBusCallFlags.NONE, 25000, None)
        uids = res.unpack()[0]
        return {"ok": True, "calendar": target, "uids": list(uids),
                "summary": summary, "start": start.isoformat(),
                "minutes": minutes,
                "out": f"📅 created '{summary}' at {start.strftime('%d %b %H:%M')}"}
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}: {e}"}


def delete_event(uid, cal_uid=None):
    """Remove an event by its iCal UID (deletes in Google too)."""
    cals = writable_calendars()
    if not cals:
        return {"ok": False, "err": "no writable calendar"}
    target = cal_uid if cal_uid in cals else cals[0]
    try:
        name, path = open_calendar(target)
        # (uid, recurrence-id) pairs — empty rid means the whole event;
        # mod_type "all" removes every occurrence of a recurring series.
        _bus().call_sync(name, path, IF_CAL, "RemoveObjects",
                         GLib.Variant("(a(ss)su)", ([(uid, "")], "all", 0)), None,
                         Gio.DBusCallFlags.NONE, 25000, None)
        return {"ok": True, "out": f"🗑️  removed {uid[:24]}"}
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}: {e}"}


def find_events(match):
    """(uid, summary) for events whose summary contains `match`."""
    import re as _re
    out = []
    for db in glob.glob(CACHE_GLOB):
        cal = os.path.basename(os.path.dirname(db))
        if cal not in writable_calendars():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            rows = con.execute("SELECT ECacheUID, ECacheOBJ FROM ECacheObjects").fetchall()
            con.close()
        except Exception:
            continue
        for uid, obj in rows:
            m = _re.search(r"^SUMMARY[^:]*:(.*)$", obj or "", _re.M)
            if m and match.lower() in m.group(1).lower():
                out.append((uid, m.group(1).strip(), cal))
    return out


# ---------------------------------------------------------------- cli
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "writable":
        cals = writable_calendars()
        print("\n".join(cals) if cals else "(none)")
        return 0
    if cmd == "create":
        if len(sys.argv) < 4:
            print("usage: cal_write.py create <summary> <start> [minutes]",
                  file=sys.stderr)
            return 1
        try:
            start = parse_start(sys.argv[3])
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
        minutes = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        r = create_event(sys.argv[2], start, minutes)
        print(r.get("out") or f"❌ {r.get('err')}")
        return 0 if r["ok"] else 1
    if cmd == "delete":
        if len(sys.argv) < 3:
            print("usage: cal_write.py delete <ical-uid>", file=sys.stderr); return 1
        r = delete_event(sys.argv[2])
        print(r.get("out") or f"❌ {r.get('err')}")
        return 0 if r["ok"] else 1
    if cmd == "find":
        for uid, summary, cal in find_events(sys.argv[2] if len(sys.argv) > 2 else ""):
            print(f"{uid}\t{summary}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
