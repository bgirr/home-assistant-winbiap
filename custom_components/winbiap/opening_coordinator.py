"""Independent, cookie-free public-hours coordinator with daily caching."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from aiohttp import ClientError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .opening_hours import (
    SOURCE_URL,
    OpeningHours,
    parse_exceptions,
    parse_opening_hours,
)


class OpeningHoursCoordinator(DataUpdateCoordinator[OpeningHours | None]):
    def __init__(self, hass, entry, session):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            config_entry=entry,
            name="winbiap_opening_hours",
            update_interval=timedelta(hours=1),
        )
        self.entry = entry
        self.session = session
        self.supported = (
            entry.data["base_url"].rstrip("/")
            == "https://opac.winbiap.net/koenigsbrunn"
        )

    async def _async_update_data(self):
        if not self.supported:
            return None
        if self.data and datetime.now(UTC) - self.data.fetched_at < timedelta(days=1):
            return self.data
        try:
            async with asyncio.timeout(15):
                async with self.session.get(
                    SOURCE_URL, allow_redirects=False
                ) as response:
                    if response.status != 200:
                        raise ValueError("opening_source_unavailable")
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise ValueError("opening_source_too_large")
                    data = parse_opening_hours(body.decode("utf-8"))
            overrides = parse_exceptions(
                self.entry.options.get("opening_exceptions", "")
            )
            merged = {**dict(data.exceptions), **dict(overrides)}
            return replace(data, exceptions=tuple(sorted(merged.items())))
        except (ClientError, TimeoutError, ValueError, UnicodeError) as err:
            raise UpdateFailed("opening_hours_unavailable") from err
