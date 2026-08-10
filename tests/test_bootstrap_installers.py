import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_linux_installer_discovers_supported_python_and_bootstraps_pipx() -> None:
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "python3.10" in source
    assert "python3.11" in source
    assert "sys.version_info >= (3, 10)" in source
    assert "-m venv" in source
    assert "pipx-bootstrap" in source
    assert "-m pip install --upgrade pip pipx" in source
    assert "-m pipx install $pipx_backend_args --force --python" in source
    assert "pipx_backend_args='--backend pip'" in source
    assert "--package" in source
    assert "--check" in source


def test_windows_installer_discovers_supported_python_and_bootstraps_pipx() -> None:
    source = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert '"-3.10"' in source
    assert '"-3.11"' in source
    assert "sys.version_info >= (3, 10)" in source
    assert "-m venv" in source
    assert "pipx-bootstrap" in source
    assert "-m pip install --upgrade pip pipx" in source
    assert "$pipxBackendArguments" in source
    assert '@("--backend", "pip")' in source
    assert "[string] $Package" in source
    assert "[switch] $Check" in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert "$pipxAvailable = $LASTEXITCODE -eq 0" in source


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell installer integration test")
def test_windows_installer_bootstraps_when_selected_python_has_no_pipx(tmp_path: Path) -> None:
    selected = tmp_path / "selected-python"
    subprocess.run([sys.executable, "-m", "venv", str(selected)], check=True)
    selected_python = selected / "Scripts" / "python.exe"
    bootstrap = tmp_path / "pipx-bootstrap"
    pipx_home = tmp_path / "pipx-home"
    pipx_bin = tmp_path / "bin"
    pipx_man = tmp_path / "man"
    environment = os.environ.copy()
    environment.update(
        {
            "ADS_AGENT_BRIDGE_BOOTSTRAP_DIR": str(bootstrap),
            "PIPX_HOME": str(pipx_home),
            "PIPX_BIN_DIR": str(pipx_bin),
            "PIPX_MAN_DIR": str(pipx_man),
            "PATH": str(pipx_bin) + os.pathsep + environment.get("PATH", ""),
        }
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "install.ps1"),
            "-Python",
            str(selected_python),
            "-Package",
            str(ROOT),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=240,
    )

    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert "pipx was not found; creating an isolated bootstrap environment" in completed.stdout
    assert "uv" not in completed.stderr.lower()
    installed = subprocess.run(
        [str(pipx_bin / "ads-agent.exe"), "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"ads-agent {project_version()}" in installed.stdout


def test_publish_workflow_and_readme_expose_versioned_bootstrap_installers() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    tag = "v" + project_version()

    assert "default: " + tag in workflow
    assert "cp install.sh install.ps1 dist/" in workflow
    assert "sha256sum *.whl *.tar.gz install.sh install.ps1" in workflow
    assert "releases/download/{0}/install.sh".format(tag) in readme
    assert "releases/download/{0}/install.ps1".format(tag) in readme
