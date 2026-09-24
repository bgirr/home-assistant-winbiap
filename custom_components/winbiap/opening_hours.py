"""Verified public opening schedules, independent of private account data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .api import _tree

SOURCE_URL = "https://www.koenigsbrunn.de/kultur/einrichtungen/stadtbuecherei"
DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
Windows = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class OpeningHours:
    weekly: tuple[Windows, ...]
    exceptions: tuple[tuple[str, Windows], ...]
    fetched_at: datetime
    source: str = SOURCE_URL

    def fresh(self, now: datetime) -> bool:
        return timedelta(0) <= now - self.fetched_at < timedelta(hours=48)

    def windows_on(self, day: date) -> Windows:
        return dict(self.exceptions).get(day.isoformat(), self.weekly[day.weekday()])


def parse_windows(value: str) -> Windows:
    if value.strip().casefold() in {"geschlossen", "closed"}:
        return ()
    pattern = r"(\d{1,2})[.:](\d{2})\s*[-\u2013]\s*(\d{1,2})[.:](\d{2})"
    matches = list(re.finditer(pattern, value))
    rest = re.sub(pattern, "", value)
    rest = re.sub(r"\b(?:Uhr|und)\b|[,;]", "", rest, flags=re.I).strip()
    if not matches or rest:
        raise ValueError("invalid_opening_window")
    windows = []
    for match in matches:
        h1, m1, h2, m2 = map(int, match.groups())
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
            raise ValueError("invalid_opening_time")
        start, end = f"{h1:02}:{m1:02}", f"{h2:02}:{m2:02}"
        if start >= end or (windows and windows[-1][1] > start):
            raise ValueError("overlapping_opening_windows")
        windows.append((start, end))
    return tuple(windows)


def parse_exceptions(value: str) -> tuple[tuple[str, Windows], ...]:
    """User overrides: YYYY-MM-DD: geschlossen or HH:MM-HH:MM, ... ."""
    result = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        line = line.strip()
        day = date.fromisoformat(line[:10]).isoformat()
        if line[10:11] != ":" or day in result:
            raise ValueError("invalid_exception_date")
        result[day] = parse_windows(line[11:])
    return tuple(sorted(result.items()))


def parse_opening_hours(html: str, fetched_at: datetime | None = None) -> OpeningHours:
    root = _tree(html)
    blocks = [
        n.text
        for n in root.descendants("div")
        if "address-description" in n.attrs.get("class", "").split()
        and "Öffnungszeiten:" in n.text
    ]
    if len(blocks) != 1:
        raise ValueError("opening_schedule_not_found")
    text = blocks[0].split("Öffnungszeiten:", 1)[1].strip()
    parts = re.split(r"\b(Mo|Di|Mi|Do|Fr|Sa|So)\.\s*", text)
    if parts[0].strip() or len(parts) < 13:
        raise ValueError("incomplete_opening_schedule")
    schedule = {}
    for i in range(1, len(parts), 2):
        if parts[i] in schedule:
            raise ValueError("duplicate_opening_day")
        schedule[parts[i]] = parse_windows(parts[i + 1])
    if not set(DAYS[:6]).issubset(schedule):
        raise ValueError("incomplete_opening_week")
    # Official schedule lists Monday-Saturday; unlisted Sunday is treated as closed.
    exceptions = {}
    for node in root.descendants("p"):
        match = re.search(
            r"(?:Stadt)?bücherei (?:ist|bleibt) (?:am|vom) (\d{2}\.\d{2}\.\d{4})(?: bis (\d{2}\.\d{2}\.\d{4}))? geschlossen[.!]?$",
            node.text,
            re.I,
        )
        if match:
            start = datetime.strptime(match[1], "%d.%m.%Y").date()
            end = datetime.strptime(match[2], "%d.%m.%Y").date() if match[2] else start
            if not 0 <= (end - start).days <= 366:
                raise ValueError("invalid_closure_range")
            for offset in range((end - start).days + 1):
                exceptions[(start + timedelta(days=offset)).isoformat()] = ()
        special = re.search(
            r"(?:Stadt)?bücherei ist am (\d{2}\.\d{2}\.\d{4}) von (.+) geöffnet[.!]?$",
            node.text,
            re.I,
        )
        if special:
            day = datetime.strptime(special[1], "%d.%m.%Y").date().isoformat()
            exceptions[day] = parse_windows(special[2])
    return OpeningHours(
        tuple(schedule.get(day, ()) for day in DAYS),
        tuple(sorted(exceptions.items())),
        fetched_at or datetime.now(UTC),
    )
