"""Config flow for Automate Pulse Hub v2 integration."""

import logging

import aiopulse2
import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({vol.Required("host"): str})


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Automate Pulse Hub v2."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(self, user_input=None):
        """Handle the initial step once we have info from the user."""
        errors = {}
        if user_input is not None:
            try:
                hub = aiopulse2.Hub(user_input["host"])
                await hub.test()
                info = {"title": hub.name}

                return self.async_create_entry(title=info["title"], data=user_input)
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the Automate Pulse Hub v2 integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REFRESH_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=60)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
