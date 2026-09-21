"""Config flow for WinBIAP Library."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    WinBiapCannotConnect,
    WinBiapClient,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
    account_unique_id,
    library_title,
    normalize_base_url,
)
from .const import CONF_BASE_URL, CONF_LIBRARY_CARD, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_URL,
                default=defaults.get(CONF_BASE_URL, "https://opac.winbiap.net/"),
            ): str,
            vol.Required(
                CONF_LIBRARY_CARD,
                default=defaults.get(CONF_LIBRARY_CARD, ""),
            ): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


async def _validate(hass, user_input: dict[str, Any]) -> str:
    base_url = normalize_base_url(user_input[CONF_BASE_URL])
    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    client = WinBiapClient(
        session,
        base_url,
        user_input[CONF_LIBRARY_CARD],
        user_input[CONF_PASSWORD],
    )
    try:
        await client.async_get_account()
    finally:
        await client.async_close()
    return base_url


class WinBiapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WinBIAP Library."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                user_input[CONF_BASE_URL] = await _validate(self.hass, user_input)
            except WinBiapInvalidAuth:
                errors["base"] = "invalid_auth"
            except WinBiapUnsupportedPage:
                errors["base"] = "unsupported_page"
            except (WinBiapCannotConnect, ValueError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception validating WinBIAP account")
                errors["base"] = "unknown"
            else:
                unique_id = account_unique_id(
                    user_input[CONF_BASE_URL], user_input[CONF_LIBRARY_CARD]
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=library_title(user_input[CONF_BASE_URL]),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> FlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate and save a new password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            updated = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await _validate(self.hass, updated)
            except WinBiapInvalidAuth:
                errors["base"] = "invalid_auth"
            except WinBiapUnsupportedPage:
                errors["base"] = "unsupported_page"
            except (WinBiapCannotConnect, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
