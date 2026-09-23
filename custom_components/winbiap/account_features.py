"""Conservative parsers for optional, read-only account sections."""

from __future__ import annotations

import re
from hashlib import sha256
from urllib.parse import parse_qs, urljoin, urlparse

from .api import WinBiapUnsupportedPage, _cover_url, _parse_date, _tree
from .models import WinBiapReservation


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
        rows = table.descendants("tr")
        headers = [n.text.casefold() for n in table.descendants("th")]
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
            item_id = media_identifier(row)
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
                    cover_url=_cover_url(row, base_url),
                )
            )
    if empty and not records:
        return ()
    if not records or empty or len({r.item_id for r in records}) != len(records):
        raise WinBiapUnsupportedPage("reservation_layout")
    return tuple(records)
