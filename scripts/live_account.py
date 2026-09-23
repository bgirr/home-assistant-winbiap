"""Opt-in account smoke test; only categorical diagnostics leave this process."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import sys
import warnings
from pathlib import Path
from types import ModuleType

from aiohttp import ClientSession, ClientTimeout, CookieJar, TraceConfig

# Load the production client without importing Home Assistant's integration entry.
ROOT = Path(__file__).resolve().parents[1]
for name, directory in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.winbiap", ROOT / "custom_components" / "winbiap"),
):
    package = ModuleType(name)
    package.__path__ = [str(directory)]
    sys.modules.setdefault(name, package)
sys.path.insert(0, str(ROOT))

from custom_components.winbiap.api import (  # noqa: E402
    LOGIN_NAME,
    LOGIN_PASSWORD,
    WinBiapClient,
    WinBiapInvalidAuth,
    WinBiapUnsupportedPage,
    _tree,
)


class ObservedClient(WinBiapClient):
    """Observe response categories without changing the production protocol."""

    challenge_seen = False
    challenge_completed = False
    login_succeeded = False
    responses = 0

    async def _text(self, response):
        html = await super()._text(response)
        root = _tree(html)
        challenge = any(
            form.attrs.get("action") == "/challenge"
            and {"challenge", "next"}.issubset(
                {node.attrs.get("name") for node in form.descendants("input")}
            )
            for form in root.descendants("form")
        )
        login = LOGIN_NAME in html and LOGIN_PASSWORD in html
        self.challenge_seen |= challenge
        self.challenge_completed |= self.challenge_seen and login
        page = (
            "challenge_candidate" if challenge else "login_form" if login else "other"
        )
        print(f"page_type={page}", flush=True)
        return html

    async def async_login(self):
        result = await super().async_login()
        self.login_succeeded = True
        print("login_success=true", flush=True)
        return result


async def report_http(session, context, params):
    """Trace every HTTP step, including redirects, using only fixed labels."""
    path = params.url.path
    phase = (
        "challenge"
        if path == "/challenge"
        else "login_submit"
        if path.endswith("/user/login.aspx") and params.method == "POST"
        else "login_page"
        if path.endswith("/user/login.aspx")
        else "account_page"
    )
    print(f"phase={phase} http_status={params.response.status}", flush=True)


async def run(card: str, password: str, base_url: str) -> int:
    client = None
    try:
        trace = TraceConfig()
        trace.on_request_end.append(report_http)
        async with asyncio.timeout(45):
            async with ClientSession(
                cookie_jar=CookieJar(),
                timeout=ClientTimeout(total=30),
                trace_configs=[trace],
            ) as session:
                client = ObservedClient(session, base_url, card, password)
                account = await client.async_get_account()
                print(f"loans={len(account.loans)}")
                print(
                    f"wishlist={len(account.wishlist) if account.wishlist is not None else 'unavailable'}"
                )
                print(f"fees_available={account.fees is not None}")
                print(
                    f"fees_settled={account.fees.amount == 0 if account.fees else None}"
                )
                print(
                    f"reservations={len(account.reservations) if account.reservations is not None else 'unavailable'}"
                )
        return 0
    except Exception as err:
        category = (
            "unsupported_page"
            if isinstance(err, WinBiapUnsupportedPage)
            else "invalid_auth"
            if isinstance(err, WinBiapInvalidAuth)
            else "timeout"
            if isinstance(err, TimeoutError)
            else "connection_or_unexpected_error"
        )
        print(f"exception={type(err).__name__} cause={category}")
        return 1
    finally:
        if client is not None:
            print(f"bot_detected={str(client.challenge_seen).lower()}")
            print(f"bot_completed={str(client.challenge_completed).lower()}")
            print(f"login_success={str(client.login_succeeded).lower()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", action="store_true", help="Hidden local input")
    args = parser.parse_args()
    # Never forward library logs, exception messages or tracebacks to the terminal.
    logging.disable(logging.CRITICAL)
    card = os.environ.pop("WINBIAP_CARD", "")
    password = os.environ.pop("WINBIAP_PASSWORD", "")
    if not args.prompt and (not card or not password):
        credentials_path = ROOT / ".winbiap-credentials"
        try:
            if credentials_path.exists():
                if credentials_path.stat().st_mode & 0o077:
                    print("cause=credentials_file_permissions_require_0600")
                    return 1
                values = {}
                for line in credentials_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    key, separator, value = line.partition("=")
                    if not separator or key not in {"WINBIAP_CARD", "WINBIAP_PASSWORD"}:
                        print("cause=invalid_credentials_file_format")
                        return 1
                    values[key] = value
                card = card or values.get("WINBIAP_CARD", "")
                password = password or values.get("WINBIAP_PASSWORD", "")
        except (OSError, UnicodeError):
            print("cause=credentials_file_unreadable")
            return 1
    if args.prompt:
        if not sys.stdin.isatty():
            print("SKIP: interactive_terminal_required")
            return 0
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                card = getpass.getpass("Ausweisnummer (verdeckt): ")
                password = getpass.getpass("Passwort (verdeckt): ")
            except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
                print("SKIP: secure_input_unavailable_or_cancelled")
                return 0
    if not card or not password:
        print("SKIP: credentials_missing")
        return 0
    return asyncio.run(
        run(
            card,
            password,
            os.environ.get(
                "WINBIAP_BASE_URL", "https://opac.winbiap.net/koenigsbrunn/"
            ),
        )
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("cause=cancelled")
        raise SystemExit(130) from None
