"""agent/install.sh, run the way Home Assistant's install command runs it, against a fake home folder."""
import hashlib
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from custom_components.agent_sessions import const

ROOT = Path(__file__).parent.parent
INSTALLER, AGENT = ROOT / "agent" / "install.sh", ROOT / "agent" / "agent-sessions"
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample home-assistant-agent-sessions"
pytestmark = pytest.mark.skipif(not (shutil.which("curl") and shutil.which("sha256sum")), reason="needs curl")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pinned_checksums_match_the_files():
    assert const.INSTALLER_SHA256 == sha(INSTALLER), f"update const.INSTALLER_SHA256 to {sha(INSTALLER)}"
    assert const.AGENT_SHA256 == sha(AGENT), f"update const.AGENT_SHA256 to {sha(AGENT)}"


def test_install_command_shape():
    words = shlex.split(const.install_command("192.0.2.2", KEY))
    assert words[:2] == ["sh", "-c"] and words[3] == "sh"
    assert words[4:] == [f"https://raw.githubusercontent.com/{const.REPO}/v{const.VERSION}/agent/install.sh",
                         const.INSTALLER_SHA256, f"v{const.VERSION}", "192.0.2.2", KEY, const.AGENT_SHA256]


@pytest.fixture
def run(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "screen").write_text("#!/bin/sh\n")  # the installer only checks it exists
    (bin_ / "screen").chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bin_}:/usr/bin:/bin", "AGENT_SESSIONS_URL": AGENT.as_uri()}

    def go(installer_sha=const.INSTALLER_SHA256, ip="192.0.2.2", agent_sha=const.AGENT_SHA256, url=None):
        words = shlex.split(const.install_command(ip, KEY))
        words[4], words[5], words[-1] = url or INSTALLER.as_uri(), installer_sha, agent_sha
        return subprocess.run(words, env=env, capture_output=True, text=True, timeout=60, check=False)
    go.home = home
    return go


def test_installs_the_agent_and_one_restricted_key_line(run):
    for _ in (1, 2):  # re-running replaces the line instead of adding another
        res = run()
        assert res.returncode == 0, res.stderr
    agent, ak = run.home / ".local" / "bin" / "agent-sessions", run.home / ".ssh" / "authorized_keys"
    assert agent.read_bytes() == AGENT.read_bytes() and agent.stat().st_mode & 0o777 == 0o755
    assert ak.read_text().splitlines() == [f'from="192.0.2.2",command="{agent}",restrict {KEY}']
    assert ak.stat().st_mode & 0o777 == 0o600 and (run.home / ".ssh").stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("change", [{"installer_sha": "0" * 64}, {"agent_sha": "0" * 64}, {"ip": "*"},
                                    {"ip": '1.2.3.4",command="/bin/sh'}, {"url": "file:///nonexistent"}])
def test_refuses_and_changes_nothing(run, change):
    res = run(**change)
    assert res.returncode != 0
    assert not (run.home / ".local" / "bin" / "agent-sessions").exists()
    assert not (run.home / ".ssh" / "authorized_keys").exists()


def test_cut_off_download_runs_nothing(run, tmp_path):
    """Everything is inside main(), called on the last line: half a script defines functions and stops."""
    half = tmp_path / "half.sh"
    text = INSTALLER.read_text()
    half.write_text(text[: text.index("main \"$@\"")])
    res = run(installer_sha=sha(half), url=half.as_uri())
    assert res.returncode == 0 and res.stdout == "" and not (run.home / ".ssh").exists()
