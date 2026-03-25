"""Text platform for IR Blaster."""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_NAME,
    CONF_TOPIC,
    DEFAULT_CODE_NAME_PLACEHOLDER,
    DOMAIN,
)
from .button import _send_ir

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    topic = entry.data[CONF_TOPIC]
    async_add_entities([
        CodeNameText(hass, entry, topic),
        SendCodeText(hass, entry, topic),
    ])


class IRBaseText(TextEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass, entry, topic):
        self._hass = hass
        self._entry = entry
        self._topic = topic

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._topic)},
            "name": self._entry.data.get(CONF_DEVICE_NAME, "IR Blaster"),
            "manufacturer": "Tuya",
            "model": "IRREMOTEWFBK",
        }


class CodeNameText(IRBaseText):
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 100

    def __init__(self, hass, entry, topic):
        super().__init__(hass, entry, topic)
        self._attr_name = "Code Name"
        self._attr_unique_id = f"{DOMAIN}_{topic}_code_name"
        self._attr_native_value = DEFAULT_CODE_NAME_PLACEHOLDER
        self._attr_icon = "mdi:label-outline"

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


class SendCodeText(IRBaseText):
    """Text entity that fires an IR code when its value is set.

    Accepts any of the following formats:
      - Raw hex string:          "B45A0B0B0B220B22..."
      - NEC protocol:            "nec:addr=0xDE,cmd=0xED"
      - Samsung protocol:        "samsung32:addr=0x07,cmd=0x02"
      - RC5/RC6 protocol:        "rc5:addr=0x00,cmd=0x0C"
      - Raw timings (µs):        "raw:9000,4500,560,560,560,1690,..."
      - Any other supported IR protocol (see rc_encoder.py for full list)
    """

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 500

    def __init__(self, hass, entry, topic):
        super().__init__(hass, entry, topic)
        self._attr_name = "Send Code"
        self._attr_unique_id = f"{DOMAIN}_{topic}_send_code"
        self._attr_native_value = ""
        self._attr_icon = "mdi:remote"

    async def async_set_value(self, value: str) -> None:
        if not value:
            return
        self._attr_native_value = value
        self.async_write_ha_state()
        await _send_ir(self._hass, self._topic, value)
