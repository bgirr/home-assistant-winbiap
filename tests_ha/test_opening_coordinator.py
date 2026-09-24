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
