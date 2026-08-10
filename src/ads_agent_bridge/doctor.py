from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .addon_installer import addon_status
from .bridge_client import list_sessions, probe_sessions, runtime_dir
from .config import load_config
from .discovery import discover
from .docs_kb import status as docs_status
from .paths import cache_dir, config_dir, data_dir


def _check(name: str, status: str, detail: str, remediation: str | None = None) -> dict[str, str]:
    payload = {"name": name, "status": status, "detail": detail}
    if remediation:
        payload["remediation"] = remediation
    return payload


def _ads_user_home_check(platform_name: str | None = None) -> dict[str, str] | None:
    """Report whether Linux ADS can see its ordinary per-user state."""
    if not (platform_name or sys.platform).startswith("linux"):
        return None

    home_value = os.environ.get("HOME")
    if not home_value:
        return _check(
            "ads_user_home",
            "warn",
            "HOME is not set; ADS cannot use its ordinary Linux per-user state.",
            "Keep the real user HOME and isolate Bridge state with ADS_AGENT_HOME.",
        )

    home = Path(home_value).expanduser()
    if not home.is_dir():
        return _check(
            "ads_user_home",
            "warn",
            "HOME does not identify an existing directory.",
            "Keep the real user HOME and isolate Bridge state with ADS_AGENT_HOME.",
        )

    preference = home / ".eesoflic"
    if preference.is_file() and os.access(preference, os.R_OK):
        return _check(
            "ads_user_home",
            "pass",
            "Linux HOME exists and .eesoflic is present and readable.",
        )

    return _check(
        "ads_user_home",
        "warn",
        "Linux HOME exists, but .eesoflic is absent or unreadable; this can be valid before first use or with another license configuration.",
        "For isolated Bridge tests, keep the real HOME and set ADS_AGENT_HOME instead of replacing HOME.",
    )


def diagnose(
    ads_roots: list[Path] | None = None,
    search_roots: list[Path] | None = None,
    ads_config_dir: Path | None = None,
    *,
    ping: bool = True,
) -> tuple[dict[str, Any], int]:
    """Inspect ADS Agent readiness without creating or changing local state."""
    instances = discover(ads_roots or [], search_roots or [])
    config = load_config()
    default_id = config.get("default_instance_id")
    selected = next((item for item in instances if item.instance_id == default_id), None)
    if selected is None and len(instances) == 1:
        selected = instances[0]

    checks = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(
        _check(
            "python",
            "pass" if python_ok else "fail",
            platform.python_version(),
            None if python_ok else "Install Python 3.10 or later.",
        )
    )
    ads_user_home = _ads_user_home_check()
    if ads_user_home:
        checks.append(ads_user_home)
    checks.append(
        _check(
            "ads_discovery",
            "pass" if instances else "fail",
            f"{len(instances)} installation(s) discovered",
            None if instances else "Run `ads-agent doctor --ads-root <ADS installation>`.",
        )
    )

    if selected:
        checks.append(_check("ads_selection", "pass", f"{selected.product_version} ({selected.instance_id})"))
    elif instances:
        checks.append(
            _check(
                "ads_selection",
                "warn",
                "Multiple installations were found and no configured default matches them.",
                "Run `ads-agent setup` interactively or `ads-agent instances use <INSTANCE_ID>`.",
            )
        )

    docs_missing = [item.product_version for item in instances if not item.docs_roots]
    if instances:
        checks.append(
            _check(
                "local_docs",
                "warn" if docs_missing else "pass",
                "Missing for: " + ", ".join(docs_missing) if docs_missing else "Local HTML documentation found.",
                "Install the matching ADS documentation or pass the correct --ads-root." if docs_missing else None,
            )
        )

    headless_ready = bool(selected and selected.python_executable)
    headless_detail = "ADS Python executable found." if headless_ready else "Select an ADS installation with embedded Python."
    if headless_ready and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        headless_detail = "ADS Python found; DISPLAY is not set for Linux runtime initialization."
        headless_status = "warn"
    else:
        headless_status = "pass" if headless_ready else "warn"
    checks.append(
        _check(
            "headless",
            headless_status,
            headless_detail,
            "Set DISPLAY to the isolated X display before ADS Python automation." if headless_status == "warn" and headless_ready else None,
        )
    )

    try:
        addon = addon_status(ads_config_dir)
        registration_count = sum(len(item["registrations"]) for item in addon["profiles"])
        checks.append(
            _check(
                "addon_registration",
                "pass" if registration_count else "warn",
                f"{registration_count} DE/DDS registration(s) found in {addon['config_dir']}",
                None if registration_count else "Run `ads-agent setup` or `ads-agent addon install`.",
            )
        )
    except (OSError, ValueError) as exc:
        addon = {"status": "error", "error": str(exc)}
        checks.append(_check("addon_registration", "warn", str(exc), "Inspect the ADS add-on XML before installing."))

    sessions = probe_sessions(timeout=1.0) if ping else list_sessions()
    live_count = sum(1 for item in sessions if item.get("ok")) if ping else len(sessions)
    checks.append(
        _check(
            "bridge_sessions",
            "pass" if live_count else "warn",
            f"{live_count} live session(s)" if ping else f"{live_count} session file(s); ping skipped",
            None if live_count else "Launch ADS DE or DDS after the add-on is installed.",
        )
    )

    instance_payloads = []
    for instance in instances:
        index = docs_status(instance) if instance.docs_roots else {"status": "not_available"}
        instance_payloads.append(
            {
                **instance.to_dict(),
                "docs_index": index,
            }
        )

    blocked = any(item["status"] == "fail" for item in checks)
    payload = {
        "status": "blocked" if blocked else "ready",
        "read_only": True,
        "package_version": __version__,
        "platform": {"system": platform.system(), "release": platform.release(), "python": platform.python_version()},
        "paths": {
            "config": str(config_dir(ensure=False)),
            "data": str(data_dir(ensure=False)),
            "cache": str(cache_dir(ensure=False)),
            "runtime": str(runtime_dir(ensure=False)),
            "ads_config": addon.get("config_dir") if isinstance(addon, dict) else None,
        },
        "configured_default_instance_id": default_id,
        "selected_instance_id": selected.instance_id if selected else None,
        "instances": instance_payloads,
        "addon": addon,
        "bridge_sessions": sessions,
        "checks": checks,
    }
    return payload, 2 if blocked else 0
