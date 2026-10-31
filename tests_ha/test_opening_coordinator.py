"""Public fetch failures and caching cannot invalidate library account data."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.winbiap.opening_coordinator import OpeningHoursCoordinator
from custom_components.winbiap.opening_hours import OpeningHours


def test_cached_schedule_does_not_fetch_and_stale_failure(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            entry = SimpleNamespace(
                data={"base_url": "https://opac.winbiap.net/koenigsbrunn/"},
                options={},
                async_on_unload=Mock(),
            )
            session = Mock(get=Mock(side_effect=TimeoutError))
            coordinator = OpeningHoursCoordinator(hass, entry, session)
            coordinator.data = OpeningHours(((),) * 7, (), datetime.now(UTC))
            assert await coordinator._async_update_data() is coordinator.data
            session.get.assert_not_called()
            coordinator.data = OpeningHours(
                ((),) * 7, (), datetime.now(UTC) - timedelta(days=2)
            )
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_generic_fetch_cache_restore_and_settings_isolation(tmp_path):
    from unittest.mock import AsyncMock

    from custom_components.winbiap.public_hours import parse_public_hours

    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            entry = SimpleNamespace(
                entry_id="public-test",
                data={"base_url": "https://example.org/demo/"},
                options={},
                async_on_unload=Mock(),
            )
            parsed = parse_public_hours(
                "<h2>Öffnungszeiten</h2><p>Mo: 10:00-18:00</p>",
                "https://example.org/demo/index.aspx",
            )
            original = OpeningHoursCoordinator(hass, entry, Mock())
            original._automatic = AsyncMock(return_value=parsed)
            fresh = await original._async_update_data()
            assert fresh.source == parsed.source and fresh.known_days == (0,)
            restored = OpeningHoursCoordinator(hass, entry, Mock())
            restored._automatic = AsyncMock(side_effect=TimeoutError)
            assert (await restored._async_update_data()).weekly == fresh.weekly
            restored._automatic.assert_not_called()
            restored.data = OpeningHours(
                fresh.weekly, (), datetime.now(UTC) - timedelta(days=3), fresh.source
            )
            with pytest.raises(UpdateFailed):
                await restored._async_update_data()
            assert restored.data is not None
            entry.options = {"opening_timezone": "America/New_York"}
            changed = OpeningHoursCoordinator(hass, entry, Mock())
            changed._automatic = AsyncMock(side_effect=TimeoutError)
            with pytest.raises(UpdateFailed):
                await changed._async_update_data()
            assert changed.data is None
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_manual_and_external_fallback(tmp_path):
    from unittest.mock import AsyncMock

    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            weekly = "Mo: 10:00-18:00\nDi: closed\nMi: closed\nDo: closed\nFr: closed\nSa: closed\nSo: closed"
            entry = SimpleNamespace(
                data={"base_url": "https://example.org/demo/"},
                options={
                    "opening_weekly": weekly,
                    "opening_exceptions": "2030-01-07: closed",
                },
                async_on_unload=Mock(),
            )
            coordinator = OpeningHoursCoordinator(hass, entry, Mock())
            coordinator._automatic = AsyncMock(side_effect=AssertionError)
            data = await coordinator._async_update_data()
            assert data.manual and dict(data.exceptions)["2030-01-07"] == ()
            coordinator._automatic.assert_not_called()
            entry.options = {"opening_source_url": "https://public.example/hours"}
            coordinator = OpeningHoursCoordinator(hass, entry, Mock())
            coordinator._automatic = AsyncMock(side_effect=TimeoutError)
            coordinator._http = AsyncMock(
                return_value="<h2>Öffnungszeiten</h2><p>Mo: 10:00-18:00</p>"
            )
            data = await coordinator._async_update_data()
            assert data.source == "https://public.example/hours"
            coordinator._http.assert_awaited_once_with(data.source)
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_public_browser_has_no_credentials_and_always_closes(tmp_path):
    from unittest.mock import AsyncMock, patch

    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            entry = SimpleNamespace(
                data={"base_url": "https://example.org/demo/"},
                options={},
                async_on_unload=Mock(),
            )
            coordinator = OpeningHoursCoordinator(hass, entry, Mock())
            coordinator._http = AsyncMock(side_effect=TimeoutError)
            browser = SimpleNamespace(
                async_public_page=AsyncMock(
                    return_value="<h2>Öffnungszeiten</h2><p>Mo: 10:00-18:00</p>"
                ),
                async_close=AsyncMock(),
            )
            with patch(
                "custom_components.winbiap.browser.BrowserClient", return_value=browser
            ) as factory:
                assert (await coordinator._automatic()).known_days == (0,)
                assert factory.call_args.args[1:3] == ("", "")
                browser.async_close.assert_awaited_once()
                browser.async_public_page.side_effect = TimeoutError
                with pytest.raises(TimeoutError):
                    await coordinator._automatic()
                assert browser.async_close.await_count == 2
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())
