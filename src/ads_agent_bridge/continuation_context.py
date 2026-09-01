"""Content-state bindings in the existing private ADS Runtime Context store."""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eda_bridge_runtime import EDAContext, capability_digest, stable_origin_id

from .workspace_create import _context_path, resolve_context

CONTINUATION_RECORD_SCHEMA = 2
_CONTEXT_ID = re.compile(r"ctx_[a-f0-9]{20}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_RECORD_BYTES = 65_536
_IDENTITY_FIELDS = (
    "connection_id",
    "slot",
    "profile",
    "instance",
    "version",
    "workspace",
    "design",
)


def _opaque_token(context_id: str, identity: dict[str, Any]) -> str:
    states = {"continue": "requires-authorization"}
    locator = {
        "context_id": context_id,
        "slot": identity.get("slot"),
        "profile": identity["profile"],
    }
    if identity.get("connection_id"):
        locator["connection_id"] = identity["connection_id"]
    return EDAContext(
        eda="keysight-ads",
        target_kind="workspace",
        locator={key: value for key, value in locator.items() if value},
        display_name="ADS governed continuation",
        generation=1,
        capabilities_hint=("continue",),
        origin={"origin_id": stable_origin_id("keysight-ads")},
        session={
            "session_id": None,
            "profile": identity["profile"],
            "state": "content-bound",
        },
        target={"binding": "private-host-record"},
        capabilities={"states": states, "digest": capability_digest(states)},
        freshness={"scope": "durable", "generation": 1, "state": "content-bound"},
    ).encode()


def create_continuation_context(
    *,
    identity: dict[str, Any],
    source_fingerprint: str,
) -> tuple[str, dict[str, Any]]:
    """Persist an immutable private binding and return one existing EDA_CONTEXT."""

    digest = str(source_fingerprint or "").lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError("ADS continuation Context requires a SHA-256 source fingerprint")
    normalized = {field: identity.get(field) for field in _IDENTITY_FIELDS}
    if normalized["profile"] not in {"de", "dds"}:
        raise ValueError("ADS continuation Context requires profile de or dds")
    for field in ("instance", "version", "workspace"):
        if not str(normalized.get(field) or "").strip():
            raise ValueError(f"ADS continuation Context requires exact {field} identity")
    normalized["workspace"] = str(Path(str(normalized["workspace"])).expanduser().resolve())
    normalized = {
        key: str(value) if value is not None else None
        for key, value in normalized.items()
    }
    record = {
        "schema_version": CONTINUATION_RECORD_SCHEMA,
        "context_kind": "native-continuation",
        "generation": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "allowed_operations": ["native.batch"],
        "identity": normalized,
        "content_state": {"kind": "source_fingerprint", "sha256": digest},
    }
    encoded = (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if len(encoded) > _MAX_RECORD_BYTES:
        raise ValueError("ADS continuation Context record is too large")
    for _ in range(8):
        context_id = "ctx_" + secrets.token_hex(10)
        path = _context_path(context_id)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        state = {
            "schema_version": "ads-continuation-state/v1",
            "state": "content-bound",
            "content_state": "source-fingerprint",
            "profile": normalized["profile"],
            "slot_bound": normalized["slot"] is not None,
            "connection_bound": normalized["connection_id"] is not None,
            "design_bound": normalized["design"] is not None,
        }
        return _opaque_token(context_id, normalized), state
    raise RuntimeError("could not allocate an ADS continuation Context")


def _decode_reference(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith(("EDA_CONTEXT:v2:", "EDA_CONTEXT:v1:")):
        decoded = EDAContext.decode(text)
        if decoded.eda != "keysight-ads":
            raise ValueError("continuation EDA_CONTEXT belongs to another EDA")
        if decoded.origin.get("origin_id") != stable_origin_id("keysight-ads"):
            raise ValueError("continuation EDA_CONTEXT belongs to another ADS origin")
        context_id = str(decoded.locator.get("context_id") or "")
    else:
        context_id = text
    if not _CONTEXT_ID.fullmatch(context_id):
        raise ValueError("invalid ADS continuation Context")
    return context_id


def continuation_ref(value: str) -> str:
    """Return the short host-local reference for an existing continuation."""

    return _decode_reference(value)


def resolve_continuation_context(value: str) -> dict[str, Any]:
    context_id = _decode_reference(value)
    path = _context_path(context_id)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("ADS continuation Context is unavailable on this host") from exc
    if size <= 0 or size > _MAX_RECORD_BYTES:
        raise ValueError("ADS continuation Context host record is invalid")
    record = resolve_context(context_id)
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != CONTINUATION_RECORD_SCHEMA
        or record.get("context_kind") != "native-continuation"
    ):
        raise ValueError("ADS Context is not a native continuation Context")
    if record.get("allowed_operations") != ["native.batch"]:
        raise ValueError("ADS continuation Context operation binding is invalid")
    identity = record.get("identity")
    state = record.get("content_state")
    if not isinstance(identity, dict) or set(identity) != set(_IDENTITY_FIELDS):
        raise ValueError("ADS continuation Context identity binding is invalid")
    if identity.get("profile") not in {"de", "dds"}:
        raise ValueError("ADS continuation Context profile binding is invalid")
    if not all(
        str(identity.get(field) or "").strip()
        for field in ("instance", "version", "workspace")
    ):
        raise ValueError("ADS continuation Context exact target binding is incomplete")
    if (
        not isinstance(state, dict)
        or state.get("kind") != "source_fingerprint"
        or not _SHA256.fullmatch(str(state.get("sha256") or ""))
    ):
        raise ValueError("ADS continuation Context content-state binding is invalid")
    return record


def continuation_reference(
    target: dict[str, Any], payload: dict[str, Any]
) -> str | None:
    candidates = []
    for value in (target.get("continuation_context"), payload.get("continuation_context")):
        text = str(value or "").strip()
        if text:
            candidates.append(text)
    target_context = str(target.get("context") or "").strip()
    if target_context.startswith(("EDA_CONTEXT:v2:", "EDA_CONTEXT:v1:")):
        decoded = EDAContext.decode(target_context)
        if decoded.target.get("binding") == "private-host-record":
            candidates.append(target_context)
    if not candidates:
        return None
    ids = {_decode_reference(value) for value in candidates}
    if len(ids) != 1:
        raise ValueError("conflicting ADS continuation Context references")
    return candidates[0]


def _reject_explicit_target_conflicts(
    record: dict[str, Any], target: dict[str, Any], payload: dict[str, Any]
) -> None:
    identity = record["identity"]
    explicit = {
        "connection_id": target.get("connection_id"),
        "slot": target.get("slot") or payload.get("slot"),
        "profile": target.get("profile"),
        "instance": target.get("instance") or payload.get("instance"),
        "workspace": target.get("workspace"),
        "design": target.get("design") or target.get("top_design"),
    }
    for field, value in explicit.items():
        if value is None or str(value).strip() == "":
            continue
        expected = identity.get(field)
        if field == "workspace":
            value = str(Path(str(value)).expanduser().resolve())
        else:
            value = str(value)
        if expected is None or value != str(expected):
            raise ValueError(f"ADS continuation Context conflicts with explicit {field}")


def materialize_native_batch_plan(
    value: Any,
    *,
    record: dict[str, Any],
    target: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Materialize only trusted identity/state fields into a native batch plan."""

    if not isinstance(value, dict):
        raise TypeError("native.batch requires a governed native batch plan")
    _reject_explicit_target_conflicts(record, target, payload)
    plan = json.loads(json.dumps(value))
    scope = plan.get("scope")
    transaction = plan.get("transaction")
    if not isinstance(scope, dict) or not isinstance(transaction, dict):
        raise TypeError("native.batch continuation requires scope and transaction objects")
    identity = record["identity"]
    selectors = scope.get("selectors")
    if selectors is None:
        selectors = {}
    if not isinstance(selectors, dict):
        raise TypeError("native.batch scope.selectors must be an object")
    trusted_selectors = {
        "instance": identity["instance"],
        "version": identity["version"],
        "profile": identity["profile"],
    }
    for key, expected in trusted_selectors.items():
        explicit = selectors.get(key)
        if explicit is not None and str(explicit) != str(expected):
            raise ValueError(f"ADS continuation Context conflicts with scope selector {key}")
        selectors[key] = expected
    scope["selectors"] = selectors
    if scope.get("resource_kind") not in {None, "ads-workspace"}:
        raise ValueError("ADS continuation Context conflicts with scope resource_kind")
    scope["resource_kind"] = "ads-workspace"
    workspace = str(identity["workspace"])
    read_paths = scope.get("read_paths")
    if read_paths in (None, []):
        scope["read_paths"] = [workspace]
    elif not isinstance(read_paths, list) or len(read_paths) != 1:
        raise ValueError("ADS continuation Context requires exactly one read workspace")
    elif str(Path(str(read_paths[0])).expanduser().resolve()) != workspace:
        raise ValueError("ADS continuation Context conflicts with explicit read workspace")
    else:
        scope["read_paths"] = [workspace]
    effect = str(plan.get("effect") or "")
    fingerprints = transaction.get("source_fingerprints")
    if effect == "staged_mutation":
        expected = str(record["content_state"]["sha256"])
        if fingerprints in (None, {}):
            transaction["source_fingerprints"] = {workspace: expected}
        elif not isinstance(fingerprints, dict) or fingerprints != {workspace: expected}:
            raise ValueError(
                "ADS continuation Context conflicts with explicit source fingerprint"
            )
    elif fingerprints is None:
        transaction["source_fingerprints"] = {}
    plan["scope"] = scope
    plan["transaction"] = transaction
    return plan, str(record["content_state"]["sha256"])
