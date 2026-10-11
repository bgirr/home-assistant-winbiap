# Local browser fallback

## Verified on 2026-10-11

Standard sandboxed Chromium successfully retrieved seven live loans in two
independent sessions and reused the first session. The production BrowserClient
also retrieved reservations, fees and wishlist successfully. No browser detection
settings, credentials, challenge results or cookies were modified or exported.
Seven existing Home Assistant cover proxies returned valid images.

The synthetic browser probe includes a hidden verification frame followed by a
late login redirect. This reproduces the timing fault fixed by waiting for the
actual login form. It runs in CI using the same production client.

## Host prerequisites

This deployment uses HA Core 2026.2.3 on Debian 13/x86-64, Python 3.13.
The full root filesystem was expanded from 30 to 40 GiB without removing history,
backups or account snapshots. Playwright 1.63.0 requires Chromium build 1243 and
its system libraries. Browser files are private and outside the HACS directory:
`<HA config>/.winbiap-browser/chromium-1243/chrome-linux64/chrome`.

Provision OS libraries with the pinned Playwright `install-deps chromium` command
as administrator. With that same Playwright version available, run
`scripts/install_browser_runtime.sh /path/to/python /path/to/ha-config` as the
HA service user. The integration manifest installs the Python dependency; HACS
alone cannot install OS packages. A missing runtime retains cached data with
`browser_runtime_missing`; no download or privileged command runs during polling.

## Runtime behavior

HTTP session reuse and bounded GET retries precede browser fallback. Only a
recognized browser-verification page starts Chromium. Each account has a serial
fetch lock and its own in-memory session. Browser fetches have a 120-second limit;
failed processes, unloads and HA shutdown clean up the browser and driver.
HTTP is reprobed after six hours. Failures retry at 5/15/30/60 minutes, honoring
longer Retry-After values; successful updates return to 30 minutes. Confirmed
invalid credentials stop automatic login attempts until reauthentication.

The existing private snapshot schema and entity IDs remain unchanged. Optional
section failures retain their own last successful timestamps. Cached delivery is
never represented as a successful library fetch. The dashboard shows the source
and timing; the diagnostic Abrufstatus sensor exposes safe error categories.

## Acceptance

131 fast tests and 37 real HA runtime/template tests pass locally. Both synthetic
and live production browser probes pass. Release deployment and two scheduled
post-restart fetches are still pending; this document will record their results.
