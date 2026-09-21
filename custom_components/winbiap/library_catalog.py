"""Bundled catalog of libraries listed by the WinBIAP provider."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("libraries.json")
MANUAL_LIBRARY_ID = "__manual__"


@dataclass(frozen=True, slots=True)
class WinBiapLibrary:
    """A selectable library from the provider catalog."""

    library_id: str
    name: str
    location: str
    url: str

    @property
    def label(self) -> str:
        """Return the searchable option label shown by Home Assistant."""
        return f"{self.location} — {self.name}"


def _postal_sort_key(library: WinBiapLibrary) -> tuple[int, str, str]:
    """Sort numeric postal codes first, then names and unknown locations."""
    match = re.match(r"\s*(\d{4,5})\b", library.location)
    return (
        int(match.group(1)) if match else 100_000,
        library.location.casefold(),
        library.name.casefold(),
    )


@cache
def load_library_catalog() -> tuple[WinBiapLibrary, ...]:
    """Load the generated catalog snapshot from disk."""
    payload: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    libraries = tuple(
        sorted(
            (
                WinBiapLibrary(
                    library_id=item["id"],
                    name=item["name"],
                    location=item["location"],
                    url=item["url"],
                )
                for item in payload["libraries"]
            ),
            key=_postal_sort_key,
        )
    )
    if len({library.library_id for library in libraries}) != len(libraries):
        raise ValueError("Library catalog contains duplicate IDs")
    return libraries


def library_by_id(
    libraries: tuple[WinBiapLibrary, ...], library_id: str
) -> WinBiapLibrary | None:
    """Look up a library by its stable catalog identifier."""
    return next(
        (library for library in libraries if library.library_id == library_id),
        None,
    )
