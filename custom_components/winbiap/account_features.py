"""Conservative parsers for optional, read-only account sections."""

from __future__ import annotations

import re
from decimal import Decimal
from hashlib import sha256
from urllib.parse import parse_qs, urljoin, urlparse

from .api import WinBiapUnsupportedPage, _cover_url, _parse_date, _tree
from .models import WinBiapBalance, WinBiapReservation, WinBiapWishlistItem


def account_link(html: str, response_url: str, filename: str) -> str | None:
    """Follow only a known account page, without action/query parameters."""
    expected = urlparse(response_url)
    for node in _tree(html).descendants("a"):
        url = urljoin(response_url, node.attrs.get("href", ""))
        parsed = urlparse(url)
        if (
            (parsed.scheme, parsed.netloc) == (expected.scheme, expected.netloc)
            and parsed.path.endswith("/user/" + filename)
            and not parsed.query
            and not parsed.fragment
        ):
            return url
    return None


def media_identifier(node) -> str | None:
    """Hash only stable media identifiers; never retain signed query strings."""
    value = node.attrs.get("data-item-id") or node.attrs.get("data-id")
    if not value:
        for link in node.descendants("a"):
            query = parse_qs(urlparse(link.attrs.get("href", "")).query)
            value = next(
                (query[k][0] for k in ("detail", "media", "item", "id") if k in query),
                None,
            )
            if value:
                break
    return sha256(value.encode()).hexdigest()[:20] if value else None


def table_rows(table):
    """Exclude nested metadata tables from the account's item rows."""
    return [
        row
        for child in table.children
        for row in (
            [child]
            if child.tag == "tr"
            else child.children
            if child.tag in {"thead", "tbody", "tfoot"}
            else []
        )
        if row.tag == "tr"
    ]


def detail_row(row, rows):
    index = next(i for i, item in enumerate(rows) if item is row)
    if (
        index + 1 < len(rows)
        and "rowDetails" in rows[index + 1].attrs.get("class", "").split()
    ):
        return rows[index + 1]
    return row


def parse_reservations(html: str, base_url: str) -> tuple[WinBiapReservation, ...]:
    """Parse explicit empty state or recognized reservation tables; fail closed."""
    root = _tree(html)
    empty = any(
        "LabelAccountTableResult" in n.attrs.get("id", "")
        and re.search(
            r"keine\s+Medien\s+vorbestellt|keine\s+Vorbestellungen", n.text, re.I
        )
        for n in root.descendants("span")
    )
    records = []
    for table in root.descendants("table"):
        if "reservation" not in table.attrs.get("id", "").lower():
            continue
        rows = table_rows(table)
        headers = [
            n.text.casefold()
            for row in table_rows(table)
            for n in row.children
            if n.tag == "th"
        ]
        title_index = next(
            (i for i, h in enumerate(headers) if h in {"titel", "medium"}), None
        )
        if title_index is None:
            raise WinBiapUnsupportedPage("reservation_headers")
        for row in rows:
            cells = [n for n in row.children if n.tag == "td"]
            if not cells:
                continue
            if "rowDetails" in row.attrs.get("class", ""):
                continue
            if len(cells) != len(headers):
                raise WinBiapUnsupportedPage("reservation_row")
            title = cells[title_index].text
            item_id = media_identifier(row) or media_identifier(
                detail_row(row, table_rows(table))
            )
            if not title or not item_id:
                raise WinBiapUnsupportedPage("reservation_identity")
            values = dict(zip(headers, (c.text for c in cells), strict=True))
            status = values.get("status") or values.get("bemerkung")
            ready = None
            if status:
                if re.search(
                    r"nicht\s+(?:abholbereit|bereit)|vorgemerkt|vorbestellt|wart",
                    status,
                    re.I,
                ):
                    ready = False
                elif re.search(
                    r"abholbereit|zur\s+abholung\s+bereit|liegt.*bereit", status, re.I
                ):
                    ready = True
            deadline = values.get("abholfrist") or values.get("abholen bis")
            records.append(
                WinBiapReservation(
                    item_id=item_id,
                    title=title,
                    author=values.get("verfasser") or values.get("autor"),
                    status=status,
                    ready_for_pickup=ready,
                    pickup_deadline=_parse_date(deadline) if deadline else None,
                    cover_url=_cover_url(row, base_url)
                    or _cover_url(detail_row(row, table_rows(table)), base_url),
                )
            )
    if empty and not records:
        return ()
    if not records or empty or len({r.item_id for r in records}) != len(records):
        raise WinBiapUnsupportedPage("reservation_layout")
    return tuple(records)


def parse_fees(html: str) -> WinBiapBalance:
    """Read only the explicit current balance and confirmed currency."""
    root = _tree(html)
    balances = [
        n.text
        for n in root.descendants("span")
        if n.attrs.get("id", "").endswith("LabelToolbarTotalCharge")
    ]
    if len(balances) != 1 or not re.search(r"€|\bEUR\b", root.text):
        raise WinBiapUnsupportedPage("fee_balance_or_currency")
    text = balances[0]
    if re.fullmatch(r"Kontostand:\s*ausgeglichen", text, re.I):
        return WinBiapBalance(Decimal("0.00"), "EUR")
    match = re.fullmatch(
        r"(?:Kontostand|Offene Gebühren|Guthaben):\s*([+-]?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2})\s*(?:€|EUR)",
        text,
        re.I,
    )
    if not match:
        raise WinBiapUnsupportedPage("fee_balance_format")
    amount = Decimal(match[1].replace(".", "").replace(",", "."))
    if text.casefold().startswith("guthaben"):
        amount = -abs(amount)
    return WinBiapBalance(amount, "EUR")


def parse_wishlist(html: str, base_url: str) -> tuple[WinBiapWishlistItem, ...]:
    """Accept an explicit own-list empty state or a recognized complete table."""
    root = _tree(html)
    empty = any(
        n.attrs.get("id", "").endswith("LabelStatus")
        and n.text.casefold() == "merkliste ist leer!"
        for n in root.descendants("span")
    )
    items = []
    for table in root.descendants("table"):
        if not re.search(
            r"GridView(?:Favorites|Favorite|Result)|Merkliste",
            table.attrs.get("id", ""),
            re.I,
        ):
            continue
        headers = [
            n.text.casefold()
            for row in table_rows(table)
            for n in row.children
            if n.tag == "th"
        ]
        title_index = next(
            (i for i, h in enumerate(headers) if h in {"titel", "medium"}), None
        )
        if title_index is None:
            raise WinBiapUnsupportedPage("wishlist_headers")
        for row in table_rows(table):
            cells = [n for n in row.children if n.tag == "td"]
            if (
                not cells
                or "rowDetails" in row.attrs.get("class", "")
                or "pager" in row.attrs.get("class", "").lower()
            ):
                continue
            if len(cells) != len(headers):
                raise WinBiapUnsupportedPage("wishlist_row")
            item_id = media_identifier(row) or media_identifier(
                detail_row(row, table_rows(table))
            )
            title = cells[title_index].text
            if not item_id or not title:
                raise WinBiapUnsupportedPage("wishlist_identity")
            values = dict(zip(headers, (c.text for c in cells), strict=True))
            items.append(
                WinBiapWishlistItem(
                    item_id,
                    title,
                    values.get("autor") or values.get("verfasser"),
                    _cover_url(row, base_url)
                    or _cover_url(detail_row(row, table_rows(table)), base_url),
                )
            )
    if empty and not items:
        return ()
    if not items or empty or len({i.item_id for i in items}) != len(items):
        raise WinBiapUnsupportedPage("wishlist_layout")
    return tuple(items)


def wishlist_next_page(html: str, response_url: str, current: int):
    """Allow only numbered own-list GET pages or exact read-only grid postbacks."""
    root = _tree(html)
    source = urlparse(response_url)
    candidates = []
    for control in root.descendants():
        if (
            control.tag in {"input", "button"}
            and "disabled" not in control.attrs
            and re.search(
                r"pager|page\$|nextpage",
                control.attrs.get("name", "") + control.attrs.get("onclick", ""),
                re.I,
            )
        ):
            raise WinBiapUnsupportedPage("wishlist_pagination_control")
    for link in root.descendants("a"):
        href = link.attrs.get("href", "")
        is_next = link.attrs.get("rel") == "next" or link.text.casefold() in {
            "weiter",
            "nächste",
            "nächste seite",
            ">",
            "»",
        }
        if href.lower().startswith("javascript:"):
            match = re.fullmatch(
                r"javascript:__doPostBack\('([^']*(?:GridViewFavorites|GridViewFavorite|GridViewResult))','Page\$(Next|Prev|First|[0-9]+)'\);?",
                href,
            )
            if match:
                if match[2] in {"Prev", "First"}:
                    continue
                page = current + 1 if match[2] == "Next" else int(match[2])
                if page > current:
                    candidates.append(
                        (
                            page,
                            "POST",
                            response_url,
                            {
                                "__EVENTTARGET": match[1],
                                "__EVENTARGUMENT": "Page$" + match[2],
                            },
                        )
                    )
            elif "Page$" in href or is_next:
                raise WinBiapUnsupportedPage("wishlist_pagination")
            continue
        target = urljoin(response_url, href)
        parsed = urlparse(target)
        query = parse_qs(parsed.query)
        if is_next or "page" in query:
            if (
                (parsed.scheme, parsed.netloc, parsed.path)
                != (source.scheme, source.netloc, source.path)
                or set(query) != {"page"}
                or len(query["page"]) != 1
                or not query["page"][0].isdigit()
                or parsed.fragment
            ):
                raise WinBiapUnsupportedPage("wishlist_pagination")
            page = int(query["page"][0])
            if page > current:
                candidates.append((page, "GET", target, None))
            elif is_next:
                raise WinBiapUnsupportedPage("wishlist_page_loop")
    if not candidates:
        return None
    action = min(candidates, key=lambda action: action[0])
    if action[0] != current + 1:
        raise WinBiapUnsupportedPage("wishlist_page_gap")
    return action
