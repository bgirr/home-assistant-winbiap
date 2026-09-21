"""Diagnostics support for WinBIAP Library."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LIBRARY_CARD

TO_REDACT = {CONF_LIBRARY_CARD, "password"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a config entry."""
    coordinator = entry.runtime_data
    account = coordinator.data
    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "library_name": account.library_name if account else None,
        "loan_count": len(account.loans) if account else None,
    }
