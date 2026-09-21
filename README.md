# WinBIAP Library for Home Assistant

An unofficial, read-only Home Assistant integration for library accounts hosted
by WinBIAP WebOPAC. It exposes current loans and due dates without sending
library credentials anywhere except the configured library server.

> [!WARNING]
> `0.1.0-beta.1` is a protocol-validation release. The public login form of the
> Stadtbücherei Königsbrunn is supported, but its authenticated account layout
> still needs to be verified with sanitized fixtures before a stable release.

## Current functionality

- UI configuration with a WebOPAC URL, card number, and password
- live credential and page-layout validation before an entry is created
- isolated cookie session with ASP.NET `VIEWSTATE` form handling
- automatic reauthentication prompt after rejected credentials
- 30-minute coordinator polling and automatic retry after connection failures
- account sensors for loan count, next due date, and overdue count
- one due-date sensor per loan with author, media type, barcode, branch, cover,
  days remaining, and renewal eligibility when provided by the server
- German and English configuration texts
- privacy-safe diagnostics

The integration deliberately does not renew, reserve, or otherwise change
library data.

## Installation through HACS

Until the integration is accepted into the HACS default catalog:

1. Open **HACS > Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Enter `https://github.com/bgirr/home-assistant-winbiap`.
4. Select **Integration** and add the repository.
5. Download **WinBIAP Library** and restart Home Assistant.
6. Open **Settings > Devices & services > Add integration**.
7. Select **WinBIAP Library** and enter the root URL of your WebOPAC, your
   card number, and password.

Example URL: `https://opac.winbiap.net/koenigsbrunn/`

## Entities

| Entity | State | Important attributes |
| --- | --- | --- |
| Loans | Number of active loans | Sanitized structured loan list |
| Next due date | Earliest due date | — |
| Overdue items | Number of overdue loans | — |
| One entity per loan | Due date | Title, author, type, barcode, branch, cover, remaining days, renewable |

Returned loan entities become unavailable instead of silently changing their
identity. New loans are added automatically after the next update.

## Privacy and security

- Credentials are stored in the Home Assistant config entry.
- Credentials, cookies, and card numbers are never logged or returned in
  diagnostics.
- Each account uses its own HTTP cookie session.
- Account HTML is processed locally inside Home Assistant.
- Do not attach raw account pages to public issues. Follow the sanitizing guide
  in [docs/fixtures.md](docs/fixtures.md).

## Compatibility

| Installation | Public login | Account parser | Status |
| --- | --- | --- | --- |
| Stadtbücherei Königsbrunn, WebOPAC 4.7.3 | Inspected | Fixture required | Initial target |
| Other WinBIAP WebOPAC 4.x sites | Generic ASP.NET form | Table/card parser | Community testing needed |
| B24 mobile app | Not used | Not used | Out of scope |

The client is an independent implementation. No source code from libopac or
other third-party clients was copied.

## Development

```bash
python -m venv .venv
.venv/bin/pip install aiohttp pytest ruff
.venv/bin/ruff check custom_components tests
.venv/bin/pytest
```

The parser tests use synthetic, anonymized fixtures only. See
[CONTRIBUTING.md](CONTRIBUTING.md) before contributing a new WebOPAC layout.

## Release path

- [x] Repository, HACS metadata, brand assets, Hassfest, and HACS validation
- [x] Independent async client, parser models, coordinator, config flow,
  reauthentication, sensors, diagnostics, and unit tests
- [ ] Verify an anonymized authenticated Königsbrunn account fixture
- [ ] Test at least two additional independently hosted WinBIAP installations
- [ ] Publish `v0.1.0` and collect HACS custom-repository feedback
- [ ] Publish a stable release and submit the repository to `hacs/default`
- [ ] Consider explicit renewal actions only after the read-only integration is
  stable; automatic renewal will never be enabled by default

## Troubleshooting

If setup reports **Connection failed**, first confirm that the URL opens a
WinBIAP login page in a browser. If login succeeds in a browser but setup still
fails, download diagnostics and open an issue without including credentials or
raw account HTML.

This project is not affiliated with or endorsed by datronicsoft, WinBIAP, B24,
or any participating library. Product names may be trademarks of their owners.

## License

MIT
