// Agent Sessions card: one slide per server (sensors of the agent_sessions integration).
// Running sessions with Stop, recent sessions with Resume, a New-session dialog with the flag checklist, a resume
// picker that lists sessions from every server (and can move a Claude Code session to this one), and a card editor.
const DOMAIN = "agent_sessions";
const TOOL = { claude: "Claude Code", codex: "Codex CLI" };
const BIN = { claude: "claude", codex: "codex" };
const SAVED = "agent-sessions-card:server"; // the server picked last, per browser (localStorage)
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ago = (iso) => {
  const s = (Date.now() - new Date(iso)) / 1000;
  if (isNaN(s)) return "";
  const d = Math.floor(s / 86400), h = Math.floor(s / 3600), m = Math.floor(s / 60);
  return d ? `${d}d ago` : h ? `${h}h ago` : m ? `${m}m ago` : "just now";
};
const short = (path, home) => (home && path?.startsWith(home) ? "~" + path.slice(home.length) : path || "~");
const flagArgs = (f) => [...f.args, ...(f.fmt ? [f.fmt.replace("{}", f.value ?? "")] : [])];
// a flag that takes a value can't be used without one (Codex's model has no default, and "-m ''" is refused)
const usable = (f) => !f.fmt || String(f.value ?? "").trim() !== "";
const label = (f) => (f.fmt ? f.args.join(" ") + (f.fmt === "{}" ? "" : " " + f.fmt.replace("={}", "")) : f.args.join(" "));
const COLORS = { working: "#f59e0b", idle: "#22c55e", starting: "#9ca3af" };
const store = (v) => { try { return v === undefined ? localStorage.getItem(SAVED) : localStorage.setItem(SAVED, v); } catch { return null; } };
const notify = (el, err) => el.dispatchEvent(new CustomEvent("hass-notification",
  { detail: { message: err?.message || String(err) }, bubbles: true, composed: true }));
const LOGO = `<svg viewBox="0 0 64 64" width="36" height="36" aria-hidden="true"><rect x="2" y="2" width="60" height="60" rx="15" fill="#f4ede6"/><rect x="17" y="10" width="38" height="28" rx="6" fill="#e6d8cc"/><rect x="13" y="16" width="38" height="28" rx="6" fill="#d9c4b2"/><rect x="9" y="22" width="40" height="32" rx="7" fill="#1f1a16"/><circle cx="15" cy="28" r="1.7" fill="#e0453a"/><circle cx="20.5" cy="28" r="1.7" fill="#e0951a"/><circle cx="26" cy="28" r="1.7" fill="#22a35a"/><path d="M15 36 L21 40.5 L15 45" fill="none" stroke="#d97757" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/><rect x="24" y="43" width="9" height="3.2" rx="1.6" fill="#ede8e2"/></svg>`;

// Our sensors only: the attribute alone could be faked by another integration (e.g. an MQTT sensor), the entity
// registry's platform can't.
const ours = (hass, id) => hass.states[id]?.attributes?.integration === DOMAIN && (!hass.entities || hass.entities[id]?.platform === DOMAIN);

// Server order: the card's own (editor: order/hide, or the older entities list), then each server's Position
// option, then the name.
function orderedIds(hass, config, includeHidden = false) {
  const all = Object.keys(hass.states).filter((id) => ours(hass, id));
  if (config.entities && !includeHidden) return config.entities.filter((id) => all.includes(id));
  const order = config.entities || config.order || [];
  const hide = new Set(config.hide || []);
  const rank = (id) => { const i = order.indexOf(id); return i < 0 ? 1e9 : i; };
  const at = (id) => hass.states[id].attributes;
  return all.filter((id) => includeHidden || !hide.has(id)).sort((x, y) => rank(x) - rank(y)
    || (at(x).position ?? 1) - (at(y).position ?? 1) || String(at(x).server).localeCompare(String(at(y).server)));
}

const STYLE = `
  :host { display: block; }
  ha-card { padding: 14px; }
  .head { display: flex; align-items: center; gap: 10px; }
  .logo { width: 36px; height: 36px; flex: none; display: block; }
  /* Neumorphic themes (--soft-shadow-*): controls are raised, pressed/selected ones recessed. Others stay flat. */
  button { transition: box-shadow .15s ease, transform .1s ease; }
  button:active { box-shadow: var(--soft-shadow-inset, none) !important; transform: scale(.98); }
  .t { font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 7px; }
  .s { font-size: 12px; color: var(--secondary-text-color); }
  .min { min-width: 0; flex: 1; } .min > div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nav { display: flex; gap: 8px; } .nb { width: 32px; height: 32px; border-radius: 50%; border: none; cursor: pointer;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--primary-text-color); font-size: 16px; }
  /* reachable / can't reach */
  .up, .down { width: 8px; height: 8px; border-radius: 50%; flex: none; display: inline-block; }
  .up { background: #22c55e; box-shadow: 0 0 0 3px #22c55e2e; } .down { background: #ef4444; box-shadow: 0 0 0 3px #ef44442e; }
  /* padding so the scroll box doesn't clip the chips' shadows */
  .chips { display: flex; gap: 8px; margin: 6px -8px 0; padding: 6px 8px 8px; overflow-x: auto; scrollbar-width: none; }
  .chip { padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; border: none;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--secondary-text-color); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
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
    letter-spacing: .06em; display: flex; justify-content: space-between; align-items: baseline; }
  .sub button { border: none; background: none; padding: 0; cursor: pointer; color: #5b7cfa; font: 600 12px inherit;
    text-transform: none; letter-spacing: 0; }
  .more { text-align: center; font-size: 12px; color: var(--secondary-text-color); margin-top: 10px; cursor: pointer; }
  .empty { font-size: 12px; color: var(--secondary-text-color); margin-top: 12px; }
  .off { margin-top: 12px; padding: 10px 12px; border-radius: 12px; background: #ef444418; color: #ef4444; font-size: 12px; }
  .warn { margin-top: 12px; padding: 8px 12px; border-radius: 12px; background: #f59e0b1c; color: #d48806; font-size: 12px; }
  .dots { display: flex; justify-content: center; gap: 6px; margin-top: 12px; }
  .dots b { width: 7px; height: 7px; border-radius: 4px; background: rgba(127,127,127,.3); }
  .dots b.on { background: #d97757; width: 18px; }
  .busy { opacity: .5; pointer-events: none; }
`;

class AgentSessionsCard extends HTMLElement {
  setConfig(config) {
    this._config = { recent: 3, ...config };
    this._sel = store() || null; // a config entry id; survives the card being rebuilt (view change, app reopened)
    this._more = false;
    this._confirm = null;
    this._busy = new Set();
  }

  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("agent-sessions-card-editor"); }
  getCardSize() { return 6; }

  _servers() {
    return orderedIds(this._hass, this._config).map((id) => this._hass.states[id]);
  }

  get _admin() { return this._hass?.user?.is_admin !== false; }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;
    const now = this._servers();
    if (prev && this._last && prev.user === hass.user && now.length === this._last.length
        && now.every((s, i) => s === this._last[i])) return;
    this._last = now;
    this._render();
  }

  get _idx() {
    const i = (this._last || []).findIndex((s) => s.attributes.config_entry_id === this._sel);
    return i < 0 ? 0 : i;
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
    const idx = this._idx, s = servers[idx], a = s.attributes, admin = this._admin;
    const home = a.home || "";
    const both = (a.tools || []).length > 1;
    const dot = (x) => `<span class="${x.online ? "up" : "down"}" title="${x.online ? "Reachable" : "Can't reach"}"></span>`;
    const toolTag = (t) => (both && t ? `<span class="tool">${esc(t === "codex" ? "Codex" : "Claude")}</span>` : "");
    const running = (a.running || []).map((r) => {
      const c = COLORS[r.status] || COLORS.starting, busy = this._busy.has(r.id) ? " busy" : "";
      if (this._confirm === r.id) {
        return `<div class="row"><div class="min"><div class="a">Stop “${esc(r.title || r.name)}”?</div>
          <div class="b">${r.name?.startsWith("agent-") ? "Its screen will be closed." : "The tool stops; your screen stays."}</div></div>
          <button class="pill ghost" data-act="cancel">Cancel</button>
          <button class="pill stop" data-act="stop-yes" data-id="${esc(r.id)}">Stop</button></div>`;
      }
      return `<div class="row${busy}"><span class="dot" style="background:${c}"></span>
        <div class="min"><div class="a">${esc(r.title || "New session")}${toolTag(r.tool)}</div>
        <div class="b">${esc(r.name)} · ${esc(short(r.cwd, home))}${r.started ? " · " + ago(r.started).replace(" ago", "") : ""}</div></div>
        <span class="st" style="background:${c}26;color:${c}">${esc(r.status)}</span>
        ${admin ? `<button class="pill stop" data-act="stop" data-id="${esc(r.id)}">■ Stop</button>` : ""}</div>`;
    }).join("");
    const all = a.recent || [], shown = this._more ? all : all.slice(0, this._config.recent);
    const recent = shown.map((r) => `<div class="row${this._busy.has(r.session_id) ? " busy" : ""}">
        <span class="dot" style="background:#9ca3af"></span>
        <div class="min"><div class="a">${esc(r.title)}${toolTag(r.tool)}</div>
        <div class="b">${ago(r.updated)} · ${esc(short(r.cwd, home))}</div></div>
        ${admin ? `<button class="pill resume" data-act="resume" data-id="${esc(r.session_id)}" data-tool="${esc(r.tool)}">▶ Resume</button>` : ""}</div>`).join("");
    const status = a.online ? `${a.user}@${a.host} · ${(a.running || []).length} running` : `${a.user}@${a.host} · offline`;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>
      <div class="head"><span class="logo">${LOGO}</span>
        <div class="min"><div class="t">${dot(a)}<span>${esc(a.server)}</span></div><div class="s">${esc(status)}</div></div>
        ${servers.length > 1 ? `<div class="nav"><button class="nb" data-act="prev" aria-label="Previous server">‹</button>
          <button class="nb" data-act="next" aria-label="Next server">›</button></div>` : ""}</div>
      ${servers.length > 1 ? `<div class="chips">${servers.map((x, i) => `<button class="chip${i === idx ? " on" : ""}"
        data-act="go" data-i="${i}">${dot(x.attributes)}${esc(x.attributes.server)} · ${(x.attributes.running || []).length}</button>`).join("")}</div>` : ""}
      ${a.online && admin && a.agent_outdated ? `<div class="warn">This server's agent is out of date. Settings → Repairs shows the command that updates it.</div>` : ""}
      ${a.online ? (admin ? `<button class="btn" data-act="new">+ New session</button>` : "") : `<div class="off">Can't reach ${esc(a.server)}: ${esc(a.error)}</div>`}
      ${running || (a.online ? `<div class="empty">Nothing running.</div>` : "")}
      ${all.length ? `<div class="sub"><span>Recent</span>${admin && a.online ? `<button data-act="all">All sessions ›</button>` : ""}</div>${recent}` : ""}
      ${all.length > this._config.recent ? `<div class="more" data-act="more">${this._more ? "Show less" : `Show ${all.length - this._config.recent} more`}</div>` : ""}
      ${servers.length > 1 ? `<div class="dots">${servers.map((_, i) => `<b class="${i === idx ? "on" : ""}"></b>`).join("")}</div>` : ""}
    </ha-card>`;
  }

  _go(i) {
    const list = this._last || [], n = list.length;
    if (!n) return;
    this._sel = list[(i + n) % n].attributes.config_entry_id;
    store(this._sel);
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
      notify(this, err);
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
      const args = (a.flags[tool] || []).filter((f) => f.default && f.resume && usable(f)).flatMap(flagArgs);
      this._call("resume_session", { tool, session_id: id, args }, id);
    } else if (act === "new") openDialog(this, a);
    else if (act === "all") openDialog(this, a, { resume: true });
  }
}

// ---------- dialogs (attached to <body> so pop-ups and transformed parents can't clip them) ----------
const DSTYLE = `
  .scrim { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 9999; display: flex; align-items: center;
    justify-content: center; padding: 14px; box-sizing: border-box; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .scrim.top { z-index: 10000; }
  .dlg { background: var(--soft-surface, var(--ha-card-background, var(--card-background-color, #fff))); color: var(--primary-text-color);
    border-radius: 22px; padding: 18px; width: 100%; max-width: 420px; max-height: 100%; overflow-y: auto; box-sizing: border-box;
    box-shadow: 0 20px 50px rgba(0,0,0,.3); }
  h3 { margin: 0 0 2px; font-size: 17px; } .s { font-size: 12px; color: var(--secondary-text-color); }
  label.l { display: block; font-size: 12px; font-weight: 600; color: var(--secondary-text-color); margin-top: 14px; }
  input[type=text], select { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px 12px; border-radius: 12px;
    border: none; box-shadow: var(--soft-shadow-inset, inset 0 0 0 1px var(--divider-color, rgba(127,127,127,.3)));
    background: transparent; color: inherit; font-size: 13px; outline: none; }
  input[type=text]:focus, select:focus { box-shadow: var(--soft-shadow-inset, inset 0 0 0 1px #d97757), inset 0 0 0 1px #d9775799; }
  input[type=text]:disabled { opacity: .65; }
  button { transition: box-shadow .15s ease, transform .1s ease; font-family: inherit; }
  button:active { box-shadow: var(--soft-shadow-inset, none) !important; transform: scale(.98); }
  .tools { display: flex; gap: 6px; margin-top: 6px; }
  .tools button { flex: 1; padding: 8px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--secondary-text-color); }
  .tools button.on { background: var(--soft-surface, #d9775726); box-shadow: var(--soft-shadow-inset, none); color: #d97757; }
  .chk { display: flex; align-items: center; gap: 10px; padding: 7px 2px; font: 12.5px ui-monospace, Menlo, monospace; }
  .chk.dim { opacity: .5; }
  .chk input[type=checkbox] { appearance: none; -webkit-appearance: none; width: 20px; height: 20px; flex: none; margin: 0;
    border-radius: 6px; cursor: pointer; display: grid; place-content: center;
    box-shadow: var(--soft-shadow-inset, inset 0 0 0 1.5px var(--secondary-text-color)); }
  .chk input[type=checkbox]:disabled { cursor: default; }
  .chk input[type=checkbox]:checked { background: #d97757; box-shadow: var(--soft-shadow-small, none); }
  .chk input[type=checkbox]:checked::after { content: ""; width: 5px; height: 10px; margin-top: -2px;
    border: solid #fff; border-width: 0 2.5px 2.5px 0; transform: rotate(45deg); }
  .chk input[type=checkbox]:focus-visible { outline: 2px solid #d97757; outline-offset: 2px; }
  .chk .v { margin-left: auto; width: 120px; margin-top: 0; padding: 5px 9px; font-family: inherit; }
  .chk .c { margin-left: auto; font: 11px sans-serif; color: var(--secondary-text-color); text-align: right; }
  .chk .c.no { color: #d48806; }
  .picked { margin: 2px 0 4px 30px; padding: 10px 12px; border-radius: 12px; display: flex; gap: 10px; align-items: center;
    background: var(--soft-surface, rgba(127,127,127,.1)); box-shadow: var(--soft-shadow-inset, none); }
  .picked .min { min-width: 0; flex: 1; } .picked .min div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .a { font-size: 13px; font-weight: 600; } .b { font-size: 11px; color: var(--secondary-text-color); }
  .link { border: none; background: none; color: #5b7cfa; font-weight: 600; font-size: 12px; cursor: pointer; flex: none; padding: 0; }
  .move { margin: 4px 0 4px 30px; font-size: 11.5px; color: #d48806; }
  .prev { margin-top: 12px; padding: 10px; border-radius: 12px; background: var(--soft-surface, rgba(127,127,127,.12));
    box-shadow: var(--soft-shadow-inset, none); font: 11px ui-monospace, monospace;
    color: var(--secondary-text-color); word-break: break-all; }
  .btns { display: flex; gap: 10px; margin-top: 16px; }
  .btns button { flex: 1; padding: 10px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600; font-size: 13px;
    box-shadow: var(--soft-shadow-small, none); }
  .btns button:disabled { opacity: .45; cursor: default; }
  .cancel { background: var(--soft-surface, rgba(127,127,127,.14)); color: var(--primary-text-color); }
  .start { background: #5b7cfa22; color: #5b7cfa; }
  .tool { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 6px; background: rgba(127,127,127,.15);
    color: var(--secondary-text-color); margin-left: 6px; vertical-align: 1px; }
  .up, .down { width: 8px; height: 8px; border-radius: 50%; flex: none; display: inline-block; }
  .up { background: #22c55e; } .down { background: #ef4444; }
  .fchips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .fchips button { padding: 5px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600; border: none; cursor: pointer;
    background: var(--soft-surface, rgba(127,127,127,.14)); box-shadow: var(--soft-shadow-small, none);
    color: var(--secondary-text-color); display: inline-flex; align-items: center; gap: 6px; }
  .fchips button.on { background: var(--soft-surface, #d9775726); box-shadow: var(--soft-shadow-inset, none); color: #d97757; }
  .fchips button:disabled { opacity: .5; cursor: default; }
  .grp { font: 700 11px sans-serif; text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color);
    margin: 14px 2px 4px; display: flex; align-items: center; gap: 6px; }
  .sess { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 12px; cursor: pointer; border: none;
    background: none; width: 100%; text-align: left; color: inherit; font: inherit; box-sizing: border-box; }
  .sess:hover { background: rgba(127,127,127,.1); } .sess.sel { background: #d9775722; box-shadow: inset 0 0 0 1.5px #d97757; }
  .sess:disabled { opacity: .45; cursor: not-allowed; background: none; }
  .sess .min { min-width: 0; flex: 1; } .sess .min div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .badge { flex: none; font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 8px; }
  .badge.here { background: #22c55e22; color: #16a34a; } .badge.copy { background: #f59e0b22; color: #d48806; }
  .badge.no { background: rgba(127,127,127,.15); color: var(--secondary-text-color); }
  .empty { font-size: 12px; color: var(--secondary-text-color); margin-top: 14px; }
`;

function sheet(tag, top = false) {
  const host = document.createElement(tag);
  const root = host.attachShadow({ mode: "open" });
  document.body.appendChild(host);
  root.innerHTML = `<style>${DSTYLE}</style><div class="scrim${top ? " top" : ""}"></div>`;
  return { host, root, scrim: root.querySelector(".scrim") };
}

// New session, or (with --resume) resume one: from this server, or copied from another (Claude Code only).
function openDialog(card, a, opts = {}) {
  const { host, root, scrim } = sheet("agent-sessions-dialog");
  const state = { tool: a.default_tool || a.tools[0], flags: {}, resume: false, pick: null,
    folder: a.folders[0], name: "" };
  const close = () => { host.remove(); document.removeEventListener("keydown", onKey); };
  const flagsOf = (t) => {
    if (!state.flags[t]) state.flags[t] = (a.flags[t] || []).map((f) => ({ ...f, on: f.default && usable(f) }));
    return state.flags[t];
  };
  const here = () => state.pick && state.pick.config_entry_id === a.config_entry_id;
  // Custom flags the server hasn't allowed would only fail on Start; say so up front (agents too old to tell: null).
  const builtin = (t) => new Set((a.flags[t] || []).filter((f) => !f.custom).flatMap((f) => f.args));
  const refused = (f) => f.custom && Array.isArray(a.allowed?.[state.tool])
    && !a.allowed[state.tool].some((seq) => seq.join("\0") === f.args.join("\0"))
    && !f.args.every((x) => builtin(state.tool).has(x));
  const fits = (f) => (state.resume ? f.resume !== false : !f.resume_only) && !(f.resume_only && !state.pick);
  const args = () => flagsOf(state.tool).filter((f) => f.on && usable(f) && fits(f) && !refused(f)).flatMap(flagArgs);
  const command = () => {
    const sid = state.pick?.session_id;
    const parts = state.resume && state.tool === "codex" ? [BIN.codex, "resume", ...args(), sid || "<session>"]
      : [BIN[state.tool], ...args(), ...(state.resume ? ["--resume", sid || "<session>"] : [])];
    const rc = parts.indexOf("--remote-control"); // the agent runs it last (its optional value can't take a word)
    if (rc > 0) parts.push(...parts.splice(rc, 1));
    return parts.map((x) => (/\s/.test(x) ? `'${x}'` : x)).join(" ");
  };
  const ready = () => !state.resume || !!state.pick;
  const keep = () => {
    const f = root.querySelector("#folder"), n = root.querySelector("#name");
    if (f && !f.disabled) state.folder = f.value;
    if (n) state.name = n.value;
  };
  const draw = () => { // callers save what was typed (keep) before they change state
    const p = state.pick, local = here();
    const folderVal = p ? (local ? short(p.cwd, a.home) : state.folder) : state.folder;
    const resumeLabel = state.tool === "codex" ? "resume" : "--resume";
    scrim.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="${state.resume ? "Resume a session" : "New session"}">
      <h3>${state.resume ? "Resume a session" : "New session"}</h3><div class="s">on ${esc(a.server)} (${esc(a.user)}@${esc(a.host)})</div>
      ${a.tools.length > 1 && !p ? `<label class="l">Tool</label><div class="tools">${a.tools.map((t) =>
        `<button data-tool="${t}" class="${t === state.tool ? "on" : ""}">${TOOL[t]}</button>`).join("")}</div>` : ""}
      <label class="l" for="folder">Folder</label>
      <input type="text" id="folder" list="favs" value="${esc(folderVal)}" autocomplete="off" ${p && local ? "disabled" : ""}>
      <datalist id="favs">${a.folders.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
      <div class="s" style="margin-top:4px">${p ? (local ? "The folder the session ran in" : `Folder on ${esc(a.server)}, inside ${esc(a.user)}'s home`) : "Favorites from settings · or type any path"}</div>
      <label class="l" for="name">Name (optional)${state.tool === "codex" ? " · names the screen only" : ""}</label>
      <input type="text" id="name" value="${esc(state.name)}" placeholder="${p ? esc(p.title) : "e.g. bugfix-login"}">
      <label class="l">Flags · defaults from settings</label>
      <label class="chk"><input type="checkbox" data-resume ${state.resume ? "checked" : ""}><span>${resumeLabel}</span>
        <span class="c">${p ? "" : "pick a session…"}</span></label>
      ${p ? `<div class="picked"><div class="min"><div class="a">${esc(p.title)}</div>
        <div class="b">from ${esc(p.server)} · ${esc(short(p.cwd, p.home))}${p.updated ? " · " + ago(p.updated) : ""}</div></div>
        <button class="link" data-change>Change</button></div>
        ${local ? "" : `<div class="move">The conversation is copied from ${esc(p.server)} to ${esc(a.server)}. It stays on ${esc(p.server)} too.</div>`}` : ""}
      ${flagsOf(state.tool).map((f, i) => {
        if (state.resume && f.resume === false) return "";
        const off = !fits(f), no = refused(f);
        return `<label class="chk${off || no ? " dim" : ""}"><input type="checkbox" data-i="${i}" ${f.on && !off && !no && usable(f) ? "checked" : ""}
          ${off || no || !usable(f) ? "disabled" : ""}><span>${esc(label(f))}</span>
        ${f.choices ? `<select class="v" data-v="${i}">${f.choices.map((c) => `<option ${c === f.value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`
          : f.fmt ? `<input type="text" class="v" data-v="${i}" value="${esc(f.value)}" placeholder="value">`
          : no ? `<span class="c no">not allowed on server</span>`
          : f.resume_only ? `<span class="c">with ${resumeLabel}</span>`
          : f.custom ? `<span class="c">custom</span>` : ""}</label>`;
      }).join("")}
      <div class="prev">${esc(command())}</div>
      <div class="btns"><button class="cancel">Cancel</button><button class="start" ${ready() ? "" : "disabled"}>${
        p ? (local ? "Resume" : "Copy and resume") : state.resume ? "Resume" : "Start"}</button></div>
    </div>`;
  };
  const pick = () => openPicker(card, a, state.pick, (chosen) => {
    keep();
    if (chosen) {
      state.pick = chosen;
      state.resume = true;
      state.tool = chosen.tool;
      if (chosen.config_entry_id !== a.config_entry_id) state.folder = short(chosen.cwd, chosen.home);
    } else if (!state.pick) state.resume = false;
    draw();
  });
  scrim.addEventListener("click", (e) => {
    const t = e.target;
    if (t === scrim || t.classList.contains("cancel")) close();
    else if (t.dataset.tool) { keep(); state.tool = t.dataset.tool; draw(); }
    else if (t.closest("[data-change]")) pick();
    else if (t.classList.contains("start") && ready()) {
      keep();
      const p = state.pick, name = state.name.trim(), folder = state.folder.trim() || "~";
      close();
      if (!p) {
        card._call("new_session", { tool: state.tool, folder, args: args(), name }, "new");
        return;
      }
      const data = { tool: p.tool, session_id: p.session_id, args: args(), ...(name ? { name } : {}) };
      if (!here()) Object.assign(data, { from_config_entry_id: p.config_entry_id, folder });
      card._call("resume_session", data, p.session_id);
    }
  });
  scrim.addEventListener("change", (e) => {
    const t = e.target, fl = flagsOf(state.tool);
    if (t.dataset.resume !== undefined) {
      keep();
      if (t.checked) { state.resume = true; draw(); pick(); }
      else { state.resume = false; state.pick = null; draw(); }
      return;
    }
    if (t.dataset.i !== undefined) fl[+t.dataset.i].on = t.checked;
    if (t.dataset.v !== undefined) fl[+t.dataset.v].value = t.value;
    root.querySelector(".prev").textContent = command();
  });
  scrim.addEventListener("input", (e) => {
    const i = e.target.dataset.v;
    if (i === undefined) return;
    const f = flagsOf(state.tool)[+i], box = root.querySelector(`input[data-i="${i}"]`);
    f.value = e.target.value;
    if (box && !fits(f)) return;
    if (box) {
      box.disabled = !usable(f);
      if (!usable(f)) { box.checked = false; f.on = false; }
    }
    root.querySelector(".prev").textContent = command();
  });
  const onKey = (e) => { if (e.key === "Escape" && !document.querySelector("agent-sessions-picker")) close(); };
  document.addEventListener("keydown", onKey);
  if (opts.resume) state.resume = true;
  draw();
  if (opts.resume) pick();
  else root.querySelector("#folder").focus();
}

// Resume picker: sessions from every server (list_sessions), grouped by server in the card's order.
function openPicker(card, a, current, done) {
  const { host, root, scrim } = sheet("agent-sessions-picker", true);
  const st = { data: null, error: null, filter: "all", q: "", sel: current };
  const finish = (v) => { host.remove(); document.removeEventListener("keydown", onKey); done(v); };
  const order = (card._last || []).map((s) => s.attributes.config_entry_id);
  const rank = (id) => { const i = order.indexOf(id); return i < 0 ? 1e9 : i; };
  const target = a.config_entry_id;
  const items = () => {
    const servers = [...(st.data || [])].sort((x, y) => rank(x.config_entry_id) - rank(y.config_entry_id));
    const atTarget = new Set((servers.find((s) => s.config_entry_id === target)?.sessions || []).map((x) => x.session_id));
    return servers.map((s) => ({ ...s, rows: (s.sessions || []).flatMap((x) => {
      const local = s.config_entry_id === target;
      if (!local && atTarget.has(x.session_id)) return []; // already copied here: offered under this server
      const why = x.open ? (local ? "running" : `running on ${s.server}`)
        : !local && x.tool === "codex" ? `only on ${s.server}`
        : !local && !a.tools.includes(x.tool) ? `no ${TOOL[x.tool]} here`
        : local && !a.tools.includes(x.tool) ? `no ${TOOL[x.tool]} here` : "";
      return [{ ...x, server: s.server, config_entry_id: s.config_entry_id, home: s.home, local, why }];
    }) }));
  };
  const draw = () => {
    const groups = items(), q = st.q.toLowerCase();
    const show = groups.filter((g) => g.online && (st.filter === "all" || g.config_entry_id === st.filter))
      .map((g) => ({ ...g, rows: g.rows.filter((r) => !q || `${r.title} ${r.cwd}`.toLowerCase().includes(q)) }))
      .filter((g) => g.rows.length);
    const offline = groups.filter((g) => !g.online);
    const keepFocus = root.activeElement?.id === "q", pos = root.querySelector("#q")?.selectionStart;
    scrim.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="Pick a session">
      <h3>Resume a session</h3><div class="s">Sessions from all servers · it will run on <b>${esc(a.server)}</b></div>
      <input type="text" id="q" placeholder="Search titles and folders" value="${esc(st.q)}" autocomplete="off">
      ${st.data ? `<div class="fchips"><button class="${st.filter === "all" ? "on" : ""}" data-f="all">All</button>${groups.map((g) =>
        `<button class="${st.filter === g.config_entry_id ? "on" : ""}" data-f="${esc(g.config_entry_id)}" ${g.online ? "" : "disabled"}>
          <span class="${g.online ? "up" : "down"}"></span>${esc(g.server)}</button>`).join("")}</div>` : ""}
      ${st.error ? `<div class="empty">Couldn't load sessions: ${esc(st.error)}</div>`
        : !st.data ? `<div class="empty">Loading sessions…</div>`
        : show.map((g) => `<div class="grp"><span class="up"></span>${esc(g.server)}${g.config_entry_id === target ? " · this server" : ""}</div>` +
          g.rows.map((r) => `<button class="sess${st.sel?.session_id === r.session_id && st.sel?.config_entry_id === r.config_entry_id ? " sel" : ""}"
            data-sid="${esc(r.session_id)}" data-e="${esc(r.config_entry_id)}" ${r.why ? `disabled title="${esc(r.why)}"` : ""}>
            <div class="min"><div class="a">${esc(r.title)}<span class="tool">${r.tool === "codex" ? "Codex" : "Claude"}</span></div>
            <div class="b">${ago(r.updated)} · ${esc(short(r.cwd, r.home))}</div></div>
            <span class="badge ${r.why ? "no" : r.local ? "here" : "copy"}">${esc(r.why || (r.local ? "here" : "copy"))}</span></button>`).join("")).join("")
          || `<div class="empty">No sessions match.</div>`}
      ${offline.map((g) => `<div class="empty">${esc(g.server)} is offline, so its sessions aren't listed.</div>`).join("")}
      <div class="btns"><button class="cancel">Cancel</button><button class="start" ${st.sel ? "" : "disabled"}>Use this session</button></div>
    </div>`;
    if (keepFocus) { const i = root.querySelector("#q"); i.focus(); i.setSelectionRange(pos, pos); }
  };
  scrim.addEventListener("click", (e) => {
    const t = e.target;
    if (t === scrim || t.classList.contains("cancel")) return finish(null);
    const f = t.closest("[data-f]");
    if (f && !f.disabled) { st.filter = f.dataset.f; draw(); return; }
    const s = t.closest("[data-sid]");
    if (s && !s.disabled) {
      st.sel = items().flatMap((g) => g.rows).find((r) => r.session_id === s.dataset.sid && r.config_entry_id === s.dataset.e);
      draw();
      return;
    }
    if (t.classList.contains("start") && st.sel) finish(st.sel);
  });
  scrim.addEventListener("input", (e) => { if (e.target.id === "q") { st.q = e.target.value; draw(); } });
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); finish(null); } };
  document.addEventListener("keydown", onKey);
  draw();
  root.querySelector("#q").focus();
  card._hass.callWS({ type: "call_service", domain: DOMAIN, service: "list_sessions", service_data: {}, return_response: true })
    .then((r) => { st.data = r.response?.servers || []; draw(); })
    .catch((err) => { st.error = err?.message || String(err); draw(); });
}

// ---------- card editor: server order and which servers this card shows ----------
const ESTYLE = `
  :host { display: block; }
  .t { font-weight: 600; font-size: 14px; } .s { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
  .r { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px; margin-top: 8px;
    background: var(--secondary-background-color, rgba(127,127,127,.08)); }
  .r.hid { opacity: .55; }
  .n { flex: 1; min-width: 0; font-weight: 600; font-size: 13px; display: flex; align-items: center; gap: 7px; }
  .n small { font-weight: 400; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .up, .down { width: 8px; height: 8px; border-radius: 50%; flex: none; } .up { background: #22c55e; } .down { background: #ef4444; }
  button { width: 30px; height: 30px; border-radius: 8px; border: none; cursor: pointer; font-size: 12px;
    background: rgba(127,127,127,.16); color: var(--primary-text-color); }
  button:disabled { opacity: .3; cursor: default; }
  input[type=checkbox] { width: 18px; height: 18px; margin: 0; accent-color: #d97757; cursor: pointer; }
  .f { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 16px; font-size: 13px; }
  .f input { width: 70px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--divider-color, rgba(127,127,127,.4));
    background: transparent; color: inherit; font-size: 13px; }
`;

class AgentSessionsCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...config }; this._render(); }

  set hass(hass) {
    const before = this._ids?.join();
    this._hass = hass;
    if (orderedIds(hass, this._config || {}, true).join() !== before) this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._move(e));
      this.shadowRoot.addEventListener("change", (e) => this._change(e));
    }
    const c = this._config, ids = (this._ids = orderedIds(this._hass, c, true));
    const shown = new Set(orderedIds(this._hass, c));
    this.shadowRoot.innerHTML = `<style>${ESTYLE}</style>
      <div class="t">Servers on this card</div>
      <div class="s">Order on the card and in its chips. Untick a server to hide it here. Without an order set here,
        the card uses each server's Position option, then the name.</div>
      ${ids.map((id, i) => {
        const a = this._hass.states[id].attributes;
        return `<div class="r${shown.has(id) ? "" : " hid"}">
          <input type="checkbox" data-show="${esc(id)}" ${shown.has(id) ? "checked" : ""} aria-label="Show ${esc(a.server)}">
          <div class="n"><span class="${a.online ? "up" : "down"}"></span>${esc(a.server)}<small>${esc(a.user)}@${esc(a.host)}</small></div>
          <button data-mv="${i}" data-d="-1" ${i ? "" : "disabled"} aria-label="Move ${esc(a.server)} up">▲</button>
          <button data-mv="${i}" data-d="1" ${i < ids.length - 1 ? "" : "disabled"} aria-label="Move ${esc(a.server)} down">▼</button></div>`;
      }).join("") || `<div class="s">No Agent Sessions servers yet.</div>`}
      <label class="f"><span>Recent sessions shown before "Show more"</span>
        <input type="number" min="0" max="50" id="recent" value="${esc(c.recent ?? 3)}"></label>`;
  }

  _save(changes) {
    const c = { ...this._config, ...changes };
    if (c.entities) { // the older list form becomes order + hide, so servers added later still show up
      c.hide = this._ids.filter((id) => !c.entities.includes(id));
      c.order = c.order || this._ids;
      delete c.entities;
    }
    for (const k of Object.keys(c)) if (c[k] === undefined) delete c[k];
    if (!c.hide?.length) delete c.hide;
    this._config = c;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: c }, bubbles: true, composed: true }));
    this._render();
  }

  _move(e) {
    const b = e.target.closest("[data-mv]");
    if (!b || b.disabled) return;
    const ids = [...this._ids], i = +b.dataset.mv, j = i + +b.dataset.d;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    this._save({ order: ids });
  }

  _change(e) {
    const t = e.target;
    if (t.dataset.show) {
      const shown = new Set(orderedIds(this._hass, this._config));
      t.checked ? shown.add(t.dataset.show) : shown.delete(t.dataset.show);
      const order = this._config.order || this._config.entities || this._ids;
      this._save({ order, hide: this._ids.filter((id) => !shown.has(id)), entities: undefined });
    } else if (t.id === "recent") {
      this._save({ recent: Math.max(0, Math.min(50, parseInt(t.value, 10) || 0)) });
    }
  }
}

// HA swaps window.customElements for a new registry ~70 ms into page load (2026.9+); this extra module can run before
// that and define into the old one, so define again until the current registry has it. A subclass, because the new
// registry may forward to the old one, where the class is already taken. (Same fix as ha-homehub-media.)
class AgentSessionsDialog extends HTMLElement {}
class AgentSessionsPicker extends HTMLElement {}
const define = () => {
  for (const [tag, cls] of [["agent-sessions-card", AgentSessionsCard], ["agent-sessions-card-editor", AgentSessionsCardEditor],
    ["agent-sessions-dialog", AgentSessionsDialog], ["agent-sessions-picker", AgentSessionsPicker]]) {
    if (customElements.get(tag)) continue;
    try { customElements.define(tag, cls); } catch { customElements.define(tag, class extends cls {}); }
  }
};
define();
for (const ms of [100, 500, 2000, 5000]) setTimeout(define, ms);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "agent-sessions-card")) {
  window.customCards.push({ type: "agent-sessions-card", name: "Agent Sessions",
    description: "Start, stop and resume Claude Code / Codex sessions on your servers." });
}
