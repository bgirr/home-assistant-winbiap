"""The opt-in harness must not expose even exception-embedded credentials."""

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from scripts import live_account


@pytest.fixture
def local_harness(monkeypatch, tmp_path):
    monkeypatch.setattr(live_account, "ROOT", tmp_path)
    monkeypatch.setattr(live_account.sys, "argv", ["live_account.py"])
    monkeypatch.delenv("WINBIAP_CARD", raising=False)
    monkeypatch.delenv("WINBIAP_PASSWORD", raising=False)
    previous = logging.root.manager.disable
    yield tmp_path
    logging.disable(previous)


def test_missing_credentials_skip_without_network(local_harness, monkeypatch, capsys):
    run = AsyncMock()
    monkeypatch.setattr(live_account, "run", run)
    assert live_account.main() == 0
    run.assert_not_called()
    assert capsys.readouterr().out == "SKIP: credentials_missing\n"


def test_file_values_are_literal_and_not_printed(local_harness, monkeypatch, capsys):
    path = local_harness / ".winbiap-credentials"
    path.write_text("WINBIAP_CARD=SYNTHETIC\nWINBIAP_PASSWORD=$literal#= value\n")
    path.chmod(0o600)
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(live_account, "run", run)
    assert live_account.main() == 0
    assert run.call_args.args[:2] == ("SYNTHETIC", "$literal#= value")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("mode", [0o644, 0o660])
def test_shared_file_rejected(local_harness, mode, capsys):
    path = local_harness / ".winbiap-credentials"
    path.touch(mode=mode)
    path.chmod(mode)
    assert live_account.main() == 1
    assert (
        capsys.readouterr().out == "cause=credentials_file_permissions_require_0600\n"
    )


def test_exception_contents_hidden_and_standalone_session_closed(monkeypatch, capsys):
    sessions = []

    class FailingClient:
        challenge_seen = False
        challenge_completed = False
        login_succeeded = False

        def __init__(self, session, *args):
            sessions.append(session)

        async def async_get_account(self):
            raise ValueError("SYNTHETIC_SECRET_COOKIE_AND_PASSWORD")

    monkeypatch.setattr(live_account, "ObservedClient", FailingClient)
    assert (
        asyncio.run(live_account.run("SYNTHETIC", "SYNTHETIC", "https://example.org/"))
        == 1
    )
    output = capsys.readouterr().out
    assert "SYNTHETIC" not in output
    assert "exception=ValueError cause=connection_or_unexpected_error" in output
    assert sessions[0].closed
