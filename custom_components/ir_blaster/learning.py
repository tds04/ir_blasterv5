"""Learning session management for IR Blaster."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    DP_IR_CODE_2,
    DP_IR_CODE_7,
    LEARN_TIMEOUT,
    PKT_STUDY_OFF,
    PKT_STUDY_ON,
    STATE_ARMED,
    STATE_CANCELLED,
    STATE_IDLE,
    STATE_RECEIVED,
    STATE_TIMEOUT,
    TOPIC_RESULT,
    TOPIC_SEND,
)
from .ir_packet import decode_hex_to_str

_LOGGER = logging.getLogger(__name__)


@dataclass
class LearnedCode:
    """A captured IR code."""
    hex_code: str


class LearningSession:
    """Manages the IR learning lifecycle for one device."""

    def __init__(self, hass: HomeAssistant, topic: str, entry_id: str) -> None:
        self.hass = hass
        self.topic = topic
        self.entry_id = entry_id

        self._state = STATE_IDLE
        self._pending_code: LearnedCode | None = None
        self._unsubscribe: Callable | None = None
        self._timeout_task: asyncio.Task | None = None
        self._callbacks: list[Callable[[str, LearnedCode | None], None]] = []

    @property
    def state(self) -> str:
        return self._state

    @property
    def pending_code(self) -> LearnedCode | None:
        return self._pending_code

    def register_callback(self, fn: Callable[[str, LearnedCode | None], None]) -> None:
        self._callbacks.append(fn)

    def unregister_callback(self, fn: Callable[[str, LearnedCode | None], None]) -> None:
        if fn in self._callbacks:
            self._callbacks.remove(fn)

    def _notify(self) -> None:
        for fn in self._callbacks[:]:
            try:
                fn(self._state, self._pending_code)
            except Exception as err:
                _LOGGER.error("Error in learning callback: %s", err)

    async def async_start(self) -> bool:
        """Send study-on and start listening for a code."""
        if self._state != STATE_IDLE:
            _LOGGER.warning("Cannot start learning: already in state %s", self._state)
            return False

        await mqtt.async_publish(
            self.hass, TOPIC_SEND.format(topic=self.topic), PKT_STUDY_ON
        )
        _LOGGER.debug("Learning: study ON")

        result_topic = TOPIC_RESULT.format(topic=self.topic)

        @callback
        def message_received(msg):
            try:
                data = json.loads(msg.payload)
                tuya = data.get("TuyaReceived", {})
                code = tuya.get(DP_IR_CODE_7) or tuya.get(DP_IR_CODE_2)
                if code:
                    if code.startswith("0x"):
                        code = code[2:]
                    if set(code) == {"8"}:
                        return
                    self.hass.async_create_task(self._async_code_received(code))
            except (json.JSONDecodeError, AttributeError):
                pass

        self._unsubscribe = await mqtt.async_subscribe(
            self.hass, result_topic, message_received, 0
        )

        self._timeout_task = self.hass.async_create_task(self._async_timeout())
        self._state = STATE_ARMED
        self._notify()
        return True

    async def _async_code_received(self, code: str) -> None:
        if self._state != STATE_ARMED:
            return
        self._cancel_timeout()
        self._cleanup_mqtt()
        await mqtt.async_publish(
            self.hass, TOPIC_SEND.format(topic=self.topic), PKT_STUDY_OFF
        )
        self._pending_code = LearnedCode(hex_code=code)
        self._state = STATE_RECEIVED
        _LOGGER.info("IR code captured: %s", code)
        self._notify()

        # Decode to human-readable protocol string if possible
        protocol_str = decode_hex_to_str(code)
        if protocol_str != code and not protocol_str.startswith("raw:"):
            # Clean protocol match (e.g. "nec:addr=0xDE,cmd=0xED")
            protocol_line = (
                f"**Protocol:** `{protocol_str}`\n\n"
                f"**Raw hex:** `{code}`"
            )
        elif protocol_str.startswith("raw:"):
            # Decoded to raw timings — show both
            protocol_line = (
                f"**Timings:** `{protocol_str}`\n\n"
                f"**Raw hex:** `{code}`"
            )
        else:
            protocol_line = f"**Raw hex:** `{code}`"

        # Persistent notification
        await self.hass.services.async_call(
            "persistent_notification", "create", {
                "notification_id": f"ir_blaster_learned_{self.entry_id}",
                "title": "IR Blaster — Code Captured",
                "message": (
                    f"New IR code captured!\n\n"
                    f"{protocol_line}\n\n"
                    f"It has been saved automatically.\n\n"
                    f"You can also fire this code directly via automation:\n"
                    f"`text.set_value` → `{protocol_str if not protocol_str.startswith('raw:') else code}`"
                ),
            }
        )

    async def _async_timeout(self) -> None:
        await asyncio.sleep(LEARN_TIMEOUT)
        if self._state != STATE_ARMED:
            return
        _LOGGER.warning("Learning timed out after %ds", LEARN_TIMEOUT)
        self._cleanup_mqtt()
        await mqtt.async_publish(
            self.hass, TOPIC_SEND.format(topic=self.topic), PKT_STUDY_OFF
        )
        self._state = STATE_TIMEOUT
        self._notify()

    def _cancel_timeout(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    def _cleanup_mqtt(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    async def async_clear_pending(self) -> None:
        """Clear pending code and return to idle."""
        await self.hass.services.async_call(
            "persistent_notification", "dismiss", {
                "notification_id": f"ir_blaster_learned_{self.entry_id}",
            }
        )
        self._pending_code = None
        self._state = STATE_IDLE
        self._notify()

    async def async_cleanup(self) -> None:
        """Full cleanup on unload."""
        self._cancel_timeout()
        self._cleanup_mqtt()
        self._callbacks.clear()
