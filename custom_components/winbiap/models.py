"""Data models for WinBIAP Library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class WinBiapLoan:
    """A single checked-out library item."""

    item_id: str
    title: str
    due_date: date
    author: str | None = None
    media_type: str | None = None
    barcode: str | None = None
    branch: str | None = None
    cover_url: str | None = None
    renewable: bool | None = None

    @property
    def days_remaining(self) -> int:
        """Return the number of days until the item is due."""
        return (self.due_date - datetime.now().astimezone().date()).days


@dataclass(frozen=True, slots=True)
class WinBiapReservation:
    """A reservation without any account-changing action."""

    item_id: str
    title: str
    author: str | None = None
    status: str | None = None
    ready_for_pickup: bool | None = None
    pickup_deadline: date | None = None
    cover_url: str | None = None


@dataclass(frozen=True, slots=True)
class WinBiapBalance:
    """Explicit current balance, never a sum of transaction history."""

    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class WinBiapAccount:
    """Current read-only state of a WinBIAP account."""

    loans: tuple[WinBiapLoan, ...]
    reservations: tuple[WinBiapReservation, ...] | None = None
    fees: WinBiapBalance | None = None
    library_name: str | None = None
    account_status: str | None = None

    @property
    def next_due(self) -> date | None:
        """Return the earliest due date."""
        return min((loan.due_date for loan in self.loans), default=None)

    @property
    def overdue_count(self) -> int:
        """Return the number of overdue items."""
        today = datetime.now().astimezone().date()
        return sum(loan.due_date < today for loan in self.loans)
