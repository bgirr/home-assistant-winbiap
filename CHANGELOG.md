# Changelog

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
