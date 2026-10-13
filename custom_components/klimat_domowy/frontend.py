"""Automatic Lovelace resource registration for the dashboard card."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARD_PATH = Path(__file__).parent / "www" / "klimat-domowy-card.js"
CARD_URL = "/klimat_domowy/klimat-domowy-card.js"
CARD_VERSION = "0.2.0"
VERSIONED_CARD_URL = f"{CARD_URL}?v={CARD_VERSION}"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the card and schedule automatic Lovelace resource registration."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("_frontend_setup_started"):
        return
    domain_data["_frontend_setup_started"] = True

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)]
        )
    except RuntimeError:
        # A reload can happen after the HTTP path has already been registered.
        _LOGGER.debug("Klimat Domowy card path is already registered")

    if hass.state is CoreState.running:
        hass.async_create_task(_async_register_resource_when_ready(hass))
    else:
        @callback
        def _on_started(_event) -> None:
            hass.async_create_task(_async_register_resource_when_ready(hass))

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)


async def _async_register_resource_when_ready(hass: HomeAssistant) -> None:
    """Wait for Lovelace storage to load, then add or update the card resource."""
    for _attempt in range(60):
        lovelace = hass.data.get("lovelace")
        if lovelace is not None:
            resources = getattr(lovelace, "resources", None)
            mode = getattr(lovelace, "mode", "storage")
            if mode != "storage":
                # YAML dashboards cannot be edited through the resource registry.
                # Register as a frontend module so the card remains usable without
                # asking the user to edit configuration.yaml.
                add_extra_js_url(hass, VERSIONED_CARD_URL)
                return
            if resources is not None and resources.loaded:
                existing = next(
                    (
                        resource
                        for resource in resources.async_items()
                        if resource.get("url", "").split("?", 1)[0] == CARD_URL
                    ),
                    None,
                )
                if existing is None:
                    await resources.async_create_item(
                        {"res_type": "module", "url": VERSIONED_CARD_URL}
                    )
                elif existing.get("url") != VERSIONED_CARD_URL:
                    await resources.async_update_item(
                        existing["id"],
                        {"res_type": "module", "url": VERSIONED_CARD_URL},
                    )
                _LOGGER.debug("Klimat Domowy Lovelace card resource is registered")
                return
        await asyncio.sleep(1)

    _LOGGER.warning(
        "Could not register the Klimat Domowy card automatically because "
        "Lovelace resources did not become available."
    )


async def async_remove_frontend_resource(hass: HomeAssistant) -> None:
    """Remove the Lovelace resource when the config entry is permanently deleted."""
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None) if lovelace is not None else None
    if resources is not None and resources.loaded and getattr(lovelace, "mode", "storage") == "storage":
        for resource in list(resources.async_items()):
            if resource.get("url", "").split("?", 1)[0] == CARD_URL:
                await resources.async_delete_item(resource["id"])
    remove_extra_js_url(hass, VERSIONED_CARD_URL)
