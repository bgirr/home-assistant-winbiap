# Library catalog

The configuration flow ships with a snapshot of the libraries that expose a
WebOPAC link in the official [WinBIAP reference directory][source]. The
snapshot lets Home Assistant display a searchable library selector without
contacting or scraping the provider during setup.

The snapshot generated on 2026-09-21 contains 806 selectable entries. The
provider page displayed 1,210 references at that time; entries without a
published WebOPAC link are intentionally excluded. A manual URL option remains
available for missing, renamed, or newly added libraries.

Each option stores a generated stable ID, the public library name and location,
and the provider's WebOPAC URL. Credentials are never part of this catalog.
After selection, the integration sends the card number and password directly
to the selected WebOPAC server over HTTPS and validates the authenticated
account page before creating the Home Assistant config entry. Older HTTP links
published by the provider are upgraded to HTTPS before any credentials are
sent.

## Refreshing the snapshot

From the repository root, run:

```bash
python scripts/update_libraries.py
```

The updater uses only the Python standard library, accepts the optional
`--input-html` argument for an offline source copy, and refuses unexpectedly
small results. Review the resulting diff before committing it. To compare a
fresh provider page with the committed entries without rewriting the snapshot,
run:

```bash
python scripts/update_libraries.py --check
```

[source]: https://www.winbiap.de/referenzen
