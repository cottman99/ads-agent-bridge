"""ADS Agent Bridge user addon entry point."""

from __future__ import annotations

import os
import inspect
import sys
import traceback
from pathlib import Path
from typing import Any

_MODULE_DIR = Path(inspect.getfile(lambda: None)).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))


def _write_startup_error() -> None:
    try:
        root = Path(os.environ.get("ADS_AGENT_HOME") or Path.home() / ".ads-agent")
        error_dir = root / "runtime"
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / f"addon-error-{os.getpid()}.log").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
        pass


try:
    from .server import BridgeServer, detect_profile
except ImportError:
    # ADS may load a USER addon entrypoint as a top-level module rather than a
    # normal Python package, so relative imports are not always available.
    try:
        from server import BridgeServer, detect_profile
    except Exception:
        _write_startup_error()
        raise


_SERVER: BridgeServer | None = None


def setup_addon(addon: Any) -> None:
    global _SERVER
    try:
        if _SERVER is not None:
            _SERVER.stop()
        _SERVER = BridgeServer(detect_profile(addon))
        _SERVER.start()
    except Exception:
        _write_startup_error()
        raise


def shutdown_addon(addon: Any) -> None:
    del addon
    global _SERVER
    if _SERVER is not None:
        _SERVER.stop()
        _SERVER = None
