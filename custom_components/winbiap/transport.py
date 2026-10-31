"""Select HTTP or retain a working local browser with bounded work."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from .api import WinBiapCannotConnect, WinBiapInvalidAuth, WinBiapUnsupportedPage


class AccountTransport:
    def __init__(self, http, browser_factory, *, prefer_browser=False):
        self.http = http
        self._browser_factory = browser_factory
        self._browser = None
        self._prefer_browser = prefer_browser
        self._lock = asyncio.Lock()
        self._active_task = None
        self.fetch_method = "http"

    async def async_get_account(self):
        async with self._lock:
            self._active_task = asyncio.current_task()
            try:
                return await self._fetch()
            finally:
                self._active_task = None

    async def _fetch(self):
        if not self._prefer_browser:
            self.fetch_method = "http"
            try:
                async with asyncio.timeout(60):
                    account = await self.http.async_get_account()
            except WinBiapUnsupportedPage as err:
                if str(err) != "browser_verification_required":
                    raise
            else:
                await self._close_browser()
                return account
        self._prefer_browser = True
        self.fetch_method = "browser"
        try:
            if self._browser is None:
                self._browser = self._browser_factory()
            async with asyncio.timeout(120):
                account = await self._browser.async_get_account()
            return account
        except (WinBiapCannotConnect, WinBiapInvalidAuth, WinBiapUnsupportedPage):
            await self._close_browser()
            raise
        except asyncio.CancelledError:
            await self._close_browser()
            raise
        except Exception as err:
            await self._close_browser()
            # Playwright errors can contain URLs, DOM and submitted fields.
            raise WinBiapCannotConnect(
                "browser_timeout" if isinstance(err, TimeoutError) else "browser_failed"
            ) from None

    async def _close_browser(self):
        browser, self._browser = self._browser, None
        if browser is not None:
            with suppress(Exception):
                await browser.async_close()

    async def async_close(self):
        task = self._active_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with self._lock:
            await self._close_browser()
