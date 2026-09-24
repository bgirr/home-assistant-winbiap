"""Config flow for WinBIAP Library."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
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
from .const import (
    CONF_BASE_URL,
    CONF_LIBRARY_CARD,
    CONF_LIBRARY_ID,
    CONF_LIBRARY_LOCATION,
    CONF_LIBRARY_NAME,
    CONF_LIBRARY_SELECTION,
    DOMAIN,
)
from .library_catalog import (
    MANUAL_LIBRARY_ID,
    WinBiapLibrary,
    library_by_id,
    load_library_catalog,
)
from .opening_hours import parse_exceptions

_LOGGER = logging.getLogger(__name__)


def _credentials_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_LIBRARY_CARD,
                default=defaults.get(CONF_LIBRARY_CARD, ""),
            ): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


def _library_schema(libraries: tuple[WinBiapLibrary, ...]) -> vol.Schema:
    options: list[selector.SelectOptionDict] = [
        *(
            {"value": library.library_id, "label": library.label}
            for library in libraries
        ),
        {
            "value": MANUAL_LIBRARY_ID,
            "label": "Other / manual WebOPAC URL",
        },
    ]
    return vol.Schema(
        {
            vol.Required(CONF_LIBRARY_SELECTION): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    sort=False,
                )
            )
        }
    )


def _manual_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_URL,
                default=defaults.get(CONF_BASE_URL, "https://opac.winbiap.net/"),
            ): str
        }
    )


VALIDATION_TIMEOUT = 30


async def _validate(hass, user_input: dict[str, Any]) -> str:
    base_url = normalize_base_url(user_input[CONF_BASE_URL])
    session = async_create_clientsession(
        hass, auto_cleanup=False, cookie_jar=CookieJar()
    )
    try:
        client = WinBiapClient(
            session,
            base_url,
            user_input[CONF_LIBRARY_CARD],
            user_input[CONF_PASSWORD],
        )
        async with asyncio.timeout(VALIDATION_TIMEOUT):
            await client.async_get_account()
    finally:
        session.detach()
    return base_url


class WinBiapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WinBIAP Library."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WinBiapOptionsFlow()

    _base_url: str
    _selected_library: WinBiapLibrary | None = None

    async def _async_libraries(self) -> tuple[WinBiapLibrary, ...]:
        """Load the bundled catalog outside the event loop."""
        return await self.hass.async_add_executor_job(load_library_catalog)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user select a library from the provider catalog."""
        errors: dict[str, str] = {}
        libraries = await self._async_libraries()

        if user_input is not None:
            library_id = user_input[CONF_LIBRARY_SELECTION]
            if library_id == MANUAL_LIBRARY_ID:
                return await self.async_step_manual()
            if library := library_by_id(libraries, library_id):
                self._selected_library = library
                self._base_url = library.url
                return await self.async_step_credentials()
            errors["base"] = "invalid_library"

        return self.async_show_form(
            step_id="user",
            data_schema=_library_schema(libraries),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Accept a WebOPAC URL for a library missing from the catalog."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._base_url = normalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                self._selected_library = None
                return await self.async_step_credentials()

        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_schema(user_input),
            errors=errors,
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate credentials and create the config entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entry_data = {**user_input, CONF_BASE_URL: self._base_url}
            if self._selected_library is not None:
                entry_data.update(
                    {
                        CONF_LIBRARY_ID: self._selected_library.library_id,
                        CONF_LIBRARY_NAME: self._selected_library.name,
                        CONF_LIBRARY_LOCATION: self._selected_library.location,
                    }
                )
            try:
                _LOGGER.debug("WinBIAP setup validation started")
                entry_data[CONF_BASE_URL] = await _validate(self.hass, entry_data)
            except WinBiapInvalidAuth:
                _LOGGER.warning("WinBIAP setup validation failed: invalid_auth")
                errors["base"] = "invalid_auth"
            except WinBiapUnsupportedPage:
                _LOGGER.warning("WinBIAP setup validation failed: unsupported_page")
                errors["base"] = "unsupported_page"
            except TimeoutError:
                _LOGGER.warning("WinBIAP setup validation failed: timeout")
                errors["base"] = "timeout"
            except (WinBiapCannotConnect, ValueError):
                _LOGGER.warning("WinBIAP setup validation failed: cannot_connect")
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error(
                    "WinBIAP setup validation failed: unexpected %s",
                    type(err).__name__,
                )
                errors["base"] = "unknown"
            else:
                _LOGGER.debug("WinBIAP setup validation succeeded")
                unique_id = account_unique_id(
                    entry_data[CONF_BASE_URL], entry_data[CONF_LIBRARY_CARD]
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                title = (
                    self._selected_library.name
                    if self._selected_library is not None
                    else library_title(entry_data[CONF_BASE_URL])
                )
                return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(user_input),
            errors=errors,
            description_placeholders={
                "library": (
                    self._selected_library.label
                    if self._selected_library is not None
                    else self._base_url
                )
            },
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
            except TimeoutError:
                errors["base"] = "timeout"
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


class WinBiapOptionsFlow(config_entries.OptionsFlow):
    """Date-specific opening overrides without changing regular library hours."""

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                parse_exceptions(user_input.get("opening_exceptions", ""))
            except (ValueError, IndexError):
                errors["base"] = "invalid_opening_exceptions"
            else:
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, **user_input}
                )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "opening_exceptions",
                        default=self.config_entry.options.get("opening_exceptions", ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
        )
