"""Plan an in-person return without modifying the library's actual due date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import WinBiapLoan
from .opening_hours import OpeningHours, Windows

BERLIN = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class ReturnPlan:
    deadline: datetime
    due_date: date
    windows: Windows
    item_ids: tuple[str, ...]
    titles: tuple[str, ...]


def calculate_return_plan(
    loans: tuple[WinBiapLoan, ...], hours: OpeningHours | None, now: datetime
) -> ReturnPlan | None:
    if not loans or hours is None or not hours.fresh(now):
        return None
    due = min(loan.due_date for loan in loans)
    affected = tuple(loan for loan in loans if loan.due_date == due)
    for offset in range(367):
        day = due - timedelta(days=offset)
        windows = hours.windows_on(day)
        if windows:
            deadline = datetime.combine(
                day, time.fromisoformat(windows[-1][1]), tzinfo=BERLIN
            )
            return ReturnPlan(
                deadline,
                due,
                windows,
                tuple(loan.item_id for loan in affected),
                tuple(loan.title for loan in affected),
            )
    return None
