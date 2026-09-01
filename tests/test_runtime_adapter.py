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


def test_runtime_adapter_passes_typed_payload_without_args_wrapper(monkeypatch):
    pytest.importorskip("eda_bridge_runtime")
    calls = []

    def fake_bridge_request(command, args, slot, profile, timeout):
        calls.append((command, args, slot, profile, timeout))
        if command == "capabilities":
            return {
                "ok": True,
                "result": {
                    "descriptors": [
                        {
                            "id": "design.live_patch",
                            "safety": "bounded",
                            "mutates": True,
                            "state": {"available": True, "healthy": True},
                        }
                    ]
                },
            }
        return {"ok": True, "result": {"status": "passed"}}

    monkeypatch.setattr(runtime_adapter, "bridge_request", fake_bridge_request)
    request = SimpleNamespace(
        operation="design.live_patch",
        payload={
            "mutating": True,
            "design": "demo_lib:cell:schematic",
            "operations": [{"op": "set_instance_parameter"}],
            "timeout_seconds": 30,
        },
        target={"slot": "slot-1", "profile": "de"},
        is_mutating=True,
    )
    context = SimpleNamespace(emit=lambda *_args, **_kwargs: None)

    result = runtime_adapter._AdsAdapterBase().execute(request, context)

    assert result.status == "passed"
    command, args, slot, profile, timeout = calls[-1]
    assert command == "design.live_patch"
    assert args["design"] == "demo_lib:cell:schematic"
    assert args["operations"] == [{"op": "set_instance_parameter"}]
    assert args["schema_version"] == "eda.live-edit/v1"
    assert args["patch_id"].startswith("patch-")
    assert args["conflict_policy"] == "fail_on_change"
    assert args["validation"] == "readback"
    assert (slot, profile, timeout) == ("slot-1", "de", 30.0)


def test_runtime_adapter_derives_live_design_from_copied_context_target(monkeypatch):
    pytest.importorskip("eda_bridge_runtime")
    calls = []

    def fake_bridge_request(command, args, slot, profile, timeout):
        calls.append((command, args, slot, profile, timeout))
        if command == "capabilities":
            return {
                "ok": True,
                "result": {
                    "descriptors": [
                        {
                            "id": "design.live_patch",
                            "safety": "bounded",
                            "mutates": True,
                            "state": {"available": True, "healthy": True},
                        }
                    ]
                },
            }
        return {"ok": True, "result": {"status": "passed"}}

    monkeypatch.setattr(runtime_adapter, "bridge_request", fake_bridge_request)
    request = SimpleNamespace(
        operation="design.live_patch",
        payload={
            "mutating": True,
            "operations": [{"op": "set_instance_parameter"}],
        },
        target={
            "slot": "slot-1",
            "profile": "de",
            "kind": "design",
            "identity": {
                "library": "demo_lib",
                "cell": "cell",
                "view": "schematic",
            },
        },
        is_mutating=True,
    )
    context = SimpleNamespace(emit=lambda *_args, **_kwargs: None)

    runtime_adapter._AdsAdapterBase().execute(request, context)

    assert calls[-1][1]["design"] == "demo_lib:cell:schematic"


def test_runtime_adapter_revalidates_live_context_in_same_ads_process(monkeypatch):
    from eda_bridge_runtime import EDAContext, RequestEnvelope

    target = {
        "kind": "design",
        "identity": {"library": "demo_lib", "cell": "cell", "view": "schematic"},
        "display_name": "demo_lib:cell:schematic",
    }
    token = EDAContext(
        eda="keysight-ads",
        target_kind="design",
        locator={"context_id": "ctx_0123456789abcdef0123", "slot": "gui", "profile": "de"},
        display_name="demo_lib:cell:schematic",
        generation=3,
        session={"slot": "gui", "profile": "de", "display": ":4.0", "state": "live"},
        target=target,
        freshness={"generation": 3, "state": "captured-live"},
    ).encode()
    calls = []

    def fake_bridge_request(command, args, slot, profile, timeout):
        calls.append((command, args, slot, profile, timeout))
        if command == "context_get":
            return {
                "ok": True,
                "result": {
                    "target": target,
                    "freshness": {"generation": 3, "state": "captured-live"},
                },
            }
        if command == "capabilities":
            return {
                "ok": True,
                "result": {
                    "descriptors": [
                        {
                            "id": "design.live_patch",
                            "safety": "bounded",
                            "mutates": True,
                            "state": {"available": True, "healthy": True},
                        }
                    ]
                },
            }
        return {"ok": True, "result": {"status": "passed"}}

    monkeypatch.setattr(runtime_adapter, "bridge_request", fake_bridge_request)
    request = RequestEnvelope(
        purpose="Edit the selected live ADS design",
        target={"eda": "keysight-ads", "context": token},
        operation="design.live_patch",
        payload={
            "mutating": True,
            "operations": [{"op": "set_instance_parameter"}],
        },
    )
    execution_context = SimpleNamespace(emit=lambda *_args, **_kwargs: None)

    runtime_adapter._AdsAdapterBase().execute(request, execution_context)

    assert calls[0][:4] == (
        "context_get",
        {"context": "ctx_0123456789abcdef0123"},
        "gui",
        "de",
    )
    assert calls[-1][0] == "design.live_patch"
    assert calls[-1][1]["design"] == "demo_lib:cell:schematic"


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


def test_capabilities_classify_live_patch_as_typed_live_edit(monkeypatch):
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda *_args, **_kwargs: {
            "ok": True,
            "result": {
                "descriptors": [
                    {
                        "id": "design.live_patch",
                        "safety": "bounded",
                        "mutates": True,
                        "state": {"available": True, "healthy": True},
                    }
                ]
            },
        },
    )
    operations = runtime_adapter._AdsAdapterBase().capabilities(
        {"slot": "u2", "profile": "de"}
    )["operations"]
    live_patch = next(item for item in operations if item["id"] == "design.live_patch")
    assert live_patch["operation_class"] == "typed-live-edit"


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
        "experience.list",
        "experience.get",
        "native.batch",
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
    monkeypatch.setattr(
        runtime_adapter,
        "select_instance",
        lambda _value: SimpleNamespace(year=2026, product_version="2026"),
    )
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


def test_degraded_experience_disables_shortcuts_but_not_native_execution(monkeypatch):
    monkeypatch.setattr(
        runtime_adapter,
        "bridge_request",
        lambda *_args, **_kwargs: {"ok": True, "result": {"descriptors": []}},
    )
    monkeypatch.setattr(
        runtime_adapter,
        "select_instance",
        lambda _value: SimpleNamespace(
            year=2026, product_version="2026", python_executable="/ads/python"
        ),
    )
    monkeypatch.setattr(
        runtime_adapter,
        "shortcut_state",
        lambda *_args, **_kwargs: {
            "available": False,
            "healthy": False,
            "reason": "asset hash mismatch",
        },
    )

    operations = {
        item["id"]: item
        for item in runtime_adapter._AdsAdapterBase().capabilities(
            {"profile": "de", "instance": "ads2026"}
        )["operations"]
    }
    assert operations["design.apply"]["state"]["available"] is False
    assert operations["native.batch"]["state"]["available"] is True
    assert operations["native.batch"]["returns_context"] is True
    assert (
        operations["native.batch"]["input_schema"]["continuation_schema"]
        == "eda-context/v2"
    )
    native_schema = operations["native.batch"]["input_schema"]
    assert native_schema["plan_contract"]["schema_version"] == "eda.native-batch/v1"
    assert native_schema["plan_contract"]["program"]["entrypoint"] == (
        "def run(api, context)"
    )
    assert native_schema["ads_contract"]["runtime_by_profile"] == {
        "de": "ads.python.de",
        "dds": "ads.python.dds",
    }


def test_native_batch_continues_from_opaque_content_bound_context(
    tmp_path, monkeypatch
):
    from eda_bridge_runtime import RequestEnvelope

    from ads_agent_bridge import workspace_create
    from ads_agent_bridge.continuation_context import create_continuation_context

    source = tmp_path / "source_wrk"
    output = tmp_path / "output_wrk"
    captured = {}
    record = {
        "identity": {
            "connection_id": "worker-one",
            "slot": "u2",
            "profile": "de",
            "instance": "ads2027",
            "version": "2027",
            "workspace": str(source.resolve()),
            "design": "demo_lib:cell:schematic",
        },
        "content_state": {"kind": "source_fingerprint", "sha256": "a" * 64},
    }
    monkeypatch.setattr(workspace_create, "runtime_dir", lambda: tmp_path / "runtime")
    token, _state = create_continuation_context(
        identity=record["identity"],
        source_fingerprint=record["content_state"]["sha256"],
    )

    def fake_execute(plan, **kwargs):
        captured.update(plan=plan, **kwargs)
        return {
            "status": "passed",
            "effect": "staged_mutation",
            "source_fingerprint": "a" * 64,
            "output_fingerprint": "b" * 64,
        }

    monkeypatch.setattr(runtime_adapter, "execute_native_batch", fake_execute)
    monkeypatch.setattr(
        runtime_adapter,
        "select_instance",
        lambda _value: SimpleNamespace(
            instance_id="ads2027", year=2027, product_version="2027"
        ),
    )

    def fake_create_continuation(**kwargs):
        captured["continued"] = kwargs
        return "EDA_CONTEXT:v2:opaque", {
            "schema_version": "ads-continuation-state/v1",
            "state": "content-bound",
        }

    monkeypatch.setattr(
        runtime_adapter, "create_continuation_context", fake_create_continuation
    )
    plan = {
        "schema_version": "eda.native-batch/v1",
        "batch_id": "continue_demo",
        "runtime": "ads.python.de",
        "effect": "staged_mutation",
        "program": {},
        "scope": {"write_paths": [str(output)], "artifacts": []},
        "transaction": {
            "strategy": "adapter_staging",
            "fresh_reopen": True,
            "promotion": "on_validation",
        },
        "validation": {},
        "limits": {},
    }
    request = RequestEnvelope(
        purpose="Continue the exact governed ADS workspace mutation",
        target={
            "eda": "keysight-ads",
            "context": token,
            "context_id": "must-not-be-expanded-as-lifecycle-context",
        },
        operation="native.batch",
        payload={"mutating": True, "plan": plan},
        idempotency_key="continue-demo-v2",
    )
    result = runtime_adapter._AdsAdapterBase().execute(
        request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
    )

    assert captured["plan"]["scope"]["read_paths"] == [str(source.resolve())]
    assert captured["plan"]["scope"]["selectors"] == {
        "instance": "ads2027",
        "version": "2027",
        "profile": "de",
    }
    assert captured["expected_source_fingerprint"] == "a" * 64
    assert captured["continued"]["identity"]["workspace"] == str(output)
    assert captured["continued"]["source_fingerprint"] == "b" * 64
    assert result.result["bridge"]["continuation_context"].startswith("EDA_CONTEXT:v2:")
    assert result.result["bridge"]["continuation_state"] == {
        "schema_version": "ads-continuation-state/v1",
        "state": "content-bound",
    }


def test_native_continuation_context_rejects_another_operation(monkeypatch):
    from eda_bridge_runtime import RequestEnvelope

    monkeypatch.setattr(
        runtime_adapter,
        "continuation_reference",
        lambda _target, _payload: "ctx_" + "1" * 20,
    )
    request = RequestEnvelope(
        purpose="Do not broaden a continuation Context",
        target={"eda": "keysight-ads"},
        operation="session.status",
        payload={"mutating": False},
    )
    with pytest.raises(ValueError, match="bound to native.batch"):
        runtime_adapter._AdsAdapterBase().execute(
            request, SimpleNamespace(emit=lambda *_args, **_kwargs: None)
        )


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
    monkeypatch.setattr(
        runtime_adapter,
        "select_instance",
        lambda _value: SimpleNamespace(year=2026, product_version="2026"),
    )
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
    monkeypatch.setattr(
        runtime_adapter,
        "select_instance",
        lambda _value: SimpleNamespace(year=2026, product_version="2026"),
    )
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
        return {
            "status": "ready",
            "slot": kwargs["slot"],
            "ownership": "agent-owned",
            "session": {
                "slot": kwargs["slot"],
                "managed_session_id": "managed-one",
            },
        }

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
    assert result.result["resource"] == {
        "protocol": "eda-runtime.resource/v1",
        "resource_id": "managed-one",
        "kind": "ads-session",
        "ownership": "runtime-owned",
        "state": "active",
        "release_operation": "session.shutdown",
        "release_payload": {"slot": "greenfield"},
    }
