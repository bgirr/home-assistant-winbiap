#!/usr/bin/env python3
"""Generate the bundled library catalog from the official provider page."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCE_URL = "https://www.winbiap.de/referenzen"
DEFAULT_OUTPUT = Path("custom_components/winbiap/libraries.json")


@dataclass(frozen=True, slots=True)
class Library:
    """One library reference."""

    id: str
    name: str
    location: str
    url: str


class ReferenceParser(HTMLParser):
    """Extract server-rendered reference cards without external dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.libraries: list[Library] = []
        self._card_depth = 0
        self._capture: str | None = None
        self._name_parts: list[str] = []
        self._location_parts: list[str] = []
        self._url = ""

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "data_card" in classes:
            self._card_depth = 1
            self._name_parts = []
            self._location_parts = []
            self._url = ""
            return
        if not self._card_depth:
            return
        if tag == "div":
            self._card_depth += 1
        if "data_title" in classes:
            self._capture = "name"
        elif "data_sub" in classes:
            self._capture = "location"
        elif tag == "a" and attributes.get("data-tooltip") == "WebOPAC":
            self._url = urljoin(SOURCE_URL, attributes.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if not self._card_depth or tag != "div":
            return
        self._capture = None
        self._card_depth -= 1
        if self._card_depth:
            return
        name = " ".join(self._name_parts).strip()
        location = " ".join(self._location_parts).strip()
        if name and location and self._url.startswith(("http://", "https://")):
            material = f"{self._url}\n{name}\n{location}"
            self.libraries.append(
                Library(
                    id=sha256(material.encode()).hexdigest()[:16],
                    name=name,
                    location=location,
                    url=self._url,
                )
            )

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        if self._capture == "name":
            self._name_parts.append(value)
        elif self._capture == "location":
            self._location_parts.append(value)


def parse_libraries(html: str) -> list[Library]:
    """Parse and validate the catalog entries."""
    parser = ReferenceParser()
    parser.feed(html)
    libraries = sorted(
        parser.libraries,
        key=lambda library: (library.name.casefold(), library.location.casefold()),
    )
    ids = {library.id for library in libraries}
    if len(ids) != len(libraries):
        raise ValueError("Provider catalog generated duplicate IDs")
    if len(libraries) < 100:
        raise ValueError(
            f"Provider catalog unexpectedly contains only {len(libraries)} entries"
        )
    return libraries


def fetch_source() -> str:
    """Download the official provider reference page."""
    request = Request(SOURCE_URL, headers={"User-Agent": "winbiap-catalog-updater/1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def render_catalog(libraries: list[Library]) -> str:
    """Render deterministic catalog JSON."""
    payload = {
        "source": SOURCE_URL,
        "generated_at": datetime.now(UTC).date().isoformat(),
        "count": len(libraries),
        "libraries": [asdict(library) for library in libraries],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    """Update or verify the generated catalog."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-html", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    html = (
        args.input_html.read_text(encoding="utf-8")
        if args.input_html
        else fetch_source()
    )
    rendered = render_catalog(parse_libraries(html))
    if args.check:
        expected = json.loads(rendered)
        current = (
            json.loads(args.output.read_text(encoding="utf-8"))
            if args.output.exists()
            else {}
        )
        if (
            current.get("source") != expected["source"]
            or current.get("libraries") != expected["libraries"]
        ):
            print(f"Catalog is stale: {args.output}", file=sys.stderr)
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
