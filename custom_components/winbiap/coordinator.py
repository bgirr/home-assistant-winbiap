"""Update coordinator for WinBIAP Library."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    WinBiapCannotConnect,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import WinBiapAccount

_LOGGER = logging.getLogger(__name__)


class WinBiapCoordinator(DataUpdateCoordinator[WinBiapAccount]):
    """Coordinate polling a single library account."""

    def __init__(self, hass: HomeAssistant, entry, client) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> WinBiapAccount:
        try:
            return await self.client.async_get_account()
        except WinBiapInvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except (WinBiapCannotConnect, WinBiapUnsupportedPage) as err:
            raise UpdateFailed(str(err)) from err
