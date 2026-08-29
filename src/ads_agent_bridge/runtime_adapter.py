"""Adapter between the generic EDA runtime and a live ADS bridge session."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import __version__
from .bridge_client import request as bridge_request
from .config import select_instance
from .design_plan import execute_design_plan
from .docs_kb import get_document
from .docs_kb import query as query_docs
from .docs_kb import status as docs_status
from .momentum import run_generated_momentum
from .session_manager import launch as launch_session
from .session_manager import shutdown as shutdown_session
from .session_manager import status as session_status
from .workspace_create import create_workspace, resolve_context


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

    def capabilities(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        target = target or {}
        slot = target.get("slot")
        profile = str(target.get("profile") or "de")
        live_error = None
        try:
            live = self._live_capabilities(str(slot) if slot else None, profile)
        except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
            live = {"descriptors": []}
            live_error = str(exc)
        descriptors = list(live.get("descriptors") or [])
        descriptors.extend(
            [
                {
                    "id": "docs.status",
                    "category": "documentation",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {"required": [], "optional": ["instance"]},
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "docs.query",
                    "category": "documentation",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": ["query"],
                        "optional": ["instance", "domains", "limit"],
                    },
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "docs.get",
                    "category": "documentation",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": ["source_ref"],
                        "optional": ["instance", "focus", "max_chars"],
                    },
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "workspace.create",
                    "category": "workspace",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "moderate",
                    "requires_context": False,
                    "returns_context": True,
                    "input_schema": {
                        "required": ["workspace"],
                        "optional": [
                            "library",
                            "cell",
                            "instance",
                            "display",
                            "timeout_seconds",
                        ],
                    },
                    "state": {"available": profile == "de", "healthy": profile == "de"},
                },
                {
                    "id": "design.apply",
                    "category": "design",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "slow",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": ["plan"],
                        "optional": ["instance", "display", "timeout_seconds"],
                    },
                    "state": {"available": profile == "de", "healthy": profile == "de"},
                },
                {
                    "id": "momentum.run_generated",
                    "category": "simulation",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "slow",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": [
                            "source_directory",
                            "output_directory",
                            "project",
                        ],
                        "optional": [
                            "instance",
                            "display",
                            "source_fingerprint",
                            "timeout_seconds",
                        ],
                    },
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "session.launch",
                    "category": "lifecycle",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "slow",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": [],
                        "optional": [
                            "workspace",
                            "instance",
                            "slot",
                            "display",
                            "timeout_seconds",
                            "reuse_existing",
                        ],
                        "requires_one_of": ["workspace", "EDA_CONTEXT:workspace"],
                    },
                    "state": {"available": profile == "de", "healthy": profile == "de"},
                },
                {
                    "id": "session.status",
                    "category": "lifecycle",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {"required": [], "optional": ["slot"]},
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "session.shutdown",
                    "category": "lifecycle",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "moderate",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": [],
                        "optional": ["slot", "timeout_seconds"],
                        "requires_one_of": ["slot", "EDA_CONTEXT:workspace"],
                    },
                    "state": {"available": True, "healthy": True},
                },
            ]
        )
        operations_by_id = {str(item.get("id")): item for item in descriptors}
        from eda_bridge_runtime import stable_origin_id

        return {
            "eda": "keysight-ads",
            "origin_id": stable_origin_id("keysight-ads"),
            "execution_host_role": "eda-worker",
            "run_model": "synchronous",
            "session_model": "interactive",
            "operations": list(operations_by_id.values()),
            "escape_lanes": ["typed", "bounded-ui", "unsafe-native-opt-in"],
            "target": {"slot": slot, "profile": profile},
            "live_bridge": {
                "available": live_error is None,
                "reason": live_error,
            },
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
        context_id = request.target.get("context_id")
        if context_id:
            from eda_bridge_runtime import EDAContext, RequestEnvelope

            stored = resolve_context(str(context_id))
            if request.target.get("context"):
                decoded = EDAContext.decode(str(request.target["context"]))
                if stored.get("generation") != decoded.generation:
                    raise ValueError("ADS Runtime context is stale")
            data = request.to_dict()
            data["target"] = {
                **stored["target"],
                **{
                    key: value
                    for key, value in request.target.items()
                    if key != "context"
                },
                "eda": "keysight-ads",
            }
            request = RequestEnvelope.from_dict(data)
        slot = request.target.get("slot")
        profile = str(request.target.get("profile") or "de")
        if profile not in {"de", "dds"}:
            raise ValueError("ADS profile must be de or dds")
        if request.operation.startswith("docs."):
            if request.is_mutating:
                raise ValueError(
                    "ADS documentation operations require payload.mutating=false"
                )
            instance = select_instance(
                request.payload.get("instance") or request.target.get("instance")
            )
            if request.operation == "docs.status":
                result = docs_status(instance)
            elif request.operation == "docs.query":
                result = query_docs(
                    instance,
                    str(request.payload.get("query") or ""),
                    int(request.payload.get("limit", 6)),
                    domains=list(request.payload.get("domains") or []),
                )
            else:
                result = get_document(
                    instance,
                    str(request.payload.get("source_ref") or ""),
                    focus=request.payload.get("focus"),
                    max_chars=int(request.payload.get("max_chars", 4000)),
                )
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "workspace.create":
            if not request.is_mutating:
                raise ValueError("workspace.create requires payload.mutating=true")
            workspace = request.payload.get("workspace") or request.target.get(
                "workspace"
            )
            if not workspace:
                raise ValueError("workspace.create requires workspace")
            started = time.monotonic()
            result = create_workspace(
                workspace=workspace,
                library=str(request.payload.get("library") or "AgentWorkspace_lib"),
                cell=str(request.payload.get("cell") or "Main"),
                instance_id=request.payload.get("instance")
                or request.target.get("instance"),
                slot=str(slot) if slot else None,
                profile=profile,
                connection_id=request.target.get("connection_id"),
                expected_display=request.payload.get("display")
                or request.target.get("display"),
                timeout=float(request.payload.get("timeout_seconds", 120)),
            )
            context.emit(
                "ads.workspace.created",
                {
                    "status": result["status"],
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "design.apply":
            if not request.is_mutating:
                raise ValueError("design.apply requires payload.mutating=true")
            if profile != "de":
                raise ValueError("design.apply requires the ADS DE profile")
            plan = request.payload.get("plan")
            if not isinstance(plan, dict):
                raise TypeError("design.apply requires a structured plan object")
            plan = dict(plan)
            selected_instance = request.payload.get("instance") or request.target.get(
                "instance"
            )
            if selected_instance and "instance" not in plan:
                plan["instance"] = selected_instance
            result = execute_design_plan(
                plan,
                expected_display=request.payload.get("display")
                or request.target.get("display"),
                timeout=float(request.payload.get("timeout_seconds", 180)),
            )
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "momentum.run_generated":
            if not request.is_mutating:
                raise ValueError(
                    "momentum.run_generated requires payload.mutating=true"
                )
            result = run_generated_momentum(
                source_directory=request.payload.get("source_directory", ""),
                output_directory=request.payload.get("output_directory", ""),
                project=str(request.payload.get("project") or ""),
                instance_id=request.payload.get("instance")
                or request.target.get("instance"),
                expected_display=request.payload.get("display")
                or request.target.get("display"),
                source_fingerprint=request.payload.get("source_fingerprint"),
                timeout=float(request.payload.get("timeout_seconds", 600)),
            )
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "session.status":
            if request.is_mutating:
                raise ValueError("session.status requires payload.mutating=false")
            result = session_status(str(slot) if slot else None)
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "session.shutdown":
            if not request.is_mutating:
                raise ValueError("session.shutdown requires payload.mutating=true")
            result = shutdown_session(
                str(slot) if slot else None,
                wait_seconds=float(request.payload.get("timeout_seconds", 30)),
            )
            if result.get("status") != "exited":
                raise RuntimeError(
                    f"ADS session shutdown did not complete: {result.get('status')}"
                )
            return AdapterResult(status="passed", result={"bridge": result})
        if request.operation == "session.launch":
            if not request.is_mutating:
                raise ValueError("session.launch requires payload.mutating=true")
            workspace = request.payload.get("workspace") or request.target.get(
                "workspace"
            )
            if not workspace:
                raise ValueError(
                    "session.launch requires workspace or a workspace context"
                )
            result = launch_session(
                request.payload.get("instance") or request.target.get("instance"),
                Path(str(workspace)),
                slot=str(slot) if slot else None,
                display=request.payload.get("display") or request.target.get("display"),
                wait_seconds=float(request.payload.get("timeout_seconds", 120)),
                reuse_existing=bool(request.payload.get("reuse_existing")),
            )
            status = str(result.get("status") or "")
            if status not in {"ready", "running", "reused"}:
                raise RuntimeError(f"ADS session launch did not become ready: {status}")
            return AdapterResult(status="passed", result={"bridge": result})
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
            raise TypeError("ADS operation args must be an object")
        if request.operation == "open_workspace" and "workspace" not in args:
            workspace = request.target.get("workspace")
            if workspace:
                args = {**args, "workspace": workspace}
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
