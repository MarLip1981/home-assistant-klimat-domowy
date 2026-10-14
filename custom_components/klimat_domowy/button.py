"""Diagnostic notification button for Klimat Domowy."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose a button that immediately tests the configured notify target."""
    async_add_entities([KlimatDomowyTestNotificationButton(hass, entry)])


class KlimatDomowyTestNotificationButton(ButtonEntity):
    """Send a diagnostic message to the configured notification target."""

    _attr_name = "Test powiadomienia"
    _attr_icon = "mdi:message-badge"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_test_notification"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Klimat Domowy",
            "manufacturer": "MarLip1981",
            "model": "Silnik zaleceń jakości powietrza",
            "configuration_url": "https://github.com/MarLip1981/home-assistant-klimat-domowy",
        }

    async def async_press(self) -> None:
        """Send immediately, bypassing the normal recommendation delay."""
        options: dict[str, Any] = dict(self.entry.data)
        options.update(self.entry.options)
        target = str(options.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)).strip()
        service = target.split(".", 1)[1] if target.startswith("notify.") else target
        message = (
            "To jest test powiadomień integracji Klimat Domowy. "
            "Jeśli widzisz tę wiadomość, skonfigurowany kanał powiadomień działa."
        )
        try:
            if (
                target.startswith("notify.")
                and self.hass.states.get(target) is not None
                and self.hass.services.has_service("notify", "send_message")
            ):
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {
                        "entity_id": target,
                        "title": "Klimat Domowy — test",
                        "message": message,
                    },
                    blocking=True,
                )
            elif service and self.hass.services.has_service("notify", service):
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {"title": "Klimat Domowy — test", "message": message},
                    blocking=True,
                )
            else:
                raise RuntimeError(
                    f"Nie znaleziono usługi ani encji powiadomień dla celu {target!r}. "
                    "Sprawdź opcję celu powiadomień integracji."
                )
        except Exception:
            _LOGGER.exception(
                "Klimat Domowy: test powiadomienia nie powiódł się dla %s",
                target,
            )
            raise
        _LOGGER.info("Klimat Domowy: test powiadomienia wysłany do %s", target)
