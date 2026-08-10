from pathlib import Path

from ads_agent_bridge.doctor import _ads_user_home_check, diagnose


def make_ads_root(tmp_path: Path) -> Path:
    root = tmp_path / "ADS2026_Update2"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "hpeesofde").write_text("", encoding="ascii")
    (root / "tools" / "python" / "bin").mkdir(parents=True)
    (root / "tools" / "python" / "bin" / "python3.13").write_text("", encoding="ascii")
    (root / "doc" / "ads").mkdir(parents=True)
    (root / "doc" / "ads" / "index.html").write_text("<title>ADS docs</title>", encoding="utf-8")
    return root


def test_doctor_is_read_only_with_explicit_ads_root(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    ads_root = make_ads_root(tmp_path)
    monkeypatch.setenv("ADS_AGENT_HOME", str(state))

    payload, code = diagnose([ads_root], ads_config_dir=tmp_path / "missing-config", ping=False)

    assert code == 0
    assert payload["status"] == "ready"
    assert payload["read_only"] is True
    assert payload["selected_instance_id"].startswith("ads-2026-u2-")
    assert not state.exists()


def test_doctor_reports_missing_ads_as_blocked(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ADS_AGENT_HOME", str(state))

    payload, code = diagnose([tmp_path / "does-not-exist"], ads_config_dir=tmp_path / "missing-config", ping=False)

    assert code == 2
    assert payload["status"] == "blocked"
    assert next(item for item in payload["checks"] if item["name"] == "ads_discovery")["status"] == "fail"
    assert not state.exists()


def test_doctor_warns_when_linux_home_has_no_ads_user_state(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "isolated-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    check = _ads_user_home_check("linux")

    assert check is not None
    assert check["status"] == "warn"
    assert "keep the real HOME" in check["remediation"]


def test_doctor_accepts_linux_home_with_ads_user_state(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "normal-home"
    home.mkdir()
    (home / ".eesoflic").write_text("", encoding="ascii")
    monkeypatch.setenv("HOME", str(home))

    check = _ads_user_home_check("linux")

    assert check is not None
    assert check["status"] == "pass"
