import hashlib
from types import SimpleNamespace

import pytest

from ads_agent_bridge import native_batch
from ads_agent_bridge.native_batch import _validate_ads_plan


def _program(entrypoint: str):
    source = f"def {entrypoint}(api, context):\n    return {{'status': 'passed'}}\n"
    return {
        "language": "python",
        "source": source,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }


def _observe():
    return {
        "schema_version": "eda.native-batch/v1",
        "batch_id": "inspect_workspace",
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


def test_ads_native_batch_accepts_exact_official_runtime():
    assert _validate_ads_plan(_observe())["runtime"] == "ads.python.de"


def test_ads_native_batch_rejects_profile_runtime_mismatch():
    plan = _observe()
    plan["scope"]["selectors"]["profile"] = "dds"
    with pytest.raises(ValueError, match="do not match"):
        _validate_ads_plan(plan)


def test_ads_native_batch_rejects_shell_import():
    plan = _observe()
    source = "import subprocess\ndef run(api, context):\n    return {}\n"
    plan["program"] = {
        "language": "python",
        "source": source,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    with pytest.raises(ValueError, match="undeclared module"):
        _validate_ads_plan(plan)


def test_continuation_fingerprint_is_checked_before_program_runs(tmp_path, monkeypatch):
    workspace = tmp_path / "source_wrk"
    workspace.mkdir()
    plan = _observe()
    plan["scope"]["read_paths"] = [str(workspace)]
    monkeypatch.setattr(
        native_batch,
        "select_instance",
        lambda _value: SimpleNamespace(
            instance_id="ads2027",
            year=2027,
            product_version="2027",
            python_executable="ads-python",
        ),
    )
    monkeypatch.setattr(native_batch, "workspace_fingerprint", lambda _path: "b" * 64)
    monkeypatch.setattr(
        native_batch,
        "_run_program",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale continuation must fail before native code")
        ),
    )

    with pytest.raises(ValueError, match="content state does not match"):
        native_batch.execute_native_batch(plan, expected_source_fingerprint="a" * 64)


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

    assert (selector in native_batch._instance_version_selectors(instance)) is matches
