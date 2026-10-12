"""Agent Sessions: start, stop and resume Claude Code / Codex CLI sessions on your servers over SSH."""
import logging
import shlex
from datetime import timedelta
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .agent import Agent, AgentError
from .const import (
    CONF_HOST_KEY,
    CONF_PRIVATE_KEY,
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
            return await self.agent.call("list", {"recent": int(self.config_entry.options.get(OPT_RECENT, 10))})
        except AgentError as err:
            raise UpdateFailed(str(err)) from err


def lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def flag_list(tool, options):
    """The New-session checklist for one tool: built-in flags, then the user's custom flags."""
    defaults = options.get(opt_flags(tool), DEFAULT_FLAGS[tool])
    out = []
    for f in FLAGS[tool]:
        item = {"id": f["id"], "args": f["args"], "default": f["id"] in defaults, "resume": f.get("resume", True)}
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

    def coordinator(call: ServiceCall) -> Coordinator:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_server")
        return entry.runtime_data

    async def run(call: ServiceCall, verb, payload):
        coord = coordinator(call)
        if verb in ("new", "resume"):
            payload["trust"] = coord.config_entry.options.get(OPT_TRUST_ANY, False)
        try:
            res = await coord.agent.call(verb, payload)
        except AgentError as err:
            raise HomeAssistantError(f"{coord.config_entry.title}: {err}") from err
        await coord.async_request_refresh()
        return res

    base = {vol.Required("config_entry_id"): cv.string}
    args = vol.All(cv.ensure_list, [cv.string])
    async def new_session(c: ServiceCall):
        await run(c, "new", {"tool": c.data["tool"], "cwd": c.data.get("folder", "~"),
                                    "args": c.data.get("args", []), "name": c.data.get("name", "")})

    async def resume_session(c: ServiceCall):
        await run(c, "resume", {"tool": c.data["tool"], "session_id": c.data["session_id"],
                                       "args": c.data.get("args", [])})

    async def stop_session(c: ServiceCall):
        await run(c, "stop", {"id": c.data["session"]})

    # Admin-only: starting a session is close to shell access on the server.
    async_register_admin_service(hass, DOMAIN, "new_session", new_session, vol.Schema({
        **base, vol.Required("tool"): vol.In(TOOLS), vol.Optional("folder"): cv.string,
        vol.Optional("args"): args, vol.Optional("name"): cv.string}))
    async_register_admin_service(hass, DOMAIN, "resume_session", resume_session, vol.Schema({
        **base, vol.Required("tool"): vol.In(TOOLS), vol.Required("session_id"): cv.string,
        vol.Optional("args"): args}))
    async_register_admin_service(hass, DOMAIN, "stop_session", stop_session,
                                 vol.Schema({**base, vol.Required("session"): cv.string}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AgentEntry) -> bool:
    d = entry.data
    agent = Agent(d[CONF_HOST], d[CONF_PORT], d[CONF_USERNAME], d[CONF_PRIVATE_KEY], d[CONF_HOST_KEY])
    coord = Coordinator(hass, entry, agent)
    await coord.async_refresh()  # no raise: an offline server still gets its (offline) slide in the card
    entry.runtime_data = coord
    if trusted := lines(entry.options.get(OPT_TRUSTED)):
        entry.async_create_background_task(hass, _trust(coord, trusted), "agent_sessions_trust")
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _trust(coord, folders):
    try:
        await coord.agent.call("trust", {"folders": folders})
    except AgentError as err:
        _LOGGER.warning("%s: could not mark trusted folders: %s", coord.config_entry.title, err)


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AgentEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.agent.close()
    return ok

