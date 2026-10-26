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
    cancel_reminder = None
    cancel_quiet_timer = None
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
        if now.hour >= 22 or now.hour < 6:
            schedule_quiet_end(expected)
            _LOGGER.info(
                "Klimat Domowy: notification suppressed during quiet hours (22:00–06:00); latest recommendation will be reconsidered after 06:00"
            )
            return

        previous_sent = last_sent_by_recommendation.get(expected)
        if previous_sent is not None and now - previous_sent < _REPEAT_SUPPRESSION:
            _LOGGER.warning(
                "Klimat Domowy: repeated recommendation %r suppressed (sent less than %s min ago)",
                expected,
                int(_REPEAT_SUPPRESSION.total_seconds() / 60),
            )
            schedule_reminder(expected)
            return

        # Match the old automation's delivery route first: action notify.cala_rodzina
        # invokes the named notify service. Only fall back to entity-based notify
        # when this Home Assistant installation exposes no service with that name.
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
        # Prefer the concise notification summary with explicit sensor readings;
        # keep the longer explanation available on the card as "reason".
        message = attributes.get("notification_message") or attributes.get("reason") or "Sprawdź kartę Klimat Domowy."
        message = f"Zalecenie z {now.strftime('%d.%m.%Y, %H:%M')}\n\n{message}"

        try:
            if legacy_service_available:
                await hass.services.async_call(
                    "notify",
                    service,
                    {
                        "title": f"Klimat Domowy: {expected}",
                        "message": message,
                        "data": {
                            "actions": [
                                {
                                    "action": "URI",
                                    "title": "Zobacz szczegóły",
                                    "uri": "/dashboard-monitor/pogoda",
                                }
                            ]
                        },
                    },
                    blocking=True,
                )
            elif notify_entity_available:
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
        schedule_reminder(expected)

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
            # async_call_later may invoke this callback from a worker thread.
            # hass.add_job is thread-safe and schedules the coroutine on HA's loop.
            hass.add_job(send_if_unchanged, current)

        cancel_timer = async_call_later(
            hass, timedelta(minutes=delay_minutes), timer_fired
        )

    def schedule_quiet_end(expected: str) -> None:
        """Defer quiet-hour notifications and reevaluate the latest state after 06:00."""
        nonlocal cancel_quiet_timer
        if cancel_quiet_timer is not None:
            return

        now = dt_util.now()
        next_morning = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now.hour >= 22:
            next_morning += timedelta(days=1)
        delay = max(next_morning - now, timedelta(seconds=1))

        def quiet_timer_fired(_now) -> None:
            nonlocal cancel_quiet_timer
            cancel_quiet_timer = None
            current = (coordinator.data or {}).get("recommendation")
            if not current:
                return
            # Refresh source entities, then allow the normal settle window to
            # send only the latest recommendation rather than a stale night-time one.
            hass.add_job(coordinator.async_request_refresh)
            hass.add_job(
                schedule_timer,
                f"quiet hours ended; reevaluating latest recommendation {current!r}",
            )

        cancel_quiet_timer = async_call_later(hass, delay, quiet_timer_fired)
        _LOGGER.debug(
            "Klimat Domowy: quiet-hour delivery deferred until 06:00 (recommendation=%r)",
            expected,
        )

    def schedule_reminder(expected: str) -> None:
        """Repeat a still-active recommendation every two hours."""
        nonlocal cancel_reminder
        if cancel_reminder is not None:
            cancel_reminder()
            cancel_reminder = None

        def reminder_fired(_now) -> None:
            nonlocal cancel_reminder
            cancel_reminder = None
            current = (coordinator.data or {}).get("recommendation")
            if current != expected:
                _LOGGER.debug(
                    "Klimat Domowy: reminder cancelled because recommendation changed (expected=%r, current=%r)",
                    expected,
                    current,
                )
                return
            hass.add_job(
                schedule_timer,
                f"same recommendation still active; 2-hour reminder for {expected!r}",
            )

        cancel_reminder = async_call_later(hass, timedelta(hours=2), reminder_fired)
        _LOGGER.debug("Klimat Domowy: next reminder for %r scheduled in 120 min", expected)

    @callback
    def coordinator_updated() -> None:
        """Schedule changes, and retry a failed send when new sensor data arrives."""
        nonlocal last_seen, cancel_reminder
        current = (coordinator.data or {}).get("recommendation")
        if not current:
            return
        changed = current != last_seen
        if changed:
            last_seen = current
            if cancel_reminder is not None:
                cancel_reminder()
                cancel_reminder = None
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
        nonlocal cancel_timer, cancel_reminder, cancel_quiet_timer
        if remove_listener is not None:
            remove_listener()
        if cancel_timer is not None:
            cancel_timer()
            cancel_timer = None
        if cancel_reminder is not None:
            cancel_reminder()
            cancel_reminder = None
        if cancel_quiet_timer is not None:
            cancel_quiet_timer()
            cancel_quiet_timer = None

    entry.async_on_unload(cleanup)
