from pathlib import Path
from types import SimpleNamespace

import pytest

from ads_agent_bridge import momentum


def citi_text(*, invalid: bool = False) -> str:
    value = "nan,0" if invalid else "0.1,0.2"
    blocks = "\n".join(f"BEGIN\n{value}\n0.3,0.4\nEND" for _ in range(4))
    return f"""CITIFILE A.01.01
NAME Momentum.SP
CONSTANT NBR_OF_PORTS 2
CONSTANT NORMALIZATION 1.000183932
VAR freq MAG 2
DATA S[1,1] RI
DATA S[1,2] RI
DATA S[2,1] RI
DATA S[2,2] RI
VAR_LIST_BEGIN
1000000000
2000000000
VAR_LIST_END
{blocks}
"""


def test_inspect_citi_accepts_float_normalization_and_finite_two_port_data(tmp_path):
    path = tmp_path / "proj.cti"
    path.write_text(citi_text(), encoding="utf-8")

    result = momentum.inspect_citi(path)

    assert result["port_count"] == 2
    assert result["frequency_count"] == 2
    assert result["frequency_hz"] == {"start": 1e9, "stop": 2e9}
    assert set(result["s_parameters"]) == {
        "S[1,1]",
        "S[1,2]",
        "S[2,1]",
        "S[2,2]",
    }
    assert result["s_parameters"]["S[2,1]"][0]["magnitude"] == pytest.approx(
        abs(complex(0.1, 0.2))
    )


def test_inspect_citi_rejects_non_finite_values(tmp_path):
    path = tmp_path / "proj.cti"
    path.write_text(citi_text(invalid=True), encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite"):
        momentum.inspect_citi(path)


def test_generated_momentum_runs_on_copy_and_commits_only_verified_output(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (source / "proj").write_text("generated input", encoding="utf-8")
    (source / "proj.cti").write_text("stale", encoding="utf-8")
    source_before = momentum.workspace_fingerprint(source)
    monkeypatch.setenv("DISPLAY", ":4.0")
    monkeypatch.setattr(
        momentum,
        "select_instance",
        lambda _instance: SimpleNamespace(install_root=str(tmp_path / "ads")),
    )
    monkeypatch.setattr(momentum, "_wrapper", lambda _root: ["adsMomWrapper"])
    monkeypatch.setattr(momentum, "ads_runtime_environment", lambda _root: {})

    def fake_run(command, **kwargs):
        assert command == ["adsMomWrapper", "-O", "-3D", "proj", "proj"]
        cwd = Path(kwargs["cwd"])
        (cwd / "proj.cti").write_text(citi_text(), encoding="utf-8")
        (cwd / "proj.afs").write_text("interpolated", encoding="utf-8")
        (cwd / "proj.sta").write_text("statistics", encoding="utf-8")
        return SimpleNamespace(
            returncode=0,
            stdout="S-parameter simulation finished\nCould not create dataset",
            stderr="",
        )

    monkeypatch.setattr(momentum, "_run_momentum_command", fake_run)

    result = momentum.run_generated_momentum(
        source_directory=source,
        output_directory=output,
        project="proj",
        expected_display=":4.0",
        source_fingerprint=source_before,
        timeout=30,
    )

    assert result["status"] == "passed"
    assert result["source_preserved"] is True
    assert result["result"]["port_count"] == 2
    assert result["warnings"]["dataset_export_failed"] is True
    assert momentum.workspace_fingerprint(source) == source_before
    assert (source / "proj.cti").read_text(encoding="utf-8") == "stale"
    assert (output / "proj.cti").is_file()
    assert not list(tmp_path.glob(".output.staging-*"))


def test_generated_momentum_failure_does_not_commit_output(tmp_path, monkeypatch):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (source / "proj").write_text("generated input", encoding="utf-8")
    monkeypatch.setattr(
        momentum,
        "select_instance",
        lambda _instance: SimpleNamespace(install_root=str(tmp_path / "ads")),
    )
    monkeypatch.setattr(momentum, "_wrapper", lambda _root: ["adsMomWrapper"])
    monkeypatch.setattr(momentum, "ads_runtime_environment", lambda _root: {})
    monkeypatch.setattr(
        momentum,
        "_run_momentum_command",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2, stdout="failed", stderr="solver error"
        ),
    )

    with pytest.raises(RuntimeError, match="did not complete"):
        momentum.run_generated_momentum(
            source_directory=source,
            output_directory=output,
            project="proj",
        )

    assert not output.exists()
    assert not list(tmp_path.glob(".output.staging-*"))


def test_command_timeout_stops_process_tree(monkeypatch, tmp_path):
    class FakeProcess:
        pid = 1234
        returncode = None

        def communicate(self, timeout=None):
            if timeout is not None:
                raise momentum.subprocess.TimeoutExpired("wrapper", timeout)
            return "partial output", "partial error"

    process = FakeProcess()
    stopped = []
    monkeypatch.setattr(momentum.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(momentum, "_terminate_process_tree", stopped.append)

    with pytest.raises(RuntimeError, match="process tree stopped"):
        momentum._run_momentum_command(
            ["adsMomWrapper"], cwd=tmp_path, env={}, timeout=1
        )

    assert stopped == [process]
