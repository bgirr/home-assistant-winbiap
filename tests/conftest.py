"""Test bootstrap without importing Home Assistant."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[1]

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

winbiap = ModuleType("custom_components.winbiap")
winbiap.__path__ = [str(ROOT / "custom_components" / "winbiap")]
sys.modules.setdefault("custom_components.winbiap", winbiap)
