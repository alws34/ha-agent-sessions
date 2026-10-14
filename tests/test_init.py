from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.agent_sessions import flag_list
from custom_components.agent_sessions.agent import AgentError
from custom_components.agent_sessions.const import DOMAIN

DATA = {"name": "Workstation", "host": "192.0.2.20", "port": 22, "username": "dev", "ha_address": "192.0.2.2",
        "private_key": "x", "host_key": "ssh-ed25519 AAAA", "tools": ["claude", "codex"]}
LIST = {"home": "/home/dev",
        "running": [{"id": "123.agent-claude-x", "name": "agent-claude-x", "tool": "claude", "title": "Fix tests",
                     "status": "working", "cwd": "/home/dev/code", "started": None, "session_id": "s1"}],
        "recent": [{"tool": "codex", "session_id": "s2", "title": "Old", "cwd": "/home/dev", "updated": None}]}


async def setup(hass, call, options=None):
    entry = MockConfigEntry(domain=DOMAIN, title="Workstation", data=DATA, options=options or {})
    entry.add_to_hass(hass)
    with patch("custom_components.agent_sessions.Agent") as agent_cls:
        agent_cls.return_value.call = call
        agent_cls.return_value.close = AsyncMock()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def sensor(hass):
    return hass.states.get("sensor.workstation_sessions")


async def test_sensor_and_services(hass, hass_read_only_user):
    call = AsyncMock(return_value=LIST)
    entry = await setup(hass, call, {"trust_any": True, "trusted_folders": "~/code\n\n~/scratch"})
    s = sensor(hass)
    assert s.state == "1"
    a = s.attributes
    assert a["online"] and a["home"] == "/home/dev" and a["config_entry_id"] == entry.entry_id
    assert a["running"][0]["title"] == "Fix tests" and a["recent"][0]["tool"] == "codex"
    assert set(a["flags"]) == {"claude", "codex"}
    call.assert_any_call("trust", {"folders": ["~/code", "~/scratch"]})

    call.reset_mock()
    await hass.services.async_call(DOMAIN, "new_session", {
        "config_entry_id": entry.entry_id, "tool": "claude", "folder": "~/code", "args": ["--remote-control"]},
        blocking=True)
    call.assert_any_call("new", {"tool": "claude", "cwd": "~/code", "args": ["--remote-control"], "name": "",
                                 "trust": True})
    await hass.services.async_call(DOMAIN, "stop_session", {
        "config_entry_id": entry.entry_id, "session": "123.agent-claude-x"}, blocking=True)
    call.assert_any_call("stop", {"id": "123.agent-claude-x"})

    # admin only: a regular HA user can't start or stop sessions
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "new_session", {
            "config_entry_id": entry.entry_id, "tool": "claude"}, blocking=True,
            context=Context(user_id=hass_read_only_user.id))

    call.side_effect = AgentError("that session is already running")
    with pytest.raises(HomeAssistantError, match="already running"):
        await hass.services.async_call(DOMAIN, "resume_session", {
            "config_entry_id": entry.entry_id, "tool": "codex", "session_id": "s2"}, blocking=True)


async def test_offline_server_keeps_its_slide(hass):
    await setup(hass, AsyncMock(side_effect=AgentError("cannot connect")))
    s = sensor(hass)
    assert s.state == "unknown"
    assert s.attributes["online"] is False and "cannot connect" in s.attributes["error"]
    assert s.attributes["server"] == "Workstation" and s.attributes["running"] == []


def test_flag_list():
    flags = flag_list("codex", {"codex_flags": ["effort"], "codex_effort": "high",
                                "codex_custom_flags": "*--add-dir ~/shared\n--profile 'a b'\n--bad 'quote"})
    effort = next(f for f in flags if f["id"] == "effort")
    assert effort["default"] and effort["args"] == ["-c"] and effort["fmt"].format("high") == "model_reasoning_effort=high"
    custom = [f for f in flags if f.get("custom")]
    assert [f["args"] for f in custom] == [["--add-dir", "~/shared"], ["--profile", "a b"]]  # bad quoting skipped
    assert [f["default"] for f in custom] == [True, False]
    assert next(f for f in flag_list("claude", {}) if f["id"] == "continue")["resume"] is False


async def test_tool_installed_after_setup_is_picked_up(hass):
    info = {"tools": {"claude": {"path": "/bin/claude"}, "codex": {"path": "/bin/codex"}}}
    call = AsyncMock(side_effect=lambda verb, payload=None: info if verb == "info" else LIST)
    with patch.dict(DATA, tools=["claude"]):
        entry = await setup(hass, call, {"default_tool": "claude"})
    assert entry.data["tools"] == ["claude", "codex"]
    assert set(sensor(hass).attributes["flags"]) == {"claude", "codex"}
