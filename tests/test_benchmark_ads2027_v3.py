from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _runner():
    path = Path(__file__).parents[1] / "scripts" / "benchmark_ads2027_v3.py"
    spec = importlib.util.spec_from_file_location("benchmark_ads2027_v3", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v3_contract_compares_mcp_surfaces_without_legacy_cli():
    root = Path(__file__).parents[1]
    contract = json.loads(
        (root / "docs" / "benchmarks" / "ads2027-v3-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(contract["arms"]) == {"runtime", "official"}
    assert "EDA Runtime MCP" in contract["arms"]["runtime"]["surface"]
    assert "ads-agent CLI task execution" in contract["arms"]["runtime"]["forbidden"]
    assert contract["cases"]["E3"]["common_acceptance"]["simulation_count"] == 1


def test_schedule_is_serial_and_counterbalanced():
    runner = _runner()
    observed = list(
        runner.schedule(["runtime", "official"], ["codex", "pi"], ["K1"], 2)
    )
    assert len(observed) == 8
    assert [row[3] for row in observed[:2]] == ["runtime", "official"]
    assert [row[3] for row in observed[4:6]] == ["official", "runtime"]


def test_run_campaign_has_an_isolated_directory_component():
    runner = _runner()
    assert "campaign" in runner.execute_one.__annotations__


def test_runtime_validation_rejects_cli_and_official_surface(tmp_path: Path):
    runner = _runner()
    answer = {
        "case_id": "K1",
        "answer": "Use Runtime MCP eda.submit with native.batch in no-GUI mode and read a finite dataset sample.",
        "code": "",
        "sources": [],
    }
    events = [
        {"item": {"type": "command_execution", "command": "ads-agent quickstart"}},
        {"item": {"type": "mcp_tool_call", "name": "mcp__ads__start_local_session"}},
    ]
    errors = runner.validate("K1", "runtime", tmp_path, answer, events)
    assert "runtime arm crossed into official MCP" in errors
    assert "runtime arm used CLI or shell" in errors


def test_prompt_requires_run_unique_idempotency_key(tmp_path: Path):
    runner = _runner()
    contract = json.loads(
        (
            Path(__file__).parents[1]
            / "docs"
            / "benchmarks"
            / "ads2027-v3-contract.json"
        ).read_text(encoding="utf-8")
    )
    prompt = runner.prompt_for(contract, "runtime", "E3", tmp_path)
    assert "derive a unique key from this RUN_DIRECTORY" in prompt


def test_validation_ignores_surface_names_in_prompt_and_checks_actual_tools(
    tmp_path: Path,
):
    runner = _runner()
    answer = {
        "case_id": "K1",
        "answer": "Use Runtime MCP native.batch in automation mode and read a finite dataset sample.",
        "code": "",
        "sources": [],
    }
    events = [
        {"type": "message_start", "prompt": "Do not invoke ads-agent CLI or official MCP"},
        {"type": "tool_execution_start", "toolName": "eda_read"},
    ]
    assert runner.validate("K1", "runtime", tmp_path, answer, events) == []


def test_timing_facts_exclude_agent_supplied_wait_values():
    runner = _runner()
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "arguments": {"wait": {"timeout_ms": 300000}},
                "result": {"structured_content": {"client_transport_ms": 12.5}},
            },
        }
    ]
    facts = runner.event_facts(events, "codex")
    assert facts["timing_ms"] == {"client_transport_ms": [12.5]}


def test_pi_timing_facts_ignore_capability_template_values():
    runner = _runner()
    events = [
        {
            "type": "tool_execution_end",
            "result": {
                "details": {
                    "runtime": {
                        "client_transport_ms": 7.5,
                        "response": {
                            "result": {
                                "data": {
                                    "bridge": {
                                        "template": {"wait": {"timeout_ms": 300000}},
                                        "timing": {"native_total_ms": 2500.0},
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
    ]
    facts = runner.event_facts(events, "pi")
    assert facts["timing_ms"] == {
        "client_transport_ms": [7.5],
        "native_total_ms": [2500.0],
    }


def test_event_facts_records_each_completed_tool_once_with_elapsed_time():
    runner = _runner()
    events = [
        {
            "type": "item.started",
            "_benchmark_received_ms": 100.0,
            "item": {
                "id": "item_1",
                "type": "mcp_tool_call",
                "tool": "eda.submit",
                "arguments": {"operation": "native.batch"},
            },
        },
        {
            "type": "item.completed",
            "_benchmark_received_ms": 2600.0,
            "item": {
                "id": "item_1",
                "type": "mcp_tool_call",
                "tool": "eda.submit",
                "arguments": {"operation": "native.batch"},
                "result": {},
            },
        },
    ]
    facts = runner.event_facts(events, "codex")
    assert facts["tool_names"] == ["eda.submit"]
    assert facts["timing_ms"] == {"tool_native_batch_ms": [2500.0]}


def test_k6_requires_the_documented_ads2027_drc_flow(tmp_path: Path):
    runner = _runner()
    affirmative = {
        "case_id": "K6",
        "answer": (
            "Yes. The documented flow uses create_drc_job and run_drc_job. "
            "Verify the experimental import; fallback to the GUI."
        ),
        "code": "",
        "sources": ["docs:design/design_verification"],
    }
    negative = {
        "case_id": "K6",
        "answer": (
            "No documented API is established in this source. Verify the exact "
            "symbol; fallback to the GUI."
        ),
        "code": "",
        "sources": ["ads-doc:v1:example"],
    }
    assert runner.validate("K6", "runtime", tmp_path, affirmative, []) == []
    assert runner.validate("K6", "runtime", tmp_path, negative, []) == [
        "K6 contradicts the documented ADS 2027 Python DRC capability",
        "K6 lacks the documented DRC API flow",
    ]

    ael_call_flow = {
        "case_id": "K6",
        "answer": "Established through the documented AEL-call Python bridge. Verify once; fallback to GUI.",
        "code": "job = ael.call.dve_create_drc_job(); ael.call.dve_job_run_drc(job, design)",
        "sources": ["ADS 2027 Automating Design Verification using Python"],
    }
    assert runner.validate("K6", "runtime", tmp_path, ael_call_flow, []) == []


def test_codex_oauth_is_normalized_for_pi_without_changing_source(tmp_path: Path):
    runner = _runner()
    source = tmp_path / "codex-auth.json"
    destination = tmp_path / "pi-auth.json"
    payload = {"exp": 2_000_000_000}
    encoded = __import__("base64").urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    original = {
        "tokens": {
            "access_token": f"x.{encoded}.x",
            "refresh_token": "refresh",
            "account_id": "account",
        }
    }
    source.write_text(json.dumps(original), encoding="utf-8")
    runner.copy_agent_auth(source, destination, "pi")
    normalized = json.loads(destination.read_text(encoding="utf-8"))["openai-codex"]
    assert normalized == {
        "type": "oauth",
        "refresh": "refresh",
        "access": f"x.{encoded}.x",
        "expires": 2_000_000_000_000,
        "accountId": "account",
    }
    assert json.loads(source.read_text(encoding="utf-8")) == original


def test_execution_validation_requires_real_artifacts_and_one_simulation(
    tmp_path: Path,
):
    runner = _runner()
    workspace = tmp_path / "work" / "demo_wrk"
    dataset = workspace / "data" / "accepted.ds"
    dataset.mkdir(parents=True)
    answer = {
        "case_id": "E3",
        "workspace": str(workspace),
        "dataset": str(dataset),
        "simulation_count": 1,
        "simulation_completed": True,
        "dataset_read_back": True,
        "numeric_sample": 0.5,
        "gui_launched": False,
        "evidence": ["dataset opened"],
    }
    assert runner.validate("E3", "official", tmp_path / "work", answer, []) == []
    answer["simulation_count"] = 2
    assert "E3 acceptance mismatch: simulation_count" in runner.validate(
        "E3", "official", tmp_path / "work", answer, []
    )


def test_execution_validation_resolves_one_relative_runtime_artifact(tmp_path: Path):
    runner = _runner()
    work = tmp_path / "work"
    workspace = work / "accepted_wrk"
    dataset = work / "artifacts" / "ac_minimal.ds"
    workspace.mkdir(parents=True)
    dataset.parent.mkdir()
    dataset.write_text("dataset evidence", encoding="utf-8")
    answer = {
        "case_id": "E3",
        "workspace": str(workspace),
        "dataset": "ac_minimal.ds",
        "simulation_count": 1,
        "simulation_completed": True,
        "dataset_read_back": True,
        "numeric_sample": 0.5,
        "gui_launched": False,
        "evidence": ["fresh readback"],
    }

    assert runner.validate("E3", "runtime", work, answer, []) == []
