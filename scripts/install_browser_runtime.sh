#!/bin/sh
# Run as the Home Assistant service user, using a Python containing the manifest's
# pinned Playwright version. System libraries must already be provisioned.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'Usage: install_browser_runtime.sh /path/to/python /path/to/ha-config' >&2
  exit 2
fi
runtime_python="$1"
config_directory="$2"
"$runtime_python" -c 'import importlib.metadata; assert importlib.metadata.version("playwright") == "1.63.0", "Playwright version mismatch"'
mkdir -p "$config_directory/.winbiap-browser"
chmod 700 "$config_directory/.winbiap-browser"
PLAYWRIGHT_BROWSERS_PATH="$config_directory/.winbiap-browser" "$runtime_python" -m playwright install chromium --no-shell
