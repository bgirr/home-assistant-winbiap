"""Dynamic dashboard templates with synthetic data only."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as S

from jinja2 import Environment

cards = json.loads(
    (Path(__file__).parents[1] / "docs/examples/buecherei.json").read_text()
)["sections"][0]["cards"]


def render(card, states):
    return (
        Environment()
        .from_string(card["content"])
        .render(
            integration_entities=lambda _: [],
            expand=lambda _: states,
            as_datetime=datetime.fromisoformat,
            now=lambda: datetime(2030, 1, 1),
        )
    )


def source(key, records):
    return S(state=str(len(records)), attributes=S(**{key: records}))


def test_feature_dashboard_templates():
    r = {
        "id": "synthetic",
        "title": "Test <Buch>",
        "author": "Autor & Test",
        "status": "Abholbereit",
        "ready_for_pickup": True,
        "pickup_deadline": "2030-01-02",
    }
    assert "Keine Vorbestellungen" in render(cards[1], [source("reservations", [])])
    out = render(cards[1], [source("reservations", [r])])
    assert "1 abholbereit" in out and "02.01.2030" in out and "Test &lt;Buch&gt;" in out
    for n in (1, 2, 0):
        out = render(cards[3], [source("wishlist", [r] * n)])
        assert out.count("<tr>") == n
    assert "nicht verfügbar" in render(cards[3], [])
    for amount, label in [
        ("0", "ausgeglichen"),
        ("2.50", "Offene Gebühren"),
        ("-1.25", "Guthaben"),
    ]:
        assert label in render(
            cards[2], [S(state=amount, attributes=S(account_section="fees"))]
        )


def test_loan_renewal_labels():
    from types import SimpleNamespace

    template = Environment().from_string(cards[0]["content"])
    for value, label in [
        (True, "✓ Verlängerbar"),
        (False, "✕ Nicht verlängerbar"),
        (None, "Verlängerbarkeit unbekannt"),
    ]:
        loan = {
            "id": "test",
            "title": "Test",
            "author": None,
            "due_date": "2030-01-02",
            "renewable": value,
        }
        state = SimpleNamespace(
            entity_id="sensor.test", state="1", attributes=SimpleNamespace(loans=[loan])
        )
        text = template.render(
            integration_entities=lambda _: [],
            expand=lambda _, state=state: [state],
            now=lambda: datetime(2030, 1, 1),
            as_datetime=lambda v, default=None: datetime.fromisoformat(v),
        )
        assert label in text


def test_return_banner_upcoming_missed_and_unavailable():
    from zoneinfo import ZoneInfo

    loan = {
        "id": "test",
        "title": "Test",
        "author": None,
        "due_date": "2030-01-02",
        "renewable": False,
    }
    loans = S(entity_id="sensor.loans", state="1", attributes=S(loans=[loan]))
    planning = S(
        entity_id="sensor.return",
        state="2030-01-01T17:00:00+00:00",
        attributes=S(
            account_section="return_deadline",
            status="upcoming",
            opening_windows=[["10:00", "12:00"], ["14:00", "18:00"]],
            due_date="2030-01-02",
            affected_count=1,
        ),
    )

    def render_banner(states):
        return (
            Environment()
            .from_string(cards[0]["content"])
            .render(
                integration_entities=lambda _: [],
                expand=lambda _: states,
                now=lambda: datetime(2030, 1, 1),
                as_datetime=lambda v, default=None: datetime.fromisoformat(v),
                as_local=lambda dt: dt.astimezone(ZoneInfo("Europe/Berlin")),
            )
        )

    text = render_banner([loans, planning])
    assert "Spätestens Dienstag, 01.01.2030, bis 18:00 Uhr zurückgeben" in text
    assert "10:00\u201312:00 und 14:00\u201318:00 Uhr" in text
    planning.attributes.status = "missed"
    assert "Rückgabemöglichkeit verstrichen" in render_banner([loans, planning])
    assert "derzeit nicht berechenbar" in render_banner([loans])
    loans.attributes.loans = []
    assert "Spätestens" not in render_banner([loans, planning])
