"""Deterministic return planning across closures, midnight and DST."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from custom_components.winbiap.models import WinBiapLoan
from custom_components.winbiap.opening_hours import OpeningHours
from custom_components.winbiap.return_planning import calculate_return_plan

NOW = datetime(2026, 9, 24, 8, tzinfo=UTC)
HOURS = OpeningHours(
    (
        (("14:00", "18:00"),),
        (("10:00", "12:00"), ("14:00", "18:00")),
        (),
        (("10:00", "19:00"),),
        (("14:00", "18:00"),),
        (("10:00", "13:00"),),
        (),
    ),
    (),
    NOW,
)


def loan(day, identity="test", renewable=False):
    return WinBiapLoan(
        identity, "Synthetic", date.fromisoformat(day), renewable=renewable
    )


def test_earliest_due_includes_renewable_and_all_matching_books():
    plan = calculate_return_plan(
        (
            loan("2026-09-29", "a", True),
            loan("2026-10-01", "b"),
            loan("2026-09-29", "c"),
        ),
        HOURS,
        NOW,
    )
    assert plan.deadline.isoformat() == "2026-09-29T18:00:00+02:00"
    assert plan.windows == HOURS.weekly[1]
    assert plan.item_ids == ("a", "c")


def test_closed_day_and_overrides():
    plan = calculate_return_plan((loan("2026-09-30"),), HOURS, NOW)
    assert plan.deadline.day == 29
    special = replace(HOURS, exceptions=(("2026-09-29", ()),))
    assert calculate_return_plan((loan("2026-09-30"),), special, NOW).deadline.day == 28
    special = replace(HOURS, exceptions=(("2026-09-30", (("09:00", "11:00"),)),))
    assert (
        calculate_return_plan((loan("2026-09-30"),), special, NOW).deadline.hour == 11
    )


def test_past_deadline_never_moves_forward():
    plan = calculate_return_plan((loan("2026-09-23"),), HOURS, NOW)
    assert plan.deadline.date() == date(2026, 9, 22)
    assert plan.deadline < NOW


def test_unknown_stale_and_empty():
    assert calculate_return_plan((), HOURS, NOW) is None
    assert calculate_return_plan((loan("2026-09-29"),), None, NOW) is None
    assert (
        calculate_return_plan((loan("2026-09-29"),), HOURS, NOW + timedelta(hours=48))
        is None
    )
    assert (
        calculate_return_plan(
            (loan("2026-09-29"),), replace(HOURS, weekly=((),) * 7), NOW
        )
        is None
    )


def test_dst_and_midnight_are_local_not_utc_dates():
    for due, offset in [
        ("2026-03-30", timedelta(hours=2)),
        ("2026-10-26", timedelta(hours=1)),
    ]:
        now = datetime.fromisoformat(due + "T00:30:00+02:00")
        hours = replace(HOURS, fetched_at=now)
        plan = calculate_return_plan((loan(due),), hours, now)
        assert plan.deadline.date().isoformat() == due
        assert plan.deadline.utcoffset() == offset
