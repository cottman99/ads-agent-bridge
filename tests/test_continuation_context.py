from __future__ import annotations

import json
from pathlib import Path

import pytest
from eda_bridge_runtime import EDAContext

from ads_agent_bridge import continuation_context
from ads_agent_bridge import workspace_create


def _record(workspace: Path) -> dict:
    return {
        "schema_version": continuation_context.CONTINUATION_RECORD_SCHEMA,
        "context_kind": "native-continuation",
        "generation": 1,
        "captured_at": "2026-08-31T00:00:00+00:00",
        "allowed_operations": ["native.batch"],
        "identity": {
            "connection_id": "worker-one",
            "slot": "u2",
            "profile": "de",
            "instance": "ads2027",
            "version": "2027",
            "workspace": str(workspace.resolve()),
            "design": "demo_lib:cell:schematic",
        },
        "content_state": {"kind": "source_fingerprint", "sha256": "a" * 64},
    }


def _partial_plan() -> dict:
    return {
        "schema_version": "eda.native-batch/v1",
        "batch_id": "continue_demo",
        "runtime": "ads.python.de",
        "effect": "staged_mutation",
        "program": {},
        "scope": {
            "write_paths": ["output_wrk"],
            "artifacts": [],
        },
        "transaction": {
            "strategy": "adapter_staging",
            "fresh_reopen": True,
            "promotion": "on_validation",
        },
        "validation": {},
        "limits": {},
    }


def test_private_record_returns_opaque_handle(tmp_path, monkeypatch):
    private_root = tmp_path / "private-runtime"
    monkeypatch.setenv("EDA_RUNTIME_HOME", str(private_root / "eda-runtime"))
    monkeypatch.setattr(workspace_create, "runtime_dir", lambda: private_root)
    workspace = tmp_path / "private" / "private_wrk"
    token, state = continuation_context.create_continuation_context(
        identity=_record(workspace)["identity"], source_fingerprint="a" * 64
    )

    assert token.startswith("EDA_CONTEXT:v2:")
    assert "private_wrk" not in token
    assert "a" * 64 not in token
    decoded = EDAContext.decode(token)
    assert decoded.target == {"binding": "private-host-record"}
    assert "workspace" not in decoded.target
    assert "source_fingerprint" not in json.dumps(decoded.__dict__)
    context_id = decoded.locator["context_id"]
    assert continuation_context.continuation_ref(token) == context_id
    assert continuation_context.resolve_continuation_context(context_id)["identity"] == (
        _record(workspace)["identity"]
    )
    record_path = private_root / "contexts" / f"{context_id}.json"
    private_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert private_record["identity"]["workspace"] == str(workspace.resolve())
    assert private_record["content_state"]["sha256"] == "a" * 64
    resolved = continuation_context.resolve_continuation_context(token)
    assert resolved == private_record
    continued_plan, expected = continuation_context.materialize_native_batch_plan(
        _partial_plan(),
        record=resolved,
        target={"eda": "keysight-ads", "context": token},
        payload={"mutating": True},
    )
    assert continued_plan["scope"]["read_paths"] == [str(workspace.resolve())]
    assert continued_plan["transaction"]["source_fingerprints"] == {
        str(workspace.resolve()): "a" * 64
    }
    assert expected == "a" * 64
    assert state == {
        "schema_version": "ads-continuation-state/v1",
        "state": "content-bound",
        "content_state": "source-fingerprint",
        "profile": "de",
        "slot_bound": True,
        "connection_bound": True,
        "design_bound": True,
    }


def test_materialization_supplies_only_bound_identity_and_content_state(tmp_path):
    workspace = tmp_path / "source_wrk"
    record = _record(workspace)
    plan, expected = continuation_context.materialize_native_batch_plan(
        _partial_plan(),
        record=record,
        target={"eda": "keysight-ads"},
        payload={"mutating": True},
    )

    assert plan["scope"]["resource_kind"] == "ads-workspace"
    assert plan["scope"]["selectors"] == {
        "instance": "ads2027",
        "version": "2027",
        "profile": "de",
    }
    assert plan["scope"]["read_paths"] == [str(workspace.resolve())]
    assert plan["transaction"]["source_fingerprints"] == {
        str(workspace.resolve()): "a" * 64
    }
    assert expected == "a" * 64


@pytest.mark.parametrize(
    ("target", "change", "message"),
    [
        ({"profile": "dds"}, None, "explicit profile"),
        ({}, ("selectors", "instance", "ads2026"), "selector instance"),
        ({}, ("read_paths", None, ["different_wrk"]), "read workspace"),
        ({}, ("fingerprint", None, {"different_wrk": "b" * 64}), "source fingerprint"),
    ],
)
def test_materialization_rejects_explicit_conflicts(tmp_path, target, change, message):
    plan = _partial_plan()
    if change:
        kind, key, value = change
        if kind == "selectors":
            plan["scope"]["selectors"] = {key: value}
        elif kind == "read_paths":
            plan["scope"]["read_paths"] = value
        else:
            plan["transaction"]["source_fingerprints"] = value
    with pytest.raises(ValueError, match=message):
        continuation_context.materialize_native_batch_plan(
            plan,
            record=_record(tmp_path / "source_wrk"),
            target={"eda": "keysight-ads", **target},
            payload={"mutating": True},
        )


def test_conflicting_handle_locations_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        continuation_context.continuation_reference(
            {"continuation_context": "ctx_" + "1" * 20},
            {"continuation_context": "ctx_" + "2" * 20},
        )
