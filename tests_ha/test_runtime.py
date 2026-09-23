"""Tests against real HA APIs; run separately from the lightweight test doubles."""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import DummyCookieJar
from homeassistant import config_entries, loader
from homeassistant.auth import auth_manager_from_config
from homeassistant.components.image.const import DATA_COMPONENT as IMAGE_COMPONENT
from homeassistant.components.network import async_get_adapters
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.setup import async_setup_component

from custom_components.winbiap.api import WinBiapClient, WinBiapInvalidAuth
from custom_components.winbiap.config_flow import _validate
from custom_components.winbiap.models import (
    WinBiapAccount,
    WinBiapBalance,
    WinBiapLoan,
    WinBiapReservation,
    WinBiapWishlistItem,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def isolate_zeroconf_instances(monkeypatch):
    # HA normally has one process-wide instance; these tests create a fresh HA
    # per case. Avoid permanently patching the third-party Zeroconf constructor.
    monkeypatch.setattr(
        "homeassistant.components.zeroconf.install_multiple_zeroconf_catcher",
        lambda instance: None,
    )


def test_real_sensor_setup_reload_and_unload(tmp_path, caplog):
    """Exercise registration, state writing, HA session cleanup and reload."""

    async def run():
        shutil.copytree(ROOT / "custom_components", tmp_path / "custom_components")
        hass = HomeAssistant(str(tmp_path))
        frame.async_setup(hass)
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await hass.config_entries.async_initialize()
        await dr.async_load(hass)
        await er.async_load(hass)
        hass.auth = await auth_manager_from_config(hass, [], [])
        account = WinBiapAccount(
            loans=(
                WinBiapLoan(
                    item_id="synthetic-item",
                    title="Synthetic loan",
                    due_date=date(2030, 1, 2),
                    cover_url="https://covers.example.org/synthetic.png",
                ),
            )
        )
        entry = config_entries.ConfigEntry(
            version=1,
            minor_version=1,
            domain="winbiap",
            title="Synthetic library",
            data={
                "base_url": "https://example.org/demo/",
                "library_card": "SYNTHETIC",
                "password": "SYNTHETIC",
            },
            options={},
            source=config_entries.SOURCE_USER,
            unique_id="synthetic-account",
            discovery_keys=MappingProxyType({}),
            subentries_data=[],
        )
        try:
            with patch.object(
                WinBiapClient, "async_get_account", AsyncMock(return_value=account)
            ):
                await async_get_adapters(hass)
                assert await async_setup_component(hass, "sensor", {})
                await hass.config_entries.async_add(entry)
                await hass.async_block_till_done()
                assert entry.state is config_entries.ConfigEntryState.LOADED
                wishlist_entity = next(
                    s
                    for s in hass.states.async_all("sensor")
                    if s.entity_id.endswith("merkliste")
                )
                assert wishlist_entity.state == "unavailable"
                fee_entity = next(
                    s
                    for s in hass.states.async_all("sensor")
                    if s.entity_id.endswith("gebuhren")
                )
                assert fee_entity.state == "unavailable"
                reservation_entity = next(
                    s
                    for s in hass.states.async_all("sensor")
                    if s.entity_id.endswith("vorbestellungen")
                )
                assert reservation_entity.state == "unavailable"
                states = [
                    s
                    for s in hass.states.async_all("sensor")
                    if s.entity_id
                    not in {
                        reservation_entity.entity_id,
                        fee_entity.entity_id,
                        wishlist_entity.entity_id,
                    }
                ]
                assert len(states) == 4
                assert all(s.state not in {"unknown", "unavailable"} for s in states)
                assert sorted(s.state for s in states) == [
                    "0",
                    "1",
                    "2030-01-02",
                    "2030-01-02",
                ]
                images = hass.states.async_all("image")
                assert len(images) == 1
                assert images[0].state not in {"unknown", "unavailable"}
                assert (
                    images[0]
                    .attributes["entity_picture"]
                    .startswith("/api/image_proxy/")
                )
                cover_session = (
                    hass.data[IMAGE_COMPONENT].get_entity(images[0].entity_id)._session
                )
                assert isinstance(cover_session.cookie_jar, DummyCookieJar)
                second = WinBiapLoan(
                    item_id="synthetic-second",
                    title="Second synthetic book",
                    due_date=date(2030, 1, 3),
                    cover_url="https://covers.example.org/two.png",
                )
                coordinator = entry.runtime_data
                coordinator.async_set_updated_data(
                    WinBiapAccount(loans=(*account.loans, second))
                )
                await hass.async_block_till_done()
                assert len(hass.states.async_all("image")) == 2
                coordinator.async_set_updated_data(account)
                await hass.async_block_till_done()
                assert (
                    sum(
                        state.state == "unavailable"
                        for state in hass.states.async_all("image")
                    )
                    == 1
                )
                reservation = WinBiapReservation(
                    "reservation-1",
                    "Synthetic reservation",
                    status="Abholbereit",
                    ready_for_pickup=True,
                    pickup_deadline=date(2030, 1, 4),
                    cover_url="https://covers.example.org/reserved.png",
                )
                coordinator.async_set_updated_data(
                    replace(account, reservations=(reservation,))
                )
                await hass.async_block_till_done()
                reservation_state = hass.states.get(reservation_entity.entity_id)
                assert reservation_state.state == "1"
                assert reservation_state.attributes["ready_for_pickup"] == 1
                assert (
                    reservation_state.attributes["reservations"][0]["pickup_deadline"]
                    == "2030-01-04"
                )
                covers = [
                    s
                    for s in hass.states.async_all("image")
                    if s.attributes.get("reservation_id") == "reservation-1"
                ]
                assert len(covers) == 1 and covers[0].state != "unavailable"
                cover_id = covers[0].entity_id
                coordinator.async_set_updated_data(
                    replace(
                        account, reservations=(replace(reservation, status="Geändert"),)
                    )
                )
                await hass.async_block_till_done()
                assert hass.states.get(cover_id).state != "unavailable"
                coordinator.async_set_updated_data(replace(account, reservations=()))
                await hass.async_block_till_done()
                assert hass.states.get(reservation_entity.entity_id).state == "0"
                assert hass.states.get(cover_id).state == "unavailable"
                for amount in (Decimal("0.00"), Decimal("2.50"), Decimal("-1.25")):
                    coordinator.async_set_updated_data(
                        replace(account, fees=WinBiapBalance(amount, "EUR"))
                    )
                    await hass.async_block_till_done()
                    fee_state = hass.states.get(fee_entity.entity_id)
                    assert Decimal(fee_state.state) == amount
                    assert fee_state.attributes["device_class"] == "monetary"
                    assert fee_state.attributes["unit_of_measurement"] == "EUR"
                coordinator.async_set_updated_data(account)
                await hass.async_block_till_done()
                assert hass.states.get(fee_entity.entity_id).state == "unavailable"
                wished = WinBiapWishlistItem(
                    "wish-1",
                    "Synthetic wished book",
                    cover_url="https://covers.example.org/wish.png",
                )
                coordinator.async_set_updated_data(replace(account, wishlist=(wished,)))
                await hass.async_block_till_done()
                assert hass.states.get(wishlist_entity.entity_id).state == "1"
                wish_covers = [
                    s
                    for s in hass.states.async_all("image")
                    if s.attributes.get("wishlist_id") == "wish-1"
                ]
                assert len(wish_covers) == 1 and wish_covers[0].state != "unavailable"
                coordinator.async_set_updated_data(replace(account, wishlist=()))
                await hass.async_block_till_done()
                assert hass.states.get(wishlist_entity.entity_id).state == "0"
                assert hass.states.get(wish_covers[0].entity_id).state == "unavailable"
                old_session = entry.runtime_data.client._session
                assert cover_session is not old_session
                assert not old_session.closed
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert old_session.closed
                assert cover_session.closed
                new_session = entry.runtime_data.client._session
                assert new_session is not old_session
                assert new_session.cookie_jar is not old_session.cookie_jar
                assert await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()
                assert new_session.closed
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert not [
        record
        for record in caplog.records
        if record.name == "homeassistant.helpers.frame"
    ]


@pytest.mark.parametrize("failure", [None, WinBiapInvalidAuth(), TimeoutError()])
def test_real_config_flow_session_cleanup(tmp_path, caplog, failure):
    """Use the actual HA session wrapper, including its close-warning behavior."""
    from homeassistant.helpers.aiohttp_client import async_create_clientsession

    async def run():
        hass = HomeAssistant(str(tmp_path))
        frame.async_setup(hass)
        await async_get_adapters(hass)
        sessions = []

        def create(*args, **kwargs):
            session = async_create_clientsession(*args, **kwargs)
            sessions.append(session)
            return session

        try:
            with (
                patch(
                    "custom_components.winbiap.config_flow.async_create_clientsession",
                    create,
                ),
                patch.object(
                    WinBiapClient, "async_get_account", AsyncMock(side_effect=failure)
                ),
            ):
                data = {
                    "base_url": "https://example.org/demo/",
                    "library_card": "SYNTHETIC",
                    "password": "SYNTHETIC",
                }
                if failure is None:
                    assert await _validate(hass, data) == data["base_url"]
                else:
                    with pytest.raises(type(failure)):
                        await _validate(hass, data)
                assert len(sessions) == 1
                assert sessions[0].closed
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())
    assert not [
        record
        for record in caplog.records
        if record.name == "homeassistant.helpers.frame"
    ]
