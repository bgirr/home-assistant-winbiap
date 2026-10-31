"""Independent public opening schedules with bounded discovery and local cache."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from aiohttp import ClientError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WinBiapError
from .opening_hours import (
    SOURCE_URL,
    OpeningHours,
    parse_exceptions,
    parse_opening_hours,
)
from .public_hours import (
    opening_links,
    parse_public_hours,
    parse_weekly,
    validate_source,
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
        self.base_url = entry.data["base_url"].rstrip("/") + "/"
        self.timezone = entry.options.get("opening_timezone") or hass.config.time_zone
        self._store = (
            Store(hass, 1, f"winbiap.hours.{entry.entry_id}")
            if hasattr(entry, "entry_id")
            else None
        )
        self._restored = False

    def _settings(self):
        return {
            "base_url": self.base_url,
            "options": dict(self.entry.options),
            "timezone": self.timezone,
        }

    async def _restore(self):
        self._restored = True
        if self._store is None:
            return
        try:
            saved = await self._store.async_load()
            if not saved or saved["settings"] != self._settings():
                return
            weekly = parse_weekly(saved["weekly"])
            exceptions = parse_exceptions(saved["exceptions"])
            fetched = datetime.fromisoformat(saved["fetched_at"])
            known = tuple(saved["known_days"])
            if fetched.tzinfo is None or any(
                type(i) is not int or i not in range(7) for i in known
            ):
                return
            self.data = OpeningHours(
                weekly,
                exceptions,
                fetched,
                validate_source(saved["source"]),
                known,
                self.timezone,
            )
        except (OSError, ValueError, KeyError, TypeError):
            return

    async def _save(self, data):
        if self._store is None:
            return

        def windows(value):
            return ", ".join(f"{a}-{b}" for a, b in value) or "closed"

        from .opening_hours import DAYS

        payload = {
            "settings": self._settings(),
            "weekly": "\n".join(
                f"{day}: {windows(data.weekly[i])}" for i, day in enumerate(DAYS)
            ),
            "exceptions": "\n".join(
                f"{day}: {windows(w)}" for day, w in data.exceptions
            ),
            "fetched_at": data.fetched_at.isoformat(),
            "source": data.source,
            "known_days": data.known_days,
        }
        try:
            await self._store.async_save(payload)
        except OSError:
            self.logger.warning("Opening-hours cache could not be saved")

    async def _http(self, url):
        async with asyncio.timeout(15):
            async with self.session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    raise ValueError("opening_source_unavailable")
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("opening_source_too_large")
                return body.decode("utf-8")

    async def _discover(self, fetch):
        html = await fetch(self.base_url + "index.aspx")
        # Prefer the dedicated contact page, which may include dated exceptions.
        for url in opening_links(html, self.base_url):
            try:
                return parse_public_hours(await fetch(url), url)
            except (ClientError, TimeoutError, ValueError, UnicodeError, WinBiapError):
                continue
        return parse_public_hours(html, self.base_url + "index.aspx")

    async def _automatic(self):
        try:
            return await self._discover(self._http)
        except (ClientError, TimeoutError, ValueError, UnicodeError):
            pass
        # Public, separate browser context: no card, password or account session.
        from .browser import BrowserClient

        browser = BrowserClient(self.base_url, "", "", self.hass.config.config_dir)
        try:
            async with asyncio.timeout(90):
                return await self._discover(browser.async_public_page)
        finally:
            await browser.async_close()

    async def _async_update_data(self):
        if not self._restored:
            await self._restore()
        manual = self.entry.options.get("opening_weekly", "").strip()
        if (
            not manual
            and self.data
            and timedelta(0)
            <= datetime.now(UTC) - self.data.fetched_at
            < timedelta(days=1)
        ):
            return self.data
        try:
            if manual:
                data = OpeningHours(
                    parse_weekly(manual),
                    (),
                    datetime.now(UTC),
                    "manual",
                    timezone=self.timezone,
                    manual=True,
                )
            else:
                try:
                    data = await self._automatic()
                except (
                    ClientError,
                    TimeoutError,
                    ValueError,
                    UnicodeError,
                    WinBiapError,
                ):
                    source = self.entry.options.get("opening_source_url", "")
                    # Preserve the previous public source for existing Königsbrunn users.
                    if (
                        not source
                        and self.base_url == "https://opac.winbiap.net/koenigsbrunn/"
                    ):
                        source = SOURCE_URL
                    if not source:
                        raise ValueError("opening_hours_unavailable") from None
                    html = await self._http(validate_source(source))
                    if source == SOURCE_URL:
                        data = parse_opening_hours(html)
                    else:
                        data = parse_public_hours(html, source)
            overrides = parse_exceptions(
                self.entry.options.get("opening_exceptions", "")
            )
            data = replace(
                data,
                exceptions=tuple(
                    sorted({**dict(data.exceptions), **dict(overrides)}.items())
                ),
                timezone=self.timezone,
            )
            if not manual:
                await self._save(data)
            return data
        except (
            ClientError,
            TimeoutError,
            ValueError,
            UnicodeError,
            WinBiapError,
        ) as err:
            raise UpdateFailed("opening_hours_unavailable") from err
