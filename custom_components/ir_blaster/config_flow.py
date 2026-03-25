"""Config flow for IR Blaster integration."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from .const import DOMAIN, CONF_TOPIC, CONF_DEVICE_NAME, DEFAULT_TOPIC

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_NAME, default="IR Blaster"): str,
        vol.Required(CONF_TOPIC, default=DEFAULT_TOPIC): str,
    }
)


class IRBlasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IR Blaster."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TOPIC])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_DEVICE_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
