"""The server-side agent (agent/agent-sessions), run against a fake home folder."""
import base64
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "agent" / "agent-sessions"


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    loader = importlib.machinery.SourceFileLoader("agent_sessions_script", str(SCRIPT))
    spec = importlib.util.spec_from_loader("agent_sessions_script", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    yield mod
    sys.modules.pop("agent_sessions_script", None)


def b64(obj):
    return base64.b64encode(json.dumps(obj).encode()).decode()


def transcript(home, sid, lines):
    p = home / ".claude" / "projects" / "-code" / f"{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n")
    return p


def test_claude_titles_and_empty_sessions(agent, tmp_path):
    transcript(tmp_path, "a" * 8 + "-1111-1111-1111-" + "1" * 12, [
        {"type": "user", "cwd": "/code", "message": {"role": "user", "content": "fix the login bug"}},
        {"type": "ai-title", "aiTitle": "Fix login bug"}])
    transcript(tmp_path, "b" * 8 + "-1111-1111-1111-" + "1" * 12, [
        {"type": "user", "cwd": "/code", "message": {"role": "user", "content": "add <b>dark</b> mode"}}])
    transcript(tmp_path, "c" * 8 + "-1111-1111-1111-" + "1" * 12, [  # hooks only, never prompted
        {"type": "attachment", "cwd": "/code", "message": {"role": "user", "content": "<system-reminder>x"}}])
    titles = {s["title"] for s in agent.claude_recent({})}
    assert titles == {"Fix login bug", "add <b>dark</b> mode"}


def test_trust_both_tools(agent, tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / ".claude.json").write_text(json.dumps({"projects": {}, "other": 1}))
    agent.trust_dir("claude", str(tmp_path / "code"))
    d = json.loads((tmp_path / ".claude.json").read_text())
    assert d["other"] == 1 and d["projects"][str(tmp_path / "code")]["hasTrustDialogAccepted"] is True
    agent.trust_dir("codex", "/x/y")
    agent.trust_dir("codex", "/x/y")  # idempotent
    toml = (tmp_path / ".codex" / "config.toml").read_text()
    assert toml.count('[projects."/x/y"]') == 1 and 'trust_level = "trusted"' in toml


@pytest.mark.parametrize(("command", "error"), [
    ("rm -rf /", "unknown command"),
    ("list !!!notbase64", "bad request"),
    ("new " + b64([1]), "payload must be an object"),
    ("new " + b64({"tool": "bash"}), "unknown tool"),
    ("stop " + b64({"id": "1.x; reboot"}), "invalid session"),
    ("resume " + b64({"tool": "claude", "session_id": "../../etc"}), None),
    ("trust " + b64({"folders": ["/definitely/not/here"]}), "folder not found"),
])
def test_rejects_bad_requests(agent, command, error, monkeypatch):
    monkeypatch.setattr(agent, "which", lambda t: "/usr/bin/" + t)
    res = agent.main(command)
    assert "error" in res and (error is None or error in res["error"])


def test_clean_args(agent):
    assert agent.clean_args(["--add-dir", "~/x"]) == ["--add-dir", os.path.expanduser("~/x")]
    for bad in (["a\nb"], [1], "--x", ["x"] * 41):
        with pytest.raises(agent.Fail):
            agent.clean_args(bad)
