"""Shared lifecycle for the profile-specific ADS addon entrypoints."""

from __future__ import annotations

import os
import traceback
from pathlib import Path

try:
    from .context_ui import ContextUi
    from .server import BridgeServer
except ImportError:
    from context_ui import ContextUi
    from server import BridgeServer


_SERVER = None
_UI = None


def write_startup_error():
    try:
        root = Path(os.environ.get("ADS_AGENT_HOME") or Path.home() / ".ads-agent")
        error_dir = root / "runtime"
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / "addon-error-{0}.log".format(os.getpid())).write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    except Exception:
        pass


def setup_profile(profile, addon):
    global _SERVER, _UI
    shutdown_profile(addon)
    server = None
    try:
        server = BridgeServer(profile)
        server.start()
        ui = ContextUi(profile, server.contexts)
        ui.setup(addon)
    except Exception:
        if server is not None:
            try:
                server.stop()
            except Exception:
                pass
        write_startup_error()
        raise
    _SERVER = server
    _UI = ui


def shutdown_profile(addon=None):
    del addon
    global _SERVER, _UI
    ui, _UI = _UI, None
    if ui is not None:
        try:
            ui.stop()
        except Exception:
            write_startup_error()
    server, _SERVER = _SERVER, None
    if server is not None:
        server.stop()


def generate_de_menu(addon, win_def):
    if _UI is not None:
        _UI.generate_de_menu(addon, win_def)
