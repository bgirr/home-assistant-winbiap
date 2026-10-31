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
