"""Adapter between the generic EDA runtime and a live ADS bridge session."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from eda_bridge_runtime import native_program_capability_contract

from . import __version__
from .bridge_client import request as bridge_request
from .circuit_simulation import execute_simulation_plan
from .config import select_instance
from .continuation_context import (
    continuation_ref,
    continuation_reference,
    create_continuation_context,
    materialize_native_program_plan,
    resolve_continuation_context,
)
from .dds_report import execute_dds_plan
from .design_plan import execute_design_plan
from .docs_kb import get_document
from .docs_kb import query as query_docs
from .docs_kb import status as docs_status
from .experience_shortcuts import (
    compiled_shortcut_binding,
    get_asset,
    list_assets,
    shortcut_receipt,
    shortcut_state,
    validate_shortcut,
)
from .momentum import run_generated_momentum
from .native_program import execute_native_program
from .session_manager import launch as launch_session
from .session_manager import shutdown as shutdown_session
from .session_manager import status as session_status
from .workspace_create import create_workspace, resolve_context

RESOURCE_PROTOCOL = "eda-runtime.resource/v1"
_CERTIFIED_WORKFLOWS = {
    "design.apply",
    "circuit.simulate",
    "dds.create",
    "momentum.run_generated",
}


def _launched_session_resource(result: dict[str, Any]) -> dict[str, Any] | None:
    session = result.get("session")
    session = session if isinstance(session, dict) else {}
    resource_id = str(session.get("managed_session_id") or "").strip()
    slot = str(session.get("slot") or result.get("slot") or "").strip()
    if result.get("ownership") != "agent-owned" or not resource_id or not slot:
        return None
    return {
        "protocol": RESOURCE_PROTOCOL,
        "resource_id": resource_id,
        "kind": "ads-session",
        "ownership": "runtime-owned",
        "state": "active",
        "release_operation": "session.shutdown",
        "release_payload": {"slot": slot},
    }


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


_OPERATIONS = {
    "docs.status": {"handler": "_execute_docs_status", "mutates": False},
    "docs.query": {"handler": "_execute_docs_status", "mutates": False},
    "docs.get": {"handler": "_execute_docs_status", "mutates": False},
    "docs.symbol": {"handler": "_execute_docs_status", "mutates": False},
    "workspace.create": {"handler": "_execute_workspace_create", "mutates": True},
    "experience.list": {"handler": "_execute_experience_list", "mutates": False},
    "experience.get": {"handler": "_execute_experience_get", "mutates": False},
    "native.execute": {"handler": "_execute_native_execute", "mutates": True},
    "design.apply": {"handler": "_execute_design_apply", "mutates": True},
    "circuit.simulate": {"handler": "_execute_circuit_simulate", "mutates": True},
    "dds.create": {"handler": "_execute_dds_create", "mutates": True},
    "momentum.run_generated": {
        "handler": "_execute_momentum_run_generated",
        "mutates": True,
    },
    "session.status": {"handler": "_execute_session_status", "mutates": False},
    "session.shutdown": {"handler": "_execute_session_shutdown", "mutates": True},
    "session.launch": {"handler": "_execute_session_launch", "mutates": True},
}


class _AdsAdapterBase:
    @staticmethod
    def resource_keys(request):
        from eda_bridge_runtime import EDAContext, RequestEnvelope
        from eda_bridge_runtime.resources import resource_keys

        target = dict(request.target)
        continuation = continuation_reference(target, request.payload)
        if continuation:
            target.update(resolve_continuation_context(continuation)["identity"])
        elif target.get("context"):
            decoded = EDAContext.decode(target["context"])
            target.update(decoded.target.get("identity") or decoded.target)
            target["slot"] = decoded.locator.get("slot") or decoded.session.get("slot")
        elif target.get("context_id"):
            target.update(resolve_context(target["context_id"])["target"])
        data = request.to_dict()
        data["target"] = target
        keys = list(resource_keys(RequestEnvelope.from_dict(data)))
        slot = target.get("slot") or request.payload.get("slot")
        if slot:
            keys.append("keysight-ads:session:" + str(slot))
        return tuple(keys)

    name = "ads-agent-bridge"
    version = __version__

    def __init__(self) -> None:
        self._capability_cache: dict[tuple[str | None, str], tuple[float, dict[str, Any]]] = {}

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
        descriptors = [
            item
            for item in live.get("descriptors") or []
            if item.get("id") != "native.execute"
            and self._operation_definition(str(item.get("id"))) is not None
        ]
        descriptors.extend(
            [
                {
                    "id": "docs.symbol",
                    "category": "documentation",
                    "safety": "safe",
                    "mutates": False,
                    "requires_context": False,
                    "input_schema": {"required": ["query"], "optional": ["instance", "limit"]},
                    "state": {"available": True, "healthy": True},
                },
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
                        "domains": ["ads", "ael", "python", "dds"],
                        "limit": [1, 20],
                        "domain_guidance": (
                            "domains are explicit filters only; omit them for corpus-wide "
                            "capability checks because Python automation may be documented "
                            "in an ads guide"
                        ),
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
                        "source_ref": "use only a source_ref returned by docs.query",
                        "max_chars": [200, 12000],
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
                    "id": "experience.list",
                    "category": "experience",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": [],
                        "optional": [
                            "intents",
                            "tags",
                            "version",
                            "profile",
                            "capability",
                        ],
                        "filter_semantics": "exact metadata match",
                        "applicability_filters": {
                            "version": "ADS major version such as 2027",
                            "profile": ["de", "dds"],
                            "capability": "advertised operation id such as native.execute",
                        },
                        "discovery": (
                            "omit intents and tags to list the compact asset index "
                            "when exact metadata values are unknown"
                        ),
                    },
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "experience.get",
                    "category": "experience",
                    "safety": "safe",
                    "mutates": False,
                    "latency_class": "fast",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "one_of": [
                            {"required": ["asset_id"]},
                            {"required": ["version", "profile", "capability"]},
                        ],
                        "optional": ["max_chars"],
                        "normal_use": (
                            "when exact version, profile, and capability are known, "
                            "resolve and read the unique matching asset in this call"
                        ),
                        "official_refs": (
                            "provenance labels, not docs.get source_ref values; query docs "
                            "by the referenced topic"
                        ),
                    },
                    "state": {"available": True, "healthy": True},
                },
                {
                    "id": "native.execute",
                    "category": "native-execution",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "slow",
                    "requires_context": False,
                    "returns_context": True,
                    "input_schema": {
                        "required": ["plan"],
                        "optional": ["continuation_context", "redact_paths"],
                        "runtime_request_required_for_mutation": [
                            "purpose",
                            "expected_effect",
                            "idempotency_key",
                        ],
                        "plan_schema": "eda.native-program/v1",
                        "plan_contract": native_program_capability_contract(),
                        "ads_contract": {
                            "runtime_by_profile": {
                                "de": "ads.python.de",
                                "dds": "ads.python.dds",
                            },
                            "resource_kind": "ads-workspace",
                            "selectors": ["instance", "version", "profile"],
                            "program_signature": "def run(api, context)",
                            "validation_signature": "def validate(api, context)",
                            "program_api": {
                                "type": "object",
                                "members": ["api.de", "api.db"],
                            },
                            "program_context": {
                                "type": "dict",
                                "access": 'context["<key>"]',
                                "keys": [
                                    "workspace",
                                    "profile",
                                    "version",
                                    "artifact_root",
                                    "effect",
                                ],
                                "workspace": (
                                    "staged workspace path used for all workspace mutations"
                                ),
                                "artifact_root": (
                                    "pre-created only when scope.artifacts is non-empty"
                                ),
                            },
                            "validation_return": {
                                "required": {"status": "passed"},
                                "purpose": "prove persisted staged output in a fresh process",
                            },
                            "python_environment": "normal builtins, standard library and installed dependencies",
                            "modes": ["live", "background"],
                            "staged_write_paths": {
                                "without_artifacts": ["absolute distinct sibling output workspace"],
                                "with_artifacts": [
                                    "absolute distinct sibling output workspace",
                                    "absolute final artifact directory",
                                ],
                                "scope_artifacts": (
                                    'relative file paths below context["artifact_root"]'
                                ),
                                "never": "library names or relative write_paths",
                            },
                        },
                        "continuation_schema": "eda-context/v2",
                        "mutate_template": {
                            "payload": {
                                "continuation_context": "<continuation_ref>",
                                "plan": {
                                    "schema_version": "eda.native-program/v1",
                                    "mode": "background",
                                    "runtime": "ads.python.de",
                                    "effect": "mutate",
                                    "program": {
                                        "language": "python",
                                        "source": "def run(api, context): ...",
                                    },
                                    "scope": {
                                        "resource_kind": "ads-workspace",
                                        "selectors": {},
                                        "read_paths": [],
                                        "write_paths": [
                                            "<absolute sibling output workspace>",
                                            "<absolute artifact directory>",
                                        ],
                                        "artifacts": ["<relative artifact file>"],
                                    },
                                    "transaction": {
                                        "strategy": "adapter_staging",
                                        "source_fingerprints": {},
                                        "fresh_reopen": True,
                                        "promotion": "on_validation",
                                    },
                                    "validation": {
                                        "program": {
                                            "language": "python",
                                            "source": "def validate(api, context): ...",
                                        },
                                        "required_artifacts": ["<same relative artifact file>"],
                                    },
                                    "limits": {
                                        "timeout_seconds": 300,
                                        "max_output_bytes": 1048576,
                                    },
                                },
                            },
                            "runtime_fields": {
                                "purpose": "<concise engineering reason>",
                                "expected_effect": "<declared mutation outcome>",
                                "idempotency_key": "<task-unique stable key>",
                                "wait": {
                                    "timeout_ms": 300000,
                                    "poll_interval_ms": 1000,
                                },
                            },
                            "without_artifacts": (
                                "use one write_path, artifacts [], and required_artifacts []"
                            ),
                        },
                        "continuation_usage": {
                            "normal_greenfield_flow": (
                                "pass the short response continuation_ref from workspace.create "
                                "as payload.continuation_context to the first native.execute"
                            ),
                            "agent_supplies": (
                                "scope.write_paths, scope.artifacts, program, validation, "
                                "limits, purpose, expected_effect, and idempotency_key"
                            ),
                            "runtime_materializes": [
                                "scope.selectors.instance",
                                "scope.selectors.version",
                                "scope.selectors.profile",
                                "scope.read_paths",
                                "transaction.source_fingerprints",
                            ],
                            "opaque": True,
                            "long_token_fallback": (
                                "continuation_context remains available for portable EDA_CONTEXT "
                                "handoff; do not make an Agent recopy it when continuation_ref exists"
                            ),
                        },
                        "context_materializes": [
                            "scope.selectors.instance",
                            "scope.selectors.version",
                            "scope.selectors.profile",
                            "scope.read_paths",
                            "transaction.source_fingerprints",
                        ],
                    },
                    "state": {"available": True, "healthy": True},
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
                    "id": "circuit.simulate",
                    "category": "simulation",
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
                    "id": "dds.create",
                    "category": "reporting",
                    "safety": "bounded",
                    "mutates": True,
                    "latency_class": "moderate",
                    "requires_context": False,
                    "returns_context": False,
                    "input_schema": {
                        "required": ["plan"],
                        "optional": ["instance", "display", "timeout_seconds"],
                    },
                    "state": {"available": True, "healthy": True},
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
                    "resource_lifecycle": {
                        "creates_when": "a new agent-owned ADS session is launched",
                        "kind": "ads-session",
                        "release_operation": "session.shutdown",
                    },
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
        try:
            selected = select_instance(target.get("instance"))
            selected_version = str(selected.year or selected.product_version)
            python_ready = bool(selected.python_executable)
        except (OSError, TypeError, ValueError):
            selected_version = ""
            python_ready = False
        for operation, descriptor in operations_by_id.items():
            definition = self._operation_definition(operation)
            if definition:
                descriptor["mutates"] = bool(definition["mutates"])
            if operation in _CERTIFIED_WORKFLOWS:
                descriptor["operation_class"] = "certified-workflow"
                descriptor["compiled_shortcut"] = compiled_shortcut_binding(operation)
                shortcut_profile = descriptor["compiled_shortcut"]["applies_to"]["profiles"][0]
                state = shortcut_state(
                    operation, version=selected_version, profile=shortcut_profile
                )
                if not python_ready:
                    state = {
                        "available": False,
                        "healthy": False,
                        "reason": "selected ADS Python runtime is unavailable",
                    }
                descriptor["state"] = state
            elif operation == "native.execute":
                descriptor["operation_class"] = "generic-native-execution"
                if operation == "native.execute":
                    descriptor["state"] = {
                        "available": python_ready,
                        "healthy": python_ready,
                        **(
                            {}
                            if python_ready
                            else {"reason": "selected ADS Python runtime is unavailable"}
                        ),
                    }
            elif operation in {"design.live_patch", "design.live_finalize"}:
                descriptor["operation_class"] = "typed-live-edit"
                schema = dict(descriptor.get("input_schema") or {})
                schema["required"] = [
                    field for field in schema.get("required", []) if field != "design"
                ]
                schema["optional"] = [
                    *[field for field in schema.get("optional", []) if field != "design"],
                    "design",
                ]
                schema["requires_one_of"] = ["design", "EDA_CONTEXT:design"]
                descriptor["input_schema"] = schema
            elif operation in {"dds_readback", "ael_workspace_path"}:
                descriptor["operation_class"] = "acceptance-probe"
            else:
                descriptor["operation_class"] = "bridge-infrastructure"
            schema = descriptor.get("input_schema")
            if isinstance(schema, dict):
                fields = set(schema.get("required") or []) | set(schema.get("optional") or [])
                descriptions = dict(schema.get("field_descriptions") or {})
                if "instance" in fields:
                    descriptions["instance"] = (
                        "ADS installation selector (instance_id); never a schematic, "
                        "layout, view, or component instance"
                    )
                if "workspace" in fields:
                    descriptions["workspace"] = "Exact ADS workspace filesystem path"
                if "design" in fields:
                    descriptions["design"] = "Exact ADS Library:Cell:View design identity"
                if descriptions:
                    schema["field_descriptions"] = descriptions
                    descriptor["input_schema"] = schema
        from eda_bridge_runtime import stable_origin_id

        return {
            "eda": "keysight-ads",
            "origin_id": stable_origin_id("keysight-ads"),
            "execution_host_role": "eda-worker",
            "run_model": "synchronous",
            "session_model": "interactive",
            "operations": list(operations_by_id.values()),
            "execution": "native.execute",
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
            raise RuntimeError(response.get("error") or "ADS capability discovery failed")
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
        encoded_context = request.target.get("context")
        decoded_context = None
        native_continuation = False
        if encoded_context:
            from eda_bridge_runtime import EDAContext

            decoded_context = EDAContext.decode(str(encoded_context))
            native_continuation = decoded_context.target.get("binding") == ("private-host-record")
        context_id = request.target.get("context_id") or (
            decoded_context.locator.get("context_id") if decoded_context is not None else None
        )
        if context_id and not native_continuation:
            from eda_bridge_runtime import RequestEnvelope

            live_context = bool(
                decoded_context is not None
                and isinstance(decoded_context.target, dict)
                and decoded_context.target.get("kind")
            )
            if live_context:
                live_slot = str(
                    decoded_context.locator.get("slot") or decoded_context.session.get("slot") or ""
                )
                live_profile = str(
                    decoded_context.locator.get("profile")
                    or decoded_context.session.get("profile")
                    or "de"
                )
                if not live_slot:
                    raise ValueError("ADS live Context has no session slot")
                response = bridge_request(
                    "context_get",
                    {"context": str(context_id)},
                    live_slot,
                    live_profile,
                    timeout=30.0,
                )
                if not response.get("ok"):
                    raise ValueError(f"ADS live Context is unavailable: {response.get('error')}")
                envelope = response.get("result")
                if not isinstance(envelope, dict):
                    raise ValueError("ADS live Context record is invalid")
                if int(envelope.get("freshness", {}).get("generation") or 0) != int(
                    decoded_context.generation
                ):
                    raise ValueError("ADS live Context is stale; copy it again from ADS")
                if envelope.get("target") != decoded_context.target:
                    raise ValueError("ADS live Context target identity changed")
                target = {
                    **envelope["target"],
                    "slot": live_slot,
                    "profile": live_profile,
                    "context_id": str(context_id),
                    "display": decoded_context.session.get("display"),
                }
            else:
                stored = resolve_context(str(context_id))
                if decoded_context is not None and stored.get("generation") != (
                    decoded_context.generation
                ):
                    raise ValueError("ADS Runtime context is stale")
                target = {
                    **stored["target"],
                    **{key: value for key, value in request.target.items() if key != "context"},
                }
            data = request.to_dict()
            data["target"] = {
                **target,
                "eda": "keysight-ads",
            }
            request = RequestEnvelope.from_dict(data)
        continuation = continuation_reference(request.target, request.payload)
        if continuation and request.operation != "native.execute":
            raise ValueError("ADS native continuation Context is bound to native.execute")
        continuation_record = resolve_continuation_context(continuation) if continuation else None
        target_slot = request.target.get("slot")
        payload_slot = request.payload.get("slot")
        if target_slot and payload_slot and str(target_slot) != str(payload_slot):
            raise ValueError("ADS slot conflicts between target.slot and payload.slot")
        slot = target_slot or payload_slot
        if slot is None and continuation_record is not None:
            slot = continuation_record["identity"].get("slot")
        profile = str(
            request.target.get("profile")
            or (
                continuation_record["identity"].get("profile")
                if continuation_record is not None
                else None
            )
            or "de"
        )
        if profile not in {"de", "dds"}:
            raise ValueError("ADS profile must be de or dds")
        definition = self._operation_definition(request.operation)
        if definition is None:
            raise ValueError(f"Unsupported ADS operation: {request.operation}")
        return getattr(self, definition["handler"])(
            request,
            context,
            slot,
            profile,
            continuation_record,
            decoded_context,
            context_id,
            native_continuation,
        )

    @staticmethod
    def _operation_definition(operation):
        if operation in _OPERATIONS:
            return _OPERATIONS[operation]
        from .addon.AdsAgentBridge.contracts import capability_specs

        spec = next((item for item in capability_specs() if item["id"] == operation), None)
        return {**spec, "handler": "_execute_live"} if spec else None

    def requires_admission(self, request):
        definition = self._operation_definition(request.operation)
        return definition is None or bool(definition["mutates"])

    def _execute_docs_status(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if request.is_mutating:
            raise ValueError("ADS documentation operations require payload.mutating=false")
        instance = select_instance(
            request.payload.get("instance") or request.target.get("instance")
        )
        if request.operation == "docs.symbol":
            from .sdk_docs import describe

            result = describe(
                instance,
                str(request.payload.get("query") or ""),
                int(request.payload.get("limit", 6)),
            )
        elif request.operation == "docs.status":
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

    def _execute_workspace_create(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("workspace.create requires payload.mutating=true")
        workspace = request.payload.get("workspace") or request.target.get("workspace")
        if not workspace:
            raise ValueError("workspace.create requires workspace")
        started = time.monotonic()
        result = create_workspace(
            workspace=workspace,
            library=str(request.payload.get("library") or "AgentWorkspace_lib"),
            cell=str(request.payload.get("cell") or "Main"),
            instance_id=request.payload.get("instance") or request.target.get("instance"),
            slot=str(slot) if slot else None,
            profile=profile,
            connection_id=request.target.get("connection_id"),
            expected_display=request.payload.get("display") or request.target.get("display"),
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

    def _execute_experience_list(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if request.is_mutating:
            raise ValueError("experience.list requires payload.mutating=false")
        result = list_assets(
            intents=list(request.payload.get("intents") or []),
            tags=list(request.payload.get("tags") or []),
            version=(str(request.payload["version"]) if request.payload.get("version") else None),
            profile=(str(request.payload["profile"]) if request.payload.get("profile") else None),
            capability=(
                str(request.payload["capability"]) if request.payload.get("capability") else None
            ),
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_experience_get(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if request.is_mutating:
            raise ValueError("experience.get requires payload.mutating=false")
        result = get_asset(
            (str(request.payload["asset_id"]) if request.payload.get("asset_id") else None),
            version=(str(request.payload["version"]) if request.payload.get("version") else None),
            profile=(str(request.payload["profile"]) if request.payload.get("profile") else None),
            capability=(
                str(request.payload["capability"]) if request.payload.get("capability") else None
            ),
            max_chars=int(request.payload.get("max_chars", 8000)),
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_native_execute(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        plan = request.payload.get("plan")
        if not isinstance(plan, dict):
            raise TypeError("native.execute requires a governed native program plan")
        if plan.get("mode") == "live":
            from eda_bridge_runtime.errors import ExecutionError

            from .native_program import _instance_version_selectors

            if decoded_context is None or native_continuation or not context_id:
                raise ExecutionError(
                    "session_unavailable",
                    "Capture the exact ADS session context for live execution",
                )
            selectors = plan.get("scope", {}).get("selectors", {})
            selected = select_instance(selectors.get("instance"))
            if str(selectors.get("version", "")) not in _instance_version_selectors(selected):
                raise ExecutionError(
                    "version_mismatch",
                    "The requested ADS version differs from the selected installation",
                )
            response = bridge_request(
                "native.execute",
                {
                    "plan": plan,
                    "context": str(context_id),
                    "generation": decoded_context.generation,
                    "purpose": request.purpose,
                    "admission": context.admission,
                    "install_root": selected.install_root,
                },
                str(slot) if slot else None,
                profile,
                timeout=float(plan.get("limits", {}).get("timeout_seconds", 120)) + 5,
            )
            if not response.get("ok"):
                failure = response.get("failure") or {}
                raise ExecutionError(
                    failure.get("code", "execution_failed"),
                    response.get("error", "ADS execution failed"),
                    phase=failure.get("phase", "execution"),
                    evidence=failure.get("evidence"),
                    uncertain=bool(failure.get("execution_uncertain")),
                )
            return AdapterResult(status="passed", result={"bridge": response["result"]})
        expected_source_fingerprint = None
        if continuation_record is not None:
            plan, expected_source_fingerprint = materialize_native_program_plan(
                plan,
                record=continuation_record,
                target=request.target,
                payload=request.payload,
            )
        result = execute_native_program(
            plan,
            redact_paths=bool(request.payload.get("redact_paths", True)),
            expected_source_fingerprint=expected_source_fingerprint,
            admission=context.admission,
        )
        source_path = (
            plan["scope"]["write_paths"][0]
            if result.get("effect") == "mutate"
            else plan["scope"]["read_paths"][0]
        )
        source_fingerprint = (
            result.get("output_fingerprint")
            if result.get("effect") == "mutate"
            else result.get("source_fingerprint")
        )
        selected = select_instance(plan["scope"]["selectors"].get("instance"))
        continuation_token, continuation_state = create_continuation_context(
            identity={
                "connection_id": request.target.get("connection_id"),
                "slot": slot,
                "profile": plan["scope"]["selectors"]["profile"],
                "instance": selected.instance_id,
                "version": str(selected.year or selected.product_version),
                "workspace": source_path,
                "design": request.target.get("design") or request.target.get("top_design"),
            },
            source_fingerprint=str(source_fingerprint or ""),
        )
        result["continuation_context"] = continuation_token
        result["continuation_ref"] = continuation_ref(continuation_token)
        result["continuation_state"] = continuation_state
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_design_apply(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("design.apply requires payload.mutating=true")
        if profile != "de":
            raise ValueError("design.apply requires the ADS DE profile")
        plan = request.payload.get("plan")
        if not isinstance(plan, dict):
            raise TypeError("design.apply requires a structured plan object")
        plan = dict(plan)
        selected_instance = request.payload.get("instance") or request.target.get("instance")
        if selected_instance and "instance" not in plan:
            plan["instance"] = selected_instance
        instance = select_instance(selected_instance)
        version = str(instance.year or instance.product_version)
        validate_shortcut(request.operation, version=version, profile="de")
        result = execute_design_plan(
            plan,
            expected_display=request.payload.get("display") or request.target.get("display"),
            timeout=float(request.payload.get("timeout_seconds", 180)),
        )
        result["compiled_shortcut"] = shortcut_receipt(
            request.operation,
            version=version,
            profile="de",
            plan=plan,
            validation_result=result.get("assertions") or {"status": result.get("status")},
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_circuit_simulate(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("circuit.simulate requires payload.mutating=true")
        if profile != "de":
            raise ValueError("circuit.simulate requires the ADS DE profile")
        plan = request.payload.get("plan")
        if not isinstance(plan, dict):
            raise TypeError("circuit.simulate requires a structured plan object")
        plan = dict(plan)
        selected_instance = request.payload.get("instance") or request.target.get("instance")
        if selected_instance and "instance" not in plan:
            plan["instance"] = selected_instance
        instance = select_instance(selected_instance)
        version = str(instance.year or instance.product_version)
        validate_shortcut(request.operation, version=version, profile="de")
        result = execute_simulation_plan(
            plan,
            expected_display=request.payload.get("display") or request.target.get("display"),
            timeout=float(request.payload.get("timeout_seconds", 600)),
        )
        result["compiled_shortcut"] = shortcut_receipt(
            request.operation,
            version=version,
            profile="de",
            plan=plan,
            validation_result=result.get("assertions") or {"status": result.get("status")},
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_dds_create(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("dds.create requires payload.mutating=true")
        plan = request.payload.get("plan")
        if not isinstance(plan, dict):
            raise TypeError("dds.create requires a structured plan object")
        plan = dict(plan)
        selected_instance = request.payload.get("instance") or request.target.get("instance")
        if selected_instance and "instance" not in plan:
            plan["instance"] = selected_instance
        instance = select_instance(selected_instance)
        version = str(instance.year or instance.product_version)
        validate_shortcut(request.operation, version=version, profile="dds")
        result = execute_dds_plan(
            plan,
            expected_display=request.payload.get("display") or request.target.get("display"),
            timeout=float(request.payload.get("timeout_seconds", 180)),
        )
        result["compiled_shortcut"] = shortcut_receipt(
            request.operation,
            version=version,
            profile="dds",
            plan=plan,
            validation_result=result.get("assertions") or {"status": result.get("status")},
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_momentum_run_generated(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("momentum.run_generated requires payload.mutating=true")
        selected_instance = request.payload.get("instance") or request.target.get("instance")
        instance = select_instance(selected_instance)
        version = str(instance.year or instance.product_version)
        validate_shortcut(request.operation, version=version, profile="de")
        result = run_generated_momentum(
            source_directory=request.payload.get("source_directory", ""),
            output_directory=request.payload.get("output_directory", ""),
            project=str(request.payload.get("project") or ""),
            instance_id=request.payload.get("instance") or request.target.get("instance"),
            expected_display=request.payload.get("display") or request.target.get("display"),
            source_fingerprint=request.payload.get("source_fingerprint"),
            timeout=float(request.payload.get("timeout_seconds", 600)),
        )
        receipt_plan = {
            key: request.payload[key]
            for key in (
                "source_directory",
                "output_directory",
                "project",
                "source_fingerprint",
                "timeout_seconds",
            )
            if key in request.payload
        }
        result["compiled_shortcut"] = shortcut_receipt(
            request.operation,
            version=version,
            profile="de",
            plan=receipt_plan,
            validation_result=result.get("assertions") or {"status": result.get("status")},
        )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_session_status(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if request.is_mutating:
            raise ValueError("session.status requires payload.mutating=false")
        result = session_status(str(slot) if slot else None)
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_session_shutdown(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("session.shutdown requires payload.mutating=true")
        result = shutdown_session(
            str(slot) if slot else None,
            wait_seconds=float(request.payload.get("timeout_seconds", 30)),
        )
        if result.get("status") != "exited":
            return AdapterResult(
                status="failed",
                result={"bridge": result},
                error={
                    "code": "action_required",
                    "phase": "lifecycle",
                    "message": f"ADS shutdown requires attention: {result.get('status')}",
                },
            )
        return AdapterResult(status="passed", result={"bridge": result})

    def _execute_session_launch(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        if not request.is_mutating:
            raise ValueError("session.launch requires payload.mutating=true")
        workspace = request.payload.get("workspace") or request.target.get("workspace")
        if not workspace:
            raise ValueError("session.launch requires workspace or a workspace context")
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
            return AdapterResult(
                status="uncertain",
                result={"bridge": result},
                error={
                    "code": "execution_uncertain",
                    "phase": "lifecycle",
                    "message": f"ADS launch has no confirmed terminal state: {status}",
                    "execution_uncertain": True,
                },
            )
        resource = _launched_session_resource(result)
        return AdapterResult(
            status="passed",
            result={
                "bridge": result,
                **({"resource": resource} if resource else {}),
            },
        )

    def _execute_live(
        self,
        request,
        context,
        slot,
        profile,
        continuation_record,
        decoded_context,
        context_id,
        native_continuation,
    ):
        _, AdapterResult, _, _, _ = _runtime_imports()
        capabilities_started = time.monotonic()
        descriptor = self._descriptor(
            self._live_capabilities(str(slot) if slot else None, profile),
            request.operation,
        )
        capability_ms = (time.monotonic() - capabilities_started) * 1000
        safety = descriptor.get("safety")
        state = descriptor.get("state") or {}
        if not state.get("available") or not state.get("healthy"):
            reason = state.get("reason") or "unavailable"
            raise RuntimeError(f"ADS operation is not currently usable: {reason}")
        advertised_mutation = bool(descriptor.get("mutates"))
        if advertised_mutation != request.is_mutating:
            message = "request mutation flag does not match live ADS capability descriptor"
            raise ValueError(message)
        legacy_args = request.payload.get("args")
        if legacy_args is None:
            args = {
                key: value
                for key, value in request.payload.items()
                if key not in {"mutating", "timeout_seconds"}
            }
        else:
            args = legacy_args
        if not isinstance(args, dict):
            raise TypeError("ADS operation args must be an object")
        if request.operation == "design.live_patch":
            import hashlib

            from eda_bridge_runtime import LIVE_EDIT_SCHEMA, validate_live_edit

            patch_id = str(args.get("patch_id") or "")
            if not patch_id:
                material = str(
                    getattr(request, "idempotency_key", None)
                    or getattr(request, "request_id", "live-patch")
                )
                patch_id = "patch-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
            common = validate_live_edit(
                {
                    "schema_version": args.get("schema_version") or LIVE_EDIT_SCHEMA,
                    "patch_id": patch_id,
                    "expected_revision": args.get("expected_revision"),
                    "operations": args.get("operations"),
                    "conflict_policy": args.get("conflict_policy") or "fail_on_change",
                    "validation": args.get("validation") or "readback",
                }
            )
            if common["expected_revision"] is not None:
                raise ValueError(
                    "ADS live edits currently require object preconditions, not a global revision"
                )
            args = {
                **args,
                **common,
                "operations": common["operations"],
            }
        if request.operation in {
            "design.live_patch",
            "design.live_finalize",
        } and not args.get("design"):
            identity = request.target.get("identity")
            if request.target.get("kind") == "design" and isinstance(identity, dict):
                parts = [identity.get(name) for name in ("library", "cell", "view")]
                if all(isinstance(part, str) and part for part in parts):
                    args = {**args, "design": ":".join(parts)}
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
        args = {**args, "purpose": request.purpose, "admission": context.admission}
        context.assert_current()
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
            from eda_bridge_runtime.errors import ExecutionError

            failure = response.get("failure") or {}
            raise ExecutionError(
                failure.get("code", "execution_failed"),
                str(response.get("error") or "ADS bridge operation failed"),
                phase=failure.get("phase", "execution"),
                evidence=failure.get("evidence"),
                uncertain=bool(failure.get("execution_uncertain")),
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
    import sys

    from eda_bridge_runtime.service import DurableService

    jobs_path = Path(ledger_path).parent / "jobs.sqlite3"

    def command(request, job_id):
        return [
            sys.executable,
            "-m",
            "ads_agent_bridge",
            "runtime",
            "worker",
            "--jobs",
            str(jobs_path),
            "--ledger",
            str(ledger_path),
            "--job-id",
            job_id,
        ]

    service = DurableService(
        jobs_path, ledger_path, runtime_factory=build_runtime, worker_command=command
    )
    serve_json_lines(input_stream, output_stream, service.handle)


def run_worker(jobs_path, ledger_path, job_id):
    from eda_bridge_runtime import JobStore, run_job_worker

    return run_job_worker(JobStore(jobs_path), job_id, build_runtime(ledger_path).execute)
