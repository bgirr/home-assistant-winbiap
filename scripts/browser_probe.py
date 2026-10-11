"""Bounded browser feasibility probe; prints categories/counts, never account data.

Default mode uses a local synthetic site. --live reads the existing HA entry and
contacts its configured library. This is a diagnostic, not a production fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import runpy
from pathlib import Path
from urllib.parse import urljoin, urlparse

runpy.run_path(str(Path(__file__).with_name("live_account.py")))

from custom_components.winbiap.api import (  # noqa: E402
    LOGIN_BUTTON,
    LOGIN_NAME,
    LOGIN_PASSWORD,
    find_account_url,
    has_login_form,
    page_is_login,
    parse_loans,
)

ROOT = Path(__file__).resolve().parents[1]


async def fetch(page, base, card, password, reuse_url=None):
    """Use the site's actual form and keep credentials on the configured origin."""
    origin = urlparse(base)

    def same_origin(url):
        target = urlparse(url)
        return (target.scheme, target.netloc) == (origin.scheme, origin.netloc)

    await page.goto(
        reuse_url or urljoin(base, "user/login.aspx"), wait_until="domcontentloaded"
    )
    if reuse_url and not page_is_login(await page.content(), page.url):
        html = await page.content()
        loans = parse_loans(html, page.url)
        if loans:
            return page.url, len(loans), True
    # The site's JavaScript may complete its own browser verification here.
    await page.locator(f'[name="{LOGIN_PASSWORD}"]').wait_for(
        state="visible", timeout=75000
    )
    if not same_origin(page.url) or not has_login_form(await page.content()):
        raise ValueError("unexpected_login_origin_or_form")
    await page.locator(f'[name="{LOGIN_NAME}"]').fill(card)
    await page.locator(f'[name="{LOGIN_PASSWORD}"]').fill(password)
    await page.locator(f'[name="{LOGIN_BUTTON}"]').click()
    await page.wait_for_load_state("domcontentloaded")
    html = await page.content()
    if not same_origin(page.url) or page_is_login(html, page.url):
        raise ValueError("login_not_completed")
    target = find_account_url(html, page.url)
    if target and target != page.url:
        if not same_origin(target):
            raise ValueError("unexpected_account_origin")
        await page.goto(target, wait_until="domcontentloaded")
        html = await page.content()
    loans = parse_loans(html, page.url)
    if not loans:
        # This initial probe intentionally requires parsed loans for acceptance;
        # it does not equate an unrecognized/empty page with successful access.
        raise ValueError("no_loan_records_parsed")
    return page.url, len(loans), False


async def run(args):
    from aiohttp import web
    from playwright.async_api import async_playwright

    runner = None
    if args.live:
        entries = json.loads(
            (args.ha_config / ".storage/core.config_entries").read_text()
        )["data"]["entries"]
        matches = [
            e
            for e in entries
            if e["domain"] == "winbiap" and e["entry_id"] == args.entry_id
        ]
        if len(matches) != 1:
            raise ValueError("entry_not_found")
        data = matches[0]["data"]
        base, card, password = data["base_url"], data["library_card"], data["password"]
    else:
        app = web.Application()
        sessions = set()

        async def login(request):
            if request.method == "GET":
                if "verified" not in request.query:
                    return web.Response(
                        text="""<iframe id="capjs-frame" hidden></iframe>
                        <script>
                        setTimeout(() => {
                          document.getElementById('capjs-frame').remove();
                          setTimeout(() => location.href='?verified=1', 250);
                        }, 100);
                        </script>""",
                        content_type="text/html",
                    )
                return web.Response(
                    text=(ROOT / "tests/fixtures/login.html").read_text(),
                    content_type="text/html",
                )
            fields = await request.post()
            if (
                fields.get(LOGIN_NAME) != "SYNTHETIC"
                or fields.get(LOGIN_PASSWORD) != "SYNTHETIC"
            ):
                raise web.HTTPUnauthorized()
            sessions.add("synthetic")
            response = web.HTTPFound("/demo/user/loans.aspx")
            response.set_cookie("synthetic_session", "synthetic")
            return response

        async def account(request):
            if request.cookies.get("synthetic_session") not in sessions:
                raise web.HTTPFound("/demo/user/login.aspx")
            return web.Response(
                text=(ROOT / "tests/fixtures/account_table.html").read_text(),
                content_type="text/html",
            )

        app.router.add_route("*", "/demo/user/login.aspx", login)
        app.router.add_get("/demo/user/loans.aspx", account)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        server = await asyncio.get_running_loop().create_server(
            runner.server, "127.0.0.1", 0
        )
        port = server.sockets[0].getsockname()[1]
        base, card, password = (
            f"http://127.0.0.1:{port}/demo/",
            "SYNTHETIC",
            "SYNTHETIC",
        )

    try:
        if args.production:
            from custom_components.winbiap.browser import BrowserClient

            for independent in range(2):
                client = BrowserClient(base, card, password, str(args.browser_config))
                if not args.live:
                    client.base_url = base  # Local-only fixture server uses HTTP.
                try:
                    async with asyncio.timeout(120):
                        account = await client.async_get_account()
                        print(
                            json.dumps(
                                {
                                    "production_client": True,
                                    "session": independent + 1,
                                    "loans": len(account.loans),
                                    "reservations_available": account.reservations
                                    is not None,
                                    "fees_available": account.fees is not None,
                                    "wishlist_available": account.wishlist is not None,
                                }
                            ),
                            flush=True,
                        )
                        if independent == 0:
                            await client.async_get_account()
                            print("production_session_reused=true", flush=True)
                except Exception as err:
                    details = {
                        "production_failure": type(err).__name__,
                        "cause_type": type(err.__context__).__name__
                        if err.__context__
                        else None,
                    }
                    if isinstance(err, (ValueError,)) or type(err).__name__.startswith(
                        "WinBiap"
                    ):
                        allowed = {
                            "browser_login_form_missing",
                            "cross_origin_response",
                            "browser_request_failed",
                            "credentials_rejected",
                            "browser_http_error",
                        }
                        details["category"] = (
                            str(err) if str(err) in allowed else "other"
                        )
                    cause = str(err.__context__ or "").lower()
                    details.update(
                        csp_error=any(
                            word in cause
                            for word in (
                                "content security policy",
                                "unsafe-eval",
                                "evalerror",
                            )
                        ),
                        navigation_error="navigation" in cause,
                        target_closed="closed" in cause,
                    )
                    if client._page is not None:
                        html = await client._page.content()
                        details.update(
                            capjs_present="capjs-frame" in html,
                            login_form=has_login_form(html),
                            loan_records=len(parse_loans(html, client._page.url)),
                        )
                    print(json.dumps(details), flush=True)
                    raise
                finally:
                    await client.async_close()
            return
        async with async_playwright() as playwright:
            for independent in range(2):
                browser = None
                try:
                    async with asyncio.timeout(120):
                        engine = getattr(playwright, args.engine)
                        options = {"headless": True}
                        if args.engine == "chromium":
                            options.update(channel="chromium", chromium_sandbox=True)
                        browser = await engine.launch(**options)
                        context = await browser.new_context(accept_downloads=False)
                        page = await context.new_page()
                        page.set_default_timeout(20000)
                        url, count, reused = await fetch(page, base, card, password)
                        print(
                            json.dumps(
                                {
                                    "mode": "live" if args.live else "synthetic",
                                    "session": independent + 1,
                                    "loans": count,
                                    "reused": reused,
                                }
                            ),
                            flush=True,
                        )
                        if independent == 0:
                            _, count, reused = await fetch(
                                page, base, card, password, url
                            )
                            assert reused
                            print(
                                json.dumps(
                                    {"repeat_loans": count, "session_reused": reused}
                                ),
                                flush=True,
                            )
                finally:
                    if browser is not None:
                        await browser.close()
    finally:
        if runner is not None:
            server.close()
            await server.wait_closed()
            await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--browser-config", type=Path)
    parser.add_argument("--ha-config", type=Path)
    parser.add_argument("--entry-id")
    parser.add_argument("--engine", choices=("chromium", "firefox"), default="chromium")
    args = parser.parse_args()
    if args.live and (args.ha_config is None or not args.entry_id):
        parser.error("live mode requires ha-config and entry-id")
    if args.production and args.browser_config is None:
        parser.error("production requires browser-config")
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except Exception as err:
        print(
            json.dumps({"probe": "failed", "exception_type": type(err).__name__}),
            flush=True,
        )
        if not args.live:
            print(str(err)[:3000], flush=True)
        return 1
    print("probe=passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
