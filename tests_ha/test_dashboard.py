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
