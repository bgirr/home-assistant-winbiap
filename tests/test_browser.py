"""Private session restoration, scope and credential-change isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.winbiap import browser as module


@pytest.mark.parametrize("same_account", [True, False])
def test_session_restored_only_for_same_credentials(monkeypatch, same_account):
    async def run():
        store = SimpleNamespace(async_load=AsyncMock(), async_remove=AsyncMock())
        client = module.BrowserClient(
            "https://example.org/library/",
            "CARD",
            "SECRET",
            "/tmp",
            session_store=store,
        )
        state = {
            "cookies": [
                {"domain": "example.org", "name": "session", "value": "PRIVATE"},
                {"domain": "unrelated.org", "name": "session", "value": "OTHER"},
            ],
            "origins": [
                {"origin": "https://example.org", "localStorage": []},
                {"origin": "https://unrelated.org", "localStorage": []},
            ],
        }
        store.async_load.return_value = {
            "account": client._fingerprint if same_account else "other",
            "account_url": "https://example.org/library/user/loans.aspx",
            "state": state,
        }
        page = SimpleNamespace(set_default_timeout=Mock(), route=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        browser = SimpleNamespace(
            new_context=AsyncMock(return_value=context), close=AsyncMock()
        )
        driver = SimpleNamespace(
            chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)),
            stop=AsyncMock(),
        )
        monkeypatch.setattr(
            module,
            "_load_runtime",
            lambda _: (
                lambda: SimpleNamespace(start=AsyncMock(return_value=driver)),
                "/synthetic/chromium",
            ),
        )
        await client._ensure_browser()
        restored = browser.new_context.call_args.kwargs["storage_state"]
        if same_account:
            assert len(restored["cookies"]) == 1 and len(restored["origins"]) == 1
            assert client._account_url.endswith("/loans.aspx")
        else:
            assert restored is None and client._account_url is None
        assert "SECRET" not in client._fingerprint
        await client.async_close()
        browser.close.assert_awaited_once()

    asyncio.run(run())


def test_public_page_waits_for_content_without_login_and_bounds_output():
    async def run():
        client = module.BrowserClient("https://example.org/library/", "", "", "/tmp")
        client._request = AsyncMock(return_value=("<main></main>", client.base_url))
        wait = AsyncMock()
        client._page = SimpleNamespace(
            locator=Mock(return_value=SimpleNamespace(wait_for=wait))
        )
        client._settled_content = AsyncMock(
            return_value=("<main>Public hours</main>", client.base_url)
        )
        client.async_login = AsyncMock(side_effect=AssertionError)
        assert "Public hours" in await client.async_public_page(client.base_url)
        wait.assert_awaited_once_with(state="attached", timeout=15000)
        client.async_login.assert_not_called()
        client._settled_content.return_value = (
            "<main>Other library</main>",
            "https://example.org/other/index.aspx",
        )
        with pytest.raises(module.WinBiapUnsupportedPage):
            await client.async_public_page(client.base_url)
        client._settled_content.return_value = ("x" * 2_000_001, client.base_url)
        with pytest.raises(module.WinBiapCannotConnect):
            await client.async_public_page(client.base_url)
        wait.side_effect = RuntimeError("Synthetic browser error")
        with pytest.raises(
            module.WinBiapCannotConnect, match="public_page_unavailable"
        ):
            await client.async_public_page(client.base_url)

    asyncio.run(run())
