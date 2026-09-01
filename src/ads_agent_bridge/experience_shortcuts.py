"""Asset-bound compiled shortcut registry, separate from Bridge primitives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from eda_bridge_runtime import (
    get_experience_asset,
    list_experience_assets,
    validate_compiled_shortcut_binding,
)

_ROOT = Path(__file__).with_name("experience_assets")
_SHORTCUTS = {
    "design.apply": {
        "asset_id": "ads.schematic.apply-transaction",
        "asset_hash": (
            "d55af949e76a906135369dae0936ea72f60d3ad67a852ff35c17f2fc1eeaf7de"
        ),
        "implementation_version": "design-apply-v1",
        "effect_class": "mutation",
        "profile": "de",
        "plan_schema": "ads.design-plan/v1",
        "parameter_schema": {"type": "object", "required": ["plan"]},
        "validation": {"method": "fresh-process design readback"},
    },
    "circuit.simulate": {
        "asset_id": "ads.circuit.simulate-and-validate",
        "asset_hash": (
            "5f913db43afdb7c9ee4da9ad79d2c715426dc0ebe22ad1cc9a8fc893b142f399"
        ),
        "implementation_version": "circuit-simulate-v1",
        "effect_class": "job",
        "profile": "de",
        "plan_schema": "ads.circuit-simulation/v1",
        "parameter_schema": {"type": "object", "required": ["plan"]},
        "validation": {"method": "dataset and artifact assertions"},
    },
    "dds.create": {
        "asset_id": "ads.dds.create-native-display",
        "asset_hash": (
            "d1c507827c0bee3b5411b54f226a28b2c206abc17e9b3c8bdf354f2036f9f2e3"
        ),
        "implementation_version": "dds-create-v2",
        "effect_class": "mutation",
        "profile": "dds",
        "plan_schema": "ads.dds-report/v2",
        "parameter_schema": {"type": "object", "required": ["plan"]},
        "validation": {"method": "fresh-process DDS readback"},
    },
    "momentum.run_generated": {
        "asset_id": "ads.momentum.run-generated",
        "asset_hash": (
            "91ae1438c6aecc6db2e35ac6050300a06ee918df1c1f7f5c4e7bbc6a5bb3fb47"
        ),
        "implementation_version": "momentum-generated-v1",
        "effect_class": "job",
        "profile": "de",
        "plan_schema": "ads.momentum-generated-run/v1",
        "parameter_schema": {
            "type": "object",
            "required": ["source_directory", "output_directory", "project"],
        },
        "validation": {"method": "CITI artifact assertions"},
    },
}


def compiled_shortcut_binding(operation: str) -> dict[str, Any]:
    item = _SHORTCUTS[operation]
    return {
        "implements_asset_id": item["asset_id"],
        "asset_version": "1.0.0",
        "asset_schema_version": "eda.experience-asset/v1",
        "asset_content_hash": item["asset_hash"],
        "implementation_version": item["implementation_version"],
        "applies_to": {
            "eda": "keysight-ads",
            "versions": ["2026"],
            "profiles": [item["profile"]],
            "os": ["linux"],
            "capabilities": [operation],
        },
        "effect_class": item["effect_class"],
        "parameter_schema": {
            **item["parameter_schema"],
            "plan_schema": item["plan_schema"],
        },
        "validation": item["validation"],
        "fallback": "governed_native_execution",
    }


def validate_shortcut(operation: str, *, version: str, profile: str) -> dict[str, Any]:
    binding = compiled_shortcut_binding(operation)
    validate_compiled_shortcut_binding(
        binding,
        library_root=_ROOT,
        eda="keysight-ads",
        version=version,
        profile=profile,
    )
    return binding


def shortcut_state(operation: str, *, version: str, profile: str) -> dict[str, Any]:
    try:
        validate_shortcut(operation, version=version, profile=profile)
    except (OSError, TypeError, ValueError) as exc:
        return {"available": False, "healthy": False, "reason": str(exc)}
    return {"available": True, "healthy": True, "asset_eligible": True}


def shortcut_receipt(
    operation: str,
    *,
    version: str,
    profile: str,
    plan: dict[str, Any],
    validation_result: Any,
) -> dict[str, Any]:
    binding = validate_shortcut(operation, version=version, profile=profile)
    encoded = json.dumps(
        plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "implements_asset_id": binding["implements_asset_id"],
        "asset_version": binding["asset_version"],
        "asset_content_hash": binding["asset_content_hash"],
        "implementation_version": binding["implementation_version"],
        "expanded_plan_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "native_execution": (
            "official implementation calls recorded by the workflow result"
        ),
        "validation_result": validation_result,
    }


def list_assets(
    *,
    intents: list[str] | None = None,
    tags: list[str] | None = None,
    version: str | None = None,
    profile: str | None = None,
    capability: str | None = None,
):
    result = list_experience_assets(_ROOT, intents=intents, tags=tags)

    def normalized_version(value: str) -> str:
        text = str(value or "").strip().casefold()
        return text[4:].strip() if text.startswith("ads ") else text

    selected = []
    for asset in result["assets"]:
        applies = asset["applies_to"]
        if version and normalized_version(version) not in {
            normalized_version(item) for item in applies["versions"]
        }:
            continue
        if profile and str(profile) not in applies["profiles"]:
            continue
        if capability and str(capability) not in applies["capabilities"]:
            continue
        selected.append(asset)
    return {**result, "assets": selected}


def get_asset(asset_id: str, *, max_chars: int = 8000):
    return get_experience_asset(_ROOT, asset_id, max_chars=max_chars)
