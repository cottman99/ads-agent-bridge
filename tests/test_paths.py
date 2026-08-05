from pathlib import Path

from ads_agent_bridge.paths import cache_dir, config_dir, data_dir


def test_ads_agent_home_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path))
    assert config_dir() == tmp_path / "config"
    assert data_dir() == tmp_path / "data"
    assert cache_dir() == tmp_path / "cache"
