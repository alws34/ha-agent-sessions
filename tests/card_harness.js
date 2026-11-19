// Runs the real card (custom_components/agent_sessions/www/agent-sessions-card.js) under Node, without a browser, and
// answers what it would send. Used by tests/test_flags.py. Reads a JSON list of cases on stdin, prints a JSON list.
//   {mode: "new" | "resume", tool, attrs, picked, name, edits: [{id, on?, value?}]}  -> the New-session / resume dialog
//   {mode: "quick", tool, attrs, session_id}                                         -> the Resume button on a row
// Each answer: {args, command, checked}: the service call's args, the dialog's command line (as a list), and the flags
// the checklist draws ticked.
"use strict";
const fs = require("fs");
const vm = require("vm");

class HTMLElement {}
const sandbox = {
  HTMLElement, console, setTimeout: () => 0,
  customElements: { get: () => undefined, define: () => {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
const src = fs.readFileSync(process.argv[2], "utf8");
vm.runInContext(`${src}
;globalThis.__card = { startFlags, sendArgs, commandLine, ticked, AgentSessionsCard };`, sandbox);
const card = sandbox.__card;

function dialog(c) {
  const flags = card.startFlags(c.attrs, c.tool);
  for (const e of c.edits || []) { // what a click or a typed value does in the dialog
    const f = flags.find((x) => x.id === e.id);
    if ("value" in e) { f.value = e.value; f.on = String(e.value).trim() !== ""; }
    if ("on" in e) f.on = e.on;
  }
  const resume = c.mode === "resume", picked = resume && !!c.picked;
  const args = card.sendArgs(c.attrs, c.tool, flags, resume, picked);
  const checked = flags.filter((f) => card.ticked(c.attrs, c.tool, f, resume, picked)).map((f) => f.id);
  const command = card.commandLine(c.tool, args, { resume, sid: c.picked, name: (c.name || "").trim() });
  return { args, command, checked };
}

function quick(c) {
  const el = new card.AgentSessionsCard();
  el._last = [{ attributes: c.attrs }];
  el._sel = c.attrs.config_entry_id;
  let sent = null;
  el._call = (service, data) => { sent = { service, data }; };
  const button = { dataset: { act: "resume", id: c.session_id, tool: c.tool } };
  el._click({ target: { closest: () => button } });
  return { service: sent.service, args: sent.data.args, data: sent.data };
}

const cases = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map((c) => (c.mode === "quick" ? quick(c) : dialog(c)))));
