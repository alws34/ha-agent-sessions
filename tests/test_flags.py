"""Every built-in flag end to end: the options form -> HA's catalog -> what the real card (run under Node) shows and
sends -> the agent's allowlist -> the command the session's screen runs. The rule: a session starts exactly the way the
options form and the card show it, nothing hidden added and nothing shown dropped."""
import base64
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.agent_sessions import flag_list
from custom_components.agent_sessions.const import DEFAULT_VALUES, DOMAIN, EFFORTS, FLAGS

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "agent" / "agent-sessions"
CARD = ROOT / "custom_components" / "agent_sessions" / "www" / "agent-sessions-card.js"
SID = "b63eba06-b9de-4360-b686-8744a2707765"
CODEX_MODEL = "gpt-5.5"  # Codex has no default model; the -m flag can only be ticked once it has one

# What each built-in flag puts on the command line, with the default values (Codex model set as above).
EXPECTED = {
    "claude": {
        "skip_permissions": ["--dangerously-skip-permissions"],
        "remote_control": ["--remote-control"],
        "continue": ["--continue"],
        "fork_session": ["--fork-session"],
        "model": ["--model", "opus"],
        "effort": ["--effort", "high"],
        "verbose": ["--verbose"],
    },
    "codex": {
        "bypass": ["--dangerously-bypass-approvals-and-sandbox"],
        "search": ["--search"],
        "model": ["-m", CODEX_MODEL],
        "effort": ["-c", "model_reasoning_effort=medium"],
        "no_alt_screen": ["--no-alt-screen"],
    },
}
CASES = [(t, i) for t in EXPECTED for i in EXPECTED[t]]
OPTIONS = {"codex_model": CODEX_MODEL}


def card_args(f):
    """What one flag adds to the command line (flagArgs in the card)."""
    return [*f["args"], *([f["fmt"].replace("{}", f["value"].strip())] if f.get("fmt") else [])]


def node():
    try:
        import nodejs_wheel  # requirements_test.txt: a Node binary in the venv, so this runs without a system Node
        exe = Path(nodejs_wheel.__file__).parent / "bin" / "node"
        if exe.exists():
            return str(exe)
    except ImportError:
        pass
    return shutil.which("node")


RUN = subprocess.run  # the agent fixture replaces subprocess.run (the agent's screen launch)


def card(*cases):
    """Ask the real card what it shows and sends (tests/card_harness.js)."""
    if not node():
        pytest.skip("node not available")
    out = RUN([node(), str(ROOT / "tests" / "card_harness.js"), str(CARD)], input=json.dumps(cases),
                         capture_output=True, text=True, timeout=60, check=True).stdout
    return json.loads(out)


def attrs(tool, options, allowed=None):
    """The sensor attributes the card reads for one tool."""
    return {"config_entry_id": "e1", "tools": [tool], "flags": {tool: flag_list(tool, options)},
            "allowed": {tool: allowed or []} if allowed is not False else None}


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    loader = importlib.machinery.SourceFileLoader("agent_sessions_flags", str(SCRIPT))
    spec = importlib.util.spec_from_loader("agent_sessions_flags", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.setattr(mod, "which", lambda t: "/usr/bin/" + t)  # CI has neither tool
    monkeypatch.setattr(mod, "running", lambda cache=None: [])
    monkeypatch.setattr(mod, "resuming", lambda s: False)
    monkeypatch.setattr(mod, "claude_recent", lambda cache: [{"session_id": SID, "cwd": str(tmp_path), "title": "t"}])
    monkeypatch.setattr(mod, "codex_rows", lambda where="", params=(): [{"id": SID, "cwd": str(tmp_path), "title": "t"}])
    seen = {}
    monkeypatch.setattr(mod, "screens", lambda: [("1", seen["name"])] if seen else [])

    def run(cmd, **kw):
        seen.update(name=cmd[2], cmd=cmd[-1])
    monkeypatch.setattr(mod.subprocess, "run", run)
    mod.seen = seen
    yield mod
    sys.modules.pop("agent_sessions_flags", None)


def launched(agent, verb, payload):
    """The command line the agent hands to the session's bash."""
    res = agent.main(f"{verb} " + base64.b64encode(json.dumps(payload).encode()).decode())
    assert res.get("ok"), res
    return agent.seen["cmd"]


def test_every_builtin_flag_is_covered():
    assert {t: [f["id"] for f in FLAGS[t]] for t in FLAGS} == {t: list(EXPECTED[t]) for t in EXPECTED}


@pytest.mark.parametrize(("tool", "flag"), CASES)
def test_card_argv_per_flag(tool, flag):
    f = next(x for x in flag_list(tool, OPTIONS) if x["id"] == flag)
    assert card_args(f) == EXPECTED[tool][flag]


@pytest.mark.parametrize(("tool", "flag"), [c for c in CASES if c != ("claude", "fork_session")])
def test_new_session_argv_per_flag(agent, tool, flag):
    argv = EXPECTED[tool][flag]
    assert launched(agent, "new", {"tool": tool, "args": argv}) == shlex.join([f"/usr/bin/{tool}", *argv])


@pytest.mark.parametrize(("tool", "flag"), [c for c in CASES if c != ("claude", "continue")])
def test_resume_argv_per_flag(agent, tool, flag):
    argv = EXPECTED[tool][flag]
    if tool == "claude":
        want = ["/usr/bin/claude", *argv, "--resume", SID]
        if flag == "remote_control":
            want = ["/usr/bin/claude", "--resume", SID, "--remote-control"]  # its optional value can't take the id
    else:
        want = ["/usr/bin/codex", "resume", *argv, SID]
    assert launched(agent, "resume", {"tool": tool, "session_id": SID, "args": argv}) == shlex.join(want)


def test_resume_flags_in_catalog():
    claude = {f["id"]: f for f in flag_list("claude", {})}
    assert claude["continue"]["resume"] is False  # --continue picks its own session; not with --resume
    assert claude["fork_session"].get("resume_only") is True
    assert all(f["resume"] for f in flag_list("codex", {}))


@pytest.mark.parametrize("effort", EFFORTS["claude"])
def test_claude_effort_values(agent, effort):
    cmd = launched(agent, "new", {"tool": "claude", "args": ["--remote-control", "--effort", effort]})
    assert cmd == f"/usr/bin/claude --effort {effort} --remote-control"


@pytest.mark.parametrize("effort", EFFORTS["codex"])
def test_codex_effort_values(agent, effort):
    cmd = launched(agent, "new", {"tool": "codex", "args": ["-c", f"model_reasoning_effort={effort}"]})
    assert cmd == f"/usr/bin/codex -c model_reasoning_effort={effort}"


def test_agent_allowlist_matches_catalog(agent):
    for tool in FLAGS:
        assert {f["args"][0] for f in FLAGS[tool]} == set(agent.ALLOWED[tool])
    assert [e for e in EFFORTS["claude"] if agent.ALLOWED["claude"]["--effort"].fullmatch(e)] == EFFORTS["claude"]
    codex = agent.ALLOWED["codex"]["-c"]
    assert all(codex.fullmatch(f"model_reasoning_effort={e}") for e in EFFORTS["codex"])
    assert all(DEFAULT_VALUES[t]["effort"] in EFFORTS[t] for t in EFFORTS)


# ---------- the UI is the source of truth: options form and card state -> the exact argv ----------

SKIP, RC = "--dangerously-skip-permissions", "--remote-control"
BYPASS = "--dangerously-bypass-approvals-and-sandbox"
CUSTOM = {"claude_flags": [], "claude_custom_flags": "*--chrome\n--other\n*--refused"}
# (case id, tool, options form, server's allowed-args (False: agent too old to say), card state, expected args)
UI = [
    ("claude-fresh-new", "claude", {}, None, {"mode": "new"}, [SKIP, RC, "--model", "opus", "--effort", "high"]),
    ("claude-fresh-resume", "claude", {}, None, {"mode": "resume", "picked": SID},
     [SKIP, RC, "--model", "opus", "--effort", "high"]),
    ("claude-fresh-quick", "claude", {}, None, {"mode": "quick"}, [SKIP, RC, "--model", "opus", "--effort", "high"]),
    ("claude-no-model-new", "claude", {"claude_model": "", "claude_effort": "max",
                                       "claude_flags": ["continue", "verbose", "fork_session"]}, None,
     {"mode": "new"}, ["--continue", "--effort", "max", "--verbose"]),  # --fork-session needs a session to resume
    ("claude-fork-resume", "claude", {"claude_model": "", "claude_effort": "max",
                                      "claude_flags": ["continue", "verbose", "fork_session"]}, None,
     {"mode": "resume", "picked": SID}, ["--fork-session", "--effort", "max", "--verbose"]),  # no --continue
    ("claude-fork-quick", "claude", {"claude_model": "", "claude_effort": "max",
                                     "claude_flags": ["continue", "verbose", "fork_session"]}, None,
     {"mode": "quick"}, ["--fork-session", "--effort", "max", "--verbose"]),
    ("claude-continue-new", "claude", {"claude_flags": ["continue"], "claude_model": "sonnet"}, None,
     {"mode": "new"}, ["--continue", "--model", "sonnet", "--effort", "high"]),
    ("claude-edited-new", "claude", {}, None,
     {"mode": "new", "edits": [{"id": "model", "on": False}, {"id": "effort", "value": "low"}]},
     [SKIP, RC, "--effort", "low"]),
    ("claude-named-new", "claude", {}, None, {"mode": "new", "name": "bug fix"},
     [SKIP, RC, "--model", "opus", "--effort", "high"]),
    ("claude-custom-new", "claude", CUSTOM, [["--chrome"], ["--other"]], {"mode": "new"},
     ["--model", "opus", "--effort", "high", "--chrome"]),  # --refused: shown "not allowed on server", not sent
    ("claude-custom-quick", "claude", CUSTOM, [["--chrome"], ["--other"]], {"mode": "quick"},
     ["--model", "opus", "--effort", "high", "--chrome"]),
    ("claude-custom-old-agent", "claude", CUSTOM, False, {"mode": "new"},
     ["--model", "opus", "--effort", "high", "--chrome", "--refused"]),
    ("codex-fresh-new", "codex", {}, None, {"mode": "new"}, ["-c", "model_reasoning_effort=medium", "--no-alt-screen"]),
    ("codex-fresh-resume", "codex", {}, None, {"mode": "resume", "picked": SID},
     ["-c", "model_reasoning_effort=medium", "--no-alt-screen"]),
    ("codex-fresh-quick", "codex", {}, None, {"mode": "quick"}, ["-c", "model_reasoning_effort=medium", "--no-alt-screen"]),
    ("codex-set-new", "codex", {"codex_model": "gpt-5.5", "codex_effort": "xhigh", "codex_flags": ["bypass", "search"]},
     None, {"mode": "new"}, [BYPASS, "--search", "-m", "gpt-5.5", "-c", "model_reasoning_effort=xhigh"]),
    ("codex-set-quick", "codex", {"codex_model": "gpt-5.5", "codex_effort": "xhigh", "codex_flags": ["bypass", "search"]},
     None, {"mode": "quick"}, [BYPASS, "--search", "-m", "gpt-5.5", "-c", "model_reasoning_effort=xhigh"]),
    ("codex-typed-model-new", "codex", {}, None, {"mode": "new", "edits": [{"id": "model", "value": "o3"}]},
     ["-m", "o3", "-c", "model_reasoning_effort=medium", "--no-alt-screen"]),
    ("codex-custom-new", "codex", {"codex_custom_flags": "*--add-dir ~/shared\n--oss"}, [["--add-dir", "~/shared"]],
     {"mode": "new"}, ["-c", "model_reasoning_effort=medium", "--no-alt-screen", "--add-dir", "~/shared"]),
]


def agent_argv(agent, tool, mode, args, name=""):
    """The session's argv as the agent launches it, for what the card sent."""
    if mode == "new":
        payload = {"tool": tool, "args": args, **({"name": name} if name else {})}
        return shlex.split(launched(agent, "new", payload))
    return shlex.split(launched(agent, "resume", {"tool": tool, "session_id": SID, "args": args}))


@pytest.mark.parametrize(("tool", "options", "allowed", "state", "want"), [c[1:] for c in UI], ids=[c[0] for c in UI])
def test_session_starts_as_the_ui_shows(agent, tool, options, allowed, state, want):
    a = attrs(tool, options, allowed)
    (res,) = card({**state, "tool": tool, "attrs": a, "session_id": SID})
    assert res["args"] == want
    if state["mode"] == "quick":
        # the Resume button sends what the resume dialog starts with for that session
        (dlg,) = card({"mode": "resume", "picked": SID, "tool": tool, "attrs": a})
        assert res["service"] == "resume_session" and res["args"] == dlg["args"]
        res = dlg
    if not state.get("edits"):  # the checklist shows ticked exactly what is sent
        flags = {f["id"]: f for f in a["flags"][tool]}
        assert [x for i in res["checked"] for x in card_args(flags[i])] == want
    # what the dialog shows as the command is what the server runs (the server owner allows the custom flags; an
    # allowed "~/shared" reaches the tool as the home folder's path)
    custom = [f["args"] for f in a["flags"][tool] if f.get("custom")]
    if custom:
        agent.EXTRA_ARGS.parent.mkdir(parents=True, exist_ok=True)
        agent.EXTRA_ARGS.write_text("".join(f"{tool} {shlex.join(c)}\n" for c in allowed or custom))
    got = agent_argv(agent, tool, "new" if state["mode"] == "new" else "resume", res["args"], state.get("name", ""))
    assert got == [f"/usr/bin/{tool}", *[os.path.expanduser(w) for w in res["command"][1:]]]


def test_ui_table_covers_every_builtin_flag():
    sent = {(c[1], a) for c in UI for a in c[5]}
    for tool in FLAGS:
        for f in FLAGS[tool]:
            assert (tool, f["args"][0]) in sent, f


def test_named_claude_session_shows_its_name_flag():
    (res,) = card({"mode": "new", "tool": "claude", "attrs": attrs("claude", {}), "name": "bug fix"})
    assert res["command"] == ["claude", SKIP, "--model", "opus", "--effort", "high", "--name", "bug fix", RC]


def test_form_value_is_what_the_card_starts_with():
    for tool in FLAGS:
        for options, model in (({}, DEFAULT_VALUES[tool]["model"]), ({f"{tool}_model": " x1 "}, "x1"),
                               ({f"{tool}_model": ""}, "")):
            f = next(x for x in flag_list(tool, options) if x["id"] == "model")
            assert f["value"] == model and f["default"] == bool(model)
        effort = next(x for x in flag_list(tool, {f"{tool}_effort": "bogus"}) if x["id"] == "effort")
        assert effort["value"] == DEFAULT_VALUES[tool]["effort"] and effort["default"]  # what the select shows
        # stale ticks for value flags in a saved list don't matter: the value decides
        ids = {x["id"]: x["default"] for x in flag_list(tool, {f"{tool}_flags": ["model"], f"{tool}_model": ""})}
        assert ids["model"] is False and ids["effort"] is True


LISTING = {"agent": "4", "home": "/home/dev", "allowed": {"claude": [], "codex": []}, "running": [], "recent": []}
ENTRY = {"name": "Workstation", "host": "192.0.2.20", "port": 22, "username": "dev", "ha_address": "192.0.2.2",
         "private_key": "x", "host_key": "ssh-ed25519 AAAA", "tools": ["claude", "codex"]}


def patched_agent():
    p = patch("custom_components.agent_sessions.Agent")
    agent_cls = p.start()
    agent_cls.return_value.call = AsyncMock(return_value=LISTING)
    agent_cls.return_value.close = AsyncMock()
    return p


async def load(hass, entry):
    entry.add_to_hass(hass)
    p = patched_agent()
    try:
        with patch("custom_components.agent_sessions.ir.async_create_issue"):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
    finally:
        p.stop()
    return hass.states.get("sensor.workstation_sessions").attributes


@pytest.mark.parametrize("minor", [1, 2])
async def test_older_entries_start_as_their_form_shows(hass, agent, minor):
    """0.2.0 (1.1) and 5ee3ea5 (1.2) entries: model "opus" was shown in the form but never sent, and effort only while
    ticked. After the migration both are sent because the form shows them, and the saved lists hold on/off flags only."""
    flags = ["skip_permissions", "remote_control"] + (["effort"] if minor == 2 else [])
    entry = MockConfigEntry(domain=DOMAIN, title="Workstation", version=1, minor_version=minor, data=ENTRY, options={
        "claude_flags": flags, "claude_effort": "high", "claude_model": "opus", "claude_custom_flags": "",
        "codex_flags": ["no_alt_screen", "model"], "codex_model": "", "codex_effort": "low"})
    a = await load(hass, entry)
    assert entry.minor_version == 3
    assert entry.options["claude_flags"] == ["skip_permissions", "remote_control"]
    assert entry.options["codex_flags"] == ["no_alt_screen"]
    new, quick = card({"mode": "new", "tool": "claude", "attrs": a}, {"mode": "quick", "tool": "claude", "attrs": a,
                                                                      "session_id": SID})
    assert new["args"] == quick["args"] == [SKIP, RC, "--model", "opus", "--effort", "high"]
    assert agent_argv(agent, "claude", "new", new["args"]) == \
        ["/usr/bin/claude", SKIP, "--model", "opus", "--effort", "high", RC]
    (codex,) = card({"mode": "new", "tool": "codex", "attrs": a})
    assert codex["args"] == ["-c", "model_reasoning_effort=low", "--no-alt-screen"]

    from custom_components.agent_sessions import async_migrate_entry
    before = dict(entry.options)
    assert await async_migrate_entry(hass, entry)  # idempotent
    assert entry.options == before and entry.minor_version == 3


async def test_options_form_saves_what_it_shows(hass, agent):
    entry = MockConfigEntry(domain=DOMAIN, title="Workstation", version=1, minor_version=3, data=ENTRY, options={})
    await load(hass, entry)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    schema = {str(k): (k, v) for k, v in r["data_schema"].schema.items()}
    for tool in FLAGS:  # model and effort are fields of their own, not checkboxes that could hide them
        _, sel = schema[f"{tool}_flags"]
        assert [o["value"] if isinstance(o, dict) else o for o in sel.config["options"]] == \
            [f["id"] for f in FLAGS[tool] if "value" not in f]
    assert schema["claude_model"][0].description == {"suggested_value": "opus"}

    form = {"claude_flags": ["verbose"], "claude_effort": "low", "claude_custom_flags": "*--bad 'quote",
            "codex_flags": [], "codex_model": "gpt-5.5", "codex_effort": "high", "codex_custom_flags": "",
            "folders": "~", "trusted_folders": "", "trust_any": False, "recent": 10, "scan_interval": 10,
            "confirm_stop": True, "position": 1, "default_tool": "claude"}
    r = await hass.config_entries.options.async_configure(r["flow_id"], form)
    assert r["errors"] == {"claude_custom_flags": "bad_custom_flags"}
    p = patched_agent()
    try:
        # claude_model cleared: the form leaves it out; it is saved as empty, so --model is not sent
        r = await hass.config_entries.options.async_configure(r["flow_id"], {**form, "claude_custom_flags": "*--x"})
        await hass.async_block_till_done()
    finally:
        p.stop()
    assert entry.options["claude_model"] == "" and entry.options["codex_model"] == "gpt-5.5"
    a = hass.states.get("sensor.workstation_sessions").attributes
    claude, codex = card({"mode": "new", "tool": "claude", "attrs": a}, {"mode": "new", "tool": "codex", "attrs": a})
    assert claude["args"] == ["--effort", "low", "--verbose"]  # --x: the server's allowed-args doesn't list it
    assert codex["args"] == ["-m", "gpt-5.5", "-c", "model_reasoning_effort=high"]



@pytest.mark.skipif(not shutil.which("claude"), reason="claude not installed")
def test_real_claude_cli_has_every_flag():
    """Against the installed Claude Code: every built-in flag exists and --effort takes our values."""
    out = subprocess.run(["claude", "--help"], capture_output=True, text=True, timeout=60, check=True).stdout
    for f in FLAGS["claude"]:
        form = rf"{re.escape(f['args'][0])} <\w+>" if "value" in f else rf"{re.escape(f['args'][0])}(\s|$|,| \[)"
        assert re.search(form, out), f["args"][0]
    choices = re.search(r"--effort <level>\s+Effort level[^(]*\(([^)]*)\)", out)
    assert choices and [c.strip() for c in choices.group(1).split(",")] == EFFORTS["claude"]
    assert re.search(r"--remote-control \[name\]", out)  # optional value: why the agent puts it last
