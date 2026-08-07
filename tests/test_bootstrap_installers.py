import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_linux_installer_discovers_supported_python_and_bootstraps_pipx() -> None:
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "python3.10" in source
    assert "python3.11" in source
    assert "sys.version_info >= (3, 10)" in source
    assert "-m venv" in source
    assert "pipx-bootstrap" in source
    assert "-m pip install --upgrade pip pipx" in source
    assert "-m pipx install --force --python" in source
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
    assert "-m pipx install --force --python" in source
    assert "[string] $Package" in source
    assert "[switch] $Check" in source


def test_publish_workflow_and_readme_expose_versioned_bootstrap_installers() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    tag = "v" + match.group(1)

    assert "default: " + tag in workflow
    assert "cp install.sh install.ps1 dist/" in workflow
    assert "sha256sum *.whl *.tar.gz install.sh install.ps1" in workflow
    assert "releases/download/{0}/install.sh".format(tag) in readme
    assert "releases/download/{0}/install.ps1".format(tag) in readme
