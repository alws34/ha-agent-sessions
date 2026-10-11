// Agent Sessions card: one slide per server (sensor with attribute integration=agent_sessions).
// Running sessions with Stop, recent sessions with Resume, and a New-session dialog with the flag checklist.
const DOMAIN = "agent_sessions";
const TOOL = { claude: "Claude Code", codex: "Codex CLI" };
const BIN = { claude: "claude", codex: "codex" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ago = (iso) => {
  const s = (Date.now() - new Date(iso)) / 1000;
  if (isNaN(s)) return "";
  const d = Math.floor(s / 86400), h = Math.floor(s / 3600), m = Math.floor(s / 60);
  return d ? `${d}d ago` : h ? `${h}h ago` : m ? `${m}m ago` : "just now";
};
const short = (path, home) => (home && path?.startsWith(home) ? "~" + path.slice(home.length) : path || "~");
const flagArgs = (f) => [...f.args, ...(f.fmt ? [f.fmt.replace("{}", f.value ?? "")] : [])];
const label = (f) => (f.fmt ? f.args.join(" ") + (f.fmt === "{}" ? "" : " " + f.fmt.replace("={}", "")) : f.args.join(" "));
const COLORS = { working: "#f59e0b", idle: "#22c55e", starting: "#9ca3af" };

const STYLE = `
  :host { display: block; }
  ha-card { padding: 14px; }
  .head { display: flex; align-items: center; gap: 10px; }
  .logo { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--soft-surface, rgba(127,127,127,.15)); box-shadow: var(--soft-shadow-inset, none); color: #d97757;
    font-size: 20px; flex: none; }
  /* Neumorphic themes (--soft-shadow-*): controls are raised, pressed/selected ones recessed. Others stay flat. */
  button { transition: box-shadow .15s ease, transform .1s ease; }
  button:active { box-shadow: var(--soft-shadow-inset, none) !important; transform: scale(.98); }
  .t { font-weight: 600; font-size: 15px; } .s { font-size: 12px; color: var(--secondary-text-color); }
  .min { min-width: 0; flex: 1; } .min > div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nav { display: flex; gap: 8px; } .nb { width: 32px; height: 32px; border-radius: 50%; border: none; cursor: pointer;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--primary-text-color); font-size: 16px; }
  /* padding so the scroll box doesn't clip the chips' shadows */
  .chips { display: flex; gap: 8px; margin: 6px -8px 0; padding: 6px 8px 8px; overflow-x: auto; scrollbar-width: none; }
  .chip { padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; border: none;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--secondary-text-color); cursor: pointer; }
  .chip.on { background: var(--soft-surface, #d9775726); box-shadow: var(--soft-shadow-inset, none); color: #d97757; }
  .btn { display: block; width: 100%; margin-top: 12px; padding: 10px 0; border: none; border-radius: 999px; cursor: pointer;
    font: 600 13px var(--paper-font-body1_-_font-family, inherit); background: #5b7cfa22; color: #5b7cfa;
    box-shadow: var(--soft-shadow-small, none); }
  .row { display: flex; align-items: center; gap: 10px; height: 58px; padding: 0 12px; margin-top: 12px; border-radius: 16px;
    background: var(--soft-surface, var(--secondary-background-color, rgba(127,127,127,.08)));
    box-shadow: var(--soft-shadow-small, none); min-width: 0; box-sizing: border-box; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .a { font-size: 13px; font-weight: 600; } .b { font-size: 11px; color: var(--secondary-text-color); }
  .pill { flex: none; padding: 6px 11px; border-radius: 999px; font-size: 12px; font-weight: 600; border: none; cursor: pointer;
    box-shadow: var(--soft-shadow-small, none); }
  .st { flex: none; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; box-shadow: var(--soft-shadow-inset, none); }
  .tool { flex: none; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 6px; background: rgba(127,127,127,.15);
    color: var(--secondary-text-color); margin-left: 6px; vertical-align: 1px; }
  .stop { background: #ef444422; color: #ef4444; } .resume { background: #22c55e22; color: #22c55e; }
  .ghost { background: var(--soft-surface, rgba(127,127,127,.14)); color: var(--primary-text-color); }
  .sub { font-size: 12px; font-weight: 700; color: var(--secondary-text-color); margin: 16px 2px 0; text-transform: uppercase;
    letter-spacing: .06em; }
  .more { text-align: center; font-size: 12px; color: var(--secondary-text-color); margin-top: 10px; cursor: pointer; }
  .empty { font-size: 12px; color: var(--secondary-text-color); margin-top: 12px; }
  .off { margin-top: 12px; padding: 10px 12px; border-radius: 12px; background: #ef444418; color: #ef4444; font-size: 12px; }
  .dots { display: flex; justify-content: center; gap: 6px; margin-top: 12px; }
  .dots b { width: 7px; height: 7px; border-radius: 4px; background: rgba(127,127,127,.3); }
  .dots b.on { background: #d97757; width: 18px; }
  .busy { opacity: .5; pointer-events: none; }
`;

class AgentSessionsCard extends HTMLElement {
  setConfig(config) {
    this._config = { recent: 3, ...config };
    this._idx = 0;
    this._more = false;
    this._confirm = null;
    this._busy = new Set();
  }

  static getStubConfig() { return {}; }
  getCardSize() { return 6; }

  _servers() {
    const st = this._hass.states;
    const ids = this._config.entities || Object.keys(st).filter((id) => st[id].attributes?.integration === DOMAIN);
    return ids.map((id) => st[id]).filter(Boolean).sort((a, b) => a.attributes.server.localeCompare(b.attributes.server));
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;
    const now = this._servers();
    if (prev && this._last && now.length === this._last.length && now.every((s, i) => s === this._last[i])) return;
    this._last = now;
    this._render();
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._click(e));
      this.shadowRoot.addEventListener("touchstart", (e) => (this._x = e.touches[0].clientX), { passive: true });
      this.shadowRoot.addEventListener("touchend", (e) => {
        const dx = e.changedTouches[0].clientX - (this._x ?? 0);
        if (Math.abs(dx) > 60) this._go(this._idx + (dx < 0 ? 1 : -1));
      }, { passive: true });
    }
    const servers = this._last || [];
    if (!servers.length) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="empty">No Agent Sessions servers yet.
        Add one under Settings → Devices &amp; services → Add integration → Agent Sessions.</div></ha-card>`;
      return;
    }
    this._idx = Math.min(this._idx, servers.length - 1);
    const s = servers[this._idx], a = s.attributes;
    const home = a.home || "";
    const both = (a.tools || []).length > 1;
    const toolTag = (t) => (both && t ? `<span class="tool">${esc(t === "codex" ? "Codex" : "Claude")}</span>` : "");
    const running = (a.running || []).map((r) => {
      const c = COLORS[r.status] || COLORS.starting, busy = this._busy.has(r.id) ? " busy" : "";
      if (this._confirm === r.id) {
        return `<div class="row"><div class="min"><div class="a">Stop “${esc(r.title || r.name)}”?</div>
          <div class="b">Its screen will be closed.</div></div>
          <button class="pill ghost" data-act="cancel">Cancel</button>
          <button class="pill stop" data-act="stop-yes" data-id="${esc(r.id)}">Stop</button></div>`;
      }
      return `<div class="row${busy}"><span class="dot" style="background:${c}"></span>
        <div class="min"><div class="a">${esc(r.title || "New session")}${toolTag(r.tool)}</div>
        <div class="b">${esc(r.name)} · ${esc(short(r.cwd, home))}${r.started ? " · " + ago(r.started).replace(" ago", "") : ""}</div></div>
        <span class="st" style="background:${c}26;color:${c}">${esc(r.status)}</span>
        <button class="pill stop" data-act="stop" data-id="${esc(r.id)}">■ Stop</button></div>`;
    }).join("");
    const all = a.recent || [], shown = this._more ? all : all.slice(0, this._config.recent);
    const recent = shown.map((r) => `<div class="row${this._busy.has(r.session_id) ? " busy" : ""}">
        <span class="dot" style="background:#9ca3af"></span>
        <div class="min"><div class="a">${esc(r.title)}${toolTag(r.tool)}</div>
        <div class="b">${ago(r.updated)} · ${esc(short(r.cwd, home))}</div></div>
        <button class="pill resume" data-act="resume" data-id="${esc(r.session_id)}" data-tool="${esc(r.tool)}">▶ Resume</button></div>`).join("");
    const status = a.online ? `${a.user}@${a.host} · ${(a.running || []).length} running` : `${a.user}@${a.host} · offline`;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>
      <div class="head"><div class="logo">✳</div>
        <div class="min"><div class="t">${esc(a.server)}</div><div class="s">${esc(status)}</div></div>
        ${servers.length > 1 ? `<div class="nav"><button class="nb" data-act="prev" aria-label="Previous server">‹</button>
          <button class="nb" data-act="next" aria-label="Next server">›</button></div>` : ""}</div>
      ${servers.length > 1 ? `<div class="chips">${servers.map((x, i) => `<button class="chip${i === this._idx ? " on" : ""}"
        data-act="go" data-i="${i}">${esc(x.attributes.server)} · ${(x.attributes.running || []).length}</button>`).join("")}</div>` : ""}
      ${a.online ? `<button class="btn" data-act="new">+ New session</button>` : `<div class="off">Can't reach ${esc(a.server)}: ${esc(a.error)}</div>`}
      ${running || (a.online ? `<div class="empty">Nothing running.</div>` : "")}
      ${all.length ? `<div class="sub">Recent</div>${recent}` : ""}
      ${all.length > this._config.recent ? `<div class="more" data-act="more">${this._more ? "Show less" : `Show ${all.length - this._config.recent} more`}</div>` : ""}
      ${servers.length > 1 ? `<div class="dots">${servers.map((_, i) => `<b class="${i === this._idx ? "on" : ""}"></b>`).join("")}</div>` : ""}
    </ha-card>`;
  }

  _go(i) {
    const n = (this._last || []).length;
    if (!n) return;
    this._idx = (i + n) % n;
    this._more = false;
    this._confirm = null;
    this._render();
  }

  async _call(service, data, key) {
    const a = this._last[this._idx].attributes;
    this._busy.add(key);
    this._render();
    try {
      await this._hass.callService(DOMAIN, service, { config_entry_id: a.config_entry_id, ...data });
    } catch (err) {
      this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message: err.message || String(err) }, bubbles: true, composed: true }));
    } finally {
      this._busy.delete(key);
      this._render();
    }
  }

  _click(e) {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const a = this._last[this._idx]?.attributes;
    const act = el.dataset.act, id = el.dataset.id;
    if (act === "prev") this._go(this._idx - 1);
    else if (act === "next") this._go(this._idx + 1);
    else if (act === "go") this._go(+el.dataset.i);
    else if (act === "more") { this._more = !this._more; this._render(); }
    else if (act === "cancel") { this._confirm = null; this._render(); }
    else if (act === "stop" && a.confirm_stop) { this._confirm = id; this._render(); }
    else if (act === "stop" || act === "stop-yes") { this._confirm = null; this._call("stop_session", { session: id }, id); }
    else if (act === "resume") {
      const tool = el.dataset.tool;
      const args = (a.flags[tool] || []).filter((f) => f.default && f.resume).flatMap(flagArgs);
      this._call("resume_session", { tool, session_id: id, args }, id);
    } else if (act === "new") openDialog(this, a);
  }
}

// ---------- New-session dialog (attached to <body> so pop-ups and transformed parents can't clip it) ----------
const DSTYLE = `
  .scrim { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 9999; display: flex; align-items: center;
    justify-content: center; padding: 14px; box-sizing: border-box; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .dlg { background: var(--soft-surface, var(--ha-card-background, var(--card-background-color, #fff))); color: var(--primary-text-color);
    border-radius: 22px; padding: 18px; width: 100%; max-width: 420px; max-height: 100%; overflow-y: auto; box-sizing: border-box;
    box-shadow: 0 20px 50px rgba(0,0,0,.3); }
  h3 { margin: 0 0 2px; font-size: 17px; } .s { font-size: 12px; color: var(--secondary-text-color); }
  label.l { display: block; font-size: 12px; font-weight: 600; color: var(--secondary-text-color); margin-top: 14px; }
  input[type=text], select { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px 12px; border-radius: 12px;
    border: none; box-shadow: var(--soft-shadow-inset, inset 0 0 0 1px var(--divider-color, rgba(127,127,127,.3)));
    background: transparent; color: inherit; font-size: 13px; outline: none; }
  input[type=text]:focus, select:focus { box-shadow: var(--soft-shadow-inset, inset 0 0 0 1px #d97757), inset 0 0 0 1px #d9775799; }
  button { transition: box-shadow .15s ease, transform .1s ease; }
  button:active { box-shadow: var(--soft-shadow-inset, none) !important; transform: scale(.98); }
  .tools { display: flex; gap: 6px; margin-top: 6px; }
  .tools button { flex: 1; padding: 8px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--secondary-text-color); }
  .tools button.on { background: var(--soft-surface, #d9775726); box-shadow: var(--soft-shadow-inset, none); color: #d97757; }
  .chk { display: flex; align-items: center; gap: 10px; padding: 7px 2px; font: 12.5px ui-monospace, Menlo, monospace; }
  .chk input[type=checkbox] { appearance: none; -webkit-appearance: none; width: 20px; height: 20px; flex: none; margin: 0;
    border-radius: 6px; cursor: pointer; display: grid; place-content: center;
    box-shadow: var(--soft-shadow-inset, inset 0 0 0 1.5px var(--secondary-text-color)); }
  .chk input[type=checkbox]:checked { background: #d97757; box-shadow: var(--soft-shadow-small, none); }
  .chk input[type=checkbox]:checked::after { content: ""; width: 5px; height: 10px; margin-top: -2px;
    border: solid #fff; border-width: 0 2.5px 2.5px 0; transform: rotate(45deg); }
  .chk input[type=checkbox]:focus-visible { outline: 2px solid #d97757; outline-offset: 2px; }
  .chk .v { margin-left: auto; width: 120px; margin-top: 0; padding: 5px 9px; font-family: inherit; }
  .chk .c { margin-left: auto; font: 11px sans-serif; color: var(--secondary-text-color); }
  .prev { margin-top: 12px; padding: 10px; border-radius: 12px; background: var(--soft-surface, rgba(127,127,127,.12));
    box-shadow: var(--soft-shadow-inset, none); font: 11px ui-monospace, monospace;
    color: var(--secondary-text-color); word-break: break-all; }
  .btns { display: flex; gap: 10px; margin-top: 16px; }
  .btns button { flex: 1; padding: 10px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600; font-size: 13px;
    box-shadow: var(--soft-shadow-small, none); }
  .cancel { background: var(--soft-surface, rgba(127,127,127,.14)); color: var(--primary-text-color); }
  .start { background: #5b7cfa22; color: #5b7cfa; }
`;

function openDialog(card, a) {
  const host = document.createElement("agent-sessions-dialog");
  const root = host.attachShadow({ mode: "open" });
  document.body.appendChild(host);
  const state = { tool: a.default_tool || a.tools[0], flags: {} };
  const close = () => host.remove();
  const flagsOf = (t) => {
    if (!state.flags[t]) state.flags[t] = (a.flags[t] || []).map((f) => ({ ...f, on: f.default }));
    return state.flags[t];
  };
  const args = () => flagsOf(state.tool).filter((f) => f.on).flatMap(flagArgs);
  const preview = () => [BIN[state.tool], ...args()].map((x) => (/\s/.test(x) ? `'${x}'` : x)).join(" ");
  const draw = () => {
    const keep = { folder: root.querySelector("#folder")?.value ?? a.folders[0], name: root.querySelector("#name")?.value ?? "" };
    root.innerHTML = `<style>${DSTYLE}</style><div class="scrim"><div class="dlg" role="dialog" aria-label="New session">
      <h3>New session</h3><div class="s">on ${esc(a.server)} (${esc(a.user)}@${esc(a.host)})</div>
      ${a.tools.length > 1 ? `<label class="l">Tool</label><div class="tools">${a.tools.map((t) =>
        `<button data-tool="${t}" class="${t === state.tool ? "on" : ""}">${TOOL[t]}</button>`).join("")}</div>` : ""}
      <label class="l" for="folder">Folder</label>
      <input type="text" id="folder" list="favs" value="${esc(keep.folder)}" autocomplete="off">
      <datalist id="favs">${a.folders.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
      <div class="s" style="margin-top:4px">Favorites from settings · or type any path</div>
      <label class="l" for="name">Name (optional)</label>
      <input type="text" id="name" value="${esc(keep.name)}" placeholder="e.g. bugfix-login">
      <label class="l">Flags · defaults from settings</label>
      ${flagsOf(state.tool).map((f, i) => `<label class="chk"><input type="checkbox" data-i="${i}" ${f.on ? "checked" : ""}>
        <span>${esc(label(f))}</span>
        ${f.choices ? `<select class="v" data-v="${i}">${f.choices.map((c) => `<option ${c === f.value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`
          : f.fmt ? `<input type="text" class="v" data-v="${i}" value="${esc(f.value)}" placeholder="value">`
          : f.custom ? `<span class="c">custom</span>` : ""}</label>`).join("")}
      <div class="prev">${esc(preview())}</div>
      <div class="btns"><button class="cancel">Cancel</button><button class="start">Start</button></div>
    </div></div>`;
  };
  root.addEventListener("click", (e) => {
    if (e.target.classList.contains("scrim") || e.target.classList.contains("cancel")) close();
    else if (e.target.dataset.tool) { state.tool = e.target.dataset.tool; draw(); }
    else if (e.target.classList.contains("start")) {
      const data = { tool: state.tool, folder: root.querySelector("#folder").value.trim() || "~", args: args(),
        name: root.querySelector("#name").value.trim() };
      close();
      card._call("new_session", data, "new");
    }
  });
  root.addEventListener("change", (e) => {
    const t = e.target, fl = flagsOf(state.tool);
    if (t.dataset.i !== undefined) fl[+t.dataset.i].on = t.checked;
    if (t.dataset.v !== undefined) fl[+t.dataset.v].value = t.value;
    root.querySelector(".prev").textContent = preview();
  });
  root.addEventListener("input", (e) => {
    if (e.target.dataset.v === undefined) return;
    flagsOf(state.tool)[+e.target.dataset.v].value = e.target.value;
    root.querySelector(".prev").textContent = preview();
  });
  root.addEventListener("keydown", (e) => e.key === "Escape" && close());
  draw();
  root.querySelector("#folder").focus();
}

// HA swaps window.customElements for a new registry ~70 ms into page load (2026.9+); this extra module can run before
// that and define into the old one, so define again until the current registry has it. A subclass, because the new
// registry may forward to the old one, where the class is already taken. (Same fix as ha-homehub-media.)
const define = () => {
  for (const [tag, cls] of [["agent-sessions-card", AgentSessionsCard], ["agent-sessions-dialog", AgentSessionsDialog]]) {
    if (customElements.get(tag)) continue;
    try { customElements.define(tag, cls); } catch { customElements.define(tag, class extends cls {}); }
  }
};
class AgentSessionsDialog extends HTMLElement {}
define();
for (const ms of [100, 500, 2000, 5000]) setTimeout(define, ms);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "agent-sessions-card")) {
  window.customCards.push({ type: "agent-sessions-card", name: "Agent Sessions",
    description: "Start, stop and resume Claude Code / Codex sessions on your servers." });
}
