"""HTTP/browser selection, cooldown and cleanup without real credentials."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.winbiap import transport as transport_module
from custom_components.winbiap.api import (
    WinBiapCannotConnect,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
)
from custom_components.winbiap.models import WinBiapAccount
from custom_components.winbiap.transport import AccountTransport


def test_fallback_reuse_and_http_recovery(monkeypatch):
    async def run():
        clock = [100.0]
        monkeypatch.setattr(transport_module, "monotonic", lambda: clock[0])
        account = WinBiapAccount(())
        http = SimpleNamespace(
            async_get_account=AsyncMock(
                side_effect=WinBiapUnsupportedPage("browser_verification_required")
            )
        )
        browser = SimpleNamespace(
            async_get_account=AsyncMock(return_value=account), async_close=AsyncMock()
        )
        factory = Mock(return_value=browser)
        transport = AccountTransport(http, factory)
        assert await transport.async_get_account() == account
        assert transport.fetch_method == "browser"
        assert await transport.async_get_account() == account
        assert http.async_get_account.call_count == 1
        factory.assert_called_once()
        clock[0] += 6 * 3600
        http.async_get_account.side_effect = None
        http.async_get_account.return_value = account
        assert await transport.async_get_account() == account
        assert transport.fetch_method == "http"
        browser.async_close.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "error",
    [
        WinBiapCannotConnect(),
        WinBiapInvalidAuth(),
        WinBiapUnsupportedPage("changed_layout"),
    ],
)
def test_non_challenge_errors_do_not_start_browser(error):
    async def run():
        factory = Mock()
        transport = AccountTransport(
            SimpleNamespace(async_get_account=AsyncMock(side_effect=error)), factory
        )
        with pytest.raises(type(error)):
            await transport.async_get_account()
        factory.assert_not_called()

    asyncio.run(run())


def test_close_cancels_inflight_browser():
    async def run():
        started = asyncio.Event()

        async def blocked():
            started.set()
            await asyncio.Event().wait()

        browser = SimpleNamespace(async_get_account=blocked, async_close=AsyncMock())
        transport = AccountTransport(
            SimpleNamespace(
                async_get_account=AsyncMock(
                    side_effect=WinBiapUnsupportedPage("browser_verification_required")
                )
            ),
            lambda: browser,
        )
        fetch = asyncio.create_task(transport.async_get_account())
        await started.wait()
        await transport.async_close()
        assert fetch.cancelled()
        browser.async_close.assert_awaited_once()

    asyncio.run(run())


def test_browser_failure_is_private_and_retryable():
    async def run():
        browser = SimpleNamespace(
            async_get_account=AsyncMock(side_effect=RuntimeError("PRIVATE_HTML")),
            async_close=AsyncMock(),
        )
        transport = AccountTransport(
            SimpleNamespace(
                async_get_account=AsyncMock(
                    side_effect=WinBiapUnsupportedPage("browser_verification_required")
                )
            ),
            lambda: browser,
        )
        with pytest.raises(WinBiapCannotConnect, match=r"^browser_failed$"):
            await transport.async_get_account()
        browser.async_close.assert_awaited_once()

    asyncio.run(run())
