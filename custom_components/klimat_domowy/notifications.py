"""Native notification delivery for Klimat Domowy."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_NOTIFY_DELAY,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_SERVICE,
    DEFAULT_NOTIFY_DELAY,
    DEFAULT_NOTIFY_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
)

_LOGGER = logging.getLogger(__name__)


def async_setup_notifications(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: DataUpdateCoordinator,
    options: dict[str, Any],
) -> None:
    """Send a notification when a new recommendation remains stable."""
    enabled = options.get(CONF_NOTIFY_ENABLED, DEFAULT_NOTIFY_ENABLED)
    if not enabled:
        return

    service_value = str(options.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)).strip()
    if service_value.startswith("notify."):
        service = service_value.split(".", 1)[1]
    else:
        service = service_value
    delay_minutes = int(options.get(CONF_NOTIFY_DELAY, DEFAULT_NOTIFY_DELAY))
    if not service or "." in service:
        _LOGGER.warning("Klimat Domowy: invalid notify service %r; notifications disabled", service_value)
        return

    initial_data = coordinator.data or {}
    last_seen = initial_data.get("recommendation")
    last_notified = last_seen
    cancel_timer = None

    async def send_if_unchanged(expected: str) -> None:
        nonlocal last_notified
        data = coordinator.data or {}
        if data.get("recommendation") != expected or expected == last_notified:
            return
        if not hass.services.has_service("notify", service):
            _LOGGER.warning(
                "Klimat Domowy: notify service notify.%s is not registered; no notification sent",
                service,
            )
            return

        attributes = data.get("attributes", {})
        reason = attributes.get("reason", "Sprawdź kartę Klimat Domowy.")
        temp_in = attributes.get("indoor_temperature")
        humidity_in = attributes.get("indoor_humidity")
        temp_out = attributes.get("outdoor_temperature")

        def fmt(value: Any, suffix: str = "") -> str:
            try:
                return f"{float(value):.1f}{suffix}"
            except (TypeError, ValueError):
                return "brak danych"

        message = (
            f"{reason}\n\n"
            f"W domu: {fmt(temp_in, ' °C')}, wilgotność {fmt(humidity_in, '%')}.\n"
            f"Na zewnątrz: {fmt(temp_out, ' °C')}.\n"
            "Kierunek przepływu wentylacji nie jest mierzony."
        )
        await hass.services.async_call(
            "notify",
            service,
            {"title": f"Klimat Domowy: {expected}", "message": message},
            blocking=False,
        )
        last_notified = expected

    @callback
    def coordinator_updated() -> None:
        nonlocal last_seen, cancel_timer
        current = (coordinator.data or {}).get("recommendation")
        if not current or current == last_seen:
            return
        last_seen = current
        if cancel_timer:
            cancel_timer()
            cancel_timer = None

        def timer_fired(_now) -> None:
            nonlocal cancel_timer
            cancel_timer = None
            hass.async_create_task(send_if_unchanged(current))

        cancel_timer = async_call_later(
            hass, timedelta(minutes=delay_minutes), timer_fired
        )

    remove_listener = coordinator.async_add_listener(coordinator_updated)

    @callback
    def cleanup() -> None:
        nonlocal cancel_timer
        remove_listener()
        if cancel_timer:
            cancel_timer()
            cancel_timer = None

    entry.async_on_unload(cleanup)
