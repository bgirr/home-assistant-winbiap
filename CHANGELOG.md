# Changelog

## 0.1.0-beta.11 — Opening hours

- Fetch Königsbrunn’s official public weekly schedule independently with a cookie-free
  session, daily cache and 48-hour maximum freshness. Preserve split opening windows.
- Add an opening-hours sensor, source/fetch metadata, supported explicit public date
  exceptions and validated options for manual closures/special hours.
- Add the opening-hours dashboard card and periodic template refresh after HA startup.
- Validate 113 unit tests, 25 HA/runtime/template tests and the current public schedule.

## 0.1.0-beta.10 — Renewal status

- Read explicit renewal group headings in desktop WebOPAC, preserving unknown
  states and preventing status leakage between groups.
- Display renewable / not renewable / unknown on every dashboard book card.
- Validate 104 unit tests and 24 HA/runtime/template tests. No renewal action is sent.

## 0.1.0-beta.9 — Wishlist

- Add the authenticated account’s wishlist count, structured titles/authors and
  separate stable cover entities; never add, remove or reserve items.
- Follow consecutive own-list pages via restricted GET links or read-only ASP.NET
  grid pagination. Bound traversal to 20 pages / 45 seconds; incomplete or unknown
  layouts remain unavailable instead of returning a partial total.
- Support adjacent lazy cover rows without mixing nested metadata or other titles.
- Add a dynamic wishlist card and synthetic dashboard tests for all three features.
- Validate 103 unit tests and 23 HA/runtime/template tests. Live account: seven loans,
  no reservations, settled fees and an explicitly empty wishlist. Populated and
  paginated wishlists are tested synthetically because the live list is empty.

## 0.1.0-beta.8 — Fees

- Add an EUR monetary sensor for the explicit current account balance, parsed
  with Decimal; support settled accounts, outstanding fees and credits.
- Never derive the balance from recent transactions; do not expose transaction history.
- Add a dynamic fees card to the Bücherei dashboard with settled, due and credit states.
- Validate 91 unit tests and 22 real HA runtime tests, including monetary state writing.
  Live verification confirms an explicitly settled account.

## 0.1.0-beta.7 — Reservations

- Add a read-only reservation count with structured status, pickup readiness and
  pickup deadline. Explicit empty pages produce zero; unknown layouts remain unavailable.
- Add stable reservation cover entities using the existing bounded, cookie-free image proxy.
- Include the dynamic Bücherei dashboard example with a reservation overview.
- Validate empty, pending and ready states, stable identities, optional failures and
  actual Home Assistant registration/removal. Live check: 7 loans, 0 reservations.
- Populated reservation layouts are covered by synthetic fixtures; the live account
  currently has no reservations. No account-changing operations are implemented.

## 0.1.0-beta.6

- Add Home Assistant image entities for borrowed-media covers, with on-demand
  fetching, bounded in-memory caching and isolated cookie-free cover requests.
- Recognize lazy `data-src` images in WebOPAC's adjacent `rowDetails` layout and
  keep each image associated with its own loan.
- Add image parser and real HA runtime tests, cover dashboard examples and a
  roadmap for reservations, current fees and wishlist entities.

## 0.1.0-beta.5

- Fix summary-sensor registration in Home Assistant by inheriting the complete
  `SensorEntityDescription` contract instead of using an unrelated dataclass.
- Add real Home Assistant runtime coverage for sensor registration, state
  writing, entry reload and automatic session cleanup, alongside the fast tests.
- Publish a tagged prerelease that HACS can select and install; a push to
  `develop` alone does not update an existing HACS installation.

## 0.1.0-beta.4

- Handle the recognized BunkerWeb SHA-256 proof-of-work challenge before login,
  with bounded background computation and same-origin requests and redirects.
- Correct Home Assistant session ownership: detach short-lived validation
  sessions and let Home Assistant clean up isolated config-entry sessions.
- Add an opt-in local live-test harness with hidden input or ignored local
  credentials, categorical HTTP diagnostics and a 45-second overall timeout.
- Add challenge, redirect, session-lifetime and error-path regression tests.

## 0.1.0-beta.1

- Add independent async WinBIAP client with ASP.NET form handling.
- Add table and card-based loan parsers with typed account models.
- Add validated config flow, duplicate prevention, and reauthentication.
- Add update coordinator and account/loan sensors.
- Add privacy-safe diagnostics, translations, fixtures, and parser tests.
- Add automated Ruff, pytest, HACS, and Hassfest checks.

## 0.0.0

- Create the HACS-compatible integration scaffold and publication plan.
