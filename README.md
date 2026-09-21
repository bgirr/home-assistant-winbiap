# WinBIAP Library for Home Assistant

An unofficial Home Assistant custom integration for library accounts hosted by
WinBIAP. It is intended to expose current loans, due dates, renewal eligibility,
reservations, and account status without sending library credentials anywhere
except the configured library's WinBIAP server.

> [!IMPORTANT]
> This repository is an implementation scaffold. It is not ready for end users
> or HACS default inclusion yet.

## Proposed Home Assistant model

Each library account becomes one Home Assistant device. Version 1 will create
summary sensors and expose structured loan data through individual entities:

- `sensor.<account>_loans` — number of current loans
- `sensor.<account>_next_due` — earliest due date
- `sensor.<account>_overdue` — number of overdue items
- one timestamp sensor per loan, with title, author, media type, barcode,
  branch, cover URL, days remaining, and renewal eligibility

The first release is deliberately read-only. Renewal actions will only be
considered after the read-only implementation is stable across several WinBIAP
installations.

## Configuration

The integration will use a UI config flow with:

- WebOPAC base URL, for example `https://opac.winbiap.net/koenigsbrunn`
- library card number
- password

Credentials are stored in the Home Assistant config entry and are never logged
or included in diagnostics. The update coordinator will poll no more than every
30 minutes by default.

## Architecture

```text
Config flow
    -> WinBIAP client (session, ASP.NET form state, parsing)
    -> DataUpdateCoordinator (authentication and refresh lifecycle)
    -> Home Assistant entities (account and loans)
```

The client implementation will be written independently. No source code from
the discontinued GPL-licensed libopac/opacclient project will be copied.

## Delivery plan

### Phase 0 — protocol fixture and design

- Record sanitized HTML fixtures from the Königsbrunn WebOPAC login and loans
  pages.
- Document login failure, expired session, empty account, and pagination cases.
- Confirm stable selectors for title, author, item ID, due date, cover,
  reservation state, and renewal eligibility.

### Phase 1 — read-only MVP

- Implement the async HTTP client and ASP.NET hidden-field handling.
- Parse loans into typed dataclasses.
- Add config flow with connection validation and duplicate prevention.
- Add coordinator-based polling, reauthentication, and meaningful errors.
- Create summary and per-loan entities with stable unique IDs.
- Add German and English translations.

### Phase 2 — quality and compatibility

- Unit-test all parsers with sanitized fixtures and mocked HTTP responses.
- Add reauthentication, options flow, diagnostics, and entity migration tests.
- Test against at least three independently hosted WinBIAP libraries.
- Add a compatibility matrix to the documentation.

### Phase 3 — first public release

- Add brand assets, screenshots, installation instructions, and privacy notes.
- Pass Ruff, pytest, Hassfest, and HACS validation in GitHub Actions.
- Publish a semantic versioned GitHub release, starting with `v0.1.0`.
- Invite installation as a HACS custom repository and collect field reports.

### Phase 4 — HACS default submission

- Resolve beta feedback and publish a stable release.
- Ensure the repository is public, active, has issues enabled, a description,
  topics, brand assets, passing actions, and at least one GitHub release.
- Submit an alphabetically placed pull request to `hacs/default` as the
  repository owner.

### Later — renewal actions

- Add explicit `winbiap.renew_item` and `winbiap.renew_all` actions.
- Require confirmation in dashboard examples and report the server response.
- Never renew automatically by default.

## HACS installation during development

1. Open HACS.
2. Add this repository as a custom repository of type **Integration**.
3. Download **WinBIAP Library**.
4. Restart Home Assistant.
5. Add **WinBIAP Library** from **Settings > Devices & services**.

## Supported installations

The initial target is the Stadtbücherei Königsbrunn WebOPAC. The goal is broad
WinBIAP compatibility; B24 itself is not scraped and is not required.

## Project status

See the milestone plan above. Contributions and sanitized test fixtures from
other WinBIAP libraries will be welcome once the parser contract is documented.

## Disclaimer

This project is not affiliated with or endorsed by datronicsoft, WinBIAP, B24,
or any participating library. Product names may be trademarks of their owners.

## License

MIT
