import re
from pathlib import Path

from ads_agent_bridge import __version__


def test_runtime_version_matches_package_metadata():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    assert __version__ == match.group(1)
