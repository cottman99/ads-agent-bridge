from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_data_path


APP_NAME = "ads-agent"


def _override_root() -> Path | None:
    value = os.environ.get("ADS_AGENT_HOME")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    override = _override_root()
    if override:
        path = override / "config"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return user_config_path(APP_NAME, appauthor=False, ensure_exists=True)


def data_dir() -> Path:
    override = _override_root()
    if override:
        path = override / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return user_data_path(APP_NAME, appauthor=False, ensure_exists=True)


def cache_dir() -> Path:
    override = _override_root()
    if override:
        path = override / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return user_cache_path(APP_NAME, appauthor=False, ensure_exists=True)


def config_file() -> Path:
    return config_dir() / "config.json"


def docs_cache(instance_id: str) -> Path:
    path = cache_dir() / "docs" / instance_id
    path.mkdir(parents=True, exist_ok=True)
    return path
