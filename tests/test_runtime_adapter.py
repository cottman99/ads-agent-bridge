import io
import json
from types import SimpleNamespace

import pytest

from ads_agent_bridge import runtime_adapter
from ads_agent_bridge.addon.AdsAgentBridge.context import (
    ContextRegistry,
    context_reference_from,
)


class Value:
    def __init__(self, **values):
        self.__dict__.update(values)


def test_generic_context_round_trip():
    registry = ContextRegistry("de", slot="slot-1")
    design = Value(
        lib_name="demo_lib",
        cell_name="cell",
        view_name="schematic",
        selected_objects=(),
    )
    envelope = registry.capture_design(design)
    reference = context_reference_from(envelope["eda_context_ref"]["text"])
    assert reference == {
        "context_id": envelope["context_id"],
        "slot": "slot-1",
        "profile": "de",
        "is_handle": True,
    }
    assert envelope["context_ref"]["text"].startswith("ADS_CONTEXT:v1:")
    from eda_bridge_runtime import EDAContext

    context = EDAContext.decode(envelope["eda_context_ref"]["text"])
    assert context.protocol == "eda-context/v2"
    assert context.origin["origin_id"].startswith("origin-")
    assert context.session["slot"] == "slot-1"
    assert context.target["identity"]["cell"] == "cell"
    assert context.capabilities["digest"].startswith("cap-")


def test_runtime_adapter_requires_optional_runtime(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name.startswith("eda_bridge_runtime"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    with pytest.raises(RuntimeError, match="not installed"):
        runtime_adapter._runtime_imports()


def test_runtime_stdio_records_purpose(tmp_path, monkeypatch):
    pytest.importorskip("eda_bridge_runtime")
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda command, args, slot, profile, timeout: (
            {
                "ok": True,
                "result": {
                    "descriptors": [
                        {
                            "id": "ping",
                            "safety": "safe",
                            "mutates": False,
                            "state": {"available": True, "healthy": True},
                        }
                    ]
                },
            }
            if command == "capabilities"
            else {"ok": True, "result": {"status": "ok"}}
        ),
    )
    request = {
        "protocol": "eda-runtime.request/v1",
        "purpose": "Check the selected ADS session",
        "target": {"eda": "keysight-ads", "slot": "slot-1", "profile": "de"},
        "operation": "ping",
        "payload": {"mutating": False, "args": {}},
    }
    from eda_bridge_runtime.protocol import RequestEnvelope

    request = RequestEnvelope(**request)
    source = io.StringIO(
        json.dumps({"protocol": "eda-runtime.handshake/v1", "versions": [1]})
        + "\n"
        + json.dumps(request.to_dict())
        + "\n"
    )
    destination = io.StringIO()
    ledger = tmp_path / "ledger.sqlite3"
    runtime_adapter.serve(ledger, source, destination)
    responses = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert responses[1]["status"] == "passed"

    from eda_bridge_runtime import ExecutionLedger

    recorded = ExecutionLedger(ledger).events(run_id=request.run_id)
    assert recorded[0]["payload"]["declared_intent"]["purpose"] == request.purpose
    assert any(event["event_type"] == "ads.bridge.completed" for event in recorded)


def test_capabilities_include_greenfield_workspace(monkeypatch):
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda *_args, **_kwargs: {"ok": True, "result": {"descriptors": []}},
    )
    adapter = runtime_adapter._AdsAdapterBase()
    result = adapter.capabilities({"slot": "u2", "profile": "de"})
    assert result["execution_host_role"] == "eda-worker"
    assert result["run_model"] == "synchronous"
    create = next(
        item for item in result["operations"] if item["id"] == "workspace.create"
    )
    assert create["returns_context"] is True
    assert create["state"]["available"] is True


def test_capabilities_keep_greenfield_available_without_live_session(monkeypatch):
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()),
    )
    result = runtime_adapter._AdsAdapterBase().capabilities(
        {"slot": "u2", "profile": "de"}
    )
    assert result["live_bridge"]["available"] is False
    assert [item["id"] for item in result["operations"]] == [
        "docs.status",
        "docs.query",
        "docs.get",
        "workspace.create",
        "design.apply",
        "circuit.simulate",
        "dds.create",
        "momentum.run_generated",
        "session.launch",
        "session.status",
        "session.shutdown",
    ]


def test_runtime_design_apply_accepts_only_structured_plan(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    captured = {}

    def fake_execute(plan, **kwargs):
        captured.update(plan=plan, **kwargs)
        return {"status": "passed", "fresh_reopen": True}

    monkeypatch.setattr(runtime_adapter, "execute_design_plan", fake_execute)
    request = RequestEnvelope(
        purpose="Apply one bounded schematic plan",
        target={"eda": "keysight-ads", "instance": "ads2026", "display": ":4.0"},
        operation="design.apply",
        payload={
            "mutating": True,
            "plan": {
                "schema_version": "ads.design-plan/v1",
                "operation_id": "demo",
            },
        },
        idempotency_key="design-demo",
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )
    assert result.status == "passed"
    assert captured["plan"]["instance"] == "ads2026"
    assert captured["expected_display"] == ":4.0"


def test_runtime_design_apply_rejects_dds_profile(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    monkeypatch.setattr(
        runtime_adapter,
        "execute_design_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("DDS must be rejected before execution")
        ),
    )
    request = RequestEnvelope(
        purpose="Reject a schematic plan on the DDS profile",
        target={"eda": "keysight-ads", "profile": "dds"},
        operation="design.apply",
        payload={"mutating": True, "plan": {"schema_version": "ads.design-plan/v1"}},
        idempotency_key="reject-dds-design",
    )
    with pytest.raises(ValueError, match="requires the ADS DE profile"):
        runtime_adapter._AdsAdapterBase().execute(
            request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
        )


def test_runtime_circuit_simulate_accepts_structured_plan(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    captured = {}

    def fake_execute(plan, **kwargs):
        captured.update(plan=plan, **kwargs)
        return {"status": "passed", "simulation_completed": True}

    monkeypatch.setattr(runtime_adapter, "execute_simulation_plan", fake_execute)
    request = RequestEnvelope(
        purpose="Simulate the selected ADS circuit and read its dataset",
        target={"eda": "keysight-ads", "instance": "ads2026", "display": ":4.0"},
        operation="circuit.simulate",
        payload={
            "mutating": True,
            "plan": {
                "schema_version": "ads.circuit-simulation/v1",
                "operation_id": "demo",
            },
        },
        idempotency_key="simulate-demo",
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )
    assert result.status == "passed"
    assert captured["plan"]["instance"] == "ads2026"
    assert captured["expected_display"] == ":4.0"


def test_runtime_shutdown_accepts_slot_from_payload(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    captured = {}

    def fake_shutdown(slot, wait_seconds):
        captured.update(slot=slot, wait_seconds=wait_seconds)
        return {"status": "exited", "slot": slot}

    monkeypatch.setattr(runtime_adapter, "shutdown_session", fake_shutdown)
    request = RequestEnvelope(
        purpose="Close the exact agent-owned ADS session",
        target={"eda": "keysight-ads"},
        operation="session.shutdown",
        payload={"mutating": True, "slot": "u2", "timeout_seconds": 12},
        idempotency_key="shutdown-u2",
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )

    assert result.status == "passed"
    assert captured == {"slot": "u2", "wait_seconds": 12.0}


def test_runtime_rejects_conflicting_slot_sources(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    monkeypatch.setattr(
        runtime_adapter,
        "shutdown_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("conflicting slots must be rejected before shutdown")
        ),
    )
    request = RequestEnvelope(
        purpose="Reject an ambiguous ADS session target",
        target={"eda": "keysight-ads", "slot": "u2"},
        operation="session.shutdown",
        payload={"mutating": True, "slot": "u1"},
        idempotency_key="reject-slot-conflict",
    )

    with pytest.raises(ValueError, match="slot conflicts"):
        runtime_adapter._AdsAdapterBase().execute(
            request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
        )


def test_runtime_momentum_accepts_only_bounded_transaction(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "passed", "source_preserved": True}

    monkeypatch.setattr(runtime_adapter, "run_generated_momentum", fake_run)
    request = RequestEnvelope(
        purpose="Run one copied generated Momentum input",
        target={"eda": "keysight-ads", "instance": "ads2026", "display": ":4.0"},
        operation="momentum.run_generated",
        payload={
            "mutating": True,
            "source_directory": "/scratch/source",
            "output_directory": "/scratch/output",
            "project": "proj",
            "timeout_seconds": 30,
        },
        idempotency_key="momentum-demo",
    )

    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )

    assert result.status == "passed"
    assert captured["instance_id"] == "ads2026"
    assert captured["expected_display"] == ":4.0"
    assert captured["source_directory"] == "/scratch/source"


def test_runtime_docs_query_does_not_probe_live_ads(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    instance = SimpleNamespace(instance_id="ads2026")
    monkeypatch.setattr(runtime_adapter, "select_instance", lambda value: instance)
    monkeypatch.setattr(
        runtime_adapter,
        "query_docs",
        lambda selected, text, limit, domains: {
            "instance_id": selected.instance_id,
            "query": text,
            "limit": limit,
            "domains": domains,
            "results": [],
        },
    )
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("documentation lookup must not contact live ADS")
        ),
    )
    request = RequestEnvelope(
        purpose="Find one ADS Python symbol",
        target={"eda": "keysight-ads"},
        operation="docs.query",
        payload={
            "mutating": False,
            "instance": "ads2026",
            "query": "de open workspace",
            "domains": ["python"],
            "limit": 6,
        },
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )
    assert result.result["bridge"]["instance_id"] == "ads2026"


def test_session_launch_uses_workspace_from_opaque_context(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    captured = {}
    monkeypatch.setattr(
        runtime_adapter,
        "resolve_context",
        lambda _context_id: {
            "generation": 1,
            "target": {
                "workspace": "/remote/demo_wrk",
                "instance": "ads2026",
                "slot": "greenfield",
                "profile": "de",
                "display": ":4.0",
            },
        },
    )

    def fake_launch(instance, workspace, **kwargs):
        captured.update(instance=instance, workspace=str(workspace), **kwargs)
        return {"status": "ready", "slot": kwargs["slot"]}

    monkeypatch.setattr(runtime_adapter, "launch_session", fake_launch)
    request = RequestEnvelope(
        purpose="Open the newly created workspace",
        target={
            "eda": "keysight-ads",
            "context_id": "ctx_1234567890abcdef1234",
        },
        operation="session.launch",
        payload={"mutating": True},
        idempotency_key="launch-demo",
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )
    assert result.status == "passed"
    assert captured["workspace"].replace("\\", "/") == "/remote/demo_wrk"
    assert captured["display"] == ":4.0"
