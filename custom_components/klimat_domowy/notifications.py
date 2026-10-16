"""Native notification delivery for Klimat Domowy."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NOTIFY_DELAY,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_SERVICE,
    DEFAULT_NOTIFY_DELAY,
    DEFAULT_NOTIFY_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
)

_LOGGER = logging.getLogger(__name__)

# A recommendation category may be sent again after this period, but never
# because a sensor value or explanatory text changed by itself.
_REPEAT_SUPPRESSION = timedelta(minutes=60)


def async_setup_notifications(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: DataUpdateCoordinator,
    options: dict[str, Any],
) -> None:
    """Notify about meaningful recommendation changes after a short settle time."""
    enabled = options.get(CONF_NOTIFY_ENABLED, DEFAULT_NOTIFY_ENABLED)
    if enabled is False or str(enabled).strip().lower() in {"false", "off", "0", "no"}:
        _LOGGER.warning("Klimat Domowy: automatic notifications are disabled in integration options")
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

    last_sent_by_recommendation: dict[str, Any] = {}
    last_seen = (coordinator.data or {}).get("recommendation")
    retry_recommendation: str | None = None
    cancel_timer = None
    remove_listener = None

    _LOGGER.warning(
        "Klimat Domowy: notifications enabled; target=%s, settle time=%s min, repeated-category suppression=%s min",
        service_value,
        delay_minutes,
        int(_REPEAT_SUPPRESSION.total_seconds() / 60),
    )

    async def send_if_unchanged(expected: str) -> None:
        """Send only if unchanged; remember transient failures for a later retry."""
        nonlocal retry_recommendation
        data = coordinator.data or {}
        current = data.get("recommendation")
        if current != expected:
            _LOGGER.warning(
                "Klimat Domowy: notification skipped because recommendation changed before delivery (expected=%r, current=%r)",
                expected,
                current,
            )
            retry_recommendation = None
            return

        now = dt_util.now()
        previous_sent = last_sent_by_recommendation.get(expected)
        if previous_sent is not None and now - previous_sent < _REPEAT_SUPPRESSION:
            _LOGGER.warning(
                "Klimat Domowy: repeated recommendation %r suppressed (sent less than %s min ago)",
                expected,
                int(_REPEAT_SUPPRESSION.total_seconds() / 60),
            )
            return

        legacy_service_available = hass.services.has_service("notify", service)
        notify_entity_available = (
            service_value.startswith("notify.")
            and hass.states.get(service_value) is not None
            and hass.services.has_service("notify", "send_message")
        )
        if not legacy_service_available and not notify_entity_available:
            _LOGGER.error(
                "Klimat Domowy: target %r is unavailable. Check the notify target in integration options; will retry after the next sensor update.",
                service_value,
            )
            retry_recommendation = expected
            return

        attributes = data.get("attributes", {})
        message = attributes.get("reason") or "Sprawdź kartę Klimat Domowy."

        try:
            if notify_entity_available:
                await hass.services.async_call(
                    "notify",
                    "send_message",
                    {
                        "entity_id": service_value,
                        "title": f"Klimat Domowy: {expected}",
                        "message": message,
                    },
                    blocking=True,
                )
            elif legacy_service_available:
                await hass.services.async_call(
                    "notify",
                    service,
                    {"title": f"Klimat Domowy: {expected}", "message": message},
                    blocking=True,
                )
            else:
                _LOGGER.error(
                    "Klimat Domowy: no usable notify entity/service for %r",
                    service_value,
                )
                return
        except Exception:
            _LOGGER.exception(
                "Klimat Domowy: failed to send notification through %s; will retry after the next sensor update",
                service_value,
            )
            retry_recommendation = expected
            return

        retry_recommendation = None
        last_sent_by_recommendation[expected] = now
        _LOGGER.warning("Klimat Domowy: notification sent through %s for recommendation %r", service_value, expected)

    @callback
    def schedule_timer(reason: str) -> None:
        """Start one fixed settle window; subsequent changes don't restart it."""
        nonlocal cancel_timer
        if cancel_timer is not None:
            _LOGGER.debug("Klimat Domowy: settle timer already active; latest recommendation will be checked when it fires")
            return

        _LOGGER.warning("Klimat Domowy: %s; notification check scheduled in %s min", reason, delay_minutes)

        def timer_fired(_now) -> None:
            nonlocal cancel_timer
            cancel_timer = None
            current = (coordinator.data or {}).get("recommendation")
            if not current:
                _LOGGER.warning("Klimat Domowy: notification timer fired without a current recommendation")
                return
            _LOGGER.warning("Klimat Domowy: settle timer fired; checking latest recommendation %r", current)
            hass.async_create_task(send_if_unchanged(current))

        cancel_timer = async_call_later(
            hass, timedelta(minutes=delay_minutes), timer_fired
        )

    @callback
    def coordinator_updated() -> None:
        """Schedule changes, and retry a failed send when new sensor data arrives."""
        nonlocal last_seen
        current = (coordinator.data or {}).get("recommendation")
        if not current:
            return
        changed = current != last_seen
        if changed:
            last_seen = current
            # The timer is deliberately not reset for further changes. When it fires,
            # the send path reads the latest recommendation and sends at most that one.
            schedule_timer(f"recommendation changed to {current!r}")
        elif retry_recommendation == current and cancel_timer is None:
            schedule_timer(f"retrying previously failed notification for {current!r}")

    remove_listener = coordinator.async_add_listener(coordinator_updated)

    # Initial state gets the same settling treatment. Changes during this window
    # share the timer instead of cancelling/restarting it on every coordinator tick.
    if (coordinator.data or {}).get("recommendation"):
        schedule_timer("initial recommendation available")

    @callback
    def cleanup() -> None:
        nonlocal cancel_timer
        if remove_listener is not None:
            remove_listener()
        if cancel_timer is not None:
            cancel_timer()
            cancel_timer = None

    entry.async_on_unload(cleanup)
