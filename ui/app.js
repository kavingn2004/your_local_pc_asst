/* Spider-Man Assistant — control panel
   React via vendored UMD + htm (tagged templates), so there's no build step
   and no node_modules. Talks to bin/spiderman-ui over /api. */
const { useState, useEffect, useCallback, useRef } = React;
const html = htm.bind(React.createElement);

const api = {
  status: () => fetch("/api/status").then(r => r.json()),
  act: (body) => fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json()),
};

const fmtWhen = (epoch) => {
  if (!epoch) return "";
  const d = new Date(epoch * 1000), now = new Date();
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now.getTime() + 864e5).toDateString() === d.toDateString();
  if (sameDay) return t;
  if (tomorrow) return `tomorrow ${t}`;
  return `${d.toLocaleDateString([], { day: "2-digit", month: "short" })} ${t}`;
};

const ICON = { reminder: "🔔", alarm: "⏰", event: "📅" };

/* ---------------------------------------------------------------- bits */
function Pill({ kind, children }) {
  return html`<span class=${"pill " + (kind || "dim")}>${children}</span>`;
}

function Toggle({ checked, onChange, disabled }) {
  return html`
    <label class="switch">
      <input type="checkbox" checked=${!!checked} disabled=${disabled}
             onChange=${e => onChange(e.target.checked)} />
      <span class="slider"></span>
    </label>`;
}

function Row({ label, hint, children }) {
  return html`
    <div class="row">
      <div>
        <div class="label">${label}</div>
        ${hint && html`<div class="hint">${hint}</div>`}
      </div>
      <div style=${{ display: "flex", gap: "8px", alignItems: "center" }}>${children}</div>
    </div>`;
}

/* ---------------------------------------------------------------- cards */
function Assistant({ s, run, busy }) {
  const a = s.assistant;
  return html`
    <div class="card">
      <h2>🕷️ Assistant</h2>
      <${Row} label="Character" hint=${a.running ? "running on your desktop" : "not running"}>
        <${Pill} kind=${a.running ? "ok" : "bad"}>${a.running ? "on" : "off"}<//>
        <button disabled=${busy} onClick=${() => run(a.running ? "stop" : "start")}>
          ${a.running ? "Stop" : "Start"}
        </button>
      <//>
      <${Row} label="Alerts" hint=${a.muted ? "muted — nothing spoken" : "speech + voice active"}>
        <${Toggle} checked=${!a.muted} disabled=${busy}
                   onChange=${v => run(v ? "unmute" : "mute")} />
      <//>
      <${Row} label="Start at login">
        <${Toggle} checked=${a.autostart} disabled=${busy}
                   onChange=${v => run(v ? "enable" : "disable")} />
      <//>
    </div>`;
}

function Battery({ b }) {
  if (!b) return null;
  const low = b.percent <= 20, charging = /charg/i.test(b.status);
  const color = low && !charging ? "var(--bad)" : b.percent < 50 ? "var(--warn)" : "var(--ok)";
  return html`
    <div class="card">
      <h2>🔋 Battery</h2>
      <${Row} label=${`${b.percent}% — ${b.status}`}
              hint=${b.health != null ? `health ${b.health}% of design capacity` : null}>
        <${Pill} kind=${charging ? "ok" : low ? "bad" : "dim"}>
          ${charging ? "charging" : low ? "low" : "on battery"}<//>
      <//>
      <div class="bar"><span style=${{ width: b.percent + "%", background: color }}></span></div>
      ${b.health != null && b.health < 70 && html`
        <div class="note">Battery health is ${b.health}% of its original capacity —
          expect reduced runtime.</div>`}
    </div>`;
}

function Google({ g, run, busy }) {
  const connected = g.state === "connected";
  const kind = connected ? "ok" : g.state === "unconfigured" ? "bad" : "warn";
  return html`
    <div class="card">
      <h2>✅ Google Tasks</h2>
      <${Row} label="Connection"
              hint=${connected ? (g.lists || []).join(", ") : g.state.replace("_", " ")}>
        <${Pill} kind=${kind}>${connected ? "connected" : g.state.replace("_", " ")}<//>
      <//>
      ${connected && html`
        <${Row} label="Auto-push new reminders"
                hint="send every reminder you create to Google Tasks">
          <${Toggle} checked=${g.auto_push} disabled=${busy}
                     onChange=${v => run("google_auto", { value: v })} />
        <//>
        <${Row} label="Sync" hint="pull from Google + push pending">
          <button disabled=${busy} onClick=${() => run("google_sync")}>Sync now</button>
        <//>`}
      ${!connected && html`
        <div class="note bad">
          ${g.state === "unconfigured"
            ? "No credentials.json — complete the Google Cloud setup first."
            : "Not connected. Run in a terminal: spiderman google login"}
        </div>`}
    </div>`;
}

function Calendar({ c, run, busy }) {
  return html`
    <div class="card">
      <h2>📅 Calendar</h2>
      <${Row} label="Source" hint="via GNOME Online Accounts → Evolution">
        <${Pill} kind=${c.available ? "ok" : "warn"}>
          ${c.available ? `${c.calendars.length} found` : "none"}<//>
      <//>
      ${(c.calendars || []).map(cal => html`
        <${Row} key=${cal.id} label=${(cal.sample && cal.sample[0]) || cal.id}
                hint=${`${cal.count} entries`}>
          <${Toggle} checked=${cal.included} disabled=${busy}
            onChange=${v => run(v ? "calendar_include" : "calendar_exclude", { id: cal.id })} />
        <//>`)}
      <${Row} label="Upcoming (24h)"
              hint=${(c.events && c.events.length) ? null : "nothing scheduled"}>
        <button disabled=${busy} onClick=${() => run("calendar_refresh")}>Refresh</button>
      <//>
      ${(c.events || []).length > 0 && html`
        <ul class="list">${c.events.slice(0, 6).map((e, i) => html`<li key=${i}>${e}</li>`)}</ul>`}
      ${!c.available && html`
        <div class="note">Add your account in Settings → Online Accounts and enable Calendar.</div>`}
    </div>`;
}

function Slack({ s }) {
  return html`
    <div class="card">
      <h2>💬 Slack</h2>
      <${Row} label="Message announcements"
              hint=${s.installed ? (s.running ? "Slack is running" : "Slack installed, not running")
                                 : "Slack not installed"}>
        <${Pill} kind="bad">unavailable<//>
      <//>
      <div class="note bad">${s.detail}</div>
    </div>`;
}

function Tasks({ tasks, run, busy, googleReady }) {
  const [text, setText] = useState("");
  const [when, setWhen] = useState("");
  const [toGoogle, setToGoogle] = useState(false);
  const add = () => {
    if (!text.trim() || !when.trim()) return;
    run("add_task", { text: text.trim(), when: when.trim(), google: toGoogle })
      .then(() => { setText(""); setWhen(""); });
  };
  return html`
    <div class="card" style=${{ gridColumn: "1 / -1" }}>
      <h2>📋 Reminders & events <span class="pill dim">${tasks.length}</span></h2>
      ${tasks.length === 0
        ? html`<div class="hint">Nothing scheduled.</div>`
        : html`<ul class="tasks">${tasks.map(t => html`
            <li key=${t.id}>
              <span>${ICON[t.type] || "🔔"}</span>
              <span class="grow">${t.text}</span>
              ${t.source !== "local" && html`<${Pill} kind="dim">${t.source}<//>`}
              <span class=${"when" + (t.overdue ? " overdue" : "")}>${fmtWhen(t.due)}</span>
              <button class="x" title="cancel" disabled=${busy}
                      onClick=${() => run("cancel_task", { id: t.id })}>×</button>
            </li>`)}</ul>`}
      <div class="addrow">
        <input type="text" placeholder="Remind me to…" value=${text}
               onInput=${e => setText(e.target.value)}
               onKeyDown=${e => e.key === "Enter" && add()} />
        <input type="text" class="when-in" placeholder="30m / 14:30" value=${when}
               onInput=${e => setWhen(e.target.value)}
               onKeyDown=${e => e.key === "Enter" && add()} />
        ${googleReady && html`
          <label class="chk">
            <input type="checkbox" checked=${toGoogle}
                   onChange=${e => setToGoogle(e.target.checked)} /> Google
          </label>`}
        <button class="primary" disabled=${busy || !text.trim() || !when.trim()}
                onClick=${add}>Add</button>
      </div>
      <div class="hint" style=${{ marginTop: "8px" }}>
        Time accepts 30m, 1h30m, 90s, 14:30, 9am.
      </div>
    </div>`;
}

/* ---------------------------------------------------------------- app */
function App() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try { setS(await api.status()); }
    catch (e) { setToast({ bad: true, msg: "Can't reach the server" }); }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 10000);   // keep it fresh
    return () => clearInterval(timer.current);
  }, [load]);

  const run = useCallback(async (action, extra) => {
    setBusy(true);
    try {
      const r = await api.act({ action, ...(extra || {}) });
      const msg = (r.out || r.err || "done").split("\n")[0].slice(0, 90);
      setToast({ bad: r.ok === false, msg });
      await load();
      return r;
    } finally {
      setBusy(false);
      setTimeout(() => setToast(null), 3200);
    }
  }, [load]);

  if (!s) return html`<div class="wrap"><div class="hint">Loading…</div></div>`;

  const googleReady = s.google.state === "connected";
  return html`
    <div class="wrap">
      <header>
        <div class="logo">🕷️</div>
        <div>
          <h1>Spider-Man Assistant</h1>
          <div class="sub">Local control panel — nothing leaves this machine</div>
        </div>
      </header>
      <div class="grid">
        <${Assistant} s=${s} run=${run} busy=${busy} />
        <${Battery} b=${s.battery} />
        <${Google} g=${s.google} run=${run} busy=${busy} />
        <${Calendar} c=${s.calendar} run=${run} busy=${busy} />
        <${Slack} s=${s.slack} />
        <${Tasks} tasks=${s.tasks} run=${run} busy=${busy} googleReady=${googleReady} />
      </div>
      <div class="foot">
        Refreshes every 10s · served from 127.0.0.1 only ·
        <a href="/docs" style=${{ color: "var(--dim)" }}>API docs</a>
      </div>
      ${toast && html`<div class=${"toast" + (toast.bad ? " bad" : "")}>${toast.msg}</div>`}
    </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
