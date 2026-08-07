from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


CONTEXT_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "ads_agent_bridge"
    / "addon"
    / "AdsAgentBridge"
    / "context.py"
)
SPEC = importlib.util.spec_from_file_location("ads_agent_context_test", CONTEXT_PATH)
context = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(context)


class Design:
    lib_name = "demo_lib"
    cell_name = "amplifier"
    view_name = "schematic"

    def __init__(self):
        self.selected_objects = [SimpleNamespace(name="R1")]


class WorkspaceItem:
    def __init__(self, *, path="", kind="file", item_type=""):
        self.full_path_name = path
        self.name = Path(path).name if path else kind
        self.item_type = SimpleNamespace(name=item_type) if item_type else ""
        for name in ("workspace", "folder", "library", "cell", "view"):
            setattr(self, "is_" + name, name == kind)
        self.lib_name = "demo_lib" if kind in ("library", "cell", "view") else ""
        self.cell_name = "amp" if kind in ("cell", "view") else ""
        self.view_name = "schematic" if kind == "view" else ""


def test_design_capture_is_bounded_reusable_and_refreshable():
    registry = context.ContextRegistry("de", slot="candidate", instance_id="ads2025")
    design = Design()

    first = registry.capture_design(design)
    design.selected_objects = [SimpleNamespace(name="R2"), SimpleNamespace(name="C1")]
    second = registry.capture_design(design)

    assert first["context_id"] == second["context_id"]
    assert second["freshness"]["generation"] == 2
    assert second["target"] == {
        "kind": "design",
        "identity": {"library": "demo_lib", "cell": "amplifier", "view": "schematic"},
        "display_name": "demo_lib:amplifier:schematic",
    }
    assert second["selection"]["count"] == 2
    assert second["selection"]["count_is_exact"] is True
    assert "ADS_CONTEXT:v1:candidate:de:ctx-0001:" in second["context_ref"]["text"]
    assert "token" not in str(second).lower()

    design.selected_objects.append(SimpleNamespace(name="L1"))
    refreshed = registry.refresh(first["context_ref"]["text"])
    assert refreshed["selection"]["count"] == 3
    assert refreshed["freshness"]["generation"] == 3


def test_registry_uses_managed_instance_identity_before_install_root(monkeypatch):
    monkeypatch.setenv("ADS_AGENT_INSTANCE_ID", "ads-2026-u2-managed")
    monkeypatch.setenv("HPEESOF_DIR", "C:/Keysight/ADS2026_Update2")

    registry = context.ContextRegistry("de", slot="candidate")
    captured = registry.capture_design(Design())

    assert captured["session"]["instance_id"] == "ads-2026-u2-managed"


def test_workspace_tree_distinguishes_live_dds_from_file_reference():
    registry = context.ContextRegistry("de", slot="candidate")
    dds_item = WorkspaceItem(path="C:/wrk/data/display.dds", item_type="DDS")

    captured = registry.capture_workspace_items([dds_item], workspace_path="C:/wrk/demo_wrk")

    assert captured["source"]["surface"] == "workspace-tree"
    assert captured["target"]["kind"] == "dds-file-ref"
    assert captured["freshness"]["state"] == "re-resolvable"
    assert captured["capabilities"]["open"] == "requires-authorization"


def test_workspace_multi_selection_becomes_context_set():
    registry = context.ContextRegistry("de")
    items = [
        WorkspaceItem(path="C:/wrk/demo_wrk/networks", kind="folder"),
        WorkspaceItem(path="C:/wrk/demo_wrk/data/out.ds", item_type="DS"),
    ]

    captured = registry.capture_workspace_items(items)

    assert captured["target"]["kind"] == "context-set"
    assert captured["selection"]["count"] == 2
    assert captured["selection"]["homogeneous"] is False


def test_summary_returns_only_latest_context_and_registry_bounds():
    registry = context.ContextRegistry("de", slot="candidate", limit=4)
    registry.capture_design(
        SimpleNamespace(lib_name="lib", cell_name="first", view_name="schematic", selected_objects=[])
    )
    latest = registry.capture_design(
        SimpleNamespace(lib_name="lib", cell_name="second", view_name="layout", selected_objects=[])
    )

    summary = registry.summary()

    assert summary["count"] == 2
    assert summary["max_contexts"] == 4
    assert summary["latest"]["context_id"] == latest["context_id"]
    assert summary["latest"]["target"]["identity"]["cell"] == "second"


def test_dds_empty_selection_is_valid_and_page_change_marks_context_stale():
    registry = context.ContextRegistry("dds", slot="candidate")
    dds_file = SimpleNamespace(data_path="C:/wrk/demo_wrk/data/", name="report", selected_objects=[])
    window = SimpleNamespace(current_page=SimpleNamespace(name="Main"))

    captured = registry.capture_dds(dds_file, window)

    assert captured["target"]["kind"] == "dds-page"
    assert captured["selection"]["count"] == 0
    window.current_page = SimpleNamespace(name="Summary")
    refreshed = registry.refresh(captured["context_id"])
    assert refreshed["freshness"]["state"] == "stale"
    assert refreshed["freshness"]["reason"] == "active_dds_page_changed"


def test_registry_evicts_oldest_and_drop_is_idempotent():
    registry = context.ContextRegistry("de", limit=2)
    first = registry.capture_workspace_items([WorkspaceItem(path="C:/one")])
    registry.capture_workspace_items([WorkspaceItem(path="C:/two")])
    registry.capture_workspace_items([WorkspaceItem(path="C:/three")])

    assert len(registry.list()) == 2
    try:
        registry.get(first["context_id"])
    except KeyError:
        pass
    else:
        raise AssertionError("oldest context was not evicted")
    current = registry.list()[0]
    assert registry.drop(current["context_ref"]["text"]) is True
    assert registry.drop(current["context_id"]) is False


@pytest.mark.parametrize("operation", ["get", "refresh", "drop"])
def test_handle_rejects_a_different_session_slot(operation):
    registry = context.ContextRegistry("de", slot="slot-a")
    captured = registry.capture_design(Design())
    wrong_handle = captured["context_ref"]["text"].replace(
        "ADS_CONTEXT:v1:slot-a:de:", "ADS_CONTEXT:v1:slot-b:de:"
    )

    with pytest.raises(ValueError, match="slot mismatch"):
        getattr(registry, operation)(wrong_handle)


def test_handle_rejects_a_different_profile_and_malformed_handle():
    registry = context.ContextRegistry("de", slot="slot-a")
    captured = registry.capture_design(Design())
    wrong_profile = captured["context_ref"]["text"].replace(
        "ADS_CONTEXT:v1:slot-a:de:", "ADS_CONTEXT:v1:slot-a:dds:"
    )

    with pytest.raises(ValueError, match="profile mismatch"):
        registry.get(wrong_profile)
    with pytest.raises(ValueError, match="malformed"):
        registry.get("ADS_CONTEXT:v2:slot-a:de:ctx-0001:anything")


def test_selection_serialization_is_bounded():
    registry = context.ContextRegistry("de")
    design = Design()
    design.selected_objects = [SimpleNamespace(name="item-{0}".format(index)) for index in range(80)]

    captured = registry.capture_design(design)

    assert captured["selection"]["count"] == 80
    assert captured["selection"]["count_is_exact"] is True
    assert len(captured["selection"]["items"]) == context.MAX_SELECTION_ITEMS
    assert captured["selection"]["truncated"] is True


def test_generic_selection_iterator_reads_only_one_item_past_the_bound():
    registry = context.ContextRegistry("de")
    design = Design()
    observed = []

    def selected_objects():
        for index in range(1000):
            observed.append(index)
            yield SimpleNamespace(name="item-{0}".format(index))

    design.selected_objects = selected_objects()
    captured = registry.capture_design(design)

    assert len(observed) == context.MAX_SELECTION_ITEMS + 1
    assert captured["selection"]["count"] == context.MAX_SELECTION_ITEMS + 1
    assert captured["selection"]["count_is_exact"] is False
    assert len(captured["selection"]["items"]) == context.MAX_SELECTION_ITEMS
    assert captured["selection"]["truncated"] is True


def test_workspace_context_set_identity_is_also_bounded():
    registry = context.ContextRegistry("de")
    items = [WorkspaceItem(path="C:/item-{0}".format(index)) for index in range(80)]

    captured = registry.capture_workspace_items(items)

    assert captured["target"]["identity"]["count"] == 80
    assert captured["target"]["identity"]["count_is_exact"] is True
    assert captured["target"]["identity"]["truncated"] is True
    assert len(captured["target"]["identity"]["items"]) == context.MAX_SELECTION_ITEMS
