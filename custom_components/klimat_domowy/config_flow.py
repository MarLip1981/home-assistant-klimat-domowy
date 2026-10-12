"""Config flow for Klimat Domowy."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_AQI,
    CONF_BOILER_STATE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PM10,
    CONF_PM10_LIMIT,
    CONF_PM25,
    CONF_PM25_LIMIT,
    CONF_POLLEN_RISK,
    CONF_POLLEN_RISK_HOURLY,
    CONF_RAIN,
    DEFAULT_ENTITIES,
    DEFAULT_PM10_LIMIT,
    DEFAULT_PM25_LIMIT,
    DOMAIN,
)

ENTITY_FIELDS = (
    CONF_INDOOR_TEMPERATURE,
    CONF_INDOOR_HUMIDITY,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_OUTDOOR_HUMIDITY,
    CONF_PM25,
    CONF_PM10,
    CONF_AQI,
    CONF_POLLEN_RISK,
    CONF_POLLEN_RISK_HOURLY,
    CONF_BOILER_STATE,
    CONF_RAIN,
)


def _entity_schema(current: dict) -> dict:
    """Build UI selectors for source entities."""
    schema = {}
    for key in ENTITY_FIELDS:
        default = current.get(key, DEFAULT_ENTITIES.get(key))
        schema[vol.Optional(key, default=default)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )
    return schema


def _options_schema(current: dict) -> vol.Schema:
    """Build the options form."""
    schema = _entity_schema(current)
    schema.update(
        {
            vol.Optional(
                CONF_PM25_LIMIT,
                default=current.get(CONF_PM25_LIMIT, DEFAULT_PM25_LIMIT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=100, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_PM10_LIMIT,
                default=current.get(CONF_PM10_LIMIT, DEFAULT_PM10_LIMIT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=200, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )
    return vol.Schema(schema)


class KlimatDomowyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Klimat Domowy."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Set up the integration."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="Klimat Domowy",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(_entity_schema(DEFAULT_ENTITIES)),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return options flow."""
        return KlimatDomowyOptionsFlow()


class KlimatDomowyOptionsFlow(config_entries.OptionsFlow):
    """Manage integration options."""

    async def async_step_init(self, user_input=None):
        """Manage source entities and thresholds."""
        current = dict(self.config_entry.data)
        current.update(self.config_entry.options)

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current),
        )
