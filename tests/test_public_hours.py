"""Public, synthetic WebOPAC layouts and conservative date handling."""

from datetime import UTC, date, datetime

import pytest

from custom_components.winbiap.models import WinBiapLoan
from custom_components.winbiap.public_hours import (
    opening_links,
    parse_public_hours,
    parse_weekly,
    validate_source,
)
from custom_components.winbiap.return_planning import calculate_return_plan

SOURCE = "https://example.org/library/index.aspx"
PARAGRAPHS = """<h2>Kontakt & Öffnungszeiten</h2><div>Öffnungszeiten</div>
<p><span>Mo. 14.00<span> \u2013 </span>18.00 Uhr</span></p>
<p>Di. 10.00 \u2013 12.00 und 14.00 \u2013 18.00 Uhr</p>
<p>Mi. geschlossen</p><p>Do. 10.00 \u2013 19.00 Uhr</p>
<p>Fr. 14.00 \u2013 18.00 Uhr, am 31.07.2030 10 - 18.00</p>
<p>Sa. 10.00 \u2013 13.00 Uhr</p><h2>Kontakt</h2>"""
TABLE = """<div>Öffnungszeiten</div><table>
<tr><td>Montag</td><td>15:30 - 18:00 Uhr</td></tr>
<tr><td>Dienstag</td><td>17:00 - 19:30 Uhr</td></tr>
<tr><td>Mittwoch</td><td>15:30 - 18:00 Uhr</td></tr>
<tr><td>Donnerstag</td><td>10:00 - 12:00 Uhr</td></tr></table><div>Kontakt</div>"""
WEEKLY = "Mo: 10-18\nDi: 10-18\nMi: closed\nDo: 10-18\nFr: 10-18\nSa: 10-13\nSo: closed"


def test_paragraphs_nested_spans_and_dated_addition():
    result = parse_public_hours(PARAGRAPHS, SOURCE)
    assert result.weekly[0] == (("14:00", "18:00"),)
    assert result.weekly[1] == (("10:00", "12:00"), ("14:00", "18:00"))
    assert result.weekly[4] == (("14:00", "18:00"),)
    assert dict(result.exceptions)["2030-07-31"] == (("10:00", "18:00"),)
    assert result.known_days == tuple(range(6))
    assert result.source == SOURCE


def test_table_missing_days_are_unknown_and_not_closed():
    result = parse_public_hours(TABLE, SOURCE)
    assert result.known_days == (0, 1, 2, 3)
    assert result.weekly[1] == (("17:00", "19:30"),)
    loan = WinBiapLoan("id", "Synthetic", date(2030, 1, 6))  # Sunday
    assert calculate_return_plan((loan,), result, datetime.now(UTC)) is None


def test_conflicting_branches_and_invalid_times_rejected():
    for html in (
        PARAGRAPHS + TABLE,
        PARAGRAPHS.replace("14.00 \u2013 18.00 Uhr, am", "25.00 \u2013 26.00 Uhr, am"),
        "<h2>Öffnungszeiten</h2><p>Nach Vereinbarung</p>",
        "<p>Mo: 10:00-18:00</p>",
    ):
        with pytest.raises(ValueError):
            parse_public_hours(html, SOURCE)


def test_public_closure_and_line_break_split():
    result = parse_public_hours(
        PARAGRAPHS + "<p>Die Bücherei bleibt am 24.12.2030 geschlossen.</p>", SOURCE
    )
    assert dict(result.exceptions)["2030-12-24"] == ()
    result = parse_public_hours(
        "<div>Öffnungszeiten</div><p>Di. 10:00-12:00<br>14:00-18:00</p>", SOURCE
    )
    assert len(result.weekly[1]) == 2


def test_manual_schedule_explicit_full_week_and_timezone():
    from dataclasses import replace

    assert len(parse_weekly(WEEKLY)) == 7
    with pytest.raises(ValueError):
        parse_weekly(WEEKLY.replace("So: closed", ""))
    result = replace(
        parse_public_hours(PARAGRAPHS, SOURCE), timezone="America/New_York"
    )
    loan = WinBiapLoan("id", "Synthetic", date(2030, 1, 7))
    plan = calculate_return_plan((loan,), result, datetime.now(UTC))
    assert plan.deadline.hour == 18
    assert plan.deadline.utcoffset().total_seconds() == -5 * 3600


def test_discovery_never_leaves_selected_library():
    html = "".join(
        f'<a href="{url}">Kontakt &amp; Öffnungszeiten</a>'
        for url in (
            "index.aspx?data=demo",
            "https://evil.example/index.aspx",
            "../other/index.aspx",
            "user/login.aspx",
            "javascript:alert(1)",
        )
    )
    assert opening_links(html, "https://example.org/library/") == [
        SOURCE + "?data=demo"
    ]
    for url in (
        "http://example.org",
        "https://user:secret@example.org/",
        "file:///etc/hosts",
    ):
        with pytest.raises(ValueError):
            validate_source(url)
