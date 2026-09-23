# WinBIAP Library for Home Assistant

An unofficial, read-only Home Assistant integration for library accounts hosted
by WinBIAP WebOPAC. It exposes current loans and due dates without sending
library credentials anywhere except the configured library server.

> [!WARNING]
> `0.1.0-beta.5` is a protocol-validation release. The BunkerWeb challenge, login
> and account parser have been live-tested with Stadtbücherei Königsbrunn.
> Broader account-layout coverage still needs sanitized fixtures before a stable release.

## Current functionality

- searchable library selection sorted by postal code from the official WinBIAP provider directory
- manual WebOPAC URL fallback for libraries missing from the bundled catalog
- live credential and page-layout validation before an entry is created
- isolated cookie session with ASP.NET `VIEWSTATE` form handling
- bounded BunkerWeb proof-of-work support before login
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
5. Open **WinBIAP Library** in HACS, enable beta versions in its menu, and
   download **v0.1.0-beta.5** (or a newer release). Restart Home Assistant.
   A commit on the `develop` branch does not update an installed HACS version.
6. Open **Settings > Devices & services > Add integration**.
7. Select **WinBIAP Library**, search for your library by name, city, or postal
   code, and then enter your card number and password.

The integration currently bundles 806 library entries sourced from the
[official WinBIAP reference directory](https://www.winbiap.de/referenzen). If
your library is missing, choose **Other / manual WebOPAC URL** and enter its
root address, for example `https://opac.winbiap.net/koenigsbrunn/`.

The setup checks the account within 30 seconds. If it cannot complete, the
form shows an error. For a login diagnosis, enable debug logs for
`custom_components.winbiap` via Home Assistant's Logger integration before
retrying; see [docs/login-debugging.md](docs/login-debugging.md). The trace
contains request stages and HTTP status codes, without account credentials or
raw account pages.

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
| Stadtbücherei Königsbrunn, WebOPAC 4.7.3 | Live-tested with challenge | Live-tested; broader fixtures pending | Initial target |
| Other WinBIAP WebOPAC 4.x sites | Generic ASP.NET form | Table/card parser | Community testing needed |
| B24 mobile app | Not used | Not used | Out of scope |

The client is an independent implementation. No source code from libopac or
other third-party clients was copied.

## Development

```bash
python -m venv .venv
.venv/bin/pip install aiohttp pytest ruff
.venv/bin/ruff check custom_components tests tests_ha scripts
.venv/bin/ruff format --check custom_components tests tests_ha scripts
.venv/bin/pytest -q
```

### Optional local account test

Run `.venv/bin/python scripts/live_account.py --prompt` in a local terminal
for hidden card/password input. Without `--prompt`, the script uses
`WINBIAP_CARD` and `WINBIAP_PASSWORD` from the environment, falling back to
an optional `.winbiap-credentials` file in the repository root:

```text
WINBIAP_CARD=
WINBIAP_PASSWORD=
```

Create that file with mode `0600` (owner read/write only). Put values directly
after `=`, without quotes; special characters are literal, not shell syntax.
Never source the file in a shell. It and similarly named editor backups are
ignored by Git. Never force-add or share this file. Missing credentials skip
the test without making network requests.

The default URL is `https://opac.winbiap.net/koenigsbrunn/`; override it with
`WINBIAP_BASE_URL` if needed. The standalone harness owns its `aiohttp` session,
closes it through `async with`, and applies a 45-second overall timeout. It
prints only HTTP phases/statuses, page categories, challenge/login outcomes,
loan counts and categorical failures. It never saves HTML or prints credentials,
cookies, request parameters, exception messages or media details.

The client borrows its session. Home Assistant owns ongoing account sessions;
config-flow validation uses `auto_cleanup=False` and always detaches afterward.
The fast unit suite uses Home Assistant doubles and real aiohttp sessions.
A separate suite loads the integration into actual Home Assistant 2026.2.3,
registers sensors, checks their states, and exercises reload and session cleanup:

```bash
python3.13 -m venv .venv-ha
.venv-ha/bin/pip install -r requirements-test-ha.txt
.venv-ha/bin/python -m pytest -q tests_ha
```

Run the two suites separately so the lightweight test doubles do not replace
Home Assistant modules in the runtime suite. Both suites run in GitHub Actions.

Refresh the bundled provider catalog with:

```bash
.venv/bin/python scripts/update_libraries.py
```

See [docs/library-catalog.md](docs/library-catalog.md) for catalog provenance,
update behavior, and review guidance.

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
