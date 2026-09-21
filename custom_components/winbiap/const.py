"""Constants for the WinBIAP Library integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "winbiap"
PLATFORMS = [Platform.SENSOR]
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

CONF_BASE_URL = "base_url"
CONF_LIBRARY_CARD = "library_card"
