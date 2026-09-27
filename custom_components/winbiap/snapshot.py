"""Versioned, credential-free serialization of the last known account data."""

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from .models import (
    WinBiapAccount,
    WinBiapBalance,
    WinBiapLoan,
    WinBiapReservation,
    WinBiapWishlistItem,
)


def encode_account(account: WinBiapAccount) -> dict:
    """Serialize only the typed account model, never client/session data."""

    def value(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, dict):
            return {key: value(val) for key, val in item.items()}
        if isinstance(item, (tuple, list)):
            return [value(val) for val in item]
        return item

    return value(asdict(account))


def decode_account(data: dict) -> WinBiapAccount:
    """Restore model types; reject incompatible/corrupt snapshots."""
    loans = tuple(
        WinBiapLoan(**{**item, "due_date": date.fromisoformat(item["due_date"])})
        for item in data["loans"]
    )
    reservations = data.get("reservations")
    if reservations is not None:
        reservations = tuple(
            WinBiapReservation(
                **{
                    **item,
                    "pickup_deadline": date.fromisoformat(item["pickup_deadline"])
                    if item.get("pickup_deadline")
                    else None,
                }
            )
            for item in reservations
        )
    fees = data.get("fees")
    if fees is not None:
        fees = WinBiapBalance(Decimal(fees["amount"]), fees["currency"])
    wishlist = data.get("wishlist")
    return WinBiapAccount(
        loans=loans,
        reservations=reservations,
        fees=fees,
        wishlist=tuple(WinBiapWishlistItem(**item) for item in wishlist)
        if wishlist is not None
        else None,
        library_name=data.get("library_name"),
        account_status=data.get("account_status"),
    )
