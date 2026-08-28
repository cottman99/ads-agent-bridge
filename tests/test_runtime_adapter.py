import io
import json

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
