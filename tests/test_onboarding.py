import json
import subprocess
import sys
from pathlib import Path

from ads_agent_bridge.models import AdsInstance
from ads_agent_bridge import onboarding


def instance(tmp_path: Path) -> AdsInstance:
    root = tmp_path / "ADS2026_Update2"
    python = root / "tools" / "python" / "bin" / "python3.13"
    python.parent.mkdir(parents=True)
    python.touch()
    return AdsInstance(
        instance_id="ads-2026-u2-test",
        install_root=str(root),
        product_version="ADS 2026 Update 2",
        year=2026,
        update="2",
        platform="linux",
        support_tier="stable",
        python_executable=str(python),
        capabilities={"local_docs": True, "python_addon_generation": "available"},
    )


def test_quickstart_runs_ads_python_and_requires_dataset_readback(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(onboarding, "select_instance", lambda _: selected)
    monkeypatch.setattr(onboarding, "ensure_fast_index", lambda _: {"status": "ready"})
    monkeypatch.setattr(onboarding, "query", lambda *_args, **_kwargs: {"results": [{"title": "Python"}]})
    monkeypatch.setattr(
        onboarding,
        "addon_status",
        lambda _config=None: {"profiles": [{"registrations": [{"Name": "AdsAgentBridge"}]}]},
    )

    def fake_run(command, **kwargs):
        assert command[0] == selected.python_executable
        assert kwargs["env"]["HPEESOF_DIR"] == selected.install_root
        assert kwargs["cwd"].endswith("quickstarts")
        if sys.platform.startswith("linux"):
            assert "lib/linux_x86_64" in kwargs["env"]["LD_LIBRARY_PATH"]
            assert "tools/python/lib" in kwargs["env"]["LD_LIBRARY_PATH"]
        payload = {"ok": True, "workspace": command[-1], "rows": 31, "columns": ["freq", "R1_v"]}
        return subprocess.CompletedProcess(command, 0, stdout="ADS log\n" + json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(onboarding.subprocess, "run", fake_run)
    payload, code = onboarding.quickstart(workspace=tmp_path / "quickstart", config_dir=tmp_path / "config")

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["gates"]["dataset_readback"] == "passed"
    assert payload["simulation"]["rows"] == 31


def test_quickstart_returns_structured_failure_on_timeout(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(onboarding, "select_instance", lambda _: selected)
    monkeypatch.setattr(onboarding, "ensure_fast_index", lambda _: {"status": "ready"})
    monkeypatch.setattr(onboarding, "query", lambda *_args, **_kwargs: {"results": [{"title": "Python"}]})
    monkeypatch.setattr(
        onboarding,
        "addon_status",
        lambda _config=None: {"profiles": [{"registrations": [{"Name": "AdsAgentBridge"}]}]},
    )

    def timeout(command, **_kwargs):
        Path(command[-1]).mkdir()
        late_success = json.dumps({"ok": True, "workspace": command[-1], "rows": 31})
        raise subprocess.TimeoutExpired(
            command,
            12.5,
            output="partial ADS output\n" + late_success,
            stderr=b"partial error",
        )

    monkeypatch.setattr(onboarding.subprocess, "run", timeout)

    payload, code = onboarding.quickstart(
        workspace=tmp_path / "timed-out-quickstart",
        timeout=12.5,
        config_dir=tmp_path / "config",
    )

    assert code == 2
    assert payload["status"] == "failed"
    assert payload["simulation"]["timed_out"] is True
    assert payload["simulation"]["timeout_seconds"] == 12.5
    assert payload["simulation"]["stdout_tail"].startswith("partial ADS output")
    assert payload["simulation"]["stderr_tail"] == "partial error"
    assert payload["simulation"]["partial_workspace_path"].endswith("timed-out-quickstart")
    assert "workspace" not in payload["simulation"]
    assert payload["gates"]["workspace_creation"] == "failed"
    assert payload["gates"]["circuit_simulation"] == "failed"


def test_quickstart_refuses_existing_workspace(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    monkeypatch.setattr(onboarding, "select_instance", lambda _: selected)
    workspace = tmp_path / "existing"
    workspace.mkdir()

    try:
        onboarding.quickstart(workspace=workspace)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected quickstart to refuse an existing workspace")


def test_setup_degrades_when_old_install_has_no_docs_or_addons(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    selected = AdsInstance(
        **{
            **selected.to_dict(),
            "capabilities": {
                "local_docs": False,
                "embedded_python": True,
                "python_addon_generation": "unavailable",
            },
        }
    )
    monkeypatch.setattr(onboarding, "discover", lambda *_args: [selected])
    monkeypatch.setattr(onboarding, "update_instances", lambda *_args: {"default_instance_id": selected.instance_id})
    monkeypatch.setattr(onboarding, "ensure_fast_index", lambda *_args: (_ for _ in ()).throw(AssertionError("must not index")))
    monkeypatch.setattr(onboarding, "install_addon", lambda: (_ for _ in ()).throw(AssertionError("must not install")))

    payload = onboarding.setup(roots=[], search_roots=[], non_interactive=True)

    assert payload["status"] == "ready"
    assert payload["docs"]["status"] == "not_available"
    assert payload["addon"]["status"] == "skipped"


def test_setup_installs_both_public_skills_when_requested(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    expected_skills = {
        "status": "ready",
        "selection": "all",
        "skills": [
            {"skill": "ads-agent-bridge", "status": "ready"},
            {"skill": "ads-kb-docs", "status": "ready"},
        ],
    }
    monkeypatch.setattr(onboarding, "discover", lambda *_args: [selected])
    monkeypatch.setattr(onboarding, "update_instances", lambda *_args: {"default_instance_id": selected.instance_id})
    monkeypatch.setattr(onboarding, "ensure_fast_index", lambda *_args: {"status": "ready"})
    monkeypatch.setattr(onboarding, "install_addon", lambda _config=None: {"status": "installed"})

    def fake_install(selection: str):
        assert selection == "all"
        return expected_skills

    monkeypatch.setattr(onboarding, "install_skills", fake_install)

    payload = onboarding.setup(
        roots=[],
        search_roots=[],
        non_interactive=True,
        install_skill=True,
    )

    assert payload["skills"] == expected_skills


def test_setup_requires_attention_when_skill_install_conflicts(tmp_path: Path, monkeypatch) -> None:
    selected = instance(tmp_path)
    monkeypatch.setattr(onboarding, "discover", lambda *_args: [selected])
    monkeypatch.setattr(onboarding, "update_instances", lambda *_args: {"default_instance_id": selected.instance_id})
    monkeypatch.setattr(onboarding, "ensure_fast_index", lambda *_args: {"status": "ready"})
    monkeypatch.setattr(onboarding, "install_addon", lambda _config=None: {"status": "installed"})
    monkeypatch.setattr(
        onboarding,
        "install_skills",
        lambda _selection: {"status": "conflict", "selection": "all", "skills": []},
    )

    payload = onboarding.setup(
        roots=[],
        search_roots=[],
        non_interactive=True,
        install_skill=True,
    )

    assert payload["status"] == "attention_required"
