"""Last-known data survives outages, partial failures and HA restarts."""

import asyncio
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.winbiap.api import (
    WinBiapCannotConnect,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
)
from custom_components.winbiap.coordinator import WinBiapCoordinator
from custom_components.winbiap.models import (
    WinBiapAccount,
    WinBiapBalance,
    WinBiapLoan,
    WinBiapReservation,
    WinBiapWishlistItem,
)
from custom_components.winbiap.snapshot import decode_account, encode_account

ACCOUNT = WinBiapAccount(
    loans=(WinBiapLoan("book", "Synthetic title", date(2030, 1, 2), renewable=False),),
    reservations=(
        WinBiapReservation("reserved", "Synthetic", pickup_deadline=date(2030, 1, 3)),
    ),
    fees=WinBiapBalance(Decimal("2.50"), "EUR"),
    wishlist=(WinBiapWishlistItem("wish", "Synthetic"),),
)


def test_snapshot_roundtrip():
    assert decode_account(json.loads(json.dumps(encode_account(ACCOUNT)))) == ACCOUNT
    assert decode_account(encode_account(WinBiapAccount(()))) == WinBiapAccount(())


@pytest.mark.parametrize(
    "error",
    [
        WinBiapCannotConnect("request_failed"),
        WinBiapUnsupportedPage("browser_verification_required"),
        WinBiapInvalidAuth(),
        TimeoutError(),
    ],
)
def test_outage_restart_recovery_and_real_empty(tmp_path, error):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = SimpleNamespace(
            entry_id="test", async_on_unload=Mock(), async_start_reauth=Mock()
        )
        client = SimpleNamespace(async_get_account=AsyncMock(return_value=ACCOUNT))
        try:
            first = WinBiapCoordinator(hass, entry, client)
            assert await first._async_update_data() == ACCOUNT
            timestamp = first.freshness()["last_successful_update"]
            assert timestamp and not first.freshness()["data_stale"]
            client.async_get_account.side_effect = error
            assert await first._async_update_data() == ACCOUNT
            assert first.freshness()["data_stale"]
            assert first.freshness()["last_successful_update"] == timestamp
            restored = WinBiapCoordinator(hass, entry, client)
            assert await restored._async_update_data() == ACCOUNT
            assert restored.freshness()["last_successful_update"] == timestamp
            assert restored.freshness()["data_stale"]
            if isinstance(error, WinBiapInvalidAuth):
                entry.async_start_reauth.assert_called_with(hass)
            # Explicit empty data is authoritative, never sticky old loans.
            client.async_get_account.side_effect = None
            client.async_get_account.return_value = WinBiapAccount(
                (), (), WinBiapBalance(Decimal(0), "EUR"), ()
            )
            empty = await restored._async_update_data()
            assert (
                empty.loans == () and empty.reservations == () and empty.wishlist == ()
            )
            assert empty.fees.amount == 0
            assert not restored.freshness()["data_stale"]
            assert restored.refresh_error is None
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_partial_failure_retains_only_failed_sections(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = SimpleNamespace(entry_id="test", async_on_unload=Mock())
        client = SimpleNamespace(async_get_account=AsyncMock(return_value=ACCOUNT))
        try:
            coordinator = WinBiapCoordinator(hass, entry, client)
            await coordinator._async_update_data()
            old_fee_time = coordinator.freshness("fees")["last_successful_update"]
            client.async_get_account.return_value = replace(
                ACCOUNT, loans=(), reservations=(), fees=None, wishlist=None
            )
            data = await coordinator._async_update_data()
            assert data.loans == () and data.reservations == ()
            assert data.fees == ACCOUNT.fees and data.wishlist == ACCOUNT.wishlist
            assert coordinator.stale_sections == {"fees", "wishlist"}
            assert (
                coordinator.freshness("fees")["last_successful_update"] == old_fee_time
            )
            assert not coordinator.freshness()["data_stale"]
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


@pytest.mark.parametrize("corrupt", [False, True])
def test_no_snapshot_does_not_invent_zero(tmp_path, corrupt):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = SimpleNamespace(entry_id="test", async_on_unload=Mock())
        client = SimpleNamespace(
            async_get_account=AsyncMock(side_effect=WinBiapCannotConnect())
        )
        try:
            coordinator = WinBiapCoordinator(hass, entry, client)
            if corrupt:
                await coordinator._store.async_save(
                    {"account": {"loans": [{"due_date": "broken"}]}}
                )
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()
            assert coordinator._snapshot is None
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_recorder_recovery_does_not_claim_successful_poll(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = SimpleNamespace(entry_id="test", async_on_unload=Mock())
        client = SimpleNamespace(
            async_get_account=AsyncMock(side_effect=WinBiapCannotConnect())
        )
        try:
            coordinator = WinBiapCoordinator(hass, entry, client)
            stamp = "2026-09-25T13:55:17+00:00"
            await coordinator._store.async_save(
                {
                    "account": encode_account(ACCOUNT),
                    "section_updated": {"loans": stamp},
                    "section_origins": {"loans": "recorder_recovery"},
                }
            )
            assert await coordinator._async_update_data() == ACCOUNT
            assert coordinator.freshness()["last_successful_update"] is None
            assert coordinator.freshness()["last_known_update"] == stamp
            assert coordinator.freshness()["data_stale"]
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())
