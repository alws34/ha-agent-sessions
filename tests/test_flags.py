"""Every built-in flag end to end: HA's catalog -> the argv the card sends -> the agent's allowlist -> the command the
session's screen runs. Locks the exact argv for new and resumed sessions, and that the configured effort is sent."""
import base64
import importlib.machinery
import importlib.util
import json
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
    """flagArgs in the card (asserted below to still read the same)."""
    return [*f["args"], *([f["fmt"].replace("{}", f["value"] or "")] if f.get("fmt") else [])]


def card_default_args(flags, resume=False):
    """The argv the card sends with the flags ticked by default: New session, or the quick Resume button."""
    return [a for f in flags if f["default"] and (f["resume"] if resume else not f.get("resume_only"))
            and (not f.get("fmt") or (f["value"] or "").strip()) for a in card_args(f)]


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


def test_card_flag_args_unchanged():
    js = CARD.read_text()
    assert 'const flagArgs = (f) => [...f.args, ...(f.fmt ? [f.fmt.replace("{}", f.value ?? "")] : [])];' in js
    # choosing a value in New session ticks its flag, or the value would be shown but never sent
    assert "box.checked = f.on = usable(f);" in js


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


async def test_configured_high_effort_is_sent(hass, agent):
    """The reported bug: options say effort "high", but the session started at Claude Code's default (medium),
    because --effort was not a default-ticked flag and nothing was sent. A 0.2.0 entry (minor version 1) is migrated
    to tick it, and New session / quick Resume then send --effort high."""
    options = {"claude_flags": ["skip_permissions", "remote_control"], "claude_effort": "high",
               "claude_model": "opus", "claude_custom_flags": ""}
    entry = MockConfigEntry(domain=DOMAIN, title="Workstation", version=1, minor_version=1, options=options, data={
        "name": "Workstation", "host": "192.0.2.20", "port": 22, "username": "dev", "ha_address": "192.0.2.2",
        "private_key": "x", "host_key": "ssh-ed25519 AAAA", "tools": ["claude"]})
    entry.add_to_hass(hass)
    listing = {"agent": "4", "home": "/home/dev", "allowed": {"claude": []}, "running": [], "recent": []}
    with patch("custom_components.agent_sessions.Agent") as agent_cls, \
            patch("custom_components.agent_sessions.ir.async_create_issue"):
        agent_cls.return_value.call = AsyncMock(return_value=listing)
        agent_cls.return_value.close = AsyncMock()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.minor_version == 2
    assert entry.options["claude_flags"] == ["skip_permissions", "remote_control", "effort"]
    flags = hass.states.get("sensor.workstation_sessions").attributes["flags"]["claude"]

    new = card_default_args(flags)
    assert new == ["--dangerously-skip-permissions", "--remote-control", "--effort", "high"]
    assert launched(agent, "new", {"tool": "claude", "args": new}) == \
        "/usr/bin/claude --dangerously-skip-permissions --effort high --remote-control"
    resume = card_default_args(flags, resume=True)
    assert launched(agent, "resume", {"tool": "claude", "session_id": SID, "args": resume}) == \
        f"/usr/bin/claude --dangerously-skip-permissions --effort high --resume {SID} --remote-control"


async def test_migration_keeps_later_choices(hass):
    """Only 1.1 entries are migrated; unticking effort afterwards sticks."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, options={"claude_flags": ["verbose"]})
    entry.add_to_hass(hass)
    from custom_components.agent_sessions import async_migrate_entry
    assert await async_migrate_entry(hass, entry)
    assert entry.options["claude_flags"] == ["verbose"]
    assert next(f for f in flag_list("claude", {}) if f["id"] == "effort")["default"]  # new entries: ticked
    assert next(f for f in flag_list("codex", {}) if f["id"] == "effort")["default"]


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
