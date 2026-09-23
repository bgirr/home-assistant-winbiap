# Account feature plan

The account features below were delivered sequentially in beta.7–beta.9. They
remain read-only. Unrecognized layouts are unavailable, never an empty account
or a zero balance. See [feature log](feature-log.md) for delivery and validation.

## 1. Reservations (Vorbestellungen) — delivered in 0.1.0-beta.7

- A count sensor per account, with explicit zero only when the page confirms it.
- Structured records with title, author, status and cover when present.
- Pickup deadline and ready-for-pickup status when supplied by the library.
- Reuse cover entities for reservations once their stable identifiers and image
  source can be verified; distinguish their IDs from active loans.
- Acceptance: synthetic fixtures for empty, pending and ready reservations;
  repeated updates preserve entity identity and never modify reservations.

## 2. Fees (Gebühren) — delivered in 0.1.0-beta.8

- A monetary sensor for the current outstanding account balance, currency EUR
  when confirmed by the library; parse locale-specific amounts with Decimal.
- Distinguish an explicitly settled account from unavailable or unsupported data.
- Do not sum the displayed recent bookings to infer the current balance: the
  list may be truncated and can contain both charges and payments.
- Optional transaction details only after an explicit privacy and retention
  decision; do not publish account history in fixtures, diagnostics or logs.
- Acceptance: settled balance, positive balance, comma decimals, credits and
  truncated booking-list fixtures; Home Assistant monetary-sensor runtime tests.

## 3. Wishlist (Merkliste) — delivered in 0.1.0-beta.9

- A per-account count and structured list with titles, authors and covers when
  available. Preserve stable media identifiers without exposing account secrets.
- Fetch only the signed-in account's own list; handle pagination without silently
  reporting only the first page as the total.
- Acceptance: explicit empty list, populated list and paginated list fixtures;
  no add/remove/reserve operations and isolated sessions for multiple accounts.

## Shared delivery requirements

Inspect page structure in memory. Keep only synthetic or thoroughly anonymized
fixtures and never persist raw authenticated HTML. Reuse the existing same-origin
account client, bounded requests, categorical failures and HA-owned sessions.
Each feature needs parser tests, real HA entity tests, an opt-in live check,
release notes and a version installable through HACS. Unknown layouts must leave
the affected feature unavailable without breaking working loan/cover entities.
