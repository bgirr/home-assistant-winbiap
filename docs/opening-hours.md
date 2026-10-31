# Opening hours for different libraries

Opening hours are optional and independent of the authenticated account. A failure
here does not discard loans, reservations, fees, wishlist data or their history.
The implementation reads public HTML; it does not use an official B24 hours API.

## Automatic discovery

For each configured account, the integration reads its library's public
`index.aspx`. It follows at most two links labelled **Öffnungszeiten**, restricted
to `index.aspx` within the same library path and origin. A dedicated contact/hours
page takes precedence over the homepage sidebar. Recognized German weekday tables
and paragraphs are normalized into opening windows; split windows are supported.
Conflicting schedules (for example multiple branches) are not combined.

The first attempt uses a cookie-free HTTP session. If that fails, the integration
can use the locally installed browser runtime in a separate temporary context,
without the library card, password or saved account session. This requires the
same browser runtime as account verification; it is not a cloud service. Public
browser discovery is bounded to 90 seconds and always closes the context.

After a successful fetch, data are reused for 24 hours. Failed updates retry on
the hourly coordinator interval. The last successful schedule is stored locally
and restored after restart, provided the library, options and timezone still
match. Its original fetch timestamp is retained. It remains visible during an
outage, but schedules older than 48 hours are excluded from return planning.

## Integration options

Open **Settings → Devices & services → WinBIAP Library → Configure**:

- **Alternative public HTTPS source:** fallback if WinBIAP discovery fails.
  Use a public page containing a recognizable Öffnungszeiten section. Requests
  carry no account cookies and do not follow redirects; enter the final URL.
  Arbitrary website layouts are not guaranteed to work.
- **Library timezone:** an IANA timezone such as `Europe/Berlin` or
  `Europe/Vienna`. Defaults to the Home Assistant timezone. Change it when the
  library is in a different timezone from your home.
- **Manual weekly schedule:** optional complete schedule. When set, it replaces
  web fetching and remains valid until you edit it. Include every weekday,
  including explicit closed days. Multiple intervals use a comma.
- **Closed dates and special hours:** dated exceptions override both discovered
  and manual weekly hours. Use ISO dates; these entries take priority over
  exceptions extracted from the public page.

Example weekly schedule (replace these example times with your library's times):

```text
Mo: 14:00-18:00
Di: 10:00-12:00, 14:00-18:00
Mi: closed
Do: 10:00-19:00
Fr: 14:00-18:00
Sa: 10:00-13:00
So: closed
```

Example dated exceptions:

```text
2030-12-24: closed
2030-12-31: 10:00-12:00
```

Clear the manual schedule to return to automatic discovery. Clearing an alternative
source restores automatic-only discovery, except for existing Königsbrunn accounts:
the previous municipal source remains an automatic compatibility fallback there.
No additional setup is required for existing account entities.

## Unknown days, special closures and return planning

An omitted weekday is **unknown**, not closed. Unknown days are represented by
`null` in the `weekly` attribute and listed in `unknown_days`. The planner will not
skip an unknown day to invent an earlier last return date. For a complete plan,
provide a complete manual schedule or explicit dated exceptions where necessary.

Recognized dated inline additions and explicit closure notices are kept separate
from the regular week. This parser cannot guarantee detection of arbitrary prose,
image-only notices, holidays, Open Library restrictions, different branch rules,
or last-minute closures. Add known exceptions manually and verify the library's
notice before relying on an in-person return deadline. An external return box is
not treated as an opening window. The actual loan due date is never changed.

## Dashboard and portability

Import or update [the reusable Bücherei view](examples/buecherei.json), with path
`buecherei`, in your own dashboard. It discovers entities rather than relying on
an installation-specific entity ID. The opening-hours card shows each account's
schedule, unknown days, source, timezone, exceptions and original fetch timestamp.
It warns when showing saved data. The overview warns when a loan-bearing account
has no calculable return plan, even if another account has one.

The example uses built-in Markdown cards. Optional `card-mod` styles improve its
appearance; the data display does not require that custom frontend resource.
The examples are German; entity discovery works independently of customized IDs.
Existing dashboards are not overwritten by a HACS update: import the revised view
or replace its relevant cards yourself.

## Supported scope

The public Königsbrunn paragraph layout and Schwanfeld table layout were inspected;
regression tests use synthetic equivalents, not private account pages. This does
not constitute authenticated-account testing for every library in the directory.
Unsupported hours can be supplied manually on any supported HA installation.

HTTP account operation does not require a browser. Browser-protected sites still
require the pinned Chromium runtime and system dependencies. The currently
verified runtime deployment is HA Core on Debian/x86-64; HA OS, Container and ARM
browser operation are not claimed as tested or automatic. HACS cannot install
operating-system dependencies. See [runtime setup](browser-fallback-status.md).
