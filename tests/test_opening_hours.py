"""Synthetic public opening schedules and user-defined exceptions."""

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.winbiap.opening_hours import (
    parse_exceptions,
    parse_opening_hours,
    parse_windows,
)

HTML = '<div class="address-description">Öffnungszeiten: Mo. 14.00 \u2013 18.00 Uhr Di. 10.00 \u2013 12.00 Uhr und 14.00 \u2013 18.00 Uhr Mi. geschlossen Do. 10.00 \u2013 19.00 Uhr Fr. 14.00 \u2013 18.00 Uhr Sa. 10.00 \u2013 13.00 Uhr</div>'


def test_regular_hours_split_windows_and_freshness():
    now = datetime(2030, 1, 1, tzinfo=UTC)
    data = parse_opening_hours(HTML, now)
    assert data.weekly[1] == (("10:00", "12:00"), ("14:00", "18:00"))
    assert data.weekly[2] == data.weekly[6] == ()
    assert data.fresh(now + timedelta(hours=47))
    assert not data.fresh(now + timedelta(hours=48))


@pytest.mark.parametrize(
    "value",
    [
        "25:00-26:00",
        "12:00-10:00",
        "10:00-12:00, 11:00-14:00",
        "nach Vereinbarung",
        "10:99-12:00",
    ],
)
def test_bad_windows(value):
    with pytest.raises(ValueError):
        parse_windows(value)


def test_missing_schedule_is_not_closed_week():
    with pytest.raises(ValueError):
        parse_opening_hours("<p>geschlossen</p>")
    with pytest.raises(ValueError):
        parse_opening_hours(HTML.replace("Mi. geschlossen", ""))


def test_public_closures_and_manual_overrides():
    data = parse_opening_hours(
        HTML + "<p>Die Stadtbücherei ist vom 24.12.2030 bis 26.12.2030 geschlossen.</p>"
    )
    assert data.windows_on(date(2030, 12, 24)) == ()
    assert parse_exceptions("2030-12-24: geschlossen\n2030-12-31: 10:00-12:00") == (
        ("2030-12-24", ()),
        ("2030-12-31", (("10:00", "12:00"),)),
    )
    with pytest.raises(ValueError):
        parse_exceptions("2030-02-30: geschlossen")
    with pytest.raises(ValueError):
        parse_exceptions("2030-12-24: geschlossen\n2030-12-24: 10:00-12:00")


def test_closure_negation_and_special_opening():
    data = parse_opening_hours(
        HTML
        + "<p>Die Stadtbücherei ist am 24.12.2030 nicht geschlossen.</p><p>Die Stadtbücherei ist am 25.12.2030 von 10:00-12:00 geöffnet.</p>"
    )
    assert "2030-12-24" not in dict(data.exceptions)
    assert dict(data.exceptions)["2030-12-25"] == (("10:00", "12:00"),)
