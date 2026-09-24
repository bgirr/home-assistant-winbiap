"""Exercise production flow/setup using HA API contract doubles, no HA runtime."""

import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientSession, CookieJar

from custom_components.winbiap.api import WinBiapInvalidAuth, WinBiapUnsupportedPage

ROOT = Path(__file__).parents[1] / "custom_components" / "winbiap"


@pytest.fixture
def modules(monkeypatch):
    class Flow:
        def __init_subclass__(cls, **kwargs):
            pass

    def stub(name, **attrs):
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    entries = stub(
        "homeassistant.config_entries",
        ConfigFlow=Flow,
        ConfigEntry=object,
        OptionsFlow=Flow,
    )
    stub("homeassistant", config_entries=entries)
    stub(
        "homeassistant.const",
        CONF_PASSWORD="password",
        Platform=SimpleNamespace(SENSOR="sensor", IMAGE="image"),
    )
    stub("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    stub("homeassistant.data_entry_flow", FlowResult=dict)
    stub("homeassistant.helpers", selector=SimpleNamespace())
    stub("homeassistant.helpers.aiohttp_client", async_create_clientsession=Mock())
    stub("voluptuous")
    stub("custom_components.winbiap.coordinator", WinBiapCoordinator=Mock())
    stub(
        "custom_components.winbiap.opening_coordinator",
        OpeningHoursCoordinator=Mock(
            side_effect=lambda *a: SimpleNamespace(async_refresh=AsyncMock())
        ),
    )
    # Unload imports that depend on these doubles after each test.
    monkeypatch.delitem(sys.modules, "custom_components.winbiap.const", raising=False)
    loaded = []
    for short, filename in (
        ("config_flow", "config_flow.py"),
        ("entry_test", "__init__.py"),
    ):
        name = "custom_components.winbiap." + short
        spec = importlib.util.spec_from_file_location(name, ROOT / filename)
        spec.submodule_search_locations = None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        WinBiapInvalidAuth(),
        WinBiapUnsupportedPage(),
        TimeoutError(),
        asyncio.CancelledError(),
        ValueError(),
    ],
)
def test_validation_always_detaches(modules, monkeypatch, outcome, caplog):
    flow, _ = modules

    async def run():
        session = ClientSession()
        connector = session.connector

        async def forbidden_close():
            logging.getLogger("homeassistant.helpers.frame").warning("forbidden close")
            raise AssertionError("HA session must not be closed")

        session.close = forbidden_close
        original_detach = session.detach
        session.detach = Mock(side_effect=original_detach)
        factory = Mock(return_value=session)
        monkeypatch.setattr(flow, "async_create_clientsession", factory)
        monkeypatch.setattr(
            flow,
            "WinBiapClient",
            Mock(
                return_value=SimpleNamespace(
                    async_get_account=AsyncMock(side_effect=outcome)
                )
            ),
        )
        try:
            data = {
                "base_url": "https://example.org/demo/",
                "library_card": "SYNTHETIC",
                "password": "SYNTHETIC",
            }
            if outcome is None:
                assert await flow._validate(None, data) == data["base_url"]
            else:
                with pytest.raises(type(outcome)):
                    await flow._validate(None, data)
            session.detach.assert_called_once()
            assert session.closed
            assert factory.call_args.kwargs["auto_cleanup"] is False
            assert isinstance(factory.call_args.kwargs["cookie_jar"], CookieJar)
        finally:
            original_detach()
            await connector.close()

    asyncio.run(run())
    assert not [r for r in caplog.records if r.name == "homeassistant.helpers.frame"]


def test_validation_actual_timeout_and_constructor_failure(modules, monkeypatch):
    flow, _ = modules

    async def run():
        session = Mock()
        monkeypatch.setattr(
            flow, "async_create_clientsession", Mock(return_value=session)
        )

        async def blocked():
            await asyncio.Event().wait()

        monkeypatch.setattr(flow, "VALIDATION_TIMEOUT", 0.001)
        monkeypatch.setattr(
            flow,
            "WinBiapClient",
            Mock(return_value=SimpleNamespace(async_get_account=blocked)),
        )
        data = {
            "base_url": "https://example.org/",
            "library_card": "SYNTHETIC",
            "password": "SYNTHETIC",
        }
        with pytest.raises(TimeoutError):
            await flow._validate(None, data)
        session.detach.assert_called_once()
        session.reset_mock()
        monkeypatch.setattr(flow, "WinBiapClient", Mock(side_effect=ValueError))
        with pytest.raises(ValueError):
            await flow._validate(None, data)
        session.detach.assert_called_once()
        session.close.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("refresh_failure", [False, True])
def test_entry_isolated_cookies_ha_cleanup(modules, monkeypatch, refresh_failure):
    _, entry_module = modules

    async def run():
        sessions = []
        jars = []

        def create(hass, *, auto_cleanup, cookie_jar):
            assert auto_cleanup is True
            jars.append(cookie_jar)
            session = Mock(close=AsyncMock(), detach=Mock())
            sessions.append(session)
            return session

        monkeypatch.setattr(entry_module, "async_create_clientsession", create)
        monkeypatch.setattr(
            entry_module,
            "WinBiapCoordinator",
            Mock(
                side_effect=lambda *args: SimpleNamespace(
                    async_config_entry_first_refresh=AsyncMock(
                        side_effect=TimeoutError if refresh_failure else None
                    )
                )
            ),
        )
        hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(),
                async_unload_platforms=AsyncMock(return_value=True),
            )
        )
        for _ in range(2):
            entry = SimpleNamespace(
                async_on_unload=Mock(),
                add_update_listener=Mock(),
                data={
                    "base_url": "https://example.org/",
                    "library_card": "SYNTHETIC",
                    "password": "SYNTHETIC",
                },
            )
            if refresh_failure:
                with pytest.raises(TimeoutError):
                    await entry_module.async_setup_entry(hass, entry)
            else:
                assert await entry_module.async_setup_entry(hass, entry)
                assert await entry_module.async_unload_entry(hass, entry)
        assert jars[0] is not jars[1]
        for session in sessions:
            session.close.assert_not_called()
            session.detach.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (WinBiapInvalidAuth(), "invalid_auth"),
        (WinBiapUnsupportedPage(), "unsupported_page"),
        (TimeoutError(), "timeout"),
    ],
)
def test_reauth_uses_same_validation_and_categorical_errors(
    modules, monkeypatch, failure, category
):
    flow_module, _ = modules
    flow = flow_module.WinBiapConfigFlow()
    flow.hass = None
    flow._get_reauth_entry = Mock(
        return_value=SimpleNamespace(
            data={
                "base_url": "https://example.org/",
                "library_card": "SYNTHETIC",
                "password": "OLD_SYNTHETIC",
            }
        )
    )
    flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs)
    validate = AsyncMock(side_effect=failure)
    monkeypatch.setattr(flow_module, "_validate", validate)
    monkeypatch.setattr(flow_module.vol, "Schema", lambda value: value, raising=False)
    monkeypatch.setattr(flow_module.vol, "Required", lambda value: value, raising=False)
    result = asyncio.run(flow.async_step_reauth_confirm({"password": "NEW_SYNTHETIC"}))
    assert result["errors"] == {"base": category}
    assert validate.call_args.args[1]["password"] == "NEW_SYNTHETIC"
