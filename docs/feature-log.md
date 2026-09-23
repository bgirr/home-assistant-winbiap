# Account feature delivery log

Each feature has its own HACS-installable prerelease and changelog entry. The
reusable [Bücherei view](examples/buecherei.json) includes all delivered features.
It discovers account entities dynamically; list changes need no card editing.

| Version | Feature | Dashboard | Validation |
| --- | --- | --- | --- |
| 0.1.0-beta.7 | Reservations: count, status, readiness, deadline and separate covers | Dynamic reservation list and explicit empty/unavailable state | 82 unit + 22 HA runtime tests; live explicit empty page; installed and verified in HA |
| 0.1.0-beta.8 | Current fees: Decimal balance and confirmed EUR monetary sensor | Amount, settled/open/credit status | 91 unit + 22 HA runtime tests; live settled account; installed and verified in HA |
| 0.1.0-beta.9 | Own wishlist: count, titles/authors, separate covers and bounded pagination | Dynamic wishlist and explicit empty/unavailable state | 103 unit + 23 HA/runtime/template tests; live explicit empty list |

## Data and test limits

The live account currently has no reservations or wishlist entries. Populated,
ready-for-pickup, paginated and failure cases therefore use synthetic data.
Supported optional table layouts require recognizable headers and stable media
identifiers. Unsupported layouts remain unavailable; working loans stay available.
Wishlist traversal permits only consecutive own-list pages, with a maximum of
20 pages and 45 seconds. Repeated or failed pages cannot yield a partial count.

Fees use only the explicitly displayed current balance, never transaction sums.
Transaction history is intentionally not exposed or persisted. Optional sections
share each account's isolated authenticated session; cover retrieval uses a
separate cookie-free session. No reservation, payment or wishlist mutation is
implemented. Existing dashboard views are preserved during deployment and a
private backup is kept before every dashboard change.
