"""IR Blaster integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_NAME, CONF_TOPIC, DOMAIN
from .learning import LearningSession
from .storage import IRBlasterStorage

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button", "text"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR Blaster from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    topic = entry.data[CONF_TOPIC]

    storage = IRBlasterStorage(hass, entry.entry_id)
    await storage.async_load()

    learning_session = LearningSession(hass, topic, entry.entry_id)

    hass.data[DOMAIN][entry.entry_id] = {
        "storage": storage,
        "learning_session": learning_session,
        "config_entry": entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload IR Blaster config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["learning_session"].async_cleanup()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up storage on integration removal."""
    storage = IRBlasterStorage(hass, entry.entry_id)
    await storage.async_delete()
    _LOGGER.info("IR Blaster storage deleted for entry %s", entry.entry_id)
