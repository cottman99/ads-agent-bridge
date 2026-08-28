"""Adapter between the generic EDA runtime and a live ADS bridge session."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import __version__
from .bridge_client import request as bridge_request


def _runtime_imports():
    try:
        from eda_bridge_runtime import Adapter, AdapterResult, ExecutionLedger, Runtime
        from eda_bridge_runtime.transport import serve_json_lines
    except ImportError as exc:
        raise RuntimeError(
            "EDA Runtime support is not installed. Install ads-agent-bridge[runtime]."
        ) from exc
    return Adapter, AdapterResult, ExecutionLedger, Runtime, serve_json_lines


def default_ledger_path() -> Path:
    from .bridge_client import runtime_dir

    return runtime_dir() / "execution-ledger.sqlite3"


class _AdsAdapterBase:
    name = "ads-agent-bridge"
    version = __version__

    def __init__(self) -> None:
        self._capability_cache: dict[
            tuple[str | None, str], tuple[float, dict[str, Any]]
        ] = {}

    def capabilities(self) -> dict[str, Any]:
        return {
            "eda": "keysight-ads",
            "session_model": "interactive",
            "operations": "reported-by-live-bridge",
            "escape_lanes": ["typed", "bounded-ui", "unsafe-native-opt-in"],
        }

    def _live_capabilities(self, slot: str | None, profile: str) -> dict[str, Any]:
        key = (slot, profile)
        cached = self._capability_cache.get(key)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        response = bridge_request("capabilities", {}, slot, profile, timeout=5)
        if not response.get("ok") or not isinstance(response.get("result"), dict):
            raise RuntimeError(
                response.get("error") or "ADS capability discovery failed"
            )
        result = response["result"]
        self._capability_cache[key] = (time.monotonic(), result)
        return result

    @staticmethod
    def _descriptor(capabilities: dict[str, Any], operation: str) -> dict[str, Any]:
        for descriptor in capabilities.get("descriptors", []):
            if descriptor.get("id") == operation:
                return descriptor
        raise ValueError(f"ADS operation is not advertised: {operation}")

    def execute(self, request, context):
        _, AdapterResult, _, _, _ = _runtime_imports()
        slot = request.target.get("slot")
        profile = str(request.target.get("profile") or "de")
        if profile not in {"de", "dds"}:
            raise ValueError("ADS profile must be de or dds")
        capabilities_started = time.monotonic()
        descriptor = self._descriptor(
            self._live_capabilities(str(slot) if slot else None, profile),
            request.operation,
        )
        capability_ms = (time.monotonic() - capabilities_started) * 1000
        safety = descriptor.get("safety")
        state = descriptor.get("state") or {}
        if not state.get("available") or not state.get("healthy"):
            raise RuntimeError(
                f"ADS operation is not currently usable: {state.get('reason') or 'unavailable'}"
            )
        if (
            safety == "unsafe"
            and request.payload.get("escape_lane") != "unsafe-native-opt-in"
        ):
            raise ValueError(
                "unsafe ADS operation requires explicit unsafe-native-opt-in escape lane"
            )
        advertised_mutation = bool(descriptor.get("mutates"))
        if advertised_mutation != request.is_mutating:
            raise ValueError(
                "request mutation flag does not match the live ADS capability descriptor"
            )
        args = request.payload.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("ADS operation args must be an object")
        context.emit(
            "ads.capability.resolved",
            {
                "operation": request.operation,
                "safety": safety,
                "mutates": advertised_mutation,
                "capability_lookup_ms": round(capability_ms, 3),
            },
        )
        execute_started = time.monotonic()
        response = bridge_request(
            request.operation,
            args,
            str(slot) if slot else None,
            profile,
            timeout=float(request.payload.get("timeout_seconds", 120)),
        )
        execute_ms = (time.monotonic() - execute_started) * 1000
        context.emit(
            "ads.bridge.completed",
            {
                "ok": bool(response.get("ok")),
                "operation": request.operation,
                "bridge_round_trip_ms": round(execute_ms, 3),
            },
        )
        if not response.get("ok"):
            raise RuntimeError(
                str(response.get("error") or "ADS bridge operation failed")
            )
        public_response = dict(response)
        public_response.pop("session", None)
        return AdapterResult(
            status="passed",
            result={
                "bridge": public_response,
                "target": {"slot": slot, "profile": profile},
                "timing": {
                    "capability_lookup_ms": round(capability_ms, 3),
                    "bridge_round_trip_ms": round(execute_ms, 3),
                },
            },
        )


def build_runtime(ledger_path: str | Path):
    Adapter, _, ExecutionLedger, Runtime, _ = _runtime_imports()

    class AdsAdapter(_AdsAdapterBase, Adapter):
        pass

    runtime = Runtime(ExecutionLedger(ledger_path))
    runtime.register("keysight-ads", AdsAdapter())
    return runtime


def serve(ledger_path: str | Path, input_stream, output_stream) -> None:
    _, _, _, _, serve_json_lines = _runtime_imports()
    runtime = build_runtime(ledger_path)
    serve_json_lines(input_stream, output_stream, runtime.execute)
