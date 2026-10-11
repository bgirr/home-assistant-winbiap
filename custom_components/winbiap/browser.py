"""Local Chromium transport, sharing the existing read-only account parsers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urljoin

from .api import (
    LOGIN_BUTTON,
    LOGIN_NAME,
    LOGIN_PASSWORD,
    WinBiapCannotConnect,
    WinBiapClient,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
    find_account_url,
    has_login_form,
    page_is_login,
)


def browser_executable(config_dir: str) -> str:
    """Resolve the pinned runtime outside HACS files; call in an executor."""
    import playwright

    metadata = Path(playwright.__file__).parent / "driver/package/browsers.json"
    browsers = json.loads(metadata.read_text())["browsers"]
    revision = next(b["revision"] for b in browsers if b["name"] == "chromium")
    executable = (
        Path(config_dir)
        / ".winbiap-browser"
        / f"chromium-{revision}"
        / "chrome-linux64/chrome"
    )
    if not executable.is_file():
        raise WinBiapCannotConnect("browser_runtime_missing")
    return str(executable)


def _load_runtime(config_dir):
    from playwright.async_api import async_playwright

    return async_playwright, browser_executable(config_dir)


class BrowserClient(WinBiapClient):
    """Keep one ephemeral browser context per account; never export cookies."""

    def __init__(self, base_url, card, password, config_dir):
        super().__init__(None, base_url, card, password)
        self._config_dir = config_dir
        self._playwright = None
        self._browser = None
        self._page = None

    async def _ensure_browser(self):
        if self._page is not None and not self._page.is_closed():
            return
        async_playwright, executable = await asyncio.to_thread(
            _load_runtime, self._config_dir
        )
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                executable_path=executable,
                channel="chromium",
                headless=True,
                chromium_sandbox=True,
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
            context = await self._browser.new_context(accept_downloads=False)
            self._page = await context.new_page()
            self._page.set_default_timeout(20000)

            # Constrain top-level navigations, including redirects, before sending
            # credentials. The site's own verification iframe remains functional.
            async def guard(route):
                request = route.request
                if (
                    request.is_navigation_request()
                    and request.frame == self._page.main_frame
                ):
                    try:
                        self._safe_url(request.url)
                    except WinBiapUnsupportedPage:
                        await route.abort()
                        return
                await route.continue_()

            await self._page.route("**/*", guard)
        except BaseException:
            await self.async_close()
            raise

    async def _settled_content(self):
        html = await self._page.content()
        if 'id="capjs-frame"' in html or 'id="challenge"' in html:
            await self._page.locator("#capjs-frame").wait_for(
                state="detached", timeout=75000
            )
            await self._page.locator("#challenge").wait_for(
                state="detached", timeout=75000
            )
            html = await self._page.content()
        self._safe_url(self._page.url)
        return html, self._page.url

    async def _request(self, method, url, *, data=None):
        try:
            return await self._browser_request(method, url, data=data)
        except (WinBiapCannotConnect, WinBiapInvalidAuth, WinBiapUnsupportedPage):
            raise
        except Exception:
            raise WinBiapCannotConnect(
                "browser_request_failed", category="browser"
            ) from None

    async def _browser_request(self, method, url, *, data=None):
        self._safe_url(url)
        await self._ensure_browser()
        if method == "GET":
            response = await self._page.goto(url, wait_until="domcontentloaded")
            if response is not None and response.status >= 400:
                raise WinBiapCannotConnect("browser_http_error")
        elif method == "POST":
            # Only the existing own-wishlist pagination parser emits this POST.
            if not url.split("?", 1)[0].endswith("/favorites.aspx"):
                raise WinBiapUnsupportedPage("unsupported_browser_post")
            async with self._page.expect_navigation(wait_until="domcontentloaded"):
                await self._page.evaluate(
                    """({url, data}) => {
                      const form = document.createElement('form');
                      form.method = 'POST'; form.action = url;
                      for (const [name, value] of Object.entries(data)) {
                        const input = document.createElement('input');
                        input.type = 'hidden'; input.name = name; input.value = value;
                        form.appendChild(input);
                      }
                      document.body.appendChild(form); form.submit();
                    }""",
                    {"url": url, "data": data},
                )
        else:
            raise WinBiapUnsupportedPage("unsupported_browser_method")
        return await self._settled_content()

    async def async_login(self):
        html, url = await self._request(
            "GET", urljoin(self.base_url, "user/login.aspx")
        )
        if not has_login_form(html):
            # Verification can remove its DOM before the redirected login loads.
            await self._page.locator(f'[name="{LOGIN_PASSWORD}"]').wait_for(
                state="visible", timeout=75000
            )
            html, url = await self._settled_content()
        if not has_login_form(html):
            raise WinBiapUnsupportedPage("browser_login_form_missing")
        # Check the actual form action as well as the page origin before typing.
        action = await self._page.locator(
            f'form:has([name="{LOGIN_PASSWORD}"])'
        ).get_attribute("action")
        self._safe_url(urljoin(url, action or url))
        await self._page.locator(f'[name="{LOGIN_NAME}"]').fill(self._library_card)
        await self._page.locator(f'[name="{LOGIN_PASSWORD}"]').fill(self._password)
        async with self._page.expect_navigation(wait_until="domcontentloaded"):
            await self._page.locator(f'[name="{LOGIN_BUTTON}"]').click()
        html, url = await self._settled_content()
        if page_is_login(html, url):
            raise WinBiapInvalidAuth("credentials_rejected")
        self._account_url = find_account_url(html, url) or url
        return html, url

    async def async_close(self):
        """Close contexts, browser and driver, including partially started ones."""
        browser, driver = self._browser, self._playwright
        self._page = self._browser = self._playwright = None
        self._account_url = None
        try:
            if browser is not None:
                await browser.close()
        finally:
            if driver is not None:
                await driver.stop()
