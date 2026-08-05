from pathlib import Path

from ads_agent_bridge.cli import build_parser, run
from ads_agent_bridge.config import load_config

from test_discovery import make_ads_root


def test_instances_scan_saves_single_discovery_as_default(tmp_path: Path, monkeypatch) -> None:
    root = make_ads_root(tmp_path / "install", "ADS2026_Update2")
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    args = build_parser().parse_args(["instances", "scan", "--ads-root", str(root)])

    payload, code = run(args)

    assert code == 0
    assert payload["saved"] is True
    assert payload["default_instance_id"] == payload["instances"][0]["instance_id"]
    assert load_config()["default_instance_id"] == payload["default_instance_id"]


def test_instances_scan_no_save_is_read_only(tmp_path: Path, monkeypatch) -> None:
    root = make_ads_root(tmp_path / "install", "ADS2025")
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    args = build_parser().parse_args(["instances", "scan", "--no-save", "--ads-root", str(root)])

    payload, code = run(args)

    assert code == 0
    assert payload["saved"] is False
    assert load_config()["instances"] == []
