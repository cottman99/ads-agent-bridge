import hashlib

import pytest

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
