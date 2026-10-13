"""Klimat Domowy integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .frontend import async_remove_frontend_resource, async_setup_frontend
from .notifications import async_setup_notifications


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the dashboard card once, independently of the config entry."""
    await async_setup_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the configured household climate engine."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    await async_setup_frontend(hass)
    domain_data[entry.entry_id] = dict(entry.data)
    domain_data[entry.entry_id].update(entry.options)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    options = dict(entry.data)
    options.update(entry.options)
    coordinator = domain_data[entry.entry_id].get("coordinator")
    if coordinator is not None:
        async_setup_notifications(hass, entry, coordinator, options)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the configured platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the dashboard resource when the integration entry is deleted."""
    await async_remove_frontend_resource(hass)
