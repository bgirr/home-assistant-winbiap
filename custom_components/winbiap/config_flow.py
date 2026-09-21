"""Config flow for WinBIAP Library."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_BASE_URL, CONF_LIBRARY_CARD, DOMAIN


class WinBiapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WinBIAP Library."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Live validation and duplicate detection will be added with the API client.
            return self.async_create_entry(
                title="WinBIAP Library",
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL): str,
                vol.Required(CONF_LIBRARY_CARD): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
