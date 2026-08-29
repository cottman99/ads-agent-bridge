"""Durable, bounded references to live ADS UI context.

This module intentionally depends only on the Python standard library so it can
run inside every supported ADS embedded Python environment.
"""

from __future__ import annotations

import base64
import copy
import datetime as _datetime
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from collections import OrderedDict
from itertools import islice
from pathlib import Path
from urllib.parse import quote, unquote

SCHEMA_VERSION = 1
MAX_CONTEXTS = 64
MAX_SELECTION_ITEMS = 50
_HANDLE_RE = re.compile(
    r"^ADS_CONTEXT:v1:(?P<slot>[^:]+):(?P<profile>[^:]+):(?P<context_id>[^:]+):"
)
_EDA_CONTEXT_PREFIXES = ("EDA_CONTEXT:v2:", "EDA_CONTEXT:v1:")


def _utc_now():
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


def _safe_attr(value, name, default=None):
    try:
        result = getattr(value, name, default)
        return result() if callable(result) else result
    except Exception:
        return default


def _bounded_text(value, limit=240):
    if value is None:
        return ""
    try:
        text = str(value)
    except Exception:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _enum_name(value):
    name = _safe_attr(value, "name")
    return _bounded_text(name or value)


def context_reference_from(value):
    """Parse a raw context id or a versioned ADS_CONTEXT handle."""

    text = _bounded_text(value, 32768).strip()
    if not text:
        raise ValueError("context id or ADS_CONTEXT handle is required")
    prefix = next((item for item in _EDA_CONTEXT_PREFIXES if text.startswith(item)), None)
    if prefix:
        encoded = text[len(prefix) :]
        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            wrapper = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            payload = wrapper["payload"]
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
            locator = payload["locator"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("malformed EDA_CONTEXT handle") from exc
        if checksum != wrapper.get("checksum") or payload.get("eda") != "keysight-ads":
            raise ValueError("invalid or incompatible EDA_CONTEXT handle")
        return {
            "context_id": locator["context_id"],
            "slot": locator["slot"],
            "profile": locator["profile"],
            "is_handle": True,
        }
    match = _HANDLE_RE.match(text)
    if match is not None:
        return {
            "context_id": match.group("context_id"),
            "slot": unquote(match.group("slot")),
            "profile": unquote(match.group("profile")),
            "is_handle": True,
        }
    if text.startswith("ADS_CONTEXT:"):
        raise ValueError("unsupported or malformed ADS_CONTEXT handle")
    return {"context_id": text, "slot": None, "profile": None, "is_handle": False}


def _stable_origin_id():
    configured = _bounded_text(os.environ.get("EDA_BRIDGE_ORIGIN_ID"), 128)
    if configured:
        return configured
    root = Path(os.environ.get("EDA_RUNTIME_HOME") or Path.home() / ".eda-bridge-runtime")
    eda = "keysight-ads"
    path = root / "origins" / (hashlib.sha256(eda.encode("utf-8")).hexdigest()[:16] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return _bounded_text(json.loads(path.read_text(encoding="utf-8"))["origin_id"], 128)
    origin_id = "origin-" + uuid.uuid4().hex[:20]
    descriptor, temporary = tempfile.mkstemp(prefix="origin-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "eda": eda, "origin_id": origin_id}, stream)
            stream.write("\n")
        try:
            os.link(temporary, path)
        except FileExistsError:
            return _stable_origin_id()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return origin_id


def _capability_digest(capabilities):
    canonical = json.dumps(capabilities, sort_keys=True, separators=(",", ":"))
    return "cap-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _eda_context_handle(context_id, envelope):
    capabilities = envelope["capabilities"]
    available = tuple(
        sorted(name for name, state in capabilities.items() if state != "unavailable")
    )
    selection = copy.deepcopy(envelope.get("selection") or {})
    items = list(selection.get("items") or [])
    if len(items) > 12:
        selection["items"] = items[:12]
        selection["truncated"] = True
    session = copy.deepcopy(envelope["session"])
    session["session_id"] = (
        os.environ.get("ADS_AGENT_MANAGED_SESSION_ID")
        or "ads-{0}-{1}-{2}".format(session.get("pid"), session.get("slot"), session.get("profile"))
    )
    session["display"] = os.environ.get("DISPLAY")
    payload = {
        "eda": "keysight-ads",
        "target_kind": _bounded_text(envelope["target"].get("kind")),
        "locator": {
            "slot": _bounded_text(session.get("slot")),
            "profile": _bounded_text(session.get("profile")),
            "context_id": _bounded_text(context_id),
        },
        "display_name": _bounded_text(envelope["target"].get("display_name"), 512),
        "generation": int(envelope["freshness"]["generation"]),
        "capabilities_hint": available,
        "created_at": envelope["freshness"]["last_refreshed_at"],
        "origin": {"origin_id": _stable_origin_id()},
        "session": session,
        "target": copy.deepcopy(envelope["target"]),
        "selection": selection,
        "capabilities": {
            "states": copy.deepcopy(capabilities),
            "digest": _capability_digest(capabilities),
        },
        "freshness": copy.deepcopy(envelope["freshness"]),
        "protocol": "eda-context/v2",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    wrapper = {
        "payload": payload,
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
    }
    data = json.dumps(wrapper, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")
    return _EDA_CONTEXT_PREFIXES[0] + encoded


def context_id_from(value):
    """Return a context id from either an id or an ADS_CONTEXT handle."""

    return context_reference_from(value)["context_id"]


def _bounded_collection(values, limit=MAX_SELECTION_ITEMS):
    """Return a bounded prefix, an observed count, and count confidence."""

    if values is None:
        return [], 0, False, True
    try:
        total = len(values)
    except Exception:
        try:
            observed = list(islice(iter(values), limit + 1))
        except Exception:
            return [], 0, False, True
        truncated = len(observed) > limit
        return observed[:limit], len(observed), truncated, not truncated
    try:
        limited = list(values[:limit])
    except Exception:
        try:
            limited = list(islice(iter(values), limit))
        except Exception:
            limited = []
    return limited, total, total > limit, True


def _object_summary(value):
    summary = {
        "type": type(value).__name__,
        "module": type(value).__module__,
    }
    for name in ("name", "expression", "title", "text"):
        item = _safe_attr(value, name)
        if item not in (None, ""):
            summary[name] = _bounded_text(item)
            break
    return summary


def _selection_summary(values):
    limited, count, truncated, count_is_exact = _bounded_collection(values)
    items = [_object_summary(item) for item in limited]
    kinds = {item["type"] for item in items}
    return {
        "count": count,
        "count_is_exact": count_is_exact,
        "items": items,
        "truncated": truncated,
        "homogeneous": len(kinds) <= 1,
    }


def _design_identity(design):
    lib_name = _bounded_text(_safe_attr(design, "lib_name"))
    cell_name = _bounded_text(_safe_attr(design, "cell_name"))
    view_name = _bounded_text(_safe_attr(design, "view_name"))
    if not all((lib_name, cell_name, view_name)):
        lcv = _safe_attr(design, "lcv_name")
        lib_name = lib_name or _bounded_text(_safe_attr(lcv, "lib_name"))
        cell_name = cell_name or _bounded_text(_safe_attr(lcv, "cell_name"))
        view_name = view_name or _bounded_text(_safe_attr(lcv, "view_name"))
    identity = {
        "library": lib_name,
        "cell": cell_name,
        "view": view_name,
    }
    display_name = ":".join(part for part in (lib_name, cell_name, view_name) if part)
    if not display_name:
        display_name = _bounded_text(_safe_attr(design, "name") or "design")
    return identity, display_name


def _workspace_item_record(item):
    flags = {
        name: bool(_safe_attr(item, name, False))
        for name in ("is_workspace", "is_folder", "is_library", "is_cell", "is_view")
    }
    item_type = _enum_name(_safe_attr(item, "item_type"))
    lib_name = _bounded_text(_safe_attr(item, "lib_name"))
    cell_name = _bounded_text(_safe_attr(item, "cell_name"))
    view_name = _bounded_text(_safe_attr(item, "view_name"))
    full_path = _bounded_text(
        _safe_attr(item, "full_path_name")
        or _safe_attr(item, "path")
        or _safe_attr(item, "file_name")
    )
    name = _bounded_text(_safe_attr(item, "name"))

    if flags["is_workspace"]:
        kind = "workspace"
    elif flags["is_folder"]:
        kind = "folder"
    elif flags["is_library"]:
        kind = "library"
    elif flags["is_cell"]:
        kind = "cell"
    elif flags["is_view"]:
        kind = "cellview"
    elif item_type.upper() == "DDS" or full_path.lower().endswith(".dds"):
        kind = "dds-file-ref"
    elif item_type.upper() in ("DS", "DATASET") or full_path.lower().endswith(".ds"):
        kind = "dataset-ref"
    else:
        kind = "file-ref"

    identity = {}
    if lib_name:
        identity["library"] = lib_name
    if cell_name:
        identity["cell"] = cell_name
    if view_name:
        identity["view"] = view_name
    if full_path:
        identity["path"] = full_path
    if item_type:
        identity["item_type"] = item_type
    if not identity and name:
        identity["name"] = name

    display_name = ":".join(part for part in (lib_name, cell_name, view_name) if part)
    if not display_name:
        display_name = name or (Path(full_path).name if full_path else kind)
    return {
        "kind": kind,
        "identity": identity,
        "display_name": display_name,
    }


def _dds_path(dds_file):
    data_path = _safe_attr(dds_file, "data_path")
    name = _bounded_text(_safe_attr(dds_file, "name"))
    if data_path:
        try:
            path = Path(str(data_path))
            if path.suffix.lower() == ".dds":
                return str(path)
            file_name = name if name.lower().endswith(".dds") else name + ".dds"
            return str(path.parent / file_name) if file_name else str(path)
        except Exception:
            return _bounded_text(data_path, 1024)
    return name


def _dds_page(window):
    page = _safe_attr(window, "current_page")
    if page is None:
        return ""
    return _bounded_text(_safe_attr(page, "name") or _safe_attr(page, "title") or page)


class ContextRegistry:
    """Owns live-object references while exposing only serializable envelopes."""

    def __init__(self, profile, slot="", instance_id="", limit=MAX_CONTEXTS):
        self.profile = _bounded_text(profile) or "unknown"
        self.slot = _bounded_text(slot or os.environ.get("ADS_BRIDGE_SLOT", "default"))
        detected_instance = (
            instance_id
            or os.environ.get("ADS_AGENT_INSTANCE_ID")
            or os.environ.get("HPEESOF_DIR")
            or os.environ.get("ADS_ROOT", "")
        )
        self.instance_id = _bounded_text(detected_instance, 1024)
        self.limit = max(1, int(limit))
        self._records = OrderedDict()
        self._keys = {}
        self._counter = 0
        self._lock = threading.RLock()
        self._ui_status = {"state": "not-configured", "profile": self.profile}

    def set_ui_status(self, status):
        with self._lock:
            self._ui_status = copy.deepcopy(status or {})
            self._ui_status.setdefault("profile", self.profile)

    def capabilities(self):
        with self._lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "profile": self.profile,
                "slot": self.slot,
                "max_contexts": self.limit,
                "max_selection_items": MAX_SELECTION_ITEMS,
                "context_count": len(self._records),
                "ui": copy.deepcopy(self._ui_status),
            }

    def _context_capabilities(self, target_kind):
        capabilities = {
            "inspect": "available",
            "refresh": "available",
            "open": "requires-live-context",
            "edit": "unavailable",
            "simulate": "unavailable",
        }
        if target_kind in ("design", "cellview", "dds-page", "dds-file"):
            capabilities["edit"] = "requires-authorization"
        if target_kind in ("design", "cellview"):
            capabilities["simulate"] = "requires-authorization"
        if target_kind.endswith("-ref") or target_kind in ("workspace", "folder", "library", "cell"):
            capabilities["open"] = "requires-authorization"
        return capabilities

    def _handle(self, context_id, target, generation):
        display_name = quote(_bounded_text(target.get("display_name"), 512), safe="@/._-")
        return (
            "ADS_CONTEXT:v1:{slot}:{profile}:{context_id}:{target}"
            "?generation={generation}&kind={kind}"
        ).format(
            slot=quote(self.slot, safe="@._-"),
            profile=quote(self.profile, safe="@._-"),
            context_id=context_id,
            target=display_name,
            generation=generation,
            kind=quote(_bounded_text(target.get("kind")), safe="@._-"),
        )

    def _register(self, key, source, target, selection, live_object=None, window=None, state="captured-live"):
        now = _utc_now()
        with self._lock:
            context_id = self._keys.get(key)
            previous = self._records.get(context_id) if context_id else None
            if previous:
                generation = previous["envelope"]["freshness"]["generation"] + 1
                captured_at = previous["envelope"]["freshness"]["captured_at"]
            else:
                self._counter += 1
                context_id = "ctx-{0:04d}".format(self._counter)
                generation = 1
                captured_at = now

            envelope = {
                "schema_version": SCHEMA_VERSION,
                "context_id": context_id,
                "source": {"profile": self.profile, "surface": source},
                "target": copy.deepcopy(target),
                "selection": copy.deepcopy(selection),
                "session": {
                    "instance_id": self.instance_id,
                    "slot": self.slot,
                    "profile": self.profile,
                    "pid": os.getpid(),
                },
                "freshness": {
                    "state": state,
                    "generation": generation,
                    "captured_at": captured_at,
                    "last_refreshed_at": now,
                },
                "capabilities": self._context_capabilities(target["kind"]),
                "authorization_required": True,
            }
            envelope["context_ref"] = {
                "type": "ADS_CONTEXT",
                "version": 1,
                "text": self._handle(context_id, target, generation),
            }
            envelope["eda_context_ref"] = {
                "type": "EDA_CONTEXT",
                "version": 2,
                "text": _eda_context_handle(context_id, envelope),
            }
            record = {
                "key": key,
                "envelope": envelope,
                "live_object": live_object,
                "window": window,
            }
            self._records[context_id] = record
            self._records.move_to_end(context_id)
            self._keys[key] = context_id
            while len(self._records) > self.limit:
                old_id, old_record = self._records.popitem(last=False)
                self._keys.pop(old_record["key"], None)
            return copy.deepcopy(envelope)

    def capture_design(self, design, window=None, surface="design-window"):
        if design is None:
            raise ValueError("a live design is required")
        identity, display_name = _design_identity(design)
        target = {"kind": "design", "identity": identity, "display_name": display_name}
        selection = _selection_summary(_safe_attr(design, "selected_objects", ()))
        key = json.dumps(["design", identity], sort_keys=True)
        return self._register(key, surface, target, selection, design, window, "captured-live")

    def capture_workspace_items(self, items, workspace_path=""):
        limited_items, total, truncated, count_is_exact = _bounded_collection(items)
        if not limited_items:
            raise ValueError("at least one selected workspace item is required")
        records = [_workspace_item_record(item) for item in limited_items]
        if total == 1:
            target = records[0]
        else:
            identities = [{"kind": item["kind"], "identity": item["identity"]} for item in records]
            target = {
                "kind": "context-set",
                "identity": {
                    "items": identities,
                    "count": total,
                    "count_is_exact": count_is_exact,
                    "truncated": truncated,
                },
                "display_name": (
                    "{0} selected items".format(total)
                    if count_is_exact
                    else "at least {0} selected items".format(total)
                ),
            }
        target["identity"].setdefault("workspace_path", _bounded_text(workspace_path, 1024))
        kinds = {item["kind"] for item in records}
        selection = {
            "count": total,
            "count_is_exact": count_is_exact,
            "items": records,
            "truncated": truncated,
            "homogeneous": len(kinds) <= 1,
        }
        key = json.dumps(["workspace-items", target["identity"]], sort_keys=True)
        return self._register(key, "workspace-tree", target, selection, None, None, "re-resolvable")

    def capture_dds(self, dds_file, window=None):
        if dds_file is None:
            raise ValueError("a live DDS file is required")
        path = _dds_path(dds_file)
        page = _dds_page(window)
        identity = {"path": path}
        if page:
            identity["page"] = page
        display_name = path or _bounded_text(_safe_attr(dds_file, "name") or "DDS")
        if page:
            display_name += "#" + page
        kind = "dds-page" if page else "dds-file"
        target = {"kind": kind, "identity": identity, "display_name": display_name}
        selection = _selection_summary(_safe_attr(dds_file, "selected_objects", ()))
        key = json.dumps(["dds", identity], sort_keys=True)
        return self._register(key, "dds-window", target, selection, dds_file, window, "captured-live")

    def list(self):
        with self._lock:
            return [copy.deepcopy(record["envelope"]) for record in reversed(self._records.values())]

    def summary(self):
        """Return bounded registry state without copying every stored context."""

        with self._lock:
            latest = next(reversed(self._records.values()), None) if self._records else None
            return {
                "count": len(self._records),
                "max_contexts": self.limit,
                "latest": copy.deepcopy(latest["envelope"]) if latest is not None else None,
            }

    def get(self, value):
        context_id = self._validated_context_id(value)
        with self._lock:
            record = self._records.get(context_id)
            if record is None:
                raise KeyError("unknown context: {0}".format(context_id))
            self._records.move_to_end(context_id)
            return copy.deepcopy(record["envelope"])

    def refresh(self, value):
        context_id = self._validated_context_id(value)
        with self._lock:
            record = self._records.get(context_id)
            if record is None:
                raise KeyError("unknown context: {0}".format(context_id))
            envelope = record["envelope"]
            live_object = record["live_object"]
            target_kind = envelope["target"]["kind"]
            now = _utc_now()
            if live_object is None:
                envelope["freshness"]["state"] = "re-resolvable"
            elif target_kind == "design":
                identity, _ = _design_identity(live_object)
                if identity != envelope["target"]["identity"]:
                    envelope["freshness"]["state"] = "stale"
                    envelope["freshness"]["reason"] = "live_design_identity_changed"
                else:
                    envelope["selection"] = _selection_summary(_safe_attr(live_object, "selected_objects", ()))
                    envelope["freshness"]["state"] = "captured-live"
                    envelope["freshness"].pop("reason", None)
            elif target_kind in ("dds-page", "dds-file"):
                path = _dds_path(live_object)
                page = _dds_page(record["window"])
                identity = {"path": path}
                if page:
                    identity["page"] = page
                if identity != envelope["target"]["identity"]:
                    envelope["freshness"]["state"] = "stale"
                    envelope["freshness"]["reason"] = "active_dds_page_changed"
                else:
                    envelope["selection"] = _selection_summary(_safe_attr(live_object, "selected_objects", ()))
                    envelope["freshness"]["state"] = "captured-live"
                    envelope["freshness"].pop("reason", None)
            envelope["freshness"]["generation"] += 1
            envelope["freshness"]["last_refreshed_at"] = now
            envelope["context_ref"]["text"] = self._handle(
                context_id, envelope["target"], envelope["freshness"]["generation"]
            )
            self._records.move_to_end(context_id)
            return copy.deepcopy(envelope)

    def drop(self, value):
        context_id = self._validated_context_id(value)
        with self._lock:
            record = self._records.pop(context_id, None)
            if record is None:
                return False
            self._keys.pop(record["key"], None)
            return True

    def _validated_context_id(self, value):
        reference = context_reference_from(value)
        if reference["is_handle"]:
            if reference["slot"] != self.slot:
                raise ValueError(
                    "ADS_CONTEXT slot mismatch: handle={0!r}, session={1!r}".format(
                        reference["slot"], self.slot
                    )
                )
            if reference["profile"] != self.profile:
                raise ValueError(
                    "ADS_CONTEXT profile mismatch: handle={0!r}, session={1!r}".format(
                        reference["profile"], self.profile
                    )
                )
        return reference["context_id"]

    def stop(self):
        with self._lock:
            self._records.clear()
            self._keys.clear()
            self._ui_status = {"state": "stopped", "profile": self.profile}
