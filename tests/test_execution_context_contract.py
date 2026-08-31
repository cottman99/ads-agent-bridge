from __future__ import annotations

import json
from pathlib import Path

from ads_agent_bridge.addon.AdsAgentBridge.contracts import (
    CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
    RUNTIME_SNAPSHOT_SCHEMA_VERSION,
    capability_specs,
    commands_by_safety,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "schemas"


def test_contract_schemas_are_versioned_and_parseable() -> None:
    names = (
        "ads-continuation-state-v1.schema.json",
        "bridge-capability-descriptor-v1.schema.json",
        "bridge-runtime-snapshot-v1.schema.json",
    )

    schemas = [json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8")) for name in names]

    assert [schema["title"] for schema in schemas] == [
        "ADS Continuation State v1",
        "Bridge Capability Descriptor v1",
        "Bridge Runtime Snapshot v1",
    ]
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas)


def test_capability_catalog_is_unique_complete_and_json_shaped() -> None:
    specs = capability_specs()
    ids = [item["id"] for item in specs]

    assert CAPABILITY_DESCRIPTOR_SCHEMA_VERSION == 1
    assert RUNTIME_SNAPSHOT_SCHEMA_VERSION == 1
    assert len(ids) == len(set(ids))
    assert set(ids) == set(commands_by_safety("safe")) | set(commands_by_safety("bounded")) | set(
        commands_by_safety("unsafe")
    )
    assert "runtime_snapshot" in commands_by_safety("safe")
    assert json.loads(json.dumps(specs)) == specs
