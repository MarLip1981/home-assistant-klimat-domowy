"""Automatic frontend module registration for the dashboard card."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARD_PATH = Path(__file__).parent / "www" / "klimat-domowy-card.js"
CARD_URL = "/klimat_domowy/klimat-domowy-card.js"
CARD_VERSION = "0.2.3"
VERSIONED_CARD_URL = f"{CARD_URL}?v={CARD_VERSION}"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the card and register it as an extra frontend module."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_frontend_setup_started"):
        return

    # The frontend integration is a manifest dependency, so its UrlManager is
    # already initialized. Registering an extra module is the supported API and
    # works without a user-managed Lovelace resource entry.
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)]
        )
    except RuntimeError:
        # HTTP paths stay registered if a config entry is removed and re-added
        # without restarting Home Assistant.
        _LOGGER.debug("Klimat Domowy card path is already registered")

    add_extra_js_url(hass, VERSIONED_CARD_URL)
    domain_data["_frontend_setup_started"] = True
    _LOGGER.debug("Registered Klimat Domowy dashboard card module")


async def async_remove_frontend_resource(hass: HomeAssistant) -> None:
    """Unregister the extra frontend module when the integration is removed."""
    domain_data = hass.data.get(DOMAIN, {})
    if domain_data.get("_frontend_setup_started"):
        remove_extra_js_url(hass, VERSIONED_CARD_URL)
        domain_data.pop("_frontend_setup_started", None)
