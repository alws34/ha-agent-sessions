"""Config flow: server details -> authorize HA's key on the server -> confirm the server's identity. Options per server."""
import ipaddress
import re

import voluptuous as vol
from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from .agent import Agent, AgentError, AuthFailed, new_key
from .const import (
    CONF_HA_ADDRESS,
    CONF_HOST_KEY,
    CONF_PRIVATE_KEY,
    CONF_TOOLS,
    DEFAULT_FLAGS,
    DEFAULT_VALUES,
    DOMAIN,
    EFFORTS,
    FLAGS,
    OPT_CONFIRM_STOP,
    OPT_DEFAULT_TOOL,
    OPT_FOLDERS,
    OPT_INTERVAL,
    OPT_POSITION,
    OPT_RECENT,
    OPT_TRUST_ANY,
    OPT_TRUSTED,
    REPO,
    TOOL_NAMES,
    TOOLS,
    install_command,
    opt_custom,
    opt_flags,
    opt_value,
)
from .const import VERSION as RELEASE

TEXT = sel.TextSelector()
MULTILINE = sel.TextSelector(sel.TextSelectorConfig(multiline=True))


def version(text):
    m = re.search(r"\d+\.\d+[\w.-]*", text or "")
    return m.group(0) if m else ""


def valid_address(text):
    """sshd's from= list: comma-separated addresses or networks. No wildcards: "*" would accept the key from anywhere."""
    try:
        return all(ipaddress.ip_network(part.strip(), strict=False) for part in text.split(",")) and bool(text.strip())
    except ValueError:
        return False


class AgentSessionsFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data = {}
        self._public = None
        self._info = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None and not valid_address(user_input[CONF_HA_ADDRESS]):
            errors[CONF_HA_ADDRESS] = "bad_address"
        elif user_input is not None:
            user_input[CONF_HA_ADDRESS] = user_input[CONF_HA_ADDRESS].replace(" ", "")
            await self.async_set_unique_id(f"{user_input[CONF_USERNAME]}@{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            self._data = dict(user_input)
            self._data[CONF_PRIVATE_KEY], self._public = await self.hass.async_add_executor_job(new_key)
            return await self.async_step_authorize()
        try:
            me = await async_get_source_ip(self.hass)
        except OSError:  # no route to probe; the user can type it
            me = ""
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_NAME): TEXT,
            vol.Required(CONF_HOST): TEXT,
            vol.Required(CONF_PORT, default=22): sel.NumberSelector(
                sel.NumberSelectorConfig(min=1, max=65535, mode=sel.NumberSelectorMode.BOX)),
            vol.Required(CONF_USERNAME): TEXT,
            vol.Required(CONF_HA_ADDRESS, default=(user_input or {}).get(CONF_HA_ADDRESS, me)): TEXT,
        }))

    async def async_step_authorize(self, user_input=None):
        errors = {}
        if user_input is not None:
            agent = Agent(self._data[CONF_HOST], int(self._data[CONF_PORT]), self._data[CONF_USERNAME],
                          self._data[CONF_PRIVATE_KEY])
            try:
                self._info = await agent.call("info")
                self._data[CONF_HOST_KEY] = agent.server_key.export_public_key().decode().strip()
                self._data["fingerprint"] = agent.server_key.get_fingerprint("sha256")
            except AuthFailed:
                errors["base"] = "not_authorized"
            except AgentError:
                errors["base"] = "cannot_connect"
            finally:
                await agent.close()
            if not errors:
                if not any(t["path"] for t in self._info["tools"].values()):
                    errors["base"] = "no_tools"
                else:
                    return await self.async_step_confirm()
        return self.async_show_form(step_id="authorize", errors=errors, description_placeholders={
            "name": self._data[CONF_NAME], "host": self._data[CONF_HOST], "user": self._data[CONF_USERNAME],
            "ha_address": self._data[CONF_HA_ADDRESS],
            "command": install_command(self._data[CONF_HA_ADDRESS], self._public),
            "script_url": f"https://github.com/{REPO}/blob/v{RELEASE}/agent/install.sh"})

    async def async_step_confirm(self, user_input=None):
        tools = [t for t in TOOLS if self._info["tools"][t]["path"]]
        if user_input is not None:
            self._data.pop("fingerprint", None)
            self._data[CONF_TOOLS] = tools
            self._data[CONF_PORT] = int(self._data[CONF_PORT])
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data,
                                           options={OPT_DEFAULT_TOOL: tools[0]})
        found = ", ".join(f"{TOOL_NAMES[t]} {version(self._info['tools'][t]['version'])}".strip() for t in tools)
        return self.async_show_form(step_id="confirm", description_placeholders={
            "fingerprint": self._data["fingerprint"], "tools": found, "screen": self._info.get("screen") or "?"})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AgentSessionsOptions()


def options_schema(tools, o):
    """Options form for the tools found on this server, prefilled with the current options."""
    fields = {}
    if len(tools) > 1:
        fields[vol.Required(OPT_DEFAULT_TOOL, default=o.get(OPT_DEFAULT_TOOL, tools[0]))] = sel.SelectSelector(
            sel.SelectSelectorConfig(options=list(tools), translation_key="tool"))
    for t in tools:
        fields[vol.Required(opt_flags(t), default=o.get(opt_flags(t), DEFAULT_FLAGS[t]))] = sel.SelectSelector(
            sel.SelectSelectorConfig(options=[f["id"] for f in FLAGS[t]], multiple=True,
                                     translation_key=f"{t}_flags", mode=sel.SelectSelectorMode.LIST))
        fields[vol.Optional(opt_value(t, "model"), default=o.get(opt_value(t, "model"), DEFAULT_VALUES[t]["model"]))
               ] = TEXT
        fields[vol.Required(opt_value(t, "effort"), default=o.get(opt_value(t, "effort"), DEFAULT_VALUES[t]["effort"]))
               ] = sel.SelectSelector(sel.SelectSelectorConfig(options=EFFORTS[t]))
        fields[vol.Optional(opt_custom(t), default=o.get(opt_custom(t), ""))] = MULTILINE
    fields.update({
        vol.Optional(OPT_FOLDERS, default=o.get(OPT_FOLDERS, "~")): MULTILINE,
        vol.Optional(OPT_TRUSTED, default=o.get(OPT_TRUSTED, "")): MULTILINE,
        vol.Required(OPT_TRUST_ANY, default=o.get(OPT_TRUST_ANY, False)): sel.BooleanSelector(),
        vol.Required(OPT_RECENT, default=o.get(OPT_RECENT, 10)): sel.NumberSelector(
            sel.NumberSelectorConfig(min=0, max=50, mode=sel.NumberSelectorMode.BOX)),
        vol.Required(OPT_INTERVAL, default=o.get(OPT_INTERVAL, 10)): sel.NumberSelector(
            sel.NumberSelectorConfig(min=5, max=3600, unit_of_measurement="s", mode=sel.NumberSelectorMode.BOX)),
        vol.Required(OPT_CONFIRM_STOP, default=o.get(OPT_CONFIRM_STOP, True)): sel.BooleanSelector(),
        vol.Required(OPT_POSITION, default=o.get(OPT_POSITION, 1)): sel.NumberSelector(
            sel.NumberSelectorConfig(min=1, max=99, mode=sel.NumberSelectorMode.BOX)),
    })
    return vol.Schema(fields)


class AgentSessionsOptions(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=options_schema(
            self.config_entry.data[CONF_TOOLS], self.config_entry.options))
