"""Cover caching, URL safety and private failure handling against real ImageEntity."""

import asyncio
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from aiohttp import ClientError
from homeassistant.core import HomeAssistant

from custom_components.winbiap.image import (
    MAX_IMAGE_BYTES,
    WinBiapCoverImage,
    _safe_cover_url,
)
from custom_components.winbiap.models import WinBiapAccount, WinBiapLoan


class Response:
    def __init__(
        self,
        content=b"synthetic-image",
        content_type="image/png",
        status=200,
        target=None,
    ):
        self.content = self
        self.body = content
        self.content_type = content_type
        self.status = status
        self.headers = {"Location": target} if target else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        if self.status >= 400:
            raise ClientError("PRIVATE_URL_AND_TOKEN")

    async def iter_chunked(self, size):
        yield self.body


def image_for(hass, *responses):
    loan = WinBiapLoan(
        "synthetic",
        "Synthetic book",
        date(2030, 1, 2),
        cover_url="https://covers.example.org/one.png",
    )
    coordinator = SimpleNamespace(
        data=WinBiapAccount((loan,)), last_update_success=True
    )
    session = Mock(get=Mock(side_effect=responses))
    image = WinBiapCoverImage(
        hass,
        coordinator,
        SimpleNamespace(unique_id="synthetic-account", entry_id="synthetic-entry"),
        session,
        loan.item_id,
    )
    image.async_write_ha_state = Mock()
    return image, session, coordinator, loan


def test_cache_and_returned_or_changed_loan(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            image, session, coordinator, loan = image_for(
                hass, Response(), Response(b"new-cover")
            )
            assert await image.async_image() == b"synthetic-image"
            assert await image.async_image() == b"synthetic-image"
            assert session.get.call_count == 1
            original_timestamp = image.image_last_updated
            coordinator.data = WinBiapAccount(
                (replace(loan, cover_url="https://covers.example.org/two.png"),)
            )
            image._handle_coordinator_update()
            assert image.image_last_updated > original_timestamp
            assert await image.async_image() == b"new-cover"
            coordinator.data = WinBiapAccount(())
            image._handle_coordinator_update()
            assert not image.available
            assert await image.async_image() is None
            assert session.get.call_count == 2
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        Response(content_type="text/html"),
        Response(status=500),
        Response(content=b""),
        Response(content=b"x" * (MAX_IMAGE_BYTES + 1)),
        Response(status=302, target="http://unsafe.example.org/cover"),
        Response(status=302, target="https://127.0.0.1/cover"),
        ClientError("PRIVATE_URL_AND_TOKEN"),
        TimeoutError("PRIVATE_URL_AND_TOKEN"),
    ],
)
def test_invalid_images_never_cached_or_logged(tmp_path, caplog, response):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        try:
            image, session, _, _ = image_for(hass, response)
            assert await image.async_image() is None
            assert image._image_bytes is None
            assert session.get.call_count == 1
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())
    assert "PRIVATE" not in caplog.text
    assert "https://" not in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/a",
        "file:///tmp/a",
        "https://user:secret@example.org/a",
        "https://127.0.0.1/a",
        "https://192.168.1.1/a",
        "https://localhost/a",
        "https://host.local/a",
        "https://[::1]/a",
    ],
)
def test_unsafe_image_url(url):
    assert not _safe_cover_url(url)


def test_public_cover_url():
    assert _safe_cover_url("https://covers.example.org/image.png")
