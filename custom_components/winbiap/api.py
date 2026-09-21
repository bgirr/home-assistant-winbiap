"""Async client and HTML parser for WinBIAP WebOPAC."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError, ClientResponse, ClientSession

from .models import WinBiapAccount, WinBiapLoan

_LOGGER = logging.getLogger(__name__)

LOGIN_PATH = "user/login.aspx"
LOGIN_NAME = "ctl00$ContentPlaceHolderMain$TextBoxLoginName"
LOGIN_PASSWORD = "ctl00$ContentPlaceHolderMain$TextBoxLoginPassword"
LOGIN_BUTTON = "ctl00$ContentPlaceHolderMain$ButtonLogin"

_DATE_RE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
_SPACE_RE = re.compile(r"\s+")
_LOAN_LINK_RE = re.compile(
    r"(?:loan|borrow|lending|media|ausleih|entleih)", re.IGNORECASE
)
_RENEWABLE_RE = re.compile(r"(?:verlänger|renew)", re.IGNORECASE)
_NOT_RENEWABLE_RE = re.compile(
    r"(?:nicht\s+verlänger|keine\s+verlänger|not\s+renew)", re.IGNORECASE
)


class WinBiapError(Exception):
    """Base exception for WinBIAP communication errors."""


class WinBiapCannotConnect(WinBiapError):
    """Raised when the WebOPAC cannot be reached or parsed."""


class WinBiapInvalidAuth(WinBiapError):
    """Raised when the server rejects the supplied credentials."""


class WinBiapUnsupportedPage(WinBiapError):
    """Raised when no supported account layout can be found."""


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Return normalized descendant text."""
        parts = [*self.text_parts]
        parts.extend(child.text for child in self.children)
        return _normalize(" ".join(parts))

    def descendants(self, tag: str | None = None) -> list[_Node]:
        """Return all descendant nodes, optionally filtered by tag."""
        result: list[_Node] = []
        for child in self.children:
            if tag is None or child.tag == tag:
                result.append(child)
            result.extend(child.descendants(tag))
        return result


class _TreeParser(HTMLParser):
    """Small, dependency-free HTML tree builder for server-rendered pages."""

    _VOID_TAGS: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if tag.lower() not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID_TAGS:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].text_parts.append(data)


def _tree(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    return parser.root


def _normalize(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def normalize_base_url(base_url: str) -> str:
    """Normalize and validate a WebOPAC base URL."""
    value = base_url.strip()
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("WebOPAC URL has no hostname")
    # Provider catalog links are often still published as HTTP. Credentials
    # must never be submitted over an unencrypted connection.
    parsed = parsed._replace(scheme="https")

    path = parsed.path.rstrip("/")
    for suffix in ("/index.aspx", "/user/login.aspx"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)]
            break
    return parsed._replace(path=f"{path}/", params="", query="", fragment="").geturl()


def account_unique_id(base_url: str, library_card: str) -> str:
    """Create a privacy-preserving stable account identifier."""
    material = f"{normalize_base_url(base_url).lower()}\0{library_card.strip().lower()}"
    return sha256(material.encode()).hexdigest()


def library_title(base_url: str) -> str:
    """Return a non-sensitive title derived from the WebOPAC URL."""
    parsed = urlparse(normalize_base_url(base_url))
    return parsed.path.strip("/").split("/")[-1] or parsed.hostname or "WinBIAP"


def parse_hidden_fields(html: str) -> dict[str, str]:
    """Extract ASP.NET hidden fields from a page."""
    result: dict[str, str] = {}
    for node in _tree(html).descendants("input"):
        if node.attrs.get("type", "").lower() != "hidden":
            continue
        if name := node.attrs.get("name"):
            result[name] = node.attrs.get("value", "")
    return result


def _parse_date(value: str):
    if match := _DATE_RE.search(value):
        return datetime.strptime(".".join(match.groups()), "%d.%m.%Y").date()
    return None


def _header_key(value: str) -> str | None:
    normalized = value.casefold().replace("-", " ").replace("_", " ")
    aliases = {
        "title": ("titel", "title", "medium"),
        "author": ("autor", "verfasser", "author"),
        "due_date": ("fällig", "frist", "rückgabe", "due"),
        "media_type": ("medienart", "medientyp", "media type"),
        "barcode": ("exemplarnummer", "barcode", "strichcode"),
        "branch": ("zweigstelle", "filiale", "branch"),
        "renewable": ("verlänger", "renew"),
    }
    for key, words in aliases.items():
        if any(word in normalized for word in words):
            return key
    return None


def _node_identifier(node: _Node, title: str, due_date: date) -> str:
    for attribute in ("data-id", "data-item-id", "data-barcode", "id"):
        if (value := node.attrs.get(attribute)) and not value.startswith("ctl00_"):
            return value
    for child in node.descendants():
        for attribute in ("data-id", "data-item-id", "value"):
            if (
                (value := child.attrs.get(attribute))
                and len(value) >= 3
                and value.lower() not in {"true", "false", "on"}
            ):
                return value
        if href := child.attrs.get("href"):
            match = re.search(
                r"(?:id|item|media|exemplar)=([^&#]+)", href, re.IGNORECASE
            )
            if match:
                return match.group(1)
    return sha256(f"{title}\0{due_date.isoformat()}".encode()).hexdigest()[:20]


def _cover_url(node: _Node, base_url: str) -> str | None:
    for image in node.descendants("img"):
        source = image.attrs.get("src", "")
        if source and not any(
            word in source.casefold() for word in ("logo", "icon", "spacer")
        ):
            return urljoin(base_url, source)
    return None


def _loan_from_mapping(
    mapping: dict[str, str], node: _Node, base_url: str
) -> WinBiapLoan | None:
    due_date = _parse_date(mapping.get("due_date", "") or node.text)
    if due_date is None:
        return None
    title = _normalize(mapping.get("title", ""))
    if not title:
        candidates = [
            item.text
            for item in node.descendants()
            if item.tag in {"a", "strong", "h3", "h4"}
            and item.text
            and _parse_date(item.text) is None
        ]
        if not candidates:
            candidates = [
                item.text
                for item in node.descendants("td")
                if item.text
                and _parse_date(item.text) is None
                and not _RENEWABLE_RE.search(item.text)
                and not item.text.isdecimal()
            ]
        title = max(candidates, key=len, default="")
    if not title:
        return None

    renewable_text = mapping.get("renewable", "") or node.text
    renewable: bool | None = None
    if _NOT_RENEWABLE_RE.search(renewable_text):
        renewable = False
    elif _RENEWABLE_RE.search(renewable_text):
        renewable = True

    return WinBiapLoan(
        item_id=_node_identifier(node, title, due_date),
        title=title,
        due_date=due_date,
        author=_normalize(mapping.get("author", "")) or None,
        media_type=_normalize(mapping.get("media_type", "")) or None,
        barcode=_normalize(mapping.get("barcode", "")) or None,
        branch=_normalize(mapping.get("branch", "")) or None,
        cover_url=_cover_url(node, base_url),
        renewable=renewable,
    )


def parse_loans(html: str, base_url: str) -> tuple[WinBiapLoan, ...]:
    """Parse loan rows or cards from a WinBIAP account page."""
    root = _tree(html)
    loans: list[WinBiapLoan] = []

    for table in root.descendants("table"):
        rows = table.descendants("tr")
        header_map: dict[int, str] = {}
        for row in rows:
            headers = row.descendants("th")
            if headers:
                header_map = {
                    index: key
                    for index, header in enumerate(headers)
                    if (key := _header_key(header.text)) is not None
                }
                continue
            cells = [child for child in row.children if child.tag == "td"]
            if not cells:
                continue
            mapping = {
                key: cells[index].text
                for index, key in header_map.items()
                if index < len(cells)
            }
            if loan := _loan_from_mapping(mapping, row, base_url):
                loans.append(loan)

    if not loans:
        for node in root.descendants():
            classes = node.attrs.get("class", "").casefold()
            if not classes or not any(
                word in classes for word in ("loan", "borrow", "medium", "ausleih")
            ):
                continue
            mapping: dict[str, str] = {}
            for child in node.descendants():
                child_classes = child.attrs.get("class", "")
                if key := _header_key(child_classes):
                    mapping[key] = child.text
            if loan := _loan_from_mapping(mapping, node, base_url):
                loans.append(loan)

    unique = {loan.item_id: loan for loan in loans}
    return tuple(sorted(unique.values(), key=lambda loan: (loan.due_date, loan.title)))


def find_account_url(html: str, response_url: str) -> str | None:
    """Find the most likely loan/account link after login."""
    candidates: list[tuple[int, str]] = []
    for link in _tree(html).descendants("a"):
        href = link.attrs.get("href", "")
        text = link.text
        if (
            not href
            or href.casefold().startswith("javascript:")
            or "logout" in href.casefold()
        ):
            continue
        score = 0
        if _LOAN_LINK_RE.search(href):
            score += 3
        if _LOAN_LINK_RE.search(text):
            score += 4
        if "/user/" in urljoin(response_url, href).casefold():
            score += 1
        if score:
            candidates.append((score, urljoin(response_url, href)))
    return max(candidates, default=(0, ""))[1] or None


def page_is_login(html: str, response_url: str) -> bool:
    """Return whether a response is the login page."""
    return LOGIN_NAME in html or response_url.casefold().endswith("/user/login.aspx")


class WinBiapClient:
    """Read-only asynchronous WinBIAP WebOPAC client."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        library_card: str,
        password: str,
    ) -> None:
        self._session = session
        self.base_url = normalize_base_url(base_url)
        self._library_card = library_card.strip()
        self._password = password
        self._account_url: str | None = None

    async def _text(self, response: ClientResponse) -> str:
        response.raise_for_status()
        return await response.text(errors="replace")

    async def async_close(self) -> None:
        """Close the account-specific HTTP session."""
        await self._session.close()

    async def async_login(self) -> tuple[str, str]:
        """Authenticate and return the landing page HTML and URL."""
        login_url = urljoin(self.base_url, LOGIN_PATH)
        stage = "login_page"
        try:
            _LOGGER.debug("WinBIAP request started: login_page")
            async with self._session.get(login_url) as response:
                _LOGGER.debug("WinBIAP login page response: HTTP %d", response.status)
                login_html = await self._text(response)
            if LOGIN_NAME not in login_html or LOGIN_PASSWORD not in login_html:
                _LOGGER.warning(
                    "WinBIAP login page is unsupported: missing form fields"
                )
                raise WinBiapUnsupportedPage("Expected WebOPAC login form not found")
            payload = parse_hidden_fields(login_html)
            payload.update(
                {
                    LOGIN_NAME: self._library_card,
                    LOGIN_PASSWORD: self._password,
                    LOGIN_BUTTON: "Anmelden",
                }
            )
            stage = "login_submit"
            _LOGGER.debug("WinBIAP request started: login_submit")
            async with self._session.post(login_url, data=payload) as response:
                _LOGGER.debug("WinBIAP login submit response: HTTP %d", response.status)
                html = await self._text(response)
                response_url = str(response.url)
        except (ClientError, TimeoutError, UnicodeError) as err:
            _LOGGER.warning(
                "WinBIAP request failed at %s: %s", stage, type(err).__name__
            )
            raise WinBiapCannotConnect(str(err)) from err

        if page_is_login(html, response_url):
            _LOGGER.warning("WinBIAP login returned the login page")
            raise WinBiapInvalidAuth("The WebOPAC rejected the supplied credentials")
        account_link = find_account_url(html, response_url)
        self._account_url = account_link or response_url
        _LOGGER.debug(
            "WinBIAP login submit completed; account link found: %s",
            bool(account_link),
        )
        return html, response_url

    async def async_get_account(self) -> WinBiapAccount:
        """Fetch and parse the current account state."""
        landing_html, landing_url = await self.async_login()
        account_url = self._account_url or landing_url
        html = landing_html

        if account_url != landing_url:
            try:
                _LOGGER.debug("WinBIAP request started: account_page")
                async with self._session.get(account_url) as response:
                    _LOGGER.debug(
                        "WinBIAP account page response: HTTP %d", response.status
                    )
                    html = await self._text(response)
                    account_url = str(response.url)
            except (ClientError, TimeoutError, UnicodeError) as err:
                _LOGGER.warning(
                    "WinBIAP request failed at account_page: %s", type(err).__name__
                )
                raise WinBiapCannotConnect(str(err)) from err
            if page_is_login(html, account_url):
                _LOGGER.warning("WinBIAP account page redirected to login")
                raise WinBiapInvalidAuth("The WebOPAC session expired after login")

        loans = parse_loans(html, account_url)
        page_text = _tree(html).text
        empty_account = bool(
            re.search(
                r"(?:keine\s+(?:ausleihen|medien)|nothing\s+borrowed|no\s+loans)",
                page_text,
                re.IGNORECASE,
            )
        )
        if not loans and not empty_account:
            _LOGGER.warning(
                "WinBIAP account page is unsupported: no loans or empty marker"
            )
            raise WinBiapUnsupportedPage(
                "The account page was reached, but its loan layout is not supported"
            )

        _LOGGER.debug("WinBIAP account page parsed successfully")

        library_name = None
        root = _tree(html)
        for image in root.descendants("img"):
            if "logo" in image.attrs.get("src", "").casefold():
                library_name = image.attrs.get("alt") or None
                break
        return WinBiapAccount(loans=loans, library_name=library_name)
