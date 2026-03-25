"""Sensor platform for IR Blaster — captures incoming IR codes from Tasmota TuyaReceived."""

from __future__ import annotations

import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_TOPIC, TOPIC_RESULT, DP_IR_CODE_7, DP_IR_CODE_2
from .ir_packet import decode_hex_to_str

_LOGGER = logging.getLogger(__name__)

# HA state values are capped at 255 characters
_MAX_STATE_LEN = 255


class IRCapturedCodeSensor(SensorEntity):
    """Sensor that holds the last captured IR code.

    State: decoded protocol string (e.g. "nec:addr=0xDE,cmd=0xED") if recognisable,
           otherwise the raw hex with trailing zeros stripped.
    Attributes:
      raw_hex  — the original hex blob from the device, zeros stripped
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:remote"
    _attr_should_poll = False

    def __init__(self, hass, entry, topic):
        self._hass = hass
        self._entry = entry
        self._topic = topic
        self._attr_name = "Last Captured Code"
        self._attr_unique_id = f"{DOMAIN}_{topic}_captured_code"
        self._attr_native_value = None
        self._raw_hex: str | None = None
        self._unsubscribe = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._topic)},
            "name": self._entry.data.get("device_name", "IR Blaster"),
            "manufacturer": "Tuya",
            "model": "IRREMOTEWFBK",
        }

    @property
    def extra_state_attributes(self):
        if self._raw_hex:
            return {"raw_hex": self._raw_hex}
        return {}

    async def async_added_to_hass(self):
        """Subscribe to MQTT on add."""
        result_topic = TOPIC_RESULT.format(topic=self._topic)

        @callback
        def message_received(msg):
            try:
                data = json.loads(msg.payload)
                tuya = data.get("TuyaReceived", {})
                # Prefer DP7, fall back to DP2
                code = tuya.get(DP_IR_CODE_7) or tuya.get(DP_IR_CODE_2)
                if not code:
                    return

                # Strip 0x prefix added by Tasmota
                if code.startswith("0x"):
                    code = code[2:]

                # Ignore all-8s noise captures
                if set(code) == {"8"}:
                    _LOGGER.debug("Ignoring all-8s noise capture")
                    return

                # Strip trailing zero-padding and store raw hex
                raw = code.rstrip("0") or code[:2]  # keep at least 2 chars
                # Ensure even length for valid hex
                if len(raw) % 2:
                    raw = raw + "0"
                self._raw_hex = raw.upper()

                # Attempt protocol decode for a human-readable state value
                decoded = decode_hex_to_str(self._raw_hex)

                # Truncate to HA state limit as a safety net
                state_val = decoded[:_MAX_STATE_LEN]

                self._attr_native_value = state_val
                self.async_write_ha_state()
                _LOGGER.debug("IR code captured: %s (raw: %s)", decoded, self._raw_hex)

            except (json.JSONDecodeError, AttributeError):
                pass

        self._unsubscribe = await mqtt.async_subscribe(
            self._hass, result_topic, message_received, 0
        )

    async def async_will_remove_from_hass(self):
        if self._unsubscribe:
            self._unsubscribe()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IR Blaster sensor."""
    topic = entry.data[CONF_TOPIC]
    async_add_entities([IRCapturedCodeSensor(hass, entry, topic)])
