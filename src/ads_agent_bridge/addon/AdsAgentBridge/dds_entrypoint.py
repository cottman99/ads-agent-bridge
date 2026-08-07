"""ADS Data Display entrypoint.

DDS intentionally does not export ``generate_menu``; it owns menus through
DDS window and popup callbacks instead of the Design Environment hook.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_MODULE_DIR = Path(inspect.getfile(lambda: None)).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

try:
    from .entrypoint_common import setup_profile, shutdown_profile
except ImportError:
    from entrypoint_common import setup_profile, shutdown_profile


def setup_addon(addon):
    setup_profile("dds", addon)


def shutdown_addon(addon):
    shutdown_profile(addon)
