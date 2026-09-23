"""Tests against real HA APIs; run separately from the lightweight test doubles."""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import date
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, loader
from homeassistant.components.network import async_get_adapters
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.setup import async_setup_component

from custom_components.winbiap.api import WinBiapClient, WinBiapInvalidAuth
from custom_components.winbiap.config_flow import _validate
from custom_components.winbiap.models import WinBiapAccount, WinBiapLoan

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
        account = WinBiapAccount(
            loans=(
                WinBiapLoan(
                    item_id="synthetic-item",
                    title="Synthetic loan",
                    due_date=date(2030, 1, 2),
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
                states = hass.states.async_all("sensor")
                assert len(states) == 4
                assert all(s.state not in {"unknown", "unavailable"} for s in states)
                assert sorted(s.state for s in states) == [
                    "0",
                    "1",
                    "2030-01-02",
                    "2030-01-02",
                ]
                old_session = entry.runtime_data.client._session
                assert not old_session.closed
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert old_session.closed
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
