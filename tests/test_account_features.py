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


WISHLIST = '<table id="GridViewFavorites"><tr><th>Titel</th><th>Autor</th></tr><tr data-id="synthetic-1"><td>Testbuch<img src="/cover.png"></td><td>Testautor</td></tr></table>'
WISHLIST_EMPTY = (
    '<span id="ctl00_ContentPlaceHolderMain_LabelStatus">Merkliste ist leer!</span>'
)


def test_wishlist_explicit_empty_and_populated():
    from custom_components.winbiap.account_features import parse_wishlist

    assert parse_wishlist(WISHLIST_EMPTY, BASE) == ()
    item = parse_wishlist(WISHLIST, BASE)[0]
    assert item.title == "Testbuch" and item.author == "Testautor"
    assert item.cover_url == "https://example.org/cover.png"
    assert (
        item.item_id
        == parse_wishlist(WISHLIST.replace("Testautor", "Anderer Autor"), BASE)[
            0
        ].item_id
    )
    with pytest.raises(WinBiapUnsupportedPage):
        parse_wishlist("<h1>Merkliste</h1>", BASE)


def test_wishlist_pagination_collects_all_pages_and_isolates_accounts():
    async def run():
        first = WISHLIST + '<a rel="next" href="favorites.aspx?page=2">Weiter</a>'
        second = (
            WISHLIST.replace("synthetic-1", "synthetic-2")
            + '<a href="favorites.aspx?page=1">1</a>'
        )
        clients = [
            WinBiapClient(object(), BASE.removesuffix("user/"), str(i), "synthetic")
            for i in range(2)
        ]
        clients[0]._request = AsyncMock(
            side_effect=[
                (first, BASE + "favorites.aspx"),
                (second, BASE + "favorites.aspx?page=2"),
            ]
        )
        clients[1]._request = AsyncMock(
            return_value=(WISHLIST_EMPTY, BASE + "favorites.aspx")
        )
        populated, empty = await asyncio.gather(
            *(c._async_get_wishlist(BASE + "favorites.aspx") for c in clients)
        )
        assert len(populated) == 2 and empty == ()
        assert clients[0]._session is not clients[1]._session
        assert clients[0]._request.await_args_list[1].args == (
            "GET",
            BASE + "favorites.aspx?page=2",
        )

    asyncio.run(run())


def test_wishlist_readonly_aspnet_pagination():
    async def run():
        first = (
            WISHLIST
            + """<input type="hidden" name="__VIEWSTATE" value="synthetic"><a href="javascript:__doPostBack('ctl00$GridViewFavorites','Page$Next')">Weiter</a>"""
        )
        second = (
            WISHLIST.replace("synthetic-1", "synthetic-2")
            + """<a href="javascript:__doPostBack('ctl00$GridViewFavorites','Page$Prev')">Zurück</a>"""
        )
        client = WinBiapClient(
            None, BASE.removesuffix("user/"), "synthetic", "synthetic"
        )
        client._request = AsyncMock(
            side_effect=[
                (first, BASE + "favorites.aspx"),
                (second, BASE + "favorites.aspx"),
            ]
        )
        assert len(await client._async_get_wishlist(BASE + "favorites.aspx")) == 2
        call = client._request.await_args_list[1]
        assert call.args == ("POST", BASE + "favorites.aspx")
        assert call.kwargs["data"] == {
            "__VIEWSTATE": "synthetic",
            "__EVENTTARGET": "ctl00$GridViewFavorites",
            "__EVENTARGUMENT": "Page$Next",
        }

    asyncio.run(run())


@pytest.mark.parametrize(
    "href",
    [
        "favorites.aspx?page=3",
        "favorites.aspx?page=2&amp;remove=1",
        "https://evil.example/user/favorites.aspx?page=2",
        "javascript:__doPostBack('Delete','Page$Next')",
        "favorites.aspx?page=1",
    ],
)
def test_wishlist_unsafe_or_incomplete_pagination(href):
    from custom_components.winbiap.account_features import wishlist_next_page

    with pytest.raises(WinBiapUnsupportedPage):
        wishlist_next_page(
            f'<a rel="next" href="{href}">Weiter</a>', BASE + "favorites.aspx", 1
        )


def test_wishlist_repeated_page_is_unavailable_not_partial():
    async def run():
        page = WISHLIST + '<a rel="next" href="favorites.aspx?page=2">Weiter</a>'
        client = WinBiapClient(
            None, BASE.removesuffix("user/"), "synthetic", "synthetic"
        )
        client._request = AsyncMock(
            side_effect=[
                (page, BASE + "favorites.aspx"),
                (WISHLIST, BASE + "favorites.aspx?page=2"),
            ]
        )
        with pytest.raises(WinBiapUnsupportedPage):
            await client._async_get_wishlist(BASE + "favorites.aspx")

    asyncio.run(run())


def test_wishlist_adjacent_details_do_not_mix_covers_or_metadata_rows():
    from custom_components.winbiap.account_features import parse_wishlist

    html = """<table id="GridViewFavorites"><tr><th>Titel</th><th>Autor</th></tr>
<tr data-id="one"><td>One</td><td>A</td></tr><tr class="rowDetails"><td colspan="2"><img data-src="/one.png"><table><tr><td>Metadata</td></tr></table></td></tr>
<tr data-id="two"><td>Two</td><td>B</td></tr><tr class="rowDetails"><td colspan="2"><img data-src="/two.png"></td></tr></table>"""
    records = parse_wishlist(html, BASE)
    assert [r.cover_url for r in records] == [
        "https://example.org/one.png",
        "https://example.org/two.png",
    ]


def test_wishlist_page_limit_and_late_failure():
    async def run():
        client = WinBiapClient(
            None, BASE.removesuffix("user/"), "synthetic", "synthetic"
        )
        pages = [
            (
                WISHLIST.replace("synthetic-1", f"synthetic-{i}")
                + f'<a rel="next" href="favorites.aspx?page={i + 1}">Weiter</a>',
                BASE + f"favorites.aspx?page={i}",
            )
            for i in range(1, 21)
        ]
        client._request = AsyncMock(side_effect=pages)
        with pytest.raises(WinBiapUnsupportedPage, match="wishlist_page_limit"):
            await client._async_get_wishlist(BASE + "favorites.aspx")
        assert client._request.await_count == 20
        client._request = AsyncMock(side_effect=[pages[0], TimeoutError()])
        with pytest.raises(TimeoutError):
            await client._async_get_wishlist(BASE + "favorites.aspx")

    asyncio.run(run())


def test_optional_wishlist_failure_keeps_working_loans():
    async def run():
        client = WinBiapClient(
            None, BASE.removesuffix("user/"), "synthetic", "synthetic"
        )
        html = fixture("account_table.html") + '<a href="favorites.aspx">Merkliste</a>'
        client.async_login = AsyncMock(return_value=(html, BASE + "loans.aspx"))
        client._async_get_wishlist = AsyncMock(
            side_effect=WinBiapUnsupportedPage("wishlist_page_limit")
        )
        account = await client.async_get_account()
        assert account.loans and account.wishlist is None

    asyncio.run(run())
