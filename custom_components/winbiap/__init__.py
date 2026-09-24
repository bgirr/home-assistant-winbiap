"""The WinBIAP Library integration."""

from __future__ import annotations

from aiohttp import CookieJar, DummyCookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import WinBiapClient
from .const import CONF_BASE_URL, CONF_LIBRARY_CARD, PLATFORMS
from .coordinator import WinBiapCoordinator
from .opening_coordinator import OpeningHoursCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WinBIAP Library from a config entry."""
    session = async_create_clientsession(
        hass, auto_cleanup=True, cookie_jar=CookieJar()
    )
    client = WinBiapClient(
        session,
        entry.data[CONF_BASE_URL],
        entry.data[CONF_LIBRARY_CARD],
        entry.data["password"],
    )
    coordinator = WinBiapCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    public_session = async_create_clientsession(
        hass, auto_cleanup=True, cookie_jar=DummyCookieJar()
    )
    coordinator.opening_hours = OpeningHoursCoordinator(hass, entry, public_session)
    await coordinator.opening_hours.async_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
