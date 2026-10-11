"""The WinBIAP Library integration."""

from __future__ import annotations

from aiohttp import CookieJar, DummyCookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import WinBiapClient
from .browser import BrowserClient
from .const import CONF_BASE_URL, CONF_LIBRARY_CARD, PLATFORMS
from .coordinator import WinBiapCoordinator
from .opening_coordinator import OpeningHoursCoordinator
from .transport import AccountTransport


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
    client = AccountTransport(
        client,
        lambda: BrowserClient(
            entry.data[CONF_BASE_URL],
            entry.data[CONF_LIBRARY_CARD],
            entry.data["password"],
            hass.config.config_dir,
        ),
    )
    coordinator = WinBiapCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await client.async_close()
        raise
    public_session = async_create_clientsession(
        hass, auto_cleanup=True, cookie_jar=DummyCookieJar()
    )
    coordinator.opening_hours = OpeningHoursCoordinator(hass, entry, public_session)
    await coordinator.opening_hours.async_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP
    from homeassistant.core import callback

    @callback
    def close_browser(_event=None):
        hass.async_create_task(client.async_close())

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_browser)
    )
    entry.runtime_data = coordinator
    coordinator.transport = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.transport.async_close()
    return unloaded


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete private cached account records when removing the integration."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"winbiap.{entry.entry_id}", private=True).async_remove()
