"""Read-only, cookie-free cover images for currently borrowed media."""

from __future__ import annotations

import asyncio
import logging
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError, ClientSession, DummyCookieJar
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import WinBiapCoordinator
from .models import WinBiapLoan

_LOGGER = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _safe_cover_url(url: str) -> bool:
    """Allow public HTTPS covers without user information or local addresses."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname.rstrip(".") if parsed.hostname else None
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or host == "localhost"
            or host.endswith((".localhost", ".local"))
        ):
            return False
        try:
            return ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add a cover entity for every loan with an image; discover new loans too."""
    coordinator: WinBiapCoordinator = entry.runtime_data
    # Never send the authenticated account session or its cookies to cover providers.
    session = async_create_clientsession(
        hass, auto_cleanup=True, cookie_jar=DummyCookieJar()
    )
    known: set[str] = set()
    known_reservations: set[str] = set()
    known_wishlist: set[str] = set()

    @callback
    def add_covers() -> None:
        new = [
            loan
            for loan in coordinator.data.loans
            if loan.item_id not in known
            and loan.cover_url
            and _safe_cover_url(loan.cover_url)
        ]
        known.update(loan.item_id for loan in new)
        async_add_entities(
            WinBiapCoverImage(hass, coordinator, entry, session, loan.item_id)
            for loan in new
        )

        reservations = [
            r
            for r in coordinator.data.reservations or ()
            if r.item_id not in known_reservations
            and r.cover_url
            and _safe_cover_url(r.cover_url)
        ]
        known_reservations.update(r.item_id for r in reservations)
        async_add_entities(
            WinBiapReservationCover(hass, coordinator, entry, session, r.item_id)
            for r in reservations
        )

        wishlist = [
            r
            for r in coordinator.data.wishlist or ()
            if r.item_id not in known_wishlist
            and r.cover_url
            and _safe_cover_url(r.cover_url)
        ]
        known_wishlist.update(r.item_id for r in wishlist)
        async_add_entities(
            WinBiapWishlistCover(hass, coordinator, entry, session, r.item_id)
            for r in wishlist
        )

    add_covers()
    entry.async_on_unload(coordinator.async_add_listener(add_covers))


class WinBiapCoverImage(CoordinatorEntity[WinBiapCoordinator], ImageEntity):
    """A cached cover served through Home Assistant's authenticated image proxy."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:book-open-page-variant"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: WinBiapCoordinator,
        entry: ConfigEntry,
        session: ClientSession,
        item_id: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._session = session
        self._item_id = item_id
        self._cover_url = self.loan.cover_url if self.loan else None
        self._image_bytes: bytes | None = None
        self._image_lock = asyncio.Lock()
        self._attr_unique_id = f"{entry.unique_id}_cover_{item_id}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def loan(self) -> WinBiapLoan | None:
        return next(
            (
                loan
                for loan in self.coordinator.data.loans
                if loan.item_id == self._item_id
            ),
            None,
        )

    @property
    def name(self) -> str:
        return f"{self.loan.title} Cover" if self.loan else "Returned item cover"

    @property
    def available(self) -> bool:
        return super().available and bool(
            self.loan and self.loan.cover_url and _safe_cover_url(self.loan.cover_url)
        )

    @property
    def extra_state_attributes(self):
        if not (loan := self.loan):
            return None
        return {
            "title": loan.title,
            "author": loan.author,
            "due_date": loan.due_date.isoformat(),
            "days_remaining": loan.days_remaining,
            "renewable": loan.renewable,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        new_url = self.loan.cover_url if self.loan else None
        if new_url != self._cover_url:
            self._cover_url = new_url
            self._image_bytes = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Fetch bounded image bytes, without logging URLs or response contents."""
        if not self.available:
            return None
        async with self._image_lock:
            if self._image_bytes is not None:
                return self._image_bytes
            source_url = self._cover_url
            url = source_url
            try:
                async with asyncio.timeout(10):
                    for _ in range(4):
                        if not url or not _safe_cover_url(url):
                            return None
                        async with self._session.get(
                            url, allow_redirects=False
                        ) as response:
                            if response.status in {301, 302, 303, 307, 308}:
                                target = response.headers.get("Location")
                                if not target:
                                    return None
                                url = urljoin(url, target)
                                continue
                            response.raise_for_status()
                            content_type = response.content_type
                            if content_type not in {
                                "image/jpeg",
                                "image/png",
                                "image/gif",
                                "image/webp",
                            }:
                                return None
                            content = bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                content.extend(chunk)
                                if len(content) > MAX_IMAGE_BYTES:
                                    return None
                            if not content:
                                return None
                            # A coordinator update may have changed/removed this loan mid-fetch.
                            if not self.available or self._cover_url != source_url:
                                return None
                            self._attr_content_type = content_type
                            self._image_bytes = bytes(content)
                            return self._image_bytes
            except (ClientError, TimeoutError, ValueError):
                _LOGGER.debug("WinBIAP cover unavailable: image_request_failed")
            return None


class WinBiapReservationCover(WinBiapCoverImage):
    """Reservation covers share the bounded cookie-free image transport."""

    def __init__(self, hass, coordinator, entry, session, item_id):
        super().__init__(hass, coordinator, entry, session, item_id)
        self._attr_unique_id = f"{entry.unique_id}_reservation_cover_{item_id}"

    @property
    def loan(self):
        return next(
            (
                r
                for r in self.coordinator.data.reservations or ()
                if r.item_id == self._item_id
            ),
            None,
        )

    @property
    def name(self):
        return (
            f"{self.loan.title} Vorbestellung Cover"
            if self.loan
            else "Vorbestellung Cover"
        )

    @property
    def extra_state_attributes(self):
        if not (item := self.loan):
            return None
        return {
            "reservation_id": item.item_id,
            "title": item.title,
            "author": item.author,
            "pickup_deadline": item.pickup_deadline.isoformat()
            if item.pickup_deadline
            else None,
            "ready_for_pickup": item.ready_for_pickup,
        }


class WinBiapWishlistCover(WinBiapCoverImage):
    """Own-list cover, isolated from loan and reservation entity identities."""

    def __init__(self, hass, coordinator, entry, session, item_id):
        super().__init__(hass, coordinator, entry, session, item_id)
        self._attr_unique_id = f"{entry.unique_id}_wishlist_cover_{item_id}"

    @property
    def loan(self):
        return next(
            (
                r
                for r in self.coordinator.data.wishlist or ()
                if r.item_id == self._item_id
            ),
            None,
        )

    @property
    def name(self):
        return f"{self.loan.title} Merkliste Cover" if self.loan else "Merkliste Cover"

    @property
    def extra_state_attributes(self):
        if not (item := self.loan):
            return None
        return {"wishlist_id": item.item_id, "title": item.title, "author": item.author}
