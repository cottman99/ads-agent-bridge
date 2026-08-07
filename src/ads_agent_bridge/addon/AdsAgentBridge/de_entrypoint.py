"""ADS Design Environment entrypoint."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_MODULE_DIR = Path(inspect.getfile(lambda: None)).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

try:
    from .entrypoint_common import generate_de_menu, setup_profile, shutdown_profile
except ImportError:
    from entrypoint_common import generate_de_menu, setup_profile, shutdown_profile


def setup_addon(addon):
    setup_profile("de", addon)


def shutdown_addon(addon):
    shutdown_profile(addon)


def generate_menu(addon, win_def):
    generate_de_menu(addon, win_def)
