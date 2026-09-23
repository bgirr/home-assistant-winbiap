"""Bounded challenge protocol, origin confinement and borrowed-session tests."""

import asyncio
import threading
from hashlib import sha256
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientError, ClientSession
from yarl import URL

from custom_components.winbiap import api
from tests.test_api import fixture

BASE = "https://example.org/demo/"
LOGIN = BASE + "user/login.aspx"


class Response:
    def __init__(self, html="", url=LOGIN, status=200, location=None):
        self.html, self.url, self.status = html, URL(url), status
        self.headers = {"Location": location} if location else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        if self.status >= 400:
            raise ClientError("SYNTHETIC_PRIVATE_ERROR")

    async def text(self, **kwargs):
        return self.html


def session_for(*responses):
    return Mock(request=Mock(side_effect=responses), close=AsyncMock(), detach=Mock())


def client_for(session):
    return api.WinBiapClient(session, BASE, "SYNTHETIC_CARD", "SYNTHETIC_PASSWORD")


def test_challenge_recognition_and_nonce():
    assert api.parse_challenge(fixture("challenge.html")) == (
        "SYNTHETICSEED",
        "/demo/user/login.aspx",
    )
    nonce = api.solve_challenge("SYNTHETICSEED")
    assert sha256(f"SYNTHETICSEED{nonce}".encode()).hexdigest().startswith("0000")
    assert api.parse_challenge(fixture("login.html")) is None


@pytest.mark.parametrize("limit", [0, 1, -1, 2_000_001])
def test_work_limit(limit):
    with pytest.raises(api.WinBiapUnsupportedPage):
        api.solve_challenge("SYNTHETICSEED", limit)


@pytest.mark.parametrize("seed", ["", "x" * 129, "bad seed", "é"])
def test_invalid_seed(seed):
    with pytest.raises(api.WinBiapUnsupportedPage):
        api.solve_challenge(seed)


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example/",
        "",
        "relative",
        "/%2f/evil.example/",
        "/demo/../evil",
        "/demo#fragment",
        "/a\npath",
    ],
)
def test_unsafe_next(target):
    html = fixture("challenge.html").replace("/demo/user/login.aspx", target)
    with pytest.raises(api.WinBiapUnsupportedPage, match="unsafe_challenge_next"):
        api.parse_challenge(html)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ('action="/challenge"', 'action="https://evil.example/challenge"'),
        ('method="post"', 'method="get"'),
        ('name="next"', 'name="other"'),
        ('type="hidden"', 'type="text"'),
        ('"0000"', '"00000"'),
        ("SYNTHETICSEED", "x" * 129),
        ("sha256_K=", "other_K="),
    ],
)
def test_changed_challenge_rejected(before, after):
    with pytest.raises(api.WinBiapUnsupportedPage):
        api.parse_challenge(fixture("challenge.html").replace(before, after))


def test_challenge_before_login_and_worker_thread(monkeypatch):
    owner = threading.get_ident()
    original = api.solve_challenge

    def solve(seed):
        assert threading.get_ident() != owner
        return original(seed)

    monkeypatch.setattr(api, "solve_challenge", solve)
    session = session_for(
        Response(status=302, location="/challenge"),
        Response(fixture("challenge.html"), "https://example.org/challenge"),
        Response(status=303, location="/demo/user/login.aspx"),
        Response(fixture("login.html")),
        Response("Keine Ausleihen", BASE + "user/account.aspx"),
    )
    account = asyncio.run(client_for(session).async_get_account())
    assert account.loans == ()
    calls = session.request.call_args_list
    assert [c.args[0] for c in calls] == ["GET", "GET", "POST", "GET", "POST"]
    assert calls[2].args[1] == "https://example.org/challenge"
    assert set(calls[2].kwargs["data"]) == {"challenge", "next"}
    assert calls[4].kwargs["data"][api.LOGIN_NAME] == "SYNTHETIC_CARD"
    assert all(c.kwargs["allow_redirects"] is False for c in calls)
    session.close.assert_not_called()
    session.detach.assert_not_called()


def test_normal_login_unchanged():
    session = session_for(
        Response(fixture("login.html")),
        Response(fixture("account_table.html"), BASE + "user/account.aspx"),
    )
    assert len(asyncio.run(client_for(session).async_get_account()).loans) == 2
    assert session.request.call_count == 2


@pytest.mark.parametrize("status", [302, 303, 307, 308])
def test_cross_origin_redirect_never_followed(status):
    session = session_for(Response(status=status, location="https://evil.example/"))
    with pytest.raises(api.WinBiapUnsupportedPage, match="cross_origin"):
        asyncio.run(client_for(session).async_login())
    assert session.request.call_count == 1


def test_challenge_must_yield_login_form():
    session = session_for(Response(fixture("challenge.html")), Response("other"))
    with pytest.raises(api.WinBiapUnsupportedPage, match="challenge_not_completed"):
        asyncio.run(client_for(session).async_login())
    assert session.request.call_count == 2


@pytest.mark.parametrize("failure", [TimeoutError(), ClientError("PRIVATE")])
def test_network_errors_are_categorical(failure):
    session = session_for(failure)
    with pytest.raises(api.WinBiapCannotConnect, match=r"^request_failed$"):
        asyncio.run(client_for(session).async_login())
    session.close.assert_not_called()
    session.detach.assert_not_called()


def test_redirect_loop_is_bounded():
    session = session_for(*(Response(status=302, location=LOGIN) for _ in range(6)))
    with pytest.raises(api.WinBiapUnsupportedPage, match="redirect_limit"):
        asyncio.run(client_for(session).async_login())
    assert session.request.call_count == 6


def test_borrowed_real_session_lifetime():
    async def run():
        async with ClientSession() as session:
            client = client_for(session)
            assert not hasattr(client, "async_close")
            del client
            assert not session.closed
        assert session.closed

    asyncio.run(run())


def test_work_limit_counts_hashes(monkeypatch):
    hashing = Mock(return_value=Mock(digest=Mock(return_value=b"\xff" * 32)))
    monkeypatch.setattr(api, "sha256", hashing)
    with pytest.raises(api.WinBiapUnsupportedPage, match="challenge_work_limit"):
        api.solve_challenge("SYNTHETICSEED", 7)
    assert hashing.call_count == 7


def test_challenge_rejects_names_without_real_form():
    html = f"{api.LOGIN_NAME} {api.LOGIN_PASSWORD} __VIEWSTATE"
    session = session_for(Response(fixture("challenge.html")), Response(html))
    with pytest.raises(api.WinBiapUnsupportedPage, match="challenge_not_completed"):
        asyncio.run(client_for(session).async_login())


def test_logs_never_include_exception_or_credentials(caplog):
    session = session_for(ClientError("SYNTHETIC_PRIVATE_EXCEPTION"))
    with caplog.at_level("DEBUG"), pytest.raises(api.WinBiapCannotConnect):
        asyncio.run(client_for(session).async_login())
    assert "SYNTHETIC" not in caplog.text
