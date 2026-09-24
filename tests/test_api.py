"""Tests for the dependency-free WinBIAP parser."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from custom_components.winbiap.api import (
    account_unique_id,
    find_account_url,
    library_title,
    normalize_base_url,
    page_is_login,
    parse_hidden_fields,
    parse_loans,
)
from custom_components.winbiap.models import WinBiapAccount

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    """Load a sanitized HTML fixture."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_normalize_base_url() -> None:
    assert (
        normalize_base_url("opac.winbiap.net/koenigsbrunn/user/login.aspx")
        == "https://opac.winbiap.net/koenigsbrunn/"
    )
    assert (
        normalize_base_url("https://example.org/library/index.aspx?ignored=true")
        == "https://example.org/library/"
    )
    assert normalize_base_url("http://example.org/library") == (
        "https://example.org/library/"
    )
    with pytest.raises(ValueError):
        normalize_base_url("ftp://example.org/library")


def test_unique_id_is_stable_and_does_not_contain_card() -> None:
    first = account_unique_id("https://example.org/demo", "CARD-123")
    second = account_unique_id("https://EXAMPLE.org/demo/", "card-123")
    assert first == second
    assert "CARD-123" not in first
    assert len(first) == 64


def test_library_title_does_not_expose_card_number() -> None:
    assert library_title("https://opac.winbiap.net/koenigsbrunn/") == "koenigsbrunn"


def test_parse_aspnet_hidden_fields() -> None:
    fields = parse_hidden_fields(fixture("login.html"))
    assert fields == {
        "__VIEWSTATE": "SANITIZED_VIEWSTATE",
        "__VIEWSTATEGENERATOR": "SANITIZED_GENERATOR",
    }


def test_login_page_detection() -> None:
    html = fixture("login.html")
    assert page_is_login(html, "https://example.org/demo/user/login.aspx")


def test_find_account_url_prefers_loans() -> None:
    html = (
        '<a href="/demo/user/profile.aspx">Konto</a><a href="loans.aspx">Ausleihen</a>'
    )
    assert find_account_url(html, "https://example.org/demo/user/home.aspx") == (
        "https://example.org/demo/user/loans.aspx"
    )


def test_parse_table_loans() -> None:
    loans = parse_loans(fixture("account_table.html"), "https://example.org/demo/")
    assert len(loans) == 2
    assert loans[0].item_id == "item-1001"
    assert loans[0].title == "Der Testroman"
    assert loans[0].author == "Erika Beispiel"
    assert loans[0].due_date == date(2026, 9, 30)
    assert loans[0].renewable is True
    assert loans[1].renewable is False


def test_parse_card_loans_and_cover_url() -> None:
    loans = parse_loans(
        fixture("account_cards.html"),
        "https://example.org/demo/user/account.aspx",
    )
    assert len(loans) == 1
    assert loans[0].title == "Kartentitel"
    assert loans[0].media_type == "Spiel"
    assert loans[0].cover_url == "https://example.org/demo/covers/1.jpg"


def test_account_summary() -> None:
    account = WinBiapAccount(
        loans=parse_loans(fixture("account_table.html"), "https://example.org/demo/")
    )
    assert account.next_due == date(2026, 9, 30)
    assert 0 <= account.overdue_count <= 2


def test_lazy_covers_follow_their_own_detail_rows():
    loans = parse_loans(
        fixture("account_lazy_covers.html"), "https://example.org/demo/"
    )
    assert len(loans) == 2
    assert loans[0].cover_url == "https://covers.example.org/one.jpg"
    assert loans[1].cover_url == "https://example.org/covers/two.jpg"


def test_missing_detail_does_not_take_next_loans_cover():
    html = fixture("account_lazy_covers.html").replace(
        'class="rowDetails"', 'class="unrelated"', 1
    )
    loans = parse_loans(html, "https://example.org/demo/")
    assert loans[0].cover_url is None
    assert loans[1].cover_url == "https://example.org/covers/two.jpg"


@pytest.mark.parametrize(
    "source",
    [
        "javascript:alert(1)",
        "https://[invalid/cover",
        "data:image/svg+xml,unsafe",
        "https://user:secret@example.org/image.jpg",
    ],
)
def test_unsafe_cover_sources_rejected(source):
    html = fixture("account_lazy_covers.html").replace(
        "https://covers.example.org/one.jpg", source
    )
    loans = parse_loans(html, "https://example.org/demo/")
    assert loans[0].cover_url is None


def test_renewal_group_headers_do_not_leak_between_sections():
    html = """<h3>Diese Medien können Sie nicht verlängern</h3><table><tr><th>Titel</th><th>Leihfrist</th></tr><tr data-id="a"><td>One</td><td>01.01.2030</td></tr></table>
<h3>Diese Medien können Sie verlängern</h3><table><tr><th>Titel</th><th>Leihfrist</th></tr><tr data-id="b"><td>Two</td><td>02.01.2030</td></tr></table>
<h3>Weitere Medien</h3><table><tr><th>Titel</th><th>Leihfrist</th></tr><tr data-id="c"><td>Three</td><td>03.01.2030</td></tr></table>"""
    assert [loan.renewable for loan in parse_loans(html, "https://example.org/")] == [
        False,
        True,
        None,
    ]
