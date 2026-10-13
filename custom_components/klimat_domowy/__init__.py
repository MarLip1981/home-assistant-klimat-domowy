"""Klimat Domowy integration."""

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

CARD_URL = "/klimat_domowy/klimat-domowy-card.js?v=0.2.0"
CARD_PATH = Path(__file__).parent / "www" / "klimat-domowy-card.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration and register its Lovelace card."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = dict(entry.data)
    domain_data[entry.entry_id].update(entry.options)

    if not domain_data.get("_frontend_static_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL.split("?")[0], str(CARD_PATH), cache_headers=True)]
        )
        domain_data["_frontend_static_registered"] = True

    add_extra_js_url(hass, CARD_URL)
    domain_data["_frontend_card_url"] = CARD_URL

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration and remove the extra module registration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        card_url = domain_data.get("_frontend_card_url")
        if card_url:
            remove_extra_js_url(hass, card_url)
            domain_data.pop("_frontend_card_url", None)
        domain_data.pop(entry.entry_id, None)
    return unload_ok
