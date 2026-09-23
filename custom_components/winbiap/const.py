"""Constants for the WinBIAP Library integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "winbiap"
PLATFORMS = [Platform.SENSOR, Platform.IMAGE]
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)

CONF_BASE_URL = "base_url"
CONF_LIBRARY_CARD = "library_card"
CONF_LIBRARY_ID = "library_id"
CONF_LIBRARY_LOCATION = "library_location"
CONF_LIBRARY_NAME = "library_name"
CONF_LIBRARY_SELECTION = "library"
