# Account feature plan

The next account features remain read-only. They are planned work, not entities
provided by the current version. Implement them incrementally after the cover
release; do not treat an unrecognized page as an empty account or a zero balance.

## 1. Reservations (Vorbestellungen)

- A count sensor per account, with explicit zero only when the page confirms it.
- Structured records with title, author, status and cover when present.
- Pickup deadline and ready-for-pickup status when supplied by the library.
- Reuse cover entities for reservations once their stable identifiers and image
  source can be verified; distinguish their IDs from active loans.
- Acceptance: synthetic fixtures for empty, pending and ready reservations;
  repeated updates preserve entity identity and never modify reservations.

## 2. Fees (Gebühren)

- A monetary sensor for the current outstanding account balance, currency EUR
  when confirmed by the library; parse locale-specific amounts with Decimal.
- Distinguish an explicitly settled account from unavailable or unsupported data.
- Do not sum the displayed recent bookings to infer the current balance: the
  list may be truncated and can contain both charges and payments.
- Optional transaction details only after an explicit privacy and retention
  decision; do not publish account history in fixtures, diagnostics or logs.
- Acceptance: settled balance, positive balance, comma decimals, credits and
  truncated booking-list fixtures; Home Assistant monetary-sensor runtime tests.

## 3. Wishlist (Merkliste)

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
