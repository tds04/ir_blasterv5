"""Persistent storage for IR Blaster codes."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class IRBlasterStorage:
    """Manage persistent storage for IR codes using HA Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}{entry_id}",
        )
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load codes from storage."""
        data = await self._store.async_load()
        if data is None:
            self._data = {"codes": []}
            _LOGGER.debug("No existing storage for %s, starting fresh", self.entry_id)
        else:
            self._data = data
            _LOGGER.info("Loaded %d IR codes for %s", len(self._data.get("codes", [])), self.entry_id)

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    def get_codes(self) -> list[dict[str, Any]]:
        return self._data.get("codes", [])

    def get_code(self, code_id: str) -> dict[str, Any] | None:
        for code in self._data.get("codes", []):
            if code.get("id") == code_id:
                return code
        return None

    def name_exists(self, name: str) -> bool:
        name_lower = name.lower().strip()
        return any(
            c.get("name", "").lower().strip() == name_lower
            for c in self._data.get("codes", [])
        )

    def code_exists(self, code_id: str) -> bool:
        return self.get_code(code_id) is not None

    async def async_add_code(self, name: str, hex_code: str) -> dict[str, Any]:
        code_id = self._generate_id(name)
        now = datetime.now(timezone.utc).isoformat()
        code = {
            "id": code_id,
            "name": name,
            "hex": hex_code,
            "created_at": now,
        }
        self._data.setdefault("codes", []).append(code)
        await self.async_save()
        _LOGGER.info("Saved IR code '%s' (%s)", name, code_id)
        return code

    async def async_delete_code(self, code_id: str) -> bool:
        codes = self._data.get("codes", [])
        new_codes = [c for c in codes if c.get("id") != code_id]
        if len(new_codes) == len(codes):
            return False
        self._data["codes"] = new_codes
        await self.async_save()
        _LOGGER.info("Deleted IR code %s", code_id)
        return True

    async def async_delete(self) -> None:
        await self._store.async_remove()
        self._data = {}

    def _generate_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "code"
        base = slug
        counter = 2
        while self.code_exists(slug):
            slug = f"{base}_{counter}"
            counter += 1
        return slug
