import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.agent_sessions.agent import AuthFailed
from custom_components.agent_sessions.const import DOMAIN, VERSION

INFO = {"agent": "1", "user": "dev", "home": "/home/dev", "screen": "Screen version 5.0",
        "tools": {"claude": {"path": "/usr/bin/claude", "version": "2.1.0"}, "codex": {"path": None, "version": None}}}
USER = {"name": "Workstation", "host": "192.0.2.20", "port": 22, "username": "dev", "ha_address": "192.0.2.2"}


def fake_agent(call):
    agent = MagicMock()
    agent.call = call
    agent.close = AsyncMock()
    agent.server_key.export_public_key.return_value = b"ssh-ed25519 AAAAserver\n"
    agent.server_key.get_fingerprint.return_value = "SHA256:abc"
    return agent


def test_version_matches_manifest():
    manifest = json.loads(Path("custom_components/agent_sessions/manifest.json").read_text())
    assert manifest["version"] == VERSION


async def test_full_flow(hass):
    call = AsyncMock(side_effect=[AuthFailed("denied"), INFO])
    with patch("custom_components.agent_sessions.config_flow.Agent", return_value=fake_agent(call)), \
            patch("custom_components.agent_sessions.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
        assert r["step_id"] == "authorize"
        cmd = r["description_placeholders"]["command"]
        assert f"/v{VERSION}/agent/install.sh" in cmd and " 192.0.2.2 'ssh-ed25519 " in cmd
        assert r["description_placeholders"]["host"] == "192.0.2.20"
        assert r["description_placeholders"]["user"] == "dev"

        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})  # key not installed yet
        assert r["errors"] == {"base": "not_authorized"}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        assert r["step_id"] == "confirm" and r["description_placeholders"]["fingerprint"] == "SHA256:abc"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    d = r["data"]
    assert d["tools"] == ["claude"] and d["host_key"] == "ssh-ed25519 AAAAserver"
    assert d["private_key"].startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert "fingerprint" not in d


async def test_no_tools(hass):
    none = {**INFO, "tools": {"claude": {"path": None, "version": None}, "codex": {"path": None, "version": None}}}
    with patch("custom_components.agent_sessions.config_flow.Agent", return_value=fake_agent(AsyncMock(return_value=none))):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["errors"] == {"base": "no_tools"}
