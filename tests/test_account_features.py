"""Synthetic optional account page fixtures; no real account records."""

import asyncio
from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock

import pytest

from custom_components.winbiap.account_features import account_link, parse_reservations
from custom_components.winbiap.api import WinBiapClient, WinBiapUnsupportedPage
from tests.test_api import fixture

BASE = "https://example.org/demo/user/"
EMPTY = '<span id="ctl00_ContentPlaceHolderMain_LabelAccountTableResult">Sie haben keine Medien vorbestellt.</span>'
PENDING = """<table id="ctl00_GridViewReservations"><tr><th>Titel</th><th>Autor</th><th>Status</th><th>Abholfrist</th></tr>
<tr data-item-id="synthetic-1"><td>Testbuch<img data-src="/cover.png"></td><td>Beispielautor</td><td>Vorgemerkt</td><td></td></tr></table>"""


def test_reservation_empty_pending_ready_and_identity():
    assert parse_reservations(EMPTY, BASE) == ()
    pending = parse_reservations(PENDING, BASE)[0]
    ready = parse_reservations(
        PENDING.replace("Vorgemerkt", "Abholbereit").replace(
            "<td></td>", "<td>30.09.2030</td>"
        ),
        BASE,
    )[0]
    assert pending.ready_for_pickup is False
    assert ready.ready_for_pickup is True
    assert ready.pickup_deadline == date(2030, 9, 30)
    assert pending.item_id == ready.item_id
    assert pending.cover_url == "https://example.org/cover.png"
    assert (
        replace(
            ready, status=pending.status, ready_for_pickup=False, pickup_deadline=None
        )
        == pending
    )


@pytest.mark.parametrize(
    "html",
    [
        "<h1>Vorbestellungen</h1>",
        PENDING.replace('data-item-id="synthetic-1"', ""),
        PENDING.replace("<th>Titel</th>", "<th>Unbekannt</th>"),
        EMPTY + PENDING,
    ],
)
def test_unknown_reservation_page_not_zero(html):
    with pytest.raises(WinBiapUnsupportedPage):
        parse_reservations(html, BASE)


def test_only_readonly_account_navigation():
    assert (
        account_link(
            '<a href="reservations.aspx">Reservations</a>',
            BASE + "loans.aspx",
            "reservations.aspx",
        )
        == BASE + "reservations.aspx"
    )
    for href in [
        "https://evil.example/user/reservations.aspx",
        "reservations.aspx?delete=1",
        "javascript:remove()",
    ]:
        assert (
            account_link(
                f'<a href="{href}">Reservations</a>',
                BASE + "loans.aspx",
                "reservations.aspx",
            )
            is None
        )


def test_optional_failure_preserves_loans():
    async def run():
        c = WinBiapClient(None, BASE.removesuffix("user/"), "synthetic", "synthetic")
        html = (
            fixture("account_table.html")
            + '<a href="reservations.aspx">Vorbestellungen</a>'
        )
        c.async_login = AsyncMock(return_value=(html, BASE + "loans.aspx"))
        c._request = AsyncMock(side_effect=TimeoutError)
        account = await c.async_get_account()
        assert account.loans and account.reservations is None
        c._request.assert_awaited_once_with("GET", BASE + "reservations.aspx")

    asyncio.run(run())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kontostand: ausgeglichen", "0.00"),
        ("Kontostand: 12,50 €", "12.50"),
        ("Offene Gebühren: 1.234,56 EUR", "1234.56"),
        ("Guthaben: 2,00 €", "-2.00"),
        ("Kontostand: -0,50 €", "-0.50"),
    ],
)
def test_explicit_fee_balance(text, expected):
    from decimal import Decimal

    from custom_components.winbiap.account_features import parse_fees

    html = f'<span id="ctl00_ContentPlaceHolderMain_LabelToolbarTotalCharge">{text}</span><table><tr><td>Letzte Buchungen (gekürzt): 999,00 €</td></tr></table>'
    result = parse_fees(html)
    assert result.amount == Decimal(expected)
    assert result.currency == "EUR"


@pytest.mark.parametrize(
    "html",
    [
        "<table><td>1,00 €</td></table>",
        '<span id="LabelToolbarTotalCharge">Kontostand: ausgeglichen</span>',
        '<span id="LabelToolbarTotalCharge">Kontostand: 2.00 USD</span>',
        '<span id="LabelToolbarTotalCharge">Kontostand: unbekannt €</span>',
    ],
)
def test_unknown_fee_balance_not_zero(html):
    from custom_components.winbiap.account_features import parse_fees

    with pytest.raises(WinBiapUnsupportedPage):
        parse_fees(html)
