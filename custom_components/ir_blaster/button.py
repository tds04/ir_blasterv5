"""Button platform for IR Blaster."""

from __future__ import annotations

import logging

from homeassistant.components import mqtt
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_NAME,
    CONF_TOPIC,
    DEFAULT_CODE_NAME_PLACEHOLDER,
    DOMAIN,
    STATE_ARMED,
    STATE_IDLE,
    STATE_RECEIVED,
    TOPIC_SEND,
)
from .ir_packet import build_send_payload
from .learning import LearnedCode, LearningSession
from .storage import IRBlasterStorage

_LOGGER = logging.getLogger(__name__)


async def _send_ir(hass, topic: str, hex_code: str) -> None:
    """Send an IR code as a single SerialSend5 packet (DP7)."""
    payload = build_send_payload(hex_code)
    if not payload:
        _LOGGER.error("Invalid hex code: %s", hex_code)
        return
    await mqtt.async_publish(hass, TOPIC_SEND.format(topic=topic), payload)
    _LOGGER.debug("IR sent: %s", payload)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    topic = entry.data[CONF_TOPIC]
    storage: IRBlasterStorage = hass.data[DOMAIN][entry.entry_id]["storage"]
    learning_session: LearningSession = hass.data[DOMAIN][entry.entry_id]["learning_session"]

    entities: list[ButtonEntity] = [
        LearnButton(hass, entry, topic, learning_session),
        SendLastButton(hass, entry, topic, learning_session),
    ]

    for code in storage.get_codes():
        entities.append(IRCodeButton(hass, entry, topic, code["id"], code["name"], code["hex"]))
        entities.append(DeleteCodeButton(hass, entry, topic, code["id"], code["name"]))

    async_add_entities(entities)


class IRBaseButton(ButtonEntity):
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


class LearnButton(IRBaseButton):
    def __init__(self, hass, entry, topic, learning_session: LearningSession):
        super().__init__(hass, entry, topic)
        self._learning_session = learning_session
        self._attr_name = "Learn"
        self._attr_unique_id = f"{DOMAIN}_{topic}_learn"
        self._attr_icon = "mdi:remote-tv"
        self._pending_name: str | None = None
        self._code_name_unique_id = f"{DOMAIN}_{topic}_code_name"

    def _get_code_name(self) -> str | None:
        registry = er.async_get(self._hass)
        entity_id = registry.async_get_entity_id("text", DOMAIN, self._code_name_unique_id)
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if not state or state.state in ("", "unavailable", "unknown", DEFAULT_CODE_NAME_PLACEHOLDER):
            return None
        return state.state.strip() or None

    async def _clear_code_name(self) -> None:
        registry = er.async_get(self._hass)
        entity_id = registry.async_get_entity_id("text", DOMAIN, self._code_name_unique_id)
        if entity_id:
            await self._hass.services.async_call(
                "text", "set_value",
                {"entity_id": entity_id, "value": DEFAULT_CODE_NAME_PLACEHOLDER},
            )

    async def async_press(self) -> None:
        if self._learning_session.state == STATE_ARMED:
            return
        if self._learning_session.state != STATE_IDLE:
            await self._learning_session.async_clear_pending()

        name = self._get_code_name()
        if not name:
            await self._hass.services.async_call(
                "persistent_notification", "create", {
                    "notification_id": f"ir_blaster_no_name_{self._entry.entry_id}",
                    "title": "IR Blaster — Name Required",
                    "message": "Enter a name in the **Code Name** field before pressing Learn.",
                }
            )
            return

        storage: IRBlasterStorage = self._hass.data[DOMAIN][self._entry.entry_id]["storage"]
        if storage.name_exists(name):
            await self._hass.services.async_call(
                "persistent_notification", "create", {
                    "notification_id": f"ir_blaster_duplicate_{self._entry.entry_id}",
                    "title": "IR Blaster — Duplicate Name",
                    "message": f"**{name}** already exists. Choose a different name.",
                }
            )
            return

        self._pending_name = name
        self._learning_session.register_callback(self._on_state_change)
        success = await self._learning_session.async_start()
        if not success:
            self._learning_session.unregister_callback(self._on_state_change)
            self._pending_name = None

    def _on_state_change(self, state: str, code: LearnedCode | None) -> None:
        if state == STATE_RECEIVED and code and self._pending_name:
            self._hass.async_create_task(self._async_save(code))

    async def _async_save(self, code: LearnedCode) -> None:
        try:
            storage: IRBlasterStorage = self._hass.data[DOMAIN][self._entry.entry_id]["storage"]
            await storage.async_add_code(self._pending_name, code.hex_code)
            await self._clear_code_name()
            await self._learning_session.async_clear_pending()
            await self._hass.config_entries.async_reload(self._entry.entry_id)
        except Exception as err:
            _LOGGER.error("Failed to save: %s", err, exc_info=True)
        finally:
            self._learning_session.unregister_callback(self._on_state_change)
            self._pending_name = None


class SendLastButton(IRBaseButton):
    def __init__(self, hass, entry, topic, learning_session: LearningSession):
        super().__init__(hass, entry, topic)
        self._learning_session = learning_session
        self._attr_name = "Send Last Captured"
        self._attr_unique_id = f"{DOMAIN}_{topic}_send_last"
        self._attr_icon = "mdi:send"
        self._sensor_unique_id = f"{DOMAIN}_{topic}_captured_code"

    def _get_last_code(self) -> str | None:
        code = self._learning_session.pending_code
        if code:
            return code.hex_code
        registry = er.async_get(self._hass)
        sensor_id = registry.async_get_entity_id("sensor", DOMAIN, self._sensor_unique_id)
        if not sensor_id:
            return None
        state = self._hass.states.get(sensor_id)
        if not state or state.state in ("unknown", "unavailable", ""):
            return None
        return state.state

    async def async_press(self) -> None:
        raw = self._get_last_code()
        if not raw:
            _LOGGER.warning("Send Last: no code available")
            return
        await _send_ir(self._hass, self._topic, raw)


class IRCodeButton(IRBaseButton):
    def __init__(self, hass, entry, topic, code_id: str, name: str, hex_code: str):
        super().__init__(hass, entry, topic)
        self._hex_code = hex_code
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{topic}_code_{code_id}"
        self._attr_icon = "mdi:remote"

    async def async_press(self) -> None:
        await _send_ir(self._hass, self._topic, self._hex_code)


class DeleteCodeButton(IRBaseButton):
    def __init__(self, hass, entry, topic, code_id: str, name: str):
        super().__init__(hass, entry, topic)
        self._code_id = code_id
        self._attr_name = f"Delete {name}"
        self._attr_unique_id = f"{DOMAIN}_{topic}_delete_{code_id}"
        self._attr_icon = "mdi:delete-outline"

    async def async_press(self) -> None:
        storage: IRBlasterStorage = self._hass.data[DOMAIN][self._entry.entry_id]["storage"]
        if await storage.async_delete_code(self._code_id):
            await self._hass.config_entries.async_reload(self._entry.entry_id)
