from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_data_path


APP_NAME = "ads-agent"


def _override_root(*, ensure: bool = True) -> Path | None:
    value = os.environ.get("ADS_AGENT_HOME")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir(*, ensure: bool = True) -> Path:
    override = _override_root(ensure=ensure)
    if override:
        path = override / "config"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path
    return user_config_path(APP_NAME, appauthor=False, ensure_exists=ensure)


def data_dir(*, ensure: bool = True) -> Path:
    override = _override_root(ensure=ensure)
    if override:
        path = override / "data"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path
    return user_data_path(APP_NAME, appauthor=False, ensure_exists=ensure)


def cache_dir(*, ensure: bool = True) -> Path:
    override = _override_root(ensure=ensure)
    if override:
        path = override / "cache"
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path
    return user_cache_path(APP_NAME, appauthor=False, ensure_exists=ensure)


def config_file(*, ensure: bool = True) -> Path:
    return config_dir(ensure=ensure) / "config.json"


def docs_cache(instance_id: str, *, ensure: bool = True) -> Path:
    path = cache_dir(ensure=ensure) / "docs" / instance_id
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path
