"""Agent Sessions: start, stop and resume Claude Code / Codex CLI sessions on your servers over SSH."""
import asyncio
import logging
import shlex
from datetime import timedelta
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .agent import Agent, AgentError, public_key
from .const import (
    AGENT_VERSION,
    CONF_HA_ADDRESS,
    CONF_HOST_KEY,
    CONF_PRIVATE_KEY,
    CONF_TOOLS,
    DEFAULT_FLAGS,
    DEFAULT_VALUES,
    DOMAIN,
    EFFORTS,
    FLAGS,
    OPT_INTERVAL,
    OPT_RECENT,
    OPT_TRUST_ANY,
    OPT_TRUSTED,
    TOOLS,
    VERSION,
    install_command,
    opt_custom,
    opt_flags,
    opt_value,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CARD_URL = "/agent_sessions_static"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type AgentEntry = ConfigEntry[Coordinator]


class Coordinator(DataUpdateCoordinator):
    """Polls the server's agent ("list") every scan_interval seconds over the kept-open SSH connection."""

    def __init__(self, hass, entry: AgentEntry, agent: Agent):
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.title,
                         update_interval=timedelta(seconds=entry.options.get(OPT_INTERVAL, 10)))
        self.agent = agent

    async def _async_update_data(self):
        try:
            data = await self.agent.call("list", {"recent": int(self.config_entry.options.get(OPT_RECENT, 10))})
        except AgentError as err:
            raise UpdateFailed(str(err)) from err
        _agent_issue(self.hass, self.config_entry, data.get("agent"))
        return data


def _agent_issue(hass, entry, agent_version):
    """A Repairs issue, with the install command, while a server runs an older agent than this release needs."""
    issue_id = f"agent_outdated_{entry.entry_id}"
    if agent_version == AGENT_VERSION:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    d = entry.data
    ir.async_create_issue(
        hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
        translation_key="agent_outdated", translation_placeholders={
            "name": entry.title, "host": d[CONF_HOST], "user": d[CONF_USERNAME],
            "command": install_command(d.get(CONF_HA_ADDRESS, "<home-assistant-ip>"), public_key(d[CONF_PRIVATE_KEY]))})


def _home_relative(path, home):
    """/home/a/code on a server whose home is /home/a -> ~/code (the same place in another server's home)."""
    if path and home and (path == home or path.startswith(home.rstrip("/") + "/")):
        return "~" + path[len(home.rstrip("/")):]
    return "~"


def lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def flag_list(tool, options):
    """The New-session checklist for one tool: built-in flags, then the user's custom flags."""
    defaults = options.get(opt_flags(tool), DEFAULT_FLAGS[tool])
    out = []
    for f in FLAGS[tool]:
        item = {"id": f["id"], "args": f["args"], "default": f["id"] in defaults, "resume": f.get("resume", True)}
        if f.get("resume_only"):
            item["resume_only"] = True
        if "value" in f:
            item["value"] = options.get(opt_value(tool, f["value"]), DEFAULT_VALUES[tool][f["value"]])
            item["fmt"] = f.get("fmt", "{}")
            if f["value"] == "effort":
                item["choices"] = EFFORTS[tool]
        out.append(item)
    for i, line in enumerate(lines(options.get(opt_custom(tool)))):
        try:
            args = shlex.split(line.lstrip("*"))
        except ValueError:
            continue  # unbalanced quotes; ponytail: silently skipped, the options form could validate instead
        if args:
            out.append({"id": f"custom{i}", "args": args, "default": line.startswith("*"), "resume": True,
                        "custom": True})
    return out


async def async_setup(hass: HomeAssistant, config):
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "www"), cache_headers=False)])
    frontend.add_extra_js_url(hass, f"{CARD_URL}/agent-sessions-card.js?v={VERSION}")

    def coordinator(entry_id) -> Coordinator:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_server")
        return entry.runtime_data

    async def call(coord, verb, payload):
        try:
            return await coord.agent.call(verb, payload)
        except AgentError as err:
            raise HomeAssistantError(f"{coord.config_entry.title}: {err}") from err

    async def run(c: ServiceCall, verb, payload):
        coord = coordinator(c.data["config_entry_id"])
        if verb in ("new", "resume"):
            payload["trust"] = coord.config_entry.options.get(OPT_TRUST_ANY, False)
        res = await call(coord, verb, payload)
        await coord.async_request_refresh()
        return res

    base = {vol.Required("config_entry_id"): cv.string}
    args = vol.All(cv.ensure_list, [cv.string])

    async def new_session(c: ServiceCall):
        await run(c, "new", {"tool": c.data["tool"], "cwd": c.data.get("folder", "~"),
                             "args": c.data.get("args", []), "name": c.data.get("name", "")})

    async def resume_session(c: ServiceCall):
        payload = {"tool": c.data["tool"], "session_id": c.data["session_id"], "args": c.data.get("args", [])}
        if c.data.get("name"):
            payload["name"] = c.data["name"]
        if c.data.get("folder"):
            payload["cwd"] = c.data["folder"]
        src_id = c.data.get("from_config_entry_id")
        if src_id and src_id != c.data["config_entry_id"]:
            # Move the conversation: read it from the server it ran on, write it into this one, resume it here.
            target, src = coordinator(c.data["config_entry_id"]), coordinator(src_id)
            if c.data["tool"] != "claude":
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="codex_move")
            exp = await call(src, "export", {"tool": "claude", "session_id": c.data["session_id"]})
            payload.setdefault("cwd", _home_relative(exp.get("cwd"), exp.get("home")))
            try:
                await target.agent.call("import", {"tool": "claude", "session_id": c.data["session_id"],
                                                   "cwd": payload["cwd"]}, exp["data"])
            except AgentError as err:
                if "already on this server" not in str(err):  # moved here before: resume the copy that's here
                    raise HomeAssistantError(f"{target.config_entry.title}: {err}") from err
        await run(c, "resume", payload)

    async def stop_session(c: ServiceCall):
        await run(c, "stop", {"id": c.data["session"]})

    async def list_sessions(c: ServiceCall):
        """Resumable sessions on every loaded server (or the ones asked for), for the card's resume picker."""
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
                   and (not c.data.get("config_entry_id") or e.entry_id in c.data["config_entry_id"])]

        async def one(e):
            out = {"config_entry_id": e.entry_id, "server": e.title, "tools": e.data[CONF_TOOLS]}
            try:
                res = await e.runtime_data.agent.call("sessions", {"limit": c.data.get("limit", 100)})
            except AgentError as err:
                return {**out, "online": False, "error": str(err), "sessions": []}
            return {**out, "online": True, "home": res.get("home"), "sessions": res.get("sessions", [])}

        return {"servers": list(await asyncio.gather(*(one(e) for e in entries)))}

    # Admin-only: starting a session is close to shell access on the server.
    async_register_admin_service(hass, DOMAIN, "new_session", new_session, vol.Schema({
        **base, vol.Required("tool"): vol.In(TOOLS), vol.Optional("folder"): cv.string,
        vol.Optional("args"): args, vol.Optional("name"): cv.string}))
    async_register_admin_service(hass, DOMAIN, "resume_session", resume_session, vol.Schema({
        **base, vol.Required("tool"): vol.In(TOOLS), vol.Required("session_id"): cv.string,
        vol.Optional("args"): args, vol.Optional("folder"): cv.string, vol.Optional("name"): cv.string,
        vol.Optional("from_config_entry_id"): cv.string}))
    async_register_admin_service(hass, DOMAIN, "stop_session", stop_session,
                                 vol.Schema({**base, vol.Required("session"): cv.string}))
    async_register_admin_service(hass, DOMAIN, "list_sessions", list_sessions, vol.Schema({
        vol.Optional("config_entry_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("limit", default=100): vol.All(vol.Coerce(int), vol.Range(min=1, max=300))}),
        supports_response=SupportsResponse.ONLY)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AgentEntry) -> bool:
    d = entry.data
    agent = Agent(d[CONF_HOST], d[CONF_PORT], d[CONF_USERNAME], d[CONF_PRIVATE_KEY], d[CONF_HOST_KEY])
    coord = Coordinator(hass, entry, agent)
    await coord.async_refresh()  # no raise: an offline server still gets its (offline) slide in the card
    entry.runtime_data = coord
    if coord.last_update_success:
        await _update_tools(hass, entry, agent)
    if trusted := lines(entry.options.get(OPT_TRUSTED)):
        entry.async_create_background_task(hass, _trust(coord, trusted), "agent_sessions_trust")
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _update_tools(hass, entry, agent):
    """Pick up a tool installed (or removed) on the server since setup; reloading the entry re-checks."""
    try:
        info = await agent.call("info")
    except AgentError:
        return
    tools = [t for t in TOOLS if info.get("tools", {}).get(t, {}).get("path")]
    if tools and tools != entry.data[CONF_TOOLS]:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOOLS: tools})


async def _trust(coord, folders):
    try:
        await coord.agent.call("trust", {"folders": folders})
    except AgentError as err:
        _LOGGER.warning("%s: could not mark trusted folders: %s", coord.config_entry.title, err)


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: AgentEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, f"agent_outdated_{entry.entry_id}")


async def async_unload_entry(hass: HomeAssistant, entry: AgentEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.agent.close()
    return ok

