from pathlib import Path
import base64

from ads_agent_bridge.cli import _dialog_image_path, _store_dialog_image, build_parser, run
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


def test_examples_and_skill_commands_are_public_cli_entrypoints() -> None:
    parser = build_parser()

    examples = parser.parse_args(["examples", "run", "live-de-context", "--slot", "test"])
    skill = parser.parse_args(["skill", "install", "docs", "--target", "codex"])
    docs = parser.parse_args(["docs", "build", "--ads", "ads-2025-test", "--background"])

    assert examples.examples_command == "run"
    assert skill.skill_command == "install"
    assert docs.docs_command == "build"


def test_session_lifecycle_commands_are_public_cli_entrypoints(tmp_path: Path) -> None:
    parser = build_parser()

    launch = parser.parse_args(["launch", "--workspace", str(tmp_path), "--display", ":4", "--dry-run"])
    status = parser.parse_args(["status", "--slot", "test"])
    disconnect = parser.parse_args(["disconnect", "--slot", "test"])
    shutdown = parser.parse_args(["shutdown", "--slot", "test"])

    assert launch.workspace == tmp_path
    assert launch.display == ":4"
    assert launch.dry_run is True
    assert status.slot == "test"
    assert disconnect.slot == "test"
    assert shutdown.slot == "test"


def test_dialog_commands_are_public_agent_entrypoints(tmp_path: Path, monkeypatch) -> None:
    parser = build_parser()
    image_path = tmp_path / "dialog.png"
    snapshot = parser.parse_args(
        ["bridge", "dialog-snapshot", "--slot", "test", "--image-out", str(image_path)]
    )
    action = parser.parse_args(
        [
            "bridge",
            "dialog-action",
            "--slot",
            "test",
            "--fingerprint",
            "fingerprint",
            "--button-id",
            "button",
            "--risk",
            "low",
            "--authorization",
            "automatic",
            "--reason",
            "Dismiss informational message",
        ]
    )
    watch = parser.parse_args(
        ["bridge", "dialog-watch", "--slot", "test", "--timeout", "0"]
    )
    calls = []

    def fake_request(command, args, slot, profile):
        calls.append((command, args, slot, profile))
        if command == "dialog_snapshot":
            return {
                "ok": True,
                "result": {
                    "present": True,
                    **(
                        {"image_png_base64": base64.b64encode(b"png-bytes").decode("ascii")}
                        if args.get("include_image")
                        else {}
                    ),
                },
            }
        return {"ok": True, "result": {"accepted": True}}

    monkeypatch.setattr("ads_agent_bridge.cli.request", fake_request)

    snapshot_payload, snapshot_code = run(snapshot)
    action_payload, action_code = run(action)
    watch_payload, watch_code = run(watch)

    assert snapshot_code == 0
    assert snapshot_payload["result"]["image_path"] == str(image_path.resolve())
    assert image_path.read_bytes() == b"png-bytes"
    assert action_code == 0
    assert action_payload["result"]["accepted"] is True
    assert calls[1][1]["decision"]["authorization"] == "automatic"
    assert watch_code == 0
    assert watch_payload["result"]["present"] is True


def test_dialog_image_write_is_exclusive_at_actuation_time(tmp_path: Path) -> None:
    image_path = _dialog_image_path(tmp_path / "dialog.png")
    assert image_path is not None
    image_path.write_bytes(b"created-by-another-client")
    response = {
        "ok": True,
        "result": {"image_png_base64": base64.b64encode(b"new-image").decode("ascii")},
    }

    try:
        _store_dialog_image(response, image_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("dialog image storage must not overwrite a concurrently created file")

    assert image_path.read_bytes() == b"created-by-another-client"


def test_context_commands_are_safe_bridge_entrypoints(monkeypatch) -> None:
    parser = build_parser()
    listed = parser.parse_args(["bridge", "context-list", "--slot", "candidate", "--profile", "dds"])
    fetched = parser.parse_args(
        ["bridge", "context-get", "ADS_CONTEXT:v1:candidate:dds:ctx-0001:report", "--slot", "candidate"]
    )
    calls = []

    def fake_request(command, args, slot, profile):
        calls.append((command, args, slot, profile))
        return {"ok": True, "result": []}

    monkeypatch.setattr("ads_agent_bridge.cli.request", fake_request)
    _, list_code = run(listed)
    _, get_code = run(fetched)

    assert list_code == get_code == 0
    assert calls[0] == ("context_list", {}, "candidate", "dds")
    assert calls[1][0] == "context_get"
    assert calls[1][1]["context"].startswith("ADS_CONTEXT:v1:")
