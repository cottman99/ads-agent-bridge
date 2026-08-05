from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import AdsInstance
from .paths import config_file


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_file()
    if not target.is_file():
        return {"schema_version": 1, "default_instance_id": None, "instances": []}
    return json.loads(target.read_text(encoding="utf-8"))


def save_config(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def configured_instances(payload: dict[str, Any] | None = None) -> list[AdsInstance]:
    data = payload or load_config()
    return [AdsInstance.from_dict(item) for item in data.get("instances", [])]


def update_instances(instances: list[AdsInstance], default_id: str | None = None) -> dict[str, Any]:
    previous = load_config()
    known_ids = {item.instance_id for item in instances}
    selected = default_id or previous.get("default_instance_id")
    if selected not in known_ids:
        selected = instances[0].instance_id if len(instances) == 1 else None
    payload = {
        "schema_version": 1,
        "default_instance_id": selected,
        "instances": [item.to_dict() for item in instances],
    }
    save_config(payload)
    return payload


def select_instance(instance_id: str | None = None) -> AdsInstance:
    payload = load_config()
    instances = configured_instances(payload)
    selected = instance_id or payload.get("default_instance_id")
    if selected:
        for instance in instances:
            if instance.instance_id == selected:
                return instance
        raise ValueError(f"Unknown ADS instance: {selected}")
    if len(instances) == 1:
        return instances[0]
    if not instances:
        raise ValueError("No ADS installations are configured. Run `ads-agent setup`.")
    raise ValueError("Multiple ADS installations are configured. Pass --ads or run `ads-agent instances use`.")


def set_default(instance_id: str) -> dict[str, Any]:
    payload = load_config()
    if instance_id not in {item.get("instance_id") for item in payload.get("instances", [])}:
        raise ValueError(f"Unknown ADS instance: {instance_id}")
    payload["default_instance_id"] = instance_id
    save_config(payload)
    return payload
