"""The WinBIAP Library integration."""

from __future__ import annotations

from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import WinBiapClient
from .const import CONF_BASE_URL, CONF_LIBRARY_CARD, PLATFORMS
from .coordinator import WinBiapCoordinator


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
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
