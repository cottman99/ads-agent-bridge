import hashlib
from types import SimpleNamespace

import pytest

from ads_agent_bridge import native_program
from ads_agent_bridge.native_program import _validate_ads_plan


def _program(entrypoint: str):
    source = f"def {entrypoint}(api, context):\n    return {{'status': 'passed'}}\n"
    return {
        "language": "python",
        "source": source,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }


def _observe():
    return {
        "schema_version": "eda.native-program/v1",
        "mode": "background",
        "program_id": "inspect_workspace",
        "runtime": "ads.python.de",
        "effect": "observe",
        "program": _program("run"),
        "scope": {
            "resource_kind": "ads-workspace",
            "selectors": {"instance": "ads2027", "version": "2027", "profile": "de"},
            "read_paths": ["/work/demo_wrk"],
            "write_paths": [],
            "artifacts": [],
        },
        "transaction": {
            "strategy": "none",
            "source_fingerprints": {},
            "fresh_reopen": False,
            "promotion": "none",
        },
        "validation": {"program": None, "required_artifacts": []},
        "limits": {"timeout_seconds": 60, "max_output_bytes": 65536},
    }


def test_ads_native_program_accepts_exact_official_runtime():
    assert _validate_ads_plan(_observe())["runtime"] == "ads.python.de"


def test_ads_native_program_rejects_profile_runtime_mismatch():
    plan = _observe()
    plan["scope"]["selectors"]["profile"] = "dds"
    with pytest.raises(ValueError, match="do not match"):
        _validate_ads_plan(plan)


def test_ads_native_program_accepts_standard_library_imports():
    plan = _observe()
    source = "import subprocess\ndef run(api, context):\n    return {}\n"
    plan["program"] = {
        "language": "python",
        "source": source,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    assert _validate_ads_plan(plan)["program"]["source"] == source


@pytest.mark.parametrize(
    "module",
    [
        "keysight.ads.dataset",
        "keysight.ads.subst",
        "keysight.ads.subst.substrate",
        "keysight.edatoolbox",
        "keysight.edatoolbox.ads",
    ],
)
def test_ads_native_program_accepts_required_official_simulation_imports(module):
    plan = _observe()
    source = f"import {module}\ndef run(api, context):\n    return {{'status': 'passed'}}\n"
    plan["program"] = {
        "language": "python",
        "source": source,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    assert _validate_ads_plan(plan)["program"]["source"] == source


def test_continuation_fingerprint_is_checked_before_program_runs(tmp_path, monkeypatch):
    workspace = tmp_path / "source_wrk"
    workspace.mkdir()
    plan = _observe()
    plan["scope"]["read_paths"] = [str(workspace)]
    monkeypatch.setattr(
        native_program,
        "select_instance",
        lambda _value: SimpleNamespace(
            instance_id="ads2027",
            year=2027,
            product_version="2027",
            python_executable="ads-python",
        ),
    )
    monkeypatch.setattr(native_program, "workspace_fingerprint", lambda _path: "b" * 64)
    monkeypatch.setattr(
        native_program,
        "_run_program",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale continuation must fail before native code")
        ),
    )

    with pytest.raises(ValueError, match="content state does not match"):
        from eda_bridge_runtime.lease import LeaseStore

        store = LeaseStore(tmp_path / "leases.sqlite3")
        lease = store.acquire(str(workspace), "test-owner")
        native_program.execute_native_program(
            plan,
            expected_source_fingerprint="a" * 64,
            admission={
                "store": str(tmp_path / "leases.sqlite3"),
                "leases": [lease.__dict__],
            },
        )


@pytest.mark.parametrize(
    ("selector", "matches"),
    [
        ("2026", True),
        ("2026 Update 2", True),
        ("ADS 2026 Update 2", True),
        ("2026 Update 1", False),
        ("2025", False),
    ],
)
def test_instance_version_selectors_preserve_update_identity(selector, matches):
    instance = SimpleNamespace(year=2026, product_version="ADS 2026 Update 2")

    assert (selector in native_program._instance_version_selectors(instance)) is matches


def test_ads_native_worker_uses_shared_execution_engine():
    from pathlib import Path

    source = Path(native_program.__file__).with_name("native_program_worker.py").read_text()
    assert "from eda_bridge_runtime.python_execution import execute_python" in source
    assert "_ALLOWED_IMPORTS" not in source
