"""Poll accounts while retaining explicitly dated last-known data on failure."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime
from decimal import InvalidOperation

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WinBiapCannotConnect, WinBiapInvalidAuth, WinBiapUnsupportedPage
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import WinBiapAccount
from .snapshot import decode_account, encode_account

_LOGGER = logging.getLogger(__name__)
SECTIONS = ("loans", "reservations", "fees", "wishlist")


class WinBiapCoordinator(DataUpdateCoordinator[WinBiapAccount]):
    """Coordinate polling and a private last-successful account snapshot."""

    def __init__(self, hass: HomeAssistant, entry, client) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=True,
        )
        self.client = client
        self._entry = entry
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}", private=True)
        self._loaded = False
        self._snapshot: WinBiapAccount | None = None
        self.section_updated: dict[str, str] = {}
        self.stale_sections: set[str] = set(SECTIONS)
        self.last_attempt: str | None = None
        self.refresh_error: str | None = None
        self.section_origins: dict[str, str] = {}

    def freshness(self, section: str = "loans") -> dict:
        """Safe metadata separate from HA's successful cache delivery flag."""
        return {
            "last_successful_update": self.section_updated.get(section)
            if self.section_origins.get(section) == "successful_fetch"
            else None,
            "last_known_update": self.section_updated.get(section),
            "last_attempt": self.last_attempt,
            "data_stale": section in self.stale_sections,
            "refresh_error": self.refresh_error,
            "stale_sections": sorted(self.stale_sections),
            "snapshot_origin": self.section_origins.get(section, "unknown"),
        }

    async def _load_snapshot(self) -> None:
        self._loaded = True
        try:
            if saved := await self._store.async_load():
                account = decode_account(saved["account"])
                times = saved["section_updated"]
                for key, value in times.items():
                    if (
                        key not in SECTIONS
                        or datetime.fromisoformat(value).tzinfo is None
                    ):
                        raise ValueError("invalid_timestamp")
                self._snapshot = account
                self.section_updated = times
                self.section_origins = saved.get("section_origins", {})
        except (ValueError, TypeError, KeyError, OSError, InvalidOperation):
            _LOGGER.warning("Ignoring an unreadable WinBIAP snapshot")

    async def _async_update_data(self) -> WinBiapAccount:
        if not self._loaded:
            await self._load_snapshot()
        self.last_attempt = datetime.now(UTC).isoformat()
        try:
            async with asyncio.timeout(90):
                account = await self.client.async_get_account()
        except (
            WinBiapInvalidAuth,
            WinBiapCannotConnect,
            WinBiapUnsupportedPage,
            TimeoutError,
        ) as err:
            self.stale_sections = set(SECTIONS)
            self.refresh_error = (
                "authentication"
                if isinstance(err, WinBiapInvalidAuth)
                else "browser_verification_required"
                if isinstance(err, WinBiapUnsupportedPage)
                and str(err) == "browser_verification_required"
                else "unsupported_page"
                if isinstance(err, WinBiapUnsupportedPage)
                else "connection"
            )
            if self._snapshot is None:
                if isinstance(err, WinBiapInvalidAuth):
                    raise ConfigEntryAuthFailed from err
                raise UpdateFailed(self.refresh_error) from err
            if isinstance(err, WinBiapInvalidAuth):
                self._entry.async_start_reauth(self.hass)
            _LOGGER.warning(
                "WinBIAP refresh failed (%s); retaining last known data",
                self.refresh_error,
            )
            return self._snapshot

        updated = datetime.now(UTC).isoformat()
        self.stale_sections = set()
        for section in SECTIONS:
            if getattr(account, section) is not None:
                self.section_updated[section] = updated
                self.section_origins[section] = "successful_fetch"
            else:
                self.stale_sections.add(section)
                if self._snapshot is not None:
                    account = replace(
                        account, **{section: getattr(self._snapshot, section)}
                    )
        self.refresh_error = "partial_update" if self.stale_sections else None
        self._snapshot = account
        try:
            await self._store.async_save(
                {
                    "account": encode_account(account),
                    "section_updated": self.section_updated,
                    "section_origins": self.section_origins,
                }
            )
        except OSError:
            _LOGGER.warning("Could not persist WinBIAP snapshot; memory copy retained")
        return account
