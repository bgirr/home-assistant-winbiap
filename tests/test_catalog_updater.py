"""Tests for the provider catalog generator."""

from scripts.update_libraries import parse_libraries


def test_parse_provider_reference_cards() -> None:
    """Only reference cards with a WebOPAC link become selectable entries."""
    html = "".join(
        f"""
        <div class="data_card">
          <div class="data_title">Stadtbücherei Königsbrunn {index:03}</div>
          <div class="data_sub">86343 Königsbrunn</div>
          <a data-tooltip="WebOPAC" href="http://opac.winbiap.net/koenigsbrunn-{index}">OPAC</a>
        </div>
        """
        for index in range(100)
    )

    libraries = parse_libraries(html)

    assert len(libraries) == 100
    assert libraries[0].name == "Stadtbücherei Königsbrunn 000"
    assert libraries[0].location == "86343 Königsbrunn"
    assert libraries[0].url == "http://opac.winbiap.net/koenigsbrunn-0"
