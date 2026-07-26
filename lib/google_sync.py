#!/usr/bin/env python3
"""Google Tasks integration for the Spider-Man assistant.

Runs under the project venv (it needs the Google client libraries), so it is
invoked as a subprocess by `bin/spiderman` rather than imported.

Phase 2 (auth) commands:
    login    open a browser, consent once, store a refresh token
    status   show whether we're connected and which task lists exist
    lists    list the Google task lists
    logout   delete the stored token
"""
import json, os, sys, stat, socket, re
from pathlib import Path
from datetime import datetime, timedelta

# --- Force IPv4 ------------------------------------------------------------
# httplib2 (used by googleapiclient) tries addresses in the order the resolver
# returns them and has no happy-eyeballs fallback. On a network where IPv6 is
# advertised but not actually routable, it connects to the AAAA record and
# hangs until timeout. Restricting lookups to AF_INET avoids that entirely.
# Set SPIDERMAN_ALLOW_IPV6=1 to disable this workaround.
if os.environ.get("SPIDERMAN_ALLOW_IPV6") != "1":
    _real_getaddrinfo = socket.getaddrinfo

    def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _real_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _ipv4_only
# ---------------------------------------------------------------------------

CONF   = Path.home() / ".config" / "spiderman" / "google"
CREDS  = CONF / "credentials.json"
TOKEN  = CONF / "token.json"
# Tasks only. Calendar deliberately lives outside OAuth: calendar.readonly is a
# "sensitive" scope that Google refuses for unverified apps, and requesting it
# would force this app into Testing mode (7-day token expiry). Calendar events
# come from a secret iCal URL instead — see lib/ical_sync.py.
SCOPES = ["https://www.googleapis.com/auth/tasks"]

# shared local task store (same file the CLI and overlay use)
TASKS_FILE = Path.home() / ".config" / "spiderman" / "tasks.json"


# Google's API discards time-of-day, so we round-trip it through `notes`
# as a leading "⏰ HH:MM" marker. Tasks created in Google's own UI have no
# marker, so they fall back to this time on their due date.
DEFAULT_HH, DEFAULT_MM = 9, 0
TIME_MARKER = re.compile(r"⏰\s*(\d{1,2}):(\d{2})")

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError as e:      # venv not built yet
    print(f"❌ Google libraries missing: {e}", file=sys.stderr)
    print("   Run:  cd ~/spider-asst && ./install.sh   (or rebuild the venv)", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- helpers
def _secure(path: Path):
    """chmod 600 — tokens and secrets must not be world readable."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _save(creds: "Credentials"):
    CONF.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json())
    _secure(TOKEN)


def load_credentials(interactive: bool = False):
    """Return valid Credentials, or None.

    Refreshes silently when possible. Only opens a browser when
    interactive=True (i.e. the user explicitly ran `login`).
    """
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    # try a silent refresh
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds)
            return creds
        except Exception as e:
            if not interactive:
                print(f"⚠️  token refresh failed: {e}", file=sys.stderr)
                return None

    if not interactive:
        return None

    # full consent flow
    if not CREDS.exists():
        print(f"❌ No credentials file at {CREDS}", file=sys.stderr)
        print("   Complete Phase 0 (download the OAuth Desktop-app JSON).", file=sys.stderr)
        return None

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
    print("🌐 Opening your browser to grant access…")
    print("   If you see \"Google hasn't verified this app\":")
    print("   click  Advanced → Go to Spider-Man Assistant (unsafe)  — that's expected.\n")
    try:
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception as e:
        msg = str(e)
        if "name resolution" in msg.lower() or "Max retries" in msg or "ConnectionError" in type(e).__name__:
            print("\n❌ Network problem while exchanging the code for a token.", file=sys.stderr)
            print("   Your browser consent worked — only the final step failed.", file=sys.stderr)
            print("   This is usually a transient DNS hiccup (Tailscale split-DNS can cause it).", file=sys.stderr)
            print("\n   Check:   getent hosts oauth2.googleapis.com", file=sys.stderr)
            print("   Then simply run 'spiderman google login' again.", file=sys.stderr)
        else:
            print(f"\n❌ Login failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    _save(creds)
    return creds


def service(creds):
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------- commands
def cmd_login(args=()):
    creds = load_credentials(interactive=True)
    if not creds:
        return 1
    try:
        lists = service(creds).tasklists().list(maxResults=20).execute().get("items", [])
    except HttpError as e:
        print(f"❌ Connected, but the Tasks API rejected the call: {e}", file=sys.stderr)
        return 1
    print(f"✅ Connected! Token saved to {TOKEN}")
    print(f"   Found {len(lists)} task list(s):")
    for l in lists:
        print(f"     • {l['title']}   (id: {l['id']})")
    if creds.refresh_token:
        print("   Refresh token stored — you shouldn't need to log in again.")
    else:
        print("   ⚠️  No refresh token returned; you may need to log in again later.")
    return 0


def cmd_status(args=()):
    if not CREDS.exists():
        print("❌ credentials.json missing — Phase 0 not finished.")
        print(f"   Expected at: {CREDS}")
        return 1
    if not TOKEN.exists():
        print("🔓 Not logged in.  Run:  spiderman google login")
        return 1
    creds = load_credentials(interactive=False)
    if not creds:
        print("⚠️  Token present but invalid/expired and could not refresh.")
        print("   Run:  spiderman google login")
        return 1
    try:
        lists = service(creds).tasklists().list(maxResults=20).execute().get("items", [])
    except HttpError as e:
        print(f"⚠️  Logged in, but API call failed: {e}")
        return 1
    except Exception as e:
        print(f"⚠️  Network/API problem: {e}")
        return 1
    print("🔗 Google Tasks: CONNECTED")
    print(f"   token    : {TOKEN}")
    print(f"   scopes   : {', '.join(creds.scopes or SCOPES)}")
    print(f"   lists    : {len(lists)}")
    for l in lists:
        print(f"     • {l['title']}")
    return 0


def cmd_lists(args=()):
    creds = load_credentials(interactive=False)
    if not creds:
        print("🔓 Not logged in.  Run:  spiderman google login")
        return 1
    lists = service(creds).tasklists().list(maxResults=50).execute().get("items", [])
    for l in lists:
        print(f"{l['id']}\t{l['title']}")
    return 0


def cmd_logout(args=()):
    if TOKEN.exists():
        TOKEN.unlink()
        print("👋 Logged out — token deleted.")
        print("   (The app still appears under your Google account permissions;")
        print("    remove it at https://myaccount.google.com/permissions if you want.)")
    else:
        print("Not logged in — nothing to do.")
    return 0


# ---------------------------------------------------------------- local store
def load_local():
    try:
        return json.loads(TASKS_FILE.read_text())
    except Exception:
        return []


def save_local(tasks):
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


# ---------------------------------------------------------------- mapping
def remote_to_local(gt, listid):
    """Convert a Google task into our local record. Returns None if it has no
    due date (undated tasks can't be announced at a time)."""
    due = gt.get("due")
    if not due:
        return None
    try:
        y, m, d = (int(x) for x in due[:10].split("-"))
    except Exception:
        return None
    hh, mm = DEFAULT_HH, DEFAULT_MM
    hit = TIME_MARKER.search(gt.get("notes") or "")
    if hit:
        h, n = int(hit.group(1)), int(hit.group(2))
        if 0 <= h <= 23 and 0 <= n <= 59:
            hh, mm = h, n
    return {
        "type":   "reminder",
        "text":   gt.get("title") or "(untitled)",
        "due":    datetime(y, m, d, hh, mm).timestamp(),
        "fired":  False,
        "source": "google",
        "gid":    gt["id"],
        "glist":  listid,
        "gupdated": gt.get("updated", ""),
    }


def fetch_remote(svc):
    """All dated, incomplete tasks across every list, keyed by Google id."""
    remote = {}
    lists = svc.tasklists().list(maxResults=50).execute().get("items", [])
    for l in lists:
        lid, page = l["id"], None
        while True:
            resp = svc.tasks().list(tasklist=lid, showCompleted=False,
                                    showDeleted=False, maxResults=100,
                                    pageToken=page).execute()
            for gt in resp.get("items", []):
                rec = remote_to_local(gt, lid)
                if rec:
                    remote[rec["gid"]] = rec
            page = resp.get("nextPageToken")
            if not page:
                break
    return remote


def pull():
    """Merge Google Tasks into the local store. Returns a stats dict."""
    creds = load_credentials(interactive=False)
    if not creds:
        return {"error": "not logged in"}
    try:
        remote = fetch_remote(service(creds))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    tasks = load_local()
    by_gid = {t["gid"]: t for t in tasks if t.get("gid")}
    next_id = max([t.get("id", 0) for t in tasks], default=0) + 1
    added = updated = 0

    for gid, rec in remote.items():
        cur = by_gid.get(gid)
        if cur:
            # only touch it when Google's copy actually changed
            if cur.get("gupdated") != rec["gupdated"]:
                cur["text"] = rec["text"]
                cur["due"] = rec["due"]
                cur["gupdated"] = rec["gupdated"]
                cur["fired"] = False
                updated += 1
        else:
            rec["id"] = next_id
            next_id += 1
            tasks.append(rec)
            added += 1

    # Drop local copies of tasks completed/deleted in Google.
    # Untouched: local-only tasks (no gid) AND calendar entries, whose ids are
    # "cal:*" and live in a different remote set — reconciling them here would
    # delete every calendar event on the first Tasks sync.
    before = len(tasks)
    tasks = [t for t in tasks
             if not t.get("gid")
             or str(t["gid"]).startswith("cal:")
             or t["gid"] in remote]
    removed = before - len(tasks)

    save_local(tasks)
    return {"added": added, "updated": updated, "removed": removed,
            "remote": len(remote)}


def push():
    """Create Google tasks for local tasks flagged with push=True.

    Runs before pull() so freshly created tasks already carry a gid and are
    never duplicated. Offline-safe: a failure just leaves the flag set and it
    is retried on the next sync.
    """
    creds = load_credentials(interactive=False)
    if not creds:
        return {"error": "not logged in"}
    tasks = load_local()
    pending = [t for t in tasks
               if t.get("push") and not t.get("gid") and not t.get("fired")]
    if not pending:
        return {"pushed": 0}
    try:
        svc = service(creds)
        lists = svc.tasklists().list(maxResults=1).execute().get("items", [])
        if not lists:
            return {"error": "no task lists in Google"}
        lid = lists[0]["id"]
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    pushed = 0
    for t in pending:
        dt = datetime.fromtimestamp(t["due"])
        body = {
            "title": t["text"],
            # the ⏰ marker is how we survive Google discarding time-of-day
            "notes": f"⏰ {dt.strftime('%H:%M')}\nfrom Spider-Man assistant",
            "due":   dt.strftime("%Y-%m-%dT00:00:00.000Z"),
        }
        try:
            r = svc.tasks().insert(tasklist=lid, body=body).execute()
        except Exception as e:
            print(f"⚠️  push failed for '{t['text']}': {e}", file=sys.stderr)
            continue
        t["gid"] = r["id"]
        t["glist"] = lid
        t["gupdated"] = r.get("updated", "")
        pushed += 1

    if pushed:
        save_local(tasks)
    return {"pushed": pushed}


def complete_remote(listid, gid):
    """Mark a task completed in Google so the next pull doesn't resurrect it."""
    creds = load_credentials(interactive=False)
    if not creds:
        return 1
    try:
        service(creds).tasks().patch(tasklist=listid, task=gid,
                                     body={"status": "completed"}).execute()
        return 0
    except Exception as e:
        print(f"⚠️  couldn't complete {gid}: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------- commands
def cmd_sync(args=()):
    # push first so new local tasks get a gid before pull reconciles
    ps = push()
    if "error" in ps:
        print(f"⚠️  push failed: {ps['error']}")
        return 1
    st = pull()
    if "error" in st:
        print(f"⚠️  pull failed: {st['error']}")
        return 1
    line = (f"🔄 synced — {st['remote']} dated task(s) in Google | "
            f"↑{ps['pushed']} pushed, +{st['added']} new, "
            f"~{st['updated']} updated, -{st['removed']} removed")
    print(line)
    return 0




def cmd_push(args=()):
    ps = push()
    if "error" in ps:
        print(f"⚠️  push failed: {ps['error']}")
        return 1
    print(f"↑ pushed {ps['pushed']} task(s) to Google Tasks")
    return 0


def cmd_tasks(args=()):
    """Show the dated tasks currently in Google."""
    creds = load_credentials(interactive=False)
    if not creds:
        print("🔓 Not logged in.  Run:  spiderman google login")
        return 1
    remote = fetch_remote(service(creds))
    if not remote:
        print("🕸️  No dated tasks in Google Tasks.")
        return 0
    print(f"🕷️  {len(remote)} dated task(s) in Google:")
    for rec in sorted(remote.values(), key=lambda r: r["due"]):
        when = datetime.fromtimestamp(rec["due"]).strftime("%d %b %H:%M")
        print(f"   {when}   {rec['text']}")
    return 0


def cmd_complete(args=()):
    if len(args) < 2:
        print("usage: google_sync.py complete <tasklist-id> <task-id>", file=sys.stderr)
        return 1
    return complete_remote(args[0], args[1])


CMDS = {"login": cmd_login, "status": cmd_status,
        "lists": cmd_lists, "logout": cmd_logout,
        "sync": cmd_sync, "push": cmd_push, "tasks": cmd_tasks,
        "complete": cmd_complete}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        return 1
    return CMDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
