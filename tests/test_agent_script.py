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
    (tmp_path / ".claude.json").chmod(0o600)
    agent.trust_dir("claude", str(tmp_path))
    assert (tmp_path / ".claude.json").stat().st_mode & 0o777 == 0o600  # rewriting doesn't loosen it


@pytest.mark.parametrize(("command", "error"), [
    ("rm -rf /", "unknown command"),
    ("list !!!notbase64", "bad request"),
    ("new " + b64([1]), "payload must be an object"),
    ("new " + b64({"tool": "bash"}), "unknown tool"),
    ("stop " + b64({"id": "1.x; reboot"}), "invalid session"),
    ("resume " + b64({"tool": "claude", "session_id": "../../etc"}), None),
    ("trust " + b64({"folders": ["~/definitely/not/here"]}), "folder not found"),
    ("trust " + b64({"folders": ["/etc"]}), "inside"),
    ("new " + b64({"tool": "claude", "args": ["--settings", "{}"]}), "argument not allowed"),
])
def test_rejects_bad_requests(agent, command, error, monkeypatch):
    monkeypatch.setattr(agent, "which", lambda t: "/usr/bin/" + t)
    res = agent.main(command)
    assert "error" in res and (error is None or error in res["error"])


def test_clean_args(agent, tmp_path):
    ok = ["--dangerously-skip-permissions", "--model", "claude-opus-5-5[1m]", "--effort", "xhigh"]
    assert agent.clean_args("claude", ok) == ok
    assert agent.clean_args("codex", ["-c", "model_reasoning_effort=high"]) == ["-c", "model_reasoning_effort=high"]
    for tool, bad in [
        ("claude", ["rm -rf ~"]),  # a prompt
        ("claude", ["--dangerously-skip-permissions", "do something"]),
        ("claude", ["--settings", '{"hooks":{}}']),
        ("claude", ["--mcp-config", "x.json"]),
        ("claude", ["--model"]),
        ("claude", ["--model", "--settings"]),
        ("codex", ["-c", "notify=[\"sh\",\"-c\",\"id\"]"]),
        ("codex", ["--dangerously-skip-permissions"]),  # another tool's flag
        ("claude", [1]), ("claude", "--verbose"), ("claude", ["--verbose"] * 41),
    ]:
        with pytest.raises(agent.Fail):
            agent.clean_args(tool, bad)
    # the server owner can allow more, per tool, exact arguments only
    agent.EXTRA_ARGS.parent.mkdir(parents=True)
    agent.EXTRA_ARGS.write_text("# mine\nclaude --chrome\ncodex --oss\n")
    assert agent.clean_args("claude", ["--chrome"]) == ["--chrome"]
    with pytest.raises(agent.Fail):
        agent.clean_args("claude", ["--oss"])
    # a line with a value allows that exact sequence only, and ~ reaches the tool as the home folder
    agent.EXTRA_ARGS.write_text("codex --add-dir ~/shared\ncodex --profile 'a b'\n")
    assert agent.clean_args("codex", ["--add-dir", "~/shared", "--search"]) == ["--add-dir", f"{tmp_path}/shared", "--search"]
    assert agent.clean_args("codex", ["--profile", "a b"]) == ["--profile", "a b"]
    for bad in (["--add-dir"], ["--add-dir", "/etc"], ["~/shared"], ["--add-dir", "--search"]):
        with pytest.raises(agent.Fail):
            agent.clean_args("codex", bad)


def test_folders_must_be_inside_home(agent, tmp_path):
    (tmp_path / "code").mkdir()
    assert agent.folder("~/code") == os.path.realpath(tmp_path / "code")
    assert agent.folder("~") == os.path.realpath(tmp_path)
    (tmp_path / "out").symlink_to("/tmp")
    for bad in ("/tmp", "~/../", "~/out", str(tmp_path) + "-evil"):
        with pytest.raises(agent.Fail, match="inside"):
            agent.folder(bad)


def test_resume_refused_while_previous_resume_is_starting(agent, monkeypatch):
    sid = "b63eba06-b9de-4360-b686-8744a2707765"
    procs = {"10": ["SCREEN", "-dmS", "agent-claude-x", "bash", "-lic", f"/bin/claude --resume {sid}"],
             "11": ["vim", f"notes-{sid}.md"]}  # mentions the id but is not a resume
    monkeypatch.setattr(agent.os, "listdir", lambda path: list(procs) if path == "/proc" else [])
    monkeypatch.setattr(agent, "argv", lambda pid: procs.get(str(pid), []))
    monkeypatch.setattr(agent, "proc_uid", lambda pid: os.getuid())
    assert agent.resuming(sid)
    monkeypatch.setattr(agent, "proc_uid", lambda pid: os.getuid() + 1)
    assert not agent.resuming(sid)  # another user's process can't block our resume
    monkeypatch.setattr(agent, "proc_uid", lambda pid: os.getuid())
    procs.pop("10")
    assert not agent.resuming(sid)


def test_resume_refuses_folders_outside_home(agent, monkeypatch):
    sid = "b63eba06-b9de-4360-b686-8744a2707765"
    monkeypatch.setattr(agent, "which", lambda t: "/usr/bin/" + t)
    monkeypatch.setattr(agent, "running", lambda cache=None: [])
    monkeypatch.setattr(agent, "resuming", lambda s: False)
    monkeypatch.setattr(agent, "claude_recent", lambda cache: [{"session_id": sid, "cwd": "/tmp", "title": "t"}])
    monkeypatch.setattr(agent, "launch", lambda *a: pytest.fail("launched outside home"))
    res = agent.main("resume " + b64({"tool": "claude", "session_id": sid, "trust": True}))
    assert "inside" in res["error"]


def test_stop_only_touches_listed_sessions(agent, monkeypatch):
    monkeypatch.setattr(agent, "screens", lambda: [("100", "agent-claude-x"), ("200", "my-irc")])
    monkeypatch.setattr(agent, "children_map", dict)
    monkeypatch.setattr(agent, "claude_live", dict)
    monkeypatch.setattr(agent, "proc_start", lambda pid: None)
    quit_ = []
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: quit_.append(cmd[2]))
    assert agent.main("stop " + b64({"id": "200.my-irc"})) == {"error": "no such session"}
    assert agent.main("stop " + b64({"id": "100.agent-claude-x"})) == {"ok": True}
    assert quit_ == ["100.agent-claude-x"]


def test_sessions_do_not_inherit_the_ssh_request(agent, monkeypatch, tmp_path):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "new e30=")
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("PATH_KEEP_ME", "1")
    seen = {}
    monkeypatch.setattr(agent, "screens", lambda: [("1", "agent-claude-x")] if seen else [])
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: seen.update(kw))
    agent.launch("claude", "/bin/claude", str(tmp_path), [], "x", False)
    assert not {"SSH_ORIGINAL_COMMAND", "CLAUDE_CODE_CHILD_SESSION", "CLAUDECODE"} & set(seen["env"])
    assert seen["env"]["PATH_KEEP_ME"] == "1"


SID = "b63eba06-b9de-4360-b686-8744a2707765"


def claude_session(home, sid=SID, cwd=None, project="-code"):
    return transcript(home, sid, [
        {"type": "user", "cwd": cwd or str(home), "sessionId": sid,
         "message": {"role": "user", "content": "fix the login bug"}},
        {"type": "ai-title", "aiTitle": "Fix login bug", "sessionId": sid}])


def no_running(agent, monkeypatch):
    monkeypatch.setattr(agent, "running", lambda cache=None: [])
    monkeypatch.setattr(agent, "claude_live", dict)


def test_move_a_session_between_servers(agent, tmp_path, monkeypatch):
    no_running(agent, monkeypatch)
    src = claude_session(tmp_path, cwd="/home/other/code")
    out = agent.main("export " + b64({"tool": "claude", "session_id": SID}))
    assert out["title"] == "Fix login bug" and out["cwd"] == "/home/other/code"
    body = src.read_bytes()
    src.unlink()  # now "this" home is the other server
    (tmp_path / "code").mkdir()
    res = agent.main("import " + b64({"tool": "claude", "session_id": SID, "cwd": "~/code"}), out["data"])
    assert res == {"ok": True, "cwd": str(tmp_path / "code")}
    dest = tmp_path / ".claude" / "projects" / agent.project_dir(str(tmp_path / "code")).name / f"{SID}.jsonl"
    assert dest.read_bytes() == body and dest.stat().st_mode & 0o777 == 0o600
    assert dest.parent.name == str(tmp_path / "code").replace("/", "-").replace("_", "-").replace(".", "-")
    # never overwrites a transcript that is already there
    again = agent.main("import " + b64({"tool": "claude", "session_id": SID, "cwd": "~/code"}), out["data"])
    assert "already on this server" in again["error"]


def test_import_checks_what_it_writes(agent, tmp_path, monkeypatch):
    import gzip
    no_running(agent, monkeypatch)

    def imp(data, **p):
        return agent.main("import " + b64({"tool": "claude", "session_id": SID, **p}), data)

    def pack(raw):
        return base64.b64encode(gzip.compress(raw)).decode()

    other = json.dumps({"sessionId": "a" * 8 + "-1111-1111-1111-" + "1" * 12}).encode()
    assert "not a transcript of this session" in imp(pack(other))["error"]
    assert "damaged" in imp("not base64!")["error"]
    assert "damaged" in imp(pack(b"not json\n"))["error"]
    assert "inside" in imp(pack(b"{}"), cwd="/tmp")["error"]
    assert "only Claude Code" in imp(pack(b"{}"), tool="codex")["error"]
    monkeypatch.setattr(agent, "MAX_TRANSFER", 1000)
    bomb = pack(b'{"sessionId":"' + SID.encode() + b'"}\n' + b" " * 5000)
    assert "larger than" in imp(bomb)["error"]
    assert not list((tmp_path / ".claude").rglob("*.jsonl")) if (tmp_path / ".claude").exists() else True


def test_export_refuses_running_and_unknown(agent, tmp_path, monkeypatch):
    claude_session(tmp_path)
    monkeypatch.setattr(agent, "running", lambda cache=None: [{"session_id": SID}])
    monkeypatch.setattr(agent, "claude_live", dict)
    assert "running" in agent.main("export " + b64({"session_id": SID}))["error"]
    no_running(agent, monkeypatch)
    assert "not found" in agent.main("export " + b64({"session_id": "c" + SID[1:]}))["error"]
    assert "only Claude" in agent.main("export " + b64({"tool": "codex", "session_id": SID}))["error"]


def test_resume_folder_override_and_no_trust_of_home(agent, tmp_path, monkeypatch):
    claude_session(tmp_path, cwd="/gone/away")
    monkeypatch.setattr(agent, "which", lambda t: "/usr/bin/" + t)
    no_running(agent, monkeypatch)
    monkeypatch.setattr(agent, "resuming", lambda s: False)
    seen = []
    monkeypatch.setattr(agent, "launch", lambda *a: seen.append(a) or {"ok": True})
    agent.main("resume " + b64({"tool": "claude", "session_id": SID, "trust": True,
                                "args": ["--remote-control", "--fork-session"]}))
    _tool, _path, cwd, argv_, name, trust = seen[-1]
    assert cwd == str(tmp_path) and trust is False  # folder gone: home, but home is never trusted wholesale
    assert argv_ == ["--remote-control", "--fork-session", "--resume", SID] and name == "Fix login bug"
    (tmp_path / "code").mkdir()
    agent.main("resume " + b64({"tool": "claude", "session_id": SID, "trust": True, "cwd": "~/code"}))
    assert seen[-1][2] == str(tmp_path / "code") and seen[-1][5] is True
    assert "inside" in agent.main("resume " + b64({"tool": "claude", "session_id": SID, "cwd": "/tmp"}))["error"]


def test_remote_control_goes_last(agent, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, "screens", lambda: [("1", "agent-claude-x")] if seen else [])
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd))
    agent.launch("claude", "/bin/claude", str(tmp_path), ["--remote-control", "--resume", SID, "--name", "x"], "x", False)
    assert seen["cmd"][-1] == f"/bin/claude --resume {SID} --name x --remote-control"


def test_values_must_match_whole(agent):
    for tool, bad in [("claude", ["--model", "opus\n"]), ("claude", ["--effort", "high\n"]),
                      ("codex", ["-c", "model_reasoning_effort=high\n"])]:
        with pytest.raises(agent.Fail):
            agent.clean_args(tool, bad)
    for e in ("none", "xhigh"):
        assert agent.clean_args("codex", ["-c", f"model_reasoning_effort={e}"])
    assert "invalid session id" in agent.main("resume " + b64({"tool": "claude", "session_id": SID + "\n"}))["error"]


def test_stop_in_users_own_screen_stops_only_the_tool(agent, monkeypatch):
    monkeypatch.setattr(agent, "running", lambda cache=None: [
        {"id": "200.work", "name": "work", "pid": 4242}, {"id": "100.agent-claude-x", "name": "agent-claude-x"}])
    killed, quit_ = [], []
    monkeypatch.setattr(agent.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: quit_.append(cmd[2]))
    assert agent.main("stop " + b64({"id": "200.work"})) == {"ok": True}
    assert killed == [(4242, agent.signal.SIGTERM)] and quit_ == []
    agent.main("stop " + b64({"id": "100.agent-claude-x"}))
    assert quit_ == ["100.agent-claude-x"]


def test_codex_trust_keeps_config_readable(agent, tmp_path):
    import tomllib
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[projects]\n"/x/a" = { trust_level = "trusted" }\n')
    agent.trust_dir("codex", "/x/a")  # already listed another way: unchanged
    assert cfg.read_text().count("/x/a") == 1
    agent.trust_dir("codex", "/x/proj😀")
    assert "/x/proj😀" in tomllib.loads(cfg.read_text())["projects"]
    with pytest.raises(agent.Fail):
        agent.folder("~/a\tb")


def test_atomic_write_keeps_symlinks(agent, tmp_path):
    real = tmp_path / "dotfiles" / "claude.json"
    real.parent.mkdir()
    real.write_text("{}")
    (tmp_path / ".claude.json").symlink_to(real)
    agent.trust_dir("claude", str(tmp_path))
    assert (tmp_path / ".claude.json").is_symlink() and "hasTrustDialogAccepted" in real.read_text()


def test_sessions_lists_open_ones_too(agent, tmp_path, monkeypatch):
    claude_session(tmp_path)
    monkeypatch.setattr(agent, "running", lambda cache=None: [{"session_id": SID}])
    monkeypatch.setattr(agent, "claude_live", dict)
    out = agent.main("sessions " + b64({"limit": 50}))
    assert out["agent"] == agent.VERSION and [(s["session_id"], s["open"]) for s in out["sessions"]] == [(SID, True)]
    assert "limit" in agent.main("sessions " + b64({"limit": "x"}))["error"]


def test_deep_json_is_a_bad_request(agent):
    deep = base64.b64encode(("[" * 100000 + "]" * 100000).encode()).decode()
    assert "error" in agent.main("list " + deep)
