"""Conservative extraction of public WebOPAC schedules (no account data)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .api import _tree
from .opening_hours import DAYS, OpeningHours, parse_public_exceptions, parse_windows

_DAY = re.compile(
    r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Mo|Di|Mi|Do|Fr|Sa|So)\.*\s*:?\s+(.+)$",
    re.I,
)
_NAMES = (
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonntag",
)


class _Lines(HTMLParser):
    """Keep DOM text order, table rows and paragraph boundaries."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "h4", "br", "li"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "h4", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _day(name):
    name = name.lower()
    return (
        _NAMES.index(name) if name in _NAMES else [d.lower() for d in DAYS].index(name)
    )


def _windows(text):
    # WebOPAC editors also use whole hours ("10 - 18.00").
    text = re.sub(r"(?<![\d.:])(\d{1,2})(?![\d.:])", r"\1:00", text)
    return parse_windows(text)


def parse_weekly(value):
    """Manual plans must explicitly specify all seven days; never infer closure."""
    schedule = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        match = _DAY.fullmatch(line.strip())
        if not match or (day := _day(match[1])) in schedule:
            raise ValueError("invalid_weekly_schedule")
        schedule[day] = _windows(match[2])
    if set(schedule) != set(range(7)):
        raise ValueError("incomplete_weekly_schedule")
    return tuple(schedule[i] for i in range(7))


def parse_public_hours(html, source, fetched_at=None):
    parser = _Lines()
    parser.feed(html)
    candidates = []
    schedule = None
    exceptions = {}
    invalid = False
    for line in [
        re.sub(r"\s+", " ", s).strip() for s in "".join(parser.parts).splitlines()
    ]:
        if not line:
            continue
        if re.search(r"\bÖffnungszeiten\b", line, re.I):
            if schedule and not invalid:
                candidates.append((schedule, exceptions))
            schedule, exceptions, invalid = {}, {}, False
            continue
        if schedule is None:
            continue
        match = _DAY.fullmatch(line)
        if match:
            day = _day(match[1])
            try:
                if day in schedule:
                    raise ValueError("duplicate_day")
                # Explicitly dated additions cannot change the regular weekly window.
                regular, *special = re.split(r",\s*am\s+", match[2], maxsplit=1)
                schedule[day] = _windows(regular)
                if special:
                    dated = re.fullmatch(r"(\d{2}\.\d{2}\.\d{4})\s+(.+)", special[0])
                    if not dated:
                        raise ValueError("invalid_special_hours")
                    date = datetime.strptime(dated[1], "%d.%m.%Y").date().isoformat()
                    exceptions[date] = _windows(dated[2])
            except ValueError:
                invalid = True
        elif schedule:
            # A separate line may continue a day's split opening window.
            try:
                last = next(reversed(schedule))
                schedule[last] = parse_windows(
                    ", ".join(f"{a}-{b}" for a, b in schedule[last]) + ", " + line
                )
            except ValueError:
                if not invalid:
                    candidates.append((schedule, exceptions))
                schedule = None
    if schedule and not invalid:
        candidates.append((schedule, exceptions))
    if not candidates or any(c != candidates[0] for c in candidates[1:]):
        raise ValueError("missing_or_ambiguous_opening_hours")
    schedule, exceptions = candidates[0]
    exceptions = {**exceptions, **dict(parse_public_exceptions(html))}
    return OpeningHours(
        tuple(schedule.get(i, ()) for i in range(7)),
        tuple(sorted(exceptions.items())),
        fetched_at or datetime.now(UTC),
        source,
        known_days=tuple(sorted(schedule)),
    )


def opening_links(html, base_url):
    """Only public opening links within the selected library; bounded by caller."""
    base = urlsplit(base_url)
    links = []
    for node in _tree(html).descendants("a"):
        if "öffnungszeiten" not in node.text.lower():
            continue
        url = urljoin(base_url, node.attrs.get("href", ""))
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            continue
        if not parsed.path.startswith(base.path.rstrip("/") + "/"):
            continue
        if parsed.path.endswith("index.aspx") and url not in links:
            links.append(url)
    return links[:2]


def validate_source(value):
    """Explicit public HTTPS source; never accept embedded credentials."""
    if not value:
        return value
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.fragment
    ):
        raise ValueError("invalid_opening_source")
    return value
