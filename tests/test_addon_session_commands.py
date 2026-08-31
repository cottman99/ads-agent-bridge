from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


def load_server(monkeypatch):
    class FakeQObject:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

    class FakeTimer:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            self.timeout = types.SimpleNamespace(connect=lambda callback: callback)

        def setInterval(self, value) -> None:
            del value

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        @staticmethod
        def singleShot(delay, callback) -> None:
            del delay
            callback()

    fake_qt = types.ModuleType("PySide6")
    fake_qt.QtCore = types.SimpleNamespace(QObject=FakeQObject, QTimer=FakeTimer)
    fake_qt.QtWidgets = types.SimpleNamespace(QApplication=types.SimpleNamespace(instance=lambda: None))
    monkeypatch.setitem(sys.modules, "PySide6", fake_qt)
    sys.modules.pop("ads_agent_bridge.addon.AdsAgentBridge.server", None)
    return importlib.import_module("ads_agent_bridge.addon.AdsAgentBridge.server")


class FakeWorkspace:
    def __init__(self, path: Path) -> None:
        self.path = path


class FakeDe:
    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = workspace
        self.open_calls: list[str] = []

    def workspace_is_open(self) -> bool:
        return self.workspace is not None

    def active_workspace(self) -> FakeWorkspace:
        assert self.workspace is not None
        return FakeWorkspace(self.workspace)

    def open_workspace(self, path: str) -> None:
        self.open_calls.append(path)
        self.workspace = Path(path)


def make_workspace(tmp_path: Path, name: str) -> Path:
    workspace = tmp_path / name
    workspace.mkdir()
    (workspace / "lib.defs").write_text("", encoding="ascii")
    (workspace / "cds.lib").write_text("", encoding="ascii")
    return workspace


def test_design_live_patch_updates_current_gui_design_with_readback(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class Parameter:
        value = "50 Ohm"

    parameter = Parameter()
    design = types.SimpleNamespace(
        lib_name="demo_lib",
        cell_name="Main",
        view_name="schematic",
        instances={"R1": types.SimpleNamespace(parameters={"R": parameter})},
        save_design=lambda: (_ for _ in ()).throw(AssertionError("must not save")),
    )
    window = object()
    commits: list[str] = []

    class Transaction:
        def __init__(self, selected_design, label) -> None:
            assert selected_design is design
            assert "patch-1" in label

        def __enter__(self):
            return self

        def commit(self) -> None:
            commits.append("commit")

        def __exit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de"] = types.SimpleNamespace(
        db=types.SimpleNamespace(Transaction=Transaction)
    )
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: window,
        get_design_in_uu_from_window=lambda selected: design if selected is window else None,
    )

    result = runtime._dispatch(
        "design.live_patch",
        {
            "design": "demo_lib:Main:schematic",
            "patch_id": "patch-1",
            "operations": [
                {
                    "op": "set_instance_parameter",
                    "instance": "R1",
                    "parameter": "R",
                    "expected_before": "50 Ohm",
                    "value": "75 Ohm",
                }
            ],
        },
    )

    assert commits == ["commit"]
    assert parameter.value == "75 Ohm"
    assert result["readback"] == [
        {
            "instance": "R1",
            "parameter": "R",
            "before": "50 Ohm",
            "actual": "75 Ohm",
        }
    ]


def test_design_live_patch_adds_instance_and_wire_then_rolls_back_patch(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class Created:
        def __init__(self, collection=None, name=None):
            self.parameters = {"R": types.SimpleNamespace(value="50 Ohm")}
            self._collection = collection
            self._name = name
            self.deleted = False

        def delete_object(self):
            self.deleted = True
            if self._collection is not None:
                self._collection.pop(self._name, None)

    instances = {}
    wires = []

    def add_instance(item, at, **kwargs):
        assert item == ("ads_rflib", "R", "symbol")
        assert at == (1.0, 2.0)
        created = Created(instances, kwargs["name"])
        instances[kwargs["name"]] = created
        return created

    def add_wire(points):
        assert points == [(1.0, 2.0), (3.0, 2.0)]
        wire = Created()
        wire.add_wire_label = lambda label: setattr(wire, "label", label)
        wires.append(wire)
        return wire

    design = types.SimpleNamespace(
        lib_name="demo_lib",
        cell_name="Main",
        view_name="schematic",
        instances=instances,
        add_instance=add_instance,
        add_wire=add_wire,
    )

    class Transaction:
        def __init__(self, selected_design, label):
            assert selected_design is design
            assert "patch-objects" in label

        def __enter__(self):
            return self

        def commit(self):
            pass

        def __exit__(self, *_args):
            pass

    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de"] = types.SimpleNamespace(
        db=types.SimpleNamespace(Transaction=Transaction)
    )
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: object(),
        get_design_in_uu_from_window=lambda _window: design,
    )

    args = {
        "design": "demo_lib:Main:schematic",
        "patch_id": "patch-objects",
        "operations": [
            {
                "op": "add_instance",
                "name": "R_AGENT",
                "item": ["ads_rflib", "R", "symbol"],
                "at": [1.0, 2.0],
                "parameters": {"R": "75 Ohm"},
            },
            {
                "op": "add_wire",
                "points": [[1.0, 2.0], [3.0, 2.0]],
                "label": "AGENT_NET",
            },
        ],
    }
    created = runtime._dispatch("design.live_patch", args)
    preserved = runtime._dispatch("design.live_patch", args)

    assert created["reversible"] is True
    assert preserved["status"] == "preserved"
    assert instances["R_AGENT"].parameters["R"].value == "75 Ohm"
    assert wires[0].label == "AGENT_NET"

    rolled_back = runtime._dispatch(
        "design.live_finalize",
        {
            "design": "demo_lib:Main:schematic",
            "action": "rollback_patch",
            "patch_id": "patch-objects",
        },
    )

    assert rolled_back["action"] == "rollback_patch"
    assert "R_AGENT" not in instances
    assert wires[0].deleted is True


def test_design_live_patch_refuses_wrong_active_design(monkeypatch) -> None:
    server = load_server(monkeypatch)
    design = types.SimpleNamespace(
        lib_name="other_lib",
        cell_name="Main",
        view_name="schematic",
    )
    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de"] = types.SimpleNamespace(db=types.SimpleNamespace())
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: object(),
        get_design_in_uu_from_window=lambda window: design,
    )

    with pytest.raises(RuntimeError, match="Active ADS design mismatch"):
        runtime._dispatch(
            "design.live_patch",
            {
                "design": "demo_lib:Main:schematic",
                "operations": [
                    {
                        "op": "set_instance_parameter",
                        "instance": "R1",
                        "parameter": "R",
                        "expected_before": "50 Ohm",
                        "value": "75 Ohm",
                    }
                ],
            },
        )


def test_design_live_patch_can_activate_exact_named_design(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class Parameter:
        value = "50 Ohm"

    parameter = Parameter()
    design = types.SimpleNamespace(
        lib_name="demo_lib",
        cell_name="Main",
        view_name="schematic",
        instances={"R1": types.SimpleNamespace(parameters={"R": parameter})},
    )
    state = {"window": None}
    target_window = object()

    class Transaction:
        def __init__(self, selected_design, label) -> None:
            del selected_design, label

        def __enter__(self):
            return self

        def commit(self) -> None:
            pass

        def __exit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

    def bring_to_top(context) -> None:
        assert context == "design-context"
        state["window"] = target_window

    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de"] = types.SimpleNamespace(
        db=types.SimpleNamespace(Transaction=Transaction)
    )
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: state["window"],
        get_design_in_uu_from_window=lambda window: design
        if window is target_window
        else (_ for _ in ()).throw(RuntimeError("not a design window")),
    )
    runtime.namespace["ael"] = types.SimpleNamespace(
        call=types.SimpleNamespace(
            de_get_design_context_from_name=lambda name: (
                "design-context"
                if name == "demo_lib:Main:schematic"
                else None
            ),
            de_bring_context_to_top_or_open_new_window=bring_to_top,
        )
    )

    result = runtime._dispatch(
        "design.live_patch",
        {
            "design": "demo_lib:Main:schematic",
            "activate": True,
            "operations": [
                {
                    "op": "set_instance_parameter",
                    "instance": "R1",
                    "parameter": "R",
                    "expected_before": "50 Ohm",
                    "value": "75 Ohm",
                }
            ],
        },
    )

    assert result["status"] == "passed"
    assert parameter.value == "75 Ohm"


def test_context_capture_active_design_reuses_context_registry(monkeypatch) -> None:
    server = load_server(monkeypatch)
    design = types.SimpleNamespace()
    window = object()
    captured = {}
    registry = types.SimpleNamespace(
        capture_design=lambda observed, observed_window, surface: captured.update(
            design=observed,
            window=observed_window,
            surface=surface,
        )
        or {"context_id": "ctx_live", "target": {"kind": "design"}}
    )
    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: window,
        get_design_in_uu_from_window=lambda observed: design
        if observed is window
        else None,
    )
    runtime.contexts = registry

    result = runtime._context_capture_active_design()

    assert result["context_id"] == "ctx_live"
    assert captured == {
        "design": design,
        "window": window,
        "surface": "agent-active-design",
    }


def test_design_live_finalize_enforces_discard_ownership(monkeypatch) -> None:
    server = load_server(monkeypatch)
    calls = []
    design = types.SimpleNamespace(
        lib_name="demo_lib",
        cell_name="Main",
        view_name="schematic",
        save_design=lambda: calls.append("save"),
        revert_design=lambda: calls.append("discard"),
    )
    window = object()
    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: window,
        get_design_in_uu_from_window=lambda observed: design
        if observed is window
        else None,
    )
    args = {
        "design": "demo_lib:Main:schematic",
        "action": "discard_unsaved",
        "decision": {
            "authorization": "agent-owned-session",
            "reason": "Discard an agent-owned disposable candidate",
        },
    }

    monkeypatch.delenv("ADS_AGENT_MANAGED_SESSION_ID", raising=False)
    with pytest.raises(PermissionError, match="managed ADS session"):
        runtime._dispatch("design.live_finalize", args)

    monkeypatch.setenv("ADS_AGENT_MANAGED_SESSION_ID", "managed-1")
    result = runtime._dispatch("design.live_finalize", args)

    assert result["action"] == "discard_unsaved"
    assert calls == ["discard"]


def test_design_live_finalize_save_requires_explicit_decision(monkeypatch) -> None:
    server = load_server(monkeypatch)
    calls = []
    design = types.SimpleNamespace(
        lib_name="demo_lib",
        cell_name="Main",
        view_name="schematic",
        save_design=lambda: calls.append("save"),
    )
    runtime = server._Runtime("de", "slot-a")
    runtime.namespace["de_app"] = types.SimpleNamespace(
        current_window=lambda: object(),
        get_design_in_uu_from_window=lambda _window: design,
    )

    with pytest.raises(ValueError, match="decision object"):
        runtime._dispatch(
            "design.live_finalize",
            {"design": "demo_lib:Main:schematic", "action": "save"},
        )
    result = runtime._dispatch(
        "design.live_finalize",
        {
            "design": "demo_lib:Main:schematic",
            "action": "save",
            "decision": {
                "authorization": "user-confirmed",
                "reason": "User explicitly requested save",
            },
        },
    )

    assert result["action"] == "save"
    assert calls == ["save"]


def test_context_registry_commands_are_safe_and_handle_addressable(monkeypatch) -> None:
    server = load_server(monkeypatch)
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.slot = "unit"
    runtime.contexts = server.ContextRegistry("de", slot="unit")
    captured = runtime.contexts.capture_design(
        types.SimpleNamespace(
            lib_name="demo_lib",
            cell_name="amp",
            view_name="schematic",
            selected_objects=[],
        )
    )

    capabilities = runtime._dispatch("capabilities", {})
    fetched = runtime._dispatch("context_get", {"context": captured["context_ref"]["text"]})
    serialized = runtime.execute("context_get", {"context": captured["context_id"]})
    dropped = runtime._dispatch("context_drop", {"context": captured["context_id"]})

    assert "context_get" in capabilities["safe_commands"]
    assert fetched["context_id"] == captured["context_id"]
    assert serialized["result"]["target"]["identity"] == {
        "library": "demo_lib",
        "cell": "amp",
        "view": "schematic",
    }
    assert serialized["result"]["selection"]["items"] == []
    assert dropped["dropped"] is True


def test_context_command_rejects_handle_from_another_session(monkeypatch) -> None:
    server = load_server(monkeypatch)
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.slot = "unit"
    runtime.contexts = server.ContextRegistry("de", slot="unit")
    captured = runtime.contexts.capture_design(
        types.SimpleNamespace(
            lib_name="demo_lib",
            cell_name="amp",
            view_name="schematic",
            selected_objects=[],
        )
    )
    wrong_handle = captured["context_ref"]["text"].replace(
        "ADS_CONTEXT:v1:unit:de:", "ADS_CONTEXT:v1:other:de:"
    )

    rejected = runtime.execute("context_get", {"context": wrong_handle})

    assert rejected["ok"] is False
    assert "slot mismatch" in rejected["error"]


def test_bounded_open_workspace_never_switches_an_existing_workspace(tmp_path: Path, monkeypatch) -> None:
    server = load_server(monkeypatch)
    current = make_workspace(tmp_path, "Current_wrk")
    requested = make_workspace(tmp_path, "Requested_wrk")
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {"de": FakeDe(current)}

    with pytest.raises(RuntimeError, match="different workspace"):
        runtime._open_workspace({"workspace": str(requested)})

    assert runtime.namespace["de"].workspace == current
    assert runtime.namespace["de"].open_calls == []


def test_bounded_open_workspace_opens_and_verifies_empty_context(tmp_path: Path, monkeypatch) -> None:
    server = load_server(monkeypatch)
    requested = make_workspace(tmp_path, "Requested_wrk")
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {"de": FakeDe()}

    result = runtime._open_workspace({"workspace": str(requested)})

    assert result["opened"] is True
    assert result["verified"] is True
    assert result["bounded"] is True


def test_safe_shutdown_prompts_before_scheduling_exit(monkeypatch) -> None:
    server = load_server(monkeypatch)
    calls: list[object] = []
    de_app = types.SimpleNamespace(
        prompt_and_save_modified_workspace=lambda: calls.append("prompt") or True,
        exit_application=lambda code=0: calls.append(("exit", code)),
    )
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {"de_app": de_app}
    runtime._modal_state = lambda: {"modal_blocking": False}

    result = runtime._safe_shutdown()

    assert result["accepted"] is True
    assert result["state"] == "scheduled"
    assert runtime._shutdown_status()["state"] == "exiting"
    assert calls == ["prompt", ("exit", 0)]


def test_safe_shutdown_honors_user_cancel(monkeypatch) -> None:
    server = load_server(monkeypatch)
    de_app = types.SimpleNamespace(
        prompt_and_save_modified_workspace=lambda: False,
        exit_application=lambda code=0: (_ for _ in ()).throw(AssertionError(f"must not exit: {code}")),
    )
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {"de_app": de_app}
    runtime._modal_state = lambda: {"modal_blocking": False}

    result = runtime._safe_shutdown()

    assert result["accepted"] is True
    assert result["state"] == "scheduled"
    assert runtime._shutdown_status() == {"state": "cancelled", "reason": "user_cancelled"}


def test_status_reports_visible_windows_without_clicking_or_classifying_them(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class FakeWidget:
        def __init__(self, title: str, visible: bool = True) -> None:
            self.title = title
            self.visible = visible

        def windowTitle(self) -> str:
            return self.title

        def isVisible(self) -> bool:
            return self.visible

    main = FakeWidget("ADS - Demo_wrk")
    hidden = FakeWidget("Hidden", False)
    application = types.SimpleNamespace(
        activeModalWidget=lambda: None,
        activeWindow=lambda: main,
        topLevelWidgets=lambda: [main, hidden],
    )
    server.QtWidgets.QApplication.instance = lambda: application
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.slot = "test"
    runtime.namespace = {}

    result = runtime._status()

    assert result["ui"]["application_ready"] is True
    assert result["ui"]["visible_window_count"] == 1
    assert result["ui"]["active_window"]["title"] == "ADS - Demo_wrk"
    assert result["ui"]["windows"][0]["class_name"] == "FakeWidget"
    assert result["shutdown"] == {"state": "idle"}


def test_runtime_snapshot_is_compact_and_revision_aware(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HPEESOF_DIR", raising=False)
    server = load_server(monkeypatch)
    workspace = make_workspace(tmp_path, "Snapshot_wrk")
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.slot = "snapshot"
    runtime.namespace = {"de": FakeDe(workspace)}
    runtime.contexts = server.ContextRegistry("de", slot="snapshot")
    runtime.contexts.capture_design(
        types.SimpleNamespace(
            lib_name="demo_lib",
            cell_name="amp",
            view_name="schematic",
            selected_objects=[],
        )
    )
    runtime.contexts.list = lambda: (_ for _ in ()).throw(
        AssertionError("compact snapshot must not copy the full context registry")
    )

    first = runtime._dispatch("runtime_snapshot", {"detail": "compact"})
    wire_response = runtime.execute("runtime_snapshot", {"detail": "compact"})
    unchanged = runtime._dispatch(
        "runtime_snapshot",
        {"detail": "compact", "since_revision": first["state_revision"]},
    )

    assert first["schema_version"] == 1
    assert first["changed"] is True
    assert first["identity"] == {
        "slot": "snapshot",
        "profile": "de",
        "pid": first["identity"]["pid"],
        "hpeesof_dir": None,
        "display": None,
    }
    assert first["state"]["workspace"] == {"is_open": True, "path": str(workspace)}
    assert first["state"]["contexts"]["count"] == 1
    assert first["state"]["contexts"]["latest"]["target"]["identity"] == {
        "library": "demo_lib",
        "cell": "amp",
        "view": "schematic",
    }
    assert "windows" not in first["state"]["ui"]
    assert len(json.dumps(first, ensure_ascii=False).encode("utf-8")) < 16 * 1024
    assert first["capability_states"]["runtime_snapshot"]["available"] is True
    assert wire_response["ok"] is True
    assert wire_response["result"]["capability_states"]["runtime_snapshot"]["safe_next_actions"] == []
    assert unchanged == {
        "schema_version": 1,
        "captured_at": unchanged["captured_at"],
        "state_revision": first["state_revision"],
        "changed": False,
        "identity": first["identity"],
    }


def test_capability_descriptors_explain_runtime_and_authorization_state(monkeypatch) -> None:
    server = load_server(monkeypatch)
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "dds"
    runtime.slot = "dds-unit"
    runtime.namespace = {"dds": types.SimpleNamespace(get_dds_files=lambda: [])}
    runtime.contexts = server.ContextRegistry("dds", slot="dds-unit")

    payload = runtime._dispatch("capabilities", {})
    descriptors = {item["id"]: item for item in payload["descriptors"]}

    assert payload["descriptor_schema_version"] == 1
    assert "runtime_snapshot" in payload["safe_commands"]
    assert descriptors["runtime_snapshot"]["state"] == {
        "declared": True,
        "compatible": True,
        "available": True,
        "healthy": True,
        "authorized": True,
        "reason": None,
        "safe_next_actions": [],
    }
    assert descriptors["open_workspace"]["state"]["reason"] == "profile_not_supported"
    assert descriptors["eval"]["state"]["available"] is False
    assert descriptors["eval"]["state"]["authorized"] is False
    assert descriptors["eval"]["state"]["reason"] == "unsafe_opt_in_required"


def test_dialog_snapshot_and_action_use_exact_fingerprint_and_button_id(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class FakeLabel:
        def text(self) -> str:
            return "The operation completed."

    class FakeButton:
        clicked = False

        def objectName(self) -> str:
            return "okButton"

        def text(self) -> str:
            return "OK"

        def accessibleName(self) -> str:
            return "Confirm"

        def toolTip(self) -> str:
            return ""

        def isVisible(self) -> bool:
            return True

        def isEnabled(self) -> bool:
            return True

        def click(self) -> None:
            self.clicked = True

    class FakeButtonBox:
        def standardButton(self, _button) -> int:
            return 0x00000400

        def buttonRole(self, _button) -> int:
            return 0

    class FakeGeometry:
        x = lambda self: 10
        y = lambda self: 20
        width = lambda self: 300
        height = lambda self: 120

    button = FakeButton()
    label = FakeLabel()
    box = FakeButtonBox()

    class FakeDialog:
        title = "Information"

        def objectName(self) -> str:
            return "messageBox"

        def windowTitle(self) -> str:
            return self.title

        def frameGeometry(self):
            return FakeGeometry()

        def findChildren(self, child_type):
            if child_type is FakeLabel:
                return [label]
            if child_type is FakeButton:
                return [button]
            if child_type is FakeButtonBox:
                return [box]
            return []

    dialog = FakeDialog()
    application = types.SimpleNamespace(activeModalWidget=lambda: dialog)
    server.QtWidgets.QApplication.instance = lambda: application
    server.QtWidgets.QLabel = FakeLabel
    server.QtWidgets.QAbstractButton = FakeButton
    server.QtWidgets.QDialogButtonBox = FakeButtonBox
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {}

    snapshot = runtime._dialog_snapshot()
    result = runtime._dialog_action(
        {
            "dialog_fingerprint": snapshot["dialog_fingerprint"],
            "button_id": snapshot["buttons"][0]["button_id"],
            "decision": {"risk": "low", "authorization": "automatic", "reason": "Acknowledge information"},
        }
    )

    assert snapshot["labels"] == ["The operation completed."]
    assert snapshot["buttons"][0]["standard_button"] == 0x00000400
    assert snapshot["buttons"][0]["risk_floor"] == "low"
    assert result["accepted"] is True
    assert button.clicked is True
    assert runtime._dialog_action_status()["state"] == "actuated"

    dialog.title = "Changed dialog"
    with pytest.raises(RuntimeError, match="changed after observation"):
        runtime._dialog_action(
            {
                "dialog_fingerprint": snapshot["dialog_fingerprint"],
                "button_id": snapshot["buttons"][0]["button_id"],
                "decision": {"risk": "low", "authorization": "automatic", "reason": "Stale action"},
            }
        )


def test_dialog_action_revalidates_fingerprint_at_actuation_time(monkeypatch) -> None:
    server = load_server(monkeypatch)
    callbacks = []
    monkeypatch.setattr(server.QtCore.QTimer, "singleShot", lambda _delay, callback: callbacks.append(callback))

    class FakeButton:
        clicked = False

        def click(self) -> None:
            self.clicked = True

    button = FakeButton()
    button_summary = {
        "button_id": "button-1",
        "visible": True,
        "enabled": True,
        "risk_floor": "low",
    }
    observed = {
        "present": True,
        "dialog_fingerprint": "observed-dialog",
        "buttons": [button_summary],
    }
    changed = {
        "present": True,
        "dialog_fingerprint": "changed-dialog",
        "buttons": [button_summary],
    }
    current = {"snapshot": observed}
    runtime = server._Runtime.__new__(server._Runtime)
    runtime._dialog_snapshot_data = lambda _include_image=False: current["snapshot"]
    runtime._click_fresh_dialog_button = lambda _expected: True

    result = runtime._dialog_action(
        {
            "dialog_fingerprint": "observed-dialog",
            "button_id": "button-1",
            "decision": {"risk": "low", "authorization": "automatic", "reason": "Acknowledge"},
        }
    )
    current["snapshot"] = changed
    callbacks[0]()

    assert result["state"] == "scheduled"
    assert button.clicked is False
    assert runtime._dialog_action_status() == {
        "state": "rejected",
        "reason": "dialog_changed_before_actuation",
        "dialog_fingerprint": "observed-dialog",
        "observed_fingerprint": "changed-dialog",
        "button_id": "button-1",
    }


def test_actuation_reacquires_button_after_ads_invalidates_observed_wrappers(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class FakeButton:
        def __init__(self, valid: bool) -> None:
            self.valid = valid
            self.clicked = False

        def objectName(self): return "cancel"
        def text(self): return "Cancel"
        def isVisible(self): return self.valid
        def isEnabled(self): return self.valid

        def click(self):
            assert self.valid
            self.clicked = True

    stale = FakeButton(False)
    fresh = FakeButton(True)

    class FakeDialog:
        def findChildren(self, child_type):
            return [fresh] if child_type is FakeButton else []

    server.QtWidgets.QAbstractButton = FakeButton
    server.QtWidgets.QApplication.instance = lambda: types.SimpleNamespace(
        activeModalWidget=lambda: FakeDialog()
    )
    button_summary = {
        "button_id": "cancel-id",
        "index": 0,
        "class_name": "FakeButton",
        "object_name": "cancel",
        "text": "Cancel",
        "visible": True,
        "enabled": True,
        "risk_floor": "low",
    }
    snapshot = {
        "present": True,
        "dialog_fingerprint": "same-dialog",
        "buttons": [button_summary],
    }
    runtime = server._Runtime.__new__(server._Runtime)
    runtime._dialog_snapshot_data = lambda _include_image=False: snapshot

    runtime._actuate_dialog_button("same-dialog", "cancel-id")

    assert stale.clicked is False
    assert fresh.clicked is True
    assert runtime._dialog_action_status()["state"] == "actuated"


@pytest.mark.parametrize(
    ("standard_button", "button_role"),
    [
        (0x00010000, 0),  # No
        (0x00020000, 0),  # NoToAll
        (0, 6),  # NoRole
    ],
)
def test_negative_qt_buttons_have_medium_risk_floor(
    monkeypatch, standard_button: int, button_role: int
) -> None:
    server = load_server(monkeypatch)

    class FakeButton:
        def objectName(self): return "negative"
        def text(self): return "No"
        def accessibleName(self): return ""
        def toolTip(self): return ""
        def isVisible(self): return True
        def isEnabled(self): return True

    class FakeButtonBox:
        def standardButton(self, _button): return standard_button
        def buttonRole(self, _button): return button_role

    button = FakeButton()
    box = FakeButtonBox()

    class FakeDialog:
        def findChildren(self, child_type):
            return [box] if child_type is FakeButtonBox else []

    server.QtWidgets.QDialogButtonBox = FakeButtonBox
    runtime = server._Runtime.__new__(server._Runtime)

    assert runtime._button_summary(FakeDialog(), button, 0)["risk_floor"] == "medium"


def test_dialog_action_enforces_qt_destructive_role_risk_floor(monkeypatch) -> None:
    server = load_server(monkeypatch)

    class FakeButton:
        def objectName(self): return "discard"
        def text(self): return "Discard"
        def accessibleName(self): return ""
        def toolTip(self): return ""
        def isVisible(self): return True
        def isEnabled(self): return True
        def click(self): raise AssertionError("must not click")

    class FakeButtonBox:
        def standardButton(self, _button): return 0x00800000
        def buttonRole(self, _button): return 2

    button = FakeButton()
    box = FakeButtonBox()

    class FakeDialog:
        def objectName(self): return "warning"
        def windowTitle(self): return "Unsaved changes"
        def frameGeometry(self): raise RuntimeError("not needed")
        def findChildren(self, child_type):
            if child_type is FakeButton:
                return [button]
            if child_type is FakeButtonBox:
                return [box]
            return []

    application = types.SimpleNamespace(activeModalWidget=lambda: FakeDialog())
    server.QtWidgets.QApplication.instance = lambda: application
    server.QtWidgets.QLabel = type("FakeLabel", (), {})
    server.QtWidgets.QAbstractButton = FakeButton
    server.QtWidgets.QDialogButtonBox = FakeButtonBox
    runtime = server._Runtime.__new__(server._Runtime)
    runtime.profile = "de"
    runtime.namespace = {}
    snapshot = runtime._dialog_snapshot()

    with pytest.raises(PermissionError, match="at least 'high' risk"):
        runtime._dialog_action(
            {
                "dialog_fingerprint": snapshot["dialog_fingerprint"],
                "button_id": snapshot["buttons"][0]["button_id"],
                "decision": {"risk": "low", "authorization": "automatic", "reason": "Unsafe"},
            }
        )
