"""One sensor per server: state = running sessions; attributes carry everything the card needs."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import flag_list, lines
from .const import CONF_TOOLS, DOMAIN, OPT_CONFIRM_STOP, OPT_DEFAULT_TOOL, OPT_FOLDERS

ATTRS = frozenset({"integration", "config_entry_id", "server", "host", "user", "home", "online", "error", "tools",
                   "default_tool", "running", "recent", "flags", "folders", "confirm_stop"})


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SessionsSensor(entry.runtime_data)])


class SessionsSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "sessions"
    _attr_icon = "mdi:console"
    _unrecorded_attributes = ATTRS  # session lists change constantly; keep them out of the recorder

    def __init__(self, coord):
        super().__init__(coord)
        e = coord.config_entry
        self._attr_unique_id = e.entry_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, e.entry_id)}, name=e.title,
                                            manufacturer="Agent Sessions", model=f"{e.data[CONF_USERNAME]}@{e.data[CONF_HOST]}")

    @property
    def available(self):
        return True  # offline is shown by the card (attribute "online"), so the server's slide never disappears

    @property
    def native_value(self):
        return len(self.coordinator.data["running"]) if self.coordinator.last_update_success else None

    @property
    def extra_state_attributes(self):
        c, e = self.coordinator, self.coordinator.config_entry
        ok, data = c.last_update_success, c.data or {}
        tools = e.data[CONF_TOOLS]
        return {
            "integration": DOMAIN, "config_entry_id": e.entry_id, "server": e.title,
            "host": e.data[CONF_HOST], "user": e.data[CONF_USERNAME], "home": data.get("home"),
            "online": ok, "error": None if ok else str(c.last_exception or "unreachable"),
            "tools": tools, "default_tool": d if (d := e.options.get(OPT_DEFAULT_TOOL)) in tools else tools[0],
            "running": data.get("running", []) if ok else [], "recent": data.get("recent", []) if ok else [],
            "flags": {t: flag_list(t, e.options) for t in tools},
            "folders": lines(e.options.get(OPT_FOLDERS, "~")) or ["~"],
            "confirm_stop": e.options.get(OPT_CONFIRM_STOP, True),
        }
