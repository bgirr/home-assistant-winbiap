"""Tests for the generated provider catalog."""

from custom_components.winbiap.library_catalog import (
    WinBiapLibrary,
    _postal_sort_key,
    library_by_id,
    load_library_catalog,
)


def test_catalog_contains_provider_libraries() -> None:
    """The snapshot includes a useful number of selectable libraries."""
    libraries = load_library_catalog()

    assert len(libraries) >= 800
    assert len({library.library_id for library in libraries}) == len(libraries)
    assert all(library.url.startswith(("http://", "https://")) for library in libraries)


def test_catalog_contains_koenigsbrunn() -> None:
    """The initial reference installation can be selected by name and place."""
    library = next(
        library for library in load_library_catalog() if "Königsbrunn" in library.name
    )

    assert library.location == "86343 Königsbrunn"
    assert library.url == "http://opac.winbiap.net/koenigsbrunn"
    assert library_by_id(load_library_catalog(), library.library_id) == library


def test_catalog_is_sorted_by_postal_code() -> None:
    """The selector order follows postal codes, including four-digit codes."""
    libraries = load_library_catalog()

    assert libraries == tuple(sorted(libraries, key=_postal_sort_key))
    assert next(
        library for library in libraries if "Königsbrunn" in library.name
    ).label.startswith("86343 Königsbrunn — ")
    without_code = WinBiapLibrary(
        "other", "Unknown", "No postcode", "https://example.org"
    )
    assert _postal_sort_key(without_code) > _postal_sort_key(libraries[-1])
