"""Sensor platform for WinBIAP Library."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, DOMAIN
from .coordinator import WinBiapCoordinator
from .models import WinBiapAccount, WinBiapLoan


@dataclass(frozen=True, kw_only=True)
class WinBiapSensorDescription(SensorEntityDescription):
    """Description of an account summary sensor."""

    value_fn: Callable[[WinBiapAccount], Any]


SUMMARY_SENSORS = (
    WinBiapSensorDescription(
        key="wishlist",
        name="Merkliste",
        icon="mdi:bookmark-multiple",
        value_fn=lambda account: (
            len(account.wishlist) if account.wishlist is not None else None
        ),
    ),
    WinBiapSensorDescription(
        key="fees",
        name="Gebühren",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        value_fn=lambda account: (
            account.fees.amount if account.fees is not None else None
        ),
    ),
    WinBiapSensorDescription(
        key="reservations",
        name="Vorbestellungen",
        icon="mdi:book-clock",
        value_fn=lambda account: (
            len(account.reservations) if account.reservations is not None else None
        ),
    ),
    WinBiapSensorDescription(
        key="loans",
        name="Loans",
        value_fn=lambda account: len(account.loans),
        icon="mdi:book-multiple",
    ),
    WinBiapSensorDescription(
        key="next_due",
        name="Next due date",
        value_fn=lambda account: account.next_due,
        device_class=SensorDeviceClass.DATE,
    ),
    WinBiapSensorDescription(
        key="overdue",
        name="Overdue items",
        value_fn=lambda account: account.overdue_count,
        icon="mdi:book-alert",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WinBIAP sensors."""
    coordinator: WinBiapCoordinator = entry.runtime_data
    async_add_entities(
        WinBiapSummarySensor(coordinator, entry, description)
        for description in SUMMARY_SENSORS
    )

    known_loan_ids: set[str] = set()

    @callback
    def async_add_new_loans() -> None:
        new_loans = [
            loan
            for loan in coordinator.data.loans
            if loan.item_id not in known_loan_ids
        ]
        if new_loans:
            known_loan_ids.update(loan.item_id for loan in new_loans)
            async_add_entities(
                WinBiapLoanSensor(coordinator, entry, loan.item_id)
                for loan in new_loans
            )

    async_add_new_loans()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_loans))


class WinBiapEntity(CoordinatorEntity[WinBiapCoordinator], SensorEntity):
    """Base class for WinBIAP entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WinBiapCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="datronicsoft (unofficial integration)",
            model="WinBIAP WebOPAC account",
            configuration_url=entry.data[CONF_BASE_URL],
        )


class WinBiapSummarySensor(WinBiapEntity):
    """Account-level summary sensor."""

    def __init__(
        self,
        coordinator: WinBiapCoordinator,
        entry: ConfigEntry,
        description: WinBiapSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        """Keep unsupported optional sections unavailable, without losing loans."""
        key = self.entity_description.key
        return super().available and (
            key not in {"reservations", "fees", "wishlist"}
            or getattr(self.coordinator.data, key) is not None
        )

    @property
    def native_value(self) -> Any:
        """Return the current summary value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose structured loan data on the loan-count sensor."""
        if self.entity_description.key == "wishlist":
            records = self.coordinator.data.wishlist
            return (
                {
                    "wishlist": [
                        {"id": r.item_id, "title": r.title, "author": r.author}
                        for r in records
                    ]
                }
                if records is not None
                else None
            )
        if self.entity_description.key == "fees":
            return {"account_section": "fees"}
        if self.entity_description.key == "reservations":
            records = self.coordinator.data.reservations
            if records is None:
                return None
            return {
                "reservations": [
                    {
                        "id": r.item_id,
                        "title": r.title,
                        "author": r.author,
                        "status": r.status,
                        "ready_for_pickup": r.ready_for_pickup,
                        "pickup_deadline": r.pickup_deadline.isoformat()
                        if r.pickup_deadline
                        else None,
                    }
                    for r in records
                ],
                "ready_for_pickup": sum(r.ready_for_pickup is True for r in records),
            }
        if self.entity_description.key != "loans":
            return None
        return {
            "loans": [
                {
                    "id": loan.item_id,
                    "title": loan.title,
                    "author": loan.author,
                    "due_date": loan.due_date.isoformat(),
                    "days_remaining": loan.days_remaining,
                    "renewable": loan.renewable,
                }
                for loan in self.coordinator.data.loans
            ]
        }


class WinBiapLoanSensor(WinBiapEntity):
    """Due-date sensor for a single loan."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: WinBiapCoordinator,
        entry: ConfigEntry,
        item_id: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._item_id = item_id
        self._attr_unique_id = f"{entry.unique_id}_loan_{item_id}"

    @property
    def loan(self) -> WinBiapLoan | None:
        """Return the current loan, if it is still checked out."""
        return next(
            (
                loan
                for loan in self.coordinator.data.loans
                if loan.item_id == self._item_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return whether the item is still present in the account."""
        return super().available and self.loan is not None

    @property
    def name(self) -> str | None:
        """Return a human-readable loan name."""
        return self.loan.title if self.loan else "Returned item"

    @property
    def native_value(self) -> date | None:
        """Return the due date."""
        return self.loan.due_date if self.loan else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return metadata for the checked-out item."""
        if (loan := self.loan) is None:
            return None
        return {
            "author": loan.author,
            "media_type": loan.media_type,
            "barcode": loan.barcode,
            "branch": loan.branch,
            "cover_url": loan.cover_url,
            "days_remaining": loan.days_remaining,
            "renewable": loan.renewable,
        }
