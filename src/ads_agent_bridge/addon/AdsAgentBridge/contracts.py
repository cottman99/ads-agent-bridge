"""Standard-library-only contracts shared by the embedded bridge runtime."""

from __future__ import annotations

import copy
from typing import Any


CAPABILITY_DESCRIPTOR_SCHEMA_VERSION = 1
RUNTIME_SNAPSHOT_SCHEMA_VERSION = 1


_CAPABILITY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "ping",
        "category": "observation",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": (),
    },
    {
        "id": "status",
        "category": "observation",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": (),
    },
    {
        "id": "capabilities",
        "category": "discovery",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": (),
    },
    {
        "id": "runtime_snapshot",
        "category": "discovery",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": (),
    },
    {
        "id": "dialog_snapshot",
        "category": "ui-observation",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("qt-application",),
    },
    {
        "id": "context_capabilities",
        "category": "context",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("context-registry",),
    },
    {
        "id": "context_list",
        "category": "context",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("context-registry",),
    },
    {
        "id": "context_get",
        "category": "context",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("context-registry", "context-handle"),
    },
    {
        "id": "context_refresh",
        "category": "context",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("context-registry", "context-handle"),
    },
    {
        "id": "context_drop",
        "category": "context",
        "safety": "safe",
        "profiles": ("de", "dds"),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("context-registry", "context-handle"),
    },
    {
        "id": "dds_readback",
        "category": "dds",
        "safety": "bounded",
        "profiles": ("dds",),
        "mutates": True,
        "latency_class": "moderate",
        "requirements": ("dds-python", "workspace", "dataset"),
    },
    {
        "id": "ael_workspace_path",
        "category": "ael",
        "safety": "bounded",
        "profiles": ("de",),
        "mutates": False,
        "latency_class": "fast",
        "requirements": ("ael-python",),
    },
    {
        "id": "open_workspace",
        "category": "workspace",
        "safety": "bounded",
        "profiles": ("de",),
        "mutates": True,
        "latency_class": "moderate",
        "requirements": ("de-python", "workspace-path"),
    },
    {
        "id": "safe_shutdown",
        "category": "lifecycle",
        "safety": "bounded",
        "profiles": ("de",),
        "mutates": True,
        "latency_class": "slow",
        "requirements": ("de-app", "no-active-modal", "agent-owned-session"),
    },
    {
        "id": "dialog_action",
        "category": "ui-action",
        "safety": "bounded",
        "profiles": ("de", "dds"),
        "mutates": True,
        "latency_class": "fast",
        "requirements": ("active-modal", "dialog-fingerprint", "authorization-decision"),
    },
    {
        "id": "eval",
        "category": "python",
        "safety": "unsafe",
        "profiles": ("de", "dds"),
        "mutates": True,
        "latency_class": "variable",
        "requirements": ("unsafe-opt-in",),
    },
    {
        "id": "exec",
        "category": "python",
        "safety": "unsafe",
        "profiles": ("de", "dds"),
        "mutates": True,
        "latency_class": "variable",
        "requirements": ("unsafe-opt-in",),
    },
    {
        "id": "ael_call",
        "category": "ael",
        "safety": "unsafe",
        "profiles": ("de", "dds"),
        "mutates": True,
        "latency_class": "variable",
        "requirements": ("ael-python", "unsafe-opt-in"),
    },
)


def capability_specs() -> list[dict[str, Any]]:
    """Return a mutable JSON-shaped copy of the canonical command catalog."""

    records = copy.deepcopy(list(_CAPABILITY_SPECS))
    for record in records:
        record["profiles"] = list(record["profiles"])
        record["requirements"] = list(record["requirements"])
    return records


def commands_by_safety(safety: str) -> list[str]:
    return [record["id"] for record in _CAPABILITY_SPECS if record["safety"] == safety]
