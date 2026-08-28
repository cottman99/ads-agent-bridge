from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .addon_installer import addon_status, install_addon, uninstall_addon
from .bridge_client import list_sessions, request
from .compatibility import explain
from .config import configured_instances, load_config, select_instance, set_default, update_instances
from .discovery import discover
from .docs_kb import build_full_index, ensure_fast_index, get_document, query, start_background_build, status
from .doctor import diagnose
from .examples import run_example, list_examples, show_example
from .host_ui import action as host_ui_action
from .host_ui import snapshot as host_ui_snapshot
from .onboarding import quickstart, setup
from .session_manager import disconnect as disconnect_session
from .session_manager import launch as launch_session
from .session_manager import shutdown as shutdown_session
from .session_manager import status as session_status
from .skill_installer import install_skills, skill_status, uninstall_skills


def _emit(payload: Any, pretty: bool) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None) + "\n"
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(serialized.encode("utf-8"))
        buffer.flush()
    else:
        print(serialized, end="")


def _dialog_image_path(value: Path | None) -> Path | None:
    if value is None:
        return None
    path = value.expanduser().resolve()
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite dialog image: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"Dialog image parent directory not found: {path.parent}")
    return path


def _store_dialog_image(response: dict[str, Any], path: Path) -> None:
    result = response.get("result") if response.get("ok") else None
    if not isinstance(result, dict):
        raise RuntimeError("ADS returned no dialog snapshot")
    encoded = result.pop("image_png_base64", None)
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("ADS returned no dialog image")
    image = base64.b64decode(encoded, validate=True)
    with path.open("xb") as stream:
        stream.write(image)
    result["image_path"] = str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ads-agent", description="Unofficial local-first ADS Agent Bridge.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--ads-root", action="append", type=Path, default=[])
    doctor.add_argument("--search-root", action="append", type=Path, default=[])
    doctor.add_argument("--config-dir", type=Path, help="Explicit ADS hpeesof/config directory.")
    doctor.add_argument("--no-ping", action="store_true", help="List bridge session files without contacting them.")

    instances = commands.add_parser("instances")
    instances_commands = instances.add_subparsers(dest="instances_command", required=True)
    scan = instances_commands.add_parser("scan")
    scan.add_argument("--ads-root", action="append", type=Path, default=[])
    scan.add_argument("--search-root", action="append", type=Path, default=[])
    scan.add_argument(
        "--no-save",
        action="store_true",
        help="Inspect installations without updating the local instance registry.",
    )
    instances_commands.add_parser("list")
    use = instances_commands.add_parser("use")
    use.add_argument("instance_id")

    compatibility = commands.add_parser("compatibility")
    compatibility_commands = compatibility.add_subparsers(dest="compatibility_command", required=True)
    compatibility_explain = compatibility_commands.add_parser("explain")
    compatibility_explain.add_argument("--ads")

    docs = commands.add_parser("docs")
    docs_commands = docs.add_subparsers(dest="docs_command", required=True)
    ensure = docs_commands.add_parser("ensure")
    ensure.add_argument("--ads")
    ensure.add_argument("--force", action="store_true")
    docs_build = docs_commands.add_parser("build")
    docs_build.add_argument("--ads")
    docs_build.add_argument("--force", action="store_true")
    docs_build.add_argument("--background", action="store_true")
    docs_status = docs_commands.add_parser("status")
    docs_status.add_argument("--ads")
    docs_query = docs_commands.add_parser("query")
    docs_query.add_argument("query")
    docs_query.add_argument("--ads")
    docs_query.add_argument("--limit", type=int, default=10, help="Return 1-20 bounded results.")
    docs_query.add_argument(
        "--domain",
        action="append",
        choices=("ads", "ael", "python", "dds"),
        default=[],
        help="Restrict lookup to one or more documentation domains.",
    )
    docs_get = docs_commands.add_parser("get")
    docs_get.add_argument("source_ref")
    docs_get.add_argument("--ads")
    docs_get.add_argument("--focus", help="Return bounded sections centered on these symbols or terms.")
    docs_get.add_argument("--max-chars", type=int, default=4000, help="Total focus budget, from 200 to 12000 characters.")

    setup_parser = commands.add_parser("setup")
    setup_parser.add_argument("--ads-root", action="append", type=Path, default=[])
    setup_parser.add_argument("--search-root", action="append", type=Path, default=[])
    setup_parser.add_argument("--non-interactive", action="store_true")
    setup_parser.add_argument("--config-dir", type=Path, help="Explicit ADS hpeesof/config directory.")
    setup_parser.add_argument(
        "--skip-skill",
        action="store_true",
        help="Do not install the public Bridge and Docs Skills for Codex.",
    )
    setup_parser.add_argument("--no-background-docs", action="store_true", help="Do not enrich local docs in the background.")

    quickstart_parser = commands.add_parser("quickstart")
    quickstart_parser.add_argument("--ads")
    quickstart_parser.add_argument("--workspace", type=Path)
    quickstart_parser.add_argument("--timeout", type=float, default=300)
    quickstart_parser.add_argument("--config-dir", type=Path, help="Explicit ADS hpeesof/config directory.")

    launch_parser = commands.add_parser("launch", help="Launch or safely reuse a workspace-bound ADS session.")
    launch_parser.add_argument("--ads", help="Configured ADS instance id. Uses the explicit default when omitted.")
    launch_parser.add_argument("--workspace", type=Path, required=True, help="Existing ADS workspace to open.")
    launch_parser.add_argument("--slot", help="Bridge slot. Defaults to the selected ADS instance id.")
    launch_parser.add_argument("--display", help="Linux/X display for this ADS session, for example :4.")
    launch_parser.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for the DE bridge.")
    launch_parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse the same slot only if it has no workspace or already has the requested workspace.",
    )
    launch_parser.add_argument("--dry-run", action="store_true", help="Validate and print the launch plan only.")

    status_parser = commands.add_parser("status", help="Report managed and externally owned ADS sessions.")
    status_parser.add_argument("--slot")

    disconnect_parser = commands.add_parser("disconnect", help="End the stateless client interaction without closing ADS.")
    disconnect_parser.add_argument("--slot")

    shutdown_parser = commands.add_parser("shutdown", help="Safely exit an agent-owned ADS session.")
    shutdown_parser.add_argument("--slot", help="May be omitted only when exactly one agent-owned session is live.")
    shutdown_parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for ADS to exit normally.")

    host_ui = commands.add_parser(
        "host-ui",
        help="Observe or act on one nonce-bound pre-bridge host window.",
    )
    host_ui_commands = host_ui.add_subparsers(dest="host_ui_command", required=True)
    host_ui_snapshot_parser = host_ui_commands.add_parser(
        "snapshot",
        help="List visible candidate windows and optionally capture one targeted image.",
    )
    host_ui_snapshot_parser.add_argument("--slot", required=True)
    host_ui_snapshot_parser.add_argument("--window-id")
    host_ui_snapshot_parser.add_argument("--image-out", type=Path)
    host_ui_action_parser = host_ui_commands.add_parser(
        "action",
        help="Perform one fingerprint-bound click or native close on a pre-bridge window.",
    )
    host_ui_action_parser.add_argument("--slot", required=True)
    host_ui_action_parser.add_argument("--window-id", required=True)
    host_ui_action_parser.add_argument("--fingerprint", required=True)
    operation = host_ui_action_parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--click", nargs=2, type=int, metavar=("X", "Y"))
    operation.add_argument("--close", action="store_true")
    host_ui_action_parser.add_argument("--risk", choices=("low", "medium", "high"), required=True)
    host_ui_action_parser.add_argument(
        "--authorization",
        choices=("automatic", "workflow-policy", "user-confirmed"),
        required=True,
    )
    host_ui_action_parser.add_argument("--reason", required=True)

    examples = commands.add_parser("examples")
    examples_commands = examples.add_subparsers(dest="examples_command", required=True)
    examples_commands.add_parser("list")
    examples_show = examples_commands.add_parser("show")
    examples_show.add_argument("name")
    examples_run = examples_commands.add_parser("run")
    examples_run.add_argument("name")
    examples_run.add_argument("--ads")
    examples_run.add_argument("--ads-root", action="append", type=Path, default=[])
    examples_run.add_argument("--search-root", action="append", type=Path, default=[])
    examples_run.add_argument("--workspace", type=Path)
    examples_run.add_argument("--dataset", type=Path)
    examples_run.add_argument("--slot")
    examples_run.add_argument("--timeout", type=float, default=300)
    examples_run.add_argument("--config-dir", type=Path)

    skill = commands.add_parser("skill")
    skill_commands = skill.add_subparsers(dest="skill_command", required=True)
    for name in ("status", "install", "uninstall"):
        item = skill_commands.add_parser(name)
        item.add_argument(
            "selection",
            nargs="?",
            default="all",
            choices=("all", "bridge", "docs"),
        )
        item.add_argument("--target", choices=("codex", "agents"), default="codex")
        item.add_argument("--root", type=Path, help="Explicit parent directory for installed skills.")
        if name == "install":
            item.add_argument("--force", action="store_true")

    addon = commands.add_parser("addon")
    addon_commands = addon.add_subparsers(dest="addon_command", required=True)
    addon_install = addon_commands.add_parser("install")
    addon_install.add_argument("--config-dir", type=Path)
    addon_install.add_argument("--profile", choices=("de", "dds", "both"), default="both")
    addon_status_parser = addon_commands.add_parser("status")
    addon_status_parser.add_argument("--config-dir", type=Path)
    addon_uninstall = addon_commands.add_parser("uninstall")
    addon_uninstall.add_argument("--config-dir", type=Path)
    addon_uninstall.add_argument("--profile", choices=("de", "dds", "both"), default="both")

    bridge = commands.add_parser("bridge")
    bridge_commands = bridge.add_subparsers(dest="bridge_command", required=True)
    bridge_sessions = bridge_commands.add_parser("sessions")
    bridge_sessions.add_argument("--profile", choices=("de", "dds"))
    for name in ("ping", "status", "capabilities"):
        item = bridge_commands.add_parser(name)
        item.add_argument("--profile", choices=("de", "dds"), default="de")
        item.add_argument("--slot")
    bridge_runtime_snapshot = bridge_commands.add_parser(
        "runtime-snapshot",
        help="Return one compact, revision-aware view of the selected live ADS runtime.",
    )
    bridge_runtime_snapshot.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_runtime_snapshot.add_argument("--slot")
    bridge_runtime_snapshot.add_argument("--detail", choices=("compact", "full"), default="compact")
    bridge_runtime_snapshot.add_argument("--since-revision")
    for name in ("context-capabilities", "context-list"):
        item = bridge_commands.add_parser(name)
        item.add_argument("--profile", choices=("de", "dds"), default="de")
        item.add_argument("--slot")
    for name in ("context-get", "context-refresh", "context-drop"):
        item = bridge_commands.add_parser(name)
        item.add_argument("context", help="Context id or ADS_CONTEXT handle.")
        item.add_argument("--profile", choices=("de", "dds"), default="de")
        item.add_argument("--slot")
    bridge_dialog_snapshot = bridge_commands.add_parser(
        "dialog-snapshot", help="Inspect the active modal dialog through Qt semantics."
    )
    bridge_dialog_snapshot.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_dialog_snapshot.add_argument("--slot")
    bridge_dialog_snapshot.add_argument(
        "--image-out", type=Path, help="Write a Qt-captured PNG for Agent vision fallback; never overwrites."
    )
    bridge_dialog_watch = bridge_commands.add_parser(
        "dialog-watch", help="Wait on an independent client lane until a modal dialog appears."
    )
    bridge_dialog_watch.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_dialog_watch.add_argument("--slot")
    bridge_dialog_watch.add_argument("--timeout", type=float, default=3600.0)
    bridge_dialog_watch.add_argument("--poll", type=float, default=1.0)
    bridge_dialog_watch.add_argument("--image-out", type=Path)
    bridge_dialog_action = bridge_commands.add_parser(
        "dialog-action", help="Schedule one fingerprint-bound modal button action."
    )
    bridge_dialog_action.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_dialog_action.add_argument("--slot")
    bridge_dialog_action.add_argument("--fingerprint", required=True)
    bridge_dialog_action.add_argument("--button-id", required=True)
    bridge_dialog_action.add_argument("--risk", choices=("low", "medium", "high"), required=True)
    bridge_dialog_action.add_argument(
        "--authorization",
        choices=("automatic", "workflow-policy", "user-confirmed"),
        required=True,
    )
    bridge_dialog_action.add_argument("--reason", required=True)
    bridge_eval = bridge_commands.add_parser("eval")
    bridge_eval.add_argument("expression")
    bridge_eval.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_eval.add_argument("--slot")
    bridge_eval.add_argument("--unsafe", action="store_true")
    bridge_eval.add_argument("--timeout", type=float, default=30)
    bridge_exec = bridge_commands.add_parser("exec")
    bridge_exec.add_argument("code")
    bridge_exec.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_exec.add_argument("--slot")
    bridge_exec.add_argument("--unsafe", action="store_true")
    bridge_exec.add_argument("--timeout", type=float, default=120)
    bridge_exec_file = bridge_commands.add_parser("exec-file")
    bridge_exec_file.add_argument("path", type=Path)
    bridge_exec_file.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_exec_file.add_argument("--slot")
    bridge_exec_file.add_argument("--unsafe", action="store_true")
    bridge_exec_file.add_argument("--timeout", type=float, default=300)
    bridge_ael = bridge_commands.add_parser("ael-call")
    bridge_ael.add_argument("name")
    bridge_ael.add_argument("--arg", action="append", default=[], help="JSON-encoded positional argument.")
    bridge_ael.add_argument("--profile", choices=("de", "dds"), default="de")
    bridge_ael.add_argument("--slot")
    bridge_ael.add_argument("--unsafe", action="store_true")

    runtime = commands.add_parser(
        "runtime",
        help="Serve the generic EDA Runtime protocol over one persistent stdio channel.",
    )
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_serve = runtime_commands.add_parser(
        "serve",
        help="Serve ADS requests for local or persistent SSH transport.",
    )
    runtime_serve.add_argument(
        "--ledger",
        type=Path,
        help="Execution ledger path. Defaults to the private ADS Agent runtime directory.",
    )
    return parser


def run(args: argparse.Namespace) -> tuple[Any, int]:
    if args.command == "runtime":
        if args.runtime_command == "serve":
            from .runtime_adapter import default_ledger_path, serve

            serve(args.ledger or default_ledger_path(), sys.stdin, sys.stdout)
            return {"status": "stopped"}, 0
    if args.command == "doctor":
        return diagnose(args.ads_root, args.search_root, args.config_dir, ping=not args.no_ping)
    if args.command == "instances":
        if args.instances_command == "scan":
            found = discover(args.ads_root, args.search_root)
            config = None if args.no_save else update_instances(found)
            return {
                "default_instance_id": None if config is None else config.get("default_instance_id"),
                "saved": config is not None,
                "instances": [item.to_dict() for item in found],
            }, 0
        if args.instances_command == "list":
            config = load_config()
            return {"default_instance_id": config.get("default_instance_id"), "instances": [item.to_dict() for item in configured_instances(config)]}, 0
        if args.instances_command == "use":
            return set_default(args.instance_id), 0
    if args.command == "compatibility":
        return explain(select_instance(args.ads)), 0
    if args.command == "docs":
        instance = select_instance(args.ads)
        if args.docs_command == "ensure":
            return ensure_fast_index(instance, force=args.force), 0
        if args.docs_command == "build":
            if args.background:
                return start_background_build(instance, force=args.force), 0
            payload = build_full_index(instance, force=args.force)
            return payload, 0 if payload.get("status") == "ready" else 2
        if args.docs_command == "status":
            return status(instance), 0
        if args.docs_command == "query":
            return query(instance, args.query, args.limit, domains=args.domain), 0
        if args.docs_command == "get":
            return get_document(instance, args.source_ref, focus=args.focus, max_chars=args.max_chars), 0
    if args.command == "setup":
        payload = setup(
            roots=args.ads_root,
            search_roots=args.search_root,
            non_interactive=args.non_interactive,
            config_dir=args.config_dir,
            install_skill=not args.skip_skill,
            start_docs_build=not args.no_background_docs,
        )
        return payload, 0 if payload.get("status") == "ready" else 2
    if args.command == "quickstart":
        return quickstart(args.ads, args.workspace, args.timeout, args.config_dir)
    if args.command == "launch":
        payload = launch_session(
            args.ads,
            args.workspace,
            slot=args.slot,
            display=args.display,
            wait_seconds=args.timeout,
            reuse_existing=args.reuse_existing,
            dry_run=args.dry_run,
        )
        return payload, 0 if payload.get("status") in {"ready", "planned"} else 2
    if args.command == "status":
        return session_status(args.slot), 0
    if args.command == "disconnect":
        return disconnect_session(args.slot), 0
    if args.command == "shutdown":
        payload = shutdown_session(args.slot, args.timeout)
        return payload, 0 if payload.get("status") == "exited" else 2
    if args.command == "host-ui":
        if args.host_ui_command == "snapshot":
            image_path = _dialog_image_path(args.image_out)
            payload = host_ui_snapshot(args.slot, window_id=args.window_id, image_out=image_path)
            return payload, 0 if payload.get("status") == "ready" else 2
        if args.host_ui_command == "action":
            point = args.click or (None, None)
            payload = host_ui_action(
                args.slot,
                window_id=args.window_id,
                fingerprint=args.fingerprint,
                operation="close" if args.close else "click",
                x=point[0],
                y=point[1],
                risk=args.risk,
                authorization=args.authorization,
                reason=args.reason,
            )
            return payload, 0
    if args.command == "examples":
        if args.examples_command == "list":
            return list_examples(), 0
        if args.examples_command == "show":
            return show_example(args.name), 0
        if args.examples_command == "run":
            return run_example(
                args.name,
                instance_id=args.ads,
                ads_roots=args.ads_root,
                search_roots=args.search_root,
                workspace=args.workspace,
                dataset=args.dataset,
                slot=args.slot,
                timeout=args.timeout,
                config_dir=args.config_dir,
            )
    if args.command == "skill":
        if args.skill_command == "status":
            return skill_status(args.selection, target=args.target, root=args.root), 0
        if args.skill_command == "install":
            payload = install_skills(
                args.selection,
                target=args.target,
                root=args.root,
                force=args.force,
            )
            return payload, 0 if payload.get("status") == "ready" else 2
        if args.skill_command == "uninstall":
            return uninstall_skills(args.selection, target=args.target, root=args.root), 0
    if args.command == "addon":
        profiles = ("de", "dds") if getattr(args, "profile", "both") == "both" else (args.profile,)
        if args.addon_command == "install":
            return install_addon(args.config_dir, profiles), 0
        if args.addon_command == "status":
            return addon_status(args.config_dir), 0
        if args.addon_command == "uninstall":
            return uninstall_addon(args.config_dir, profiles), 0
    if args.command == "bridge":
        if args.bridge_command == "sessions":
            return {"sessions": list_sessions(args.profile)}, 0
        if args.bridge_command in {"ping", "status", "capabilities"}:
            response = request(args.bridge_command, {}, args.slot, args.profile)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command == "runtime-snapshot":
            payload = {"detail": args.detail}
            if args.since_revision:
                payload["since_revision"] = args.since_revision
            response = request("runtime_snapshot", payload, args.slot, args.profile)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command in {"context-capabilities", "context-list"}:
            command = args.bridge_command.replace("-", "_")
            response = request(command, {}, args.slot, args.profile)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command in {"context-get", "context-refresh", "context-drop"}:
            command = args.bridge_command.replace("-", "_")
            response = request(command, {"context": args.context}, args.slot, args.profile)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command == "dialog-snapshot":
            image_path = _dialog_image_path(args.image_out)
            response = request(
                "dialog_snapshot",
                {"include_image": image_path is not None},
                args.slot,
                args.profile,
            )
            if image_path is not None:
                _store_dialog_image(response, image_path)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command == "dialog-watch":
            image_path = _dialog_image_path(args.image_out)
            deadline = time.monotonic() + max(0.0, args.timeout)
            last_response: dict[str, Any] | None = None
            while True:
                last_response = request("dialog_snapshot", {"include_image": False}, args.slot, args.profile)
                if not last_response.get("ok"):
                    return last_response, 2
                result = last_response.get("result")
                if isinstance(result, dict) and result.get("present") is True:
                    if image_path is not None:
                        last_response = request(
                            "dialog_snapshot", {"include_image": True}, args.slot, args.profile
                        )
                        _store_dialog_image(last_response, image_path)
                    return last_response, 0
                if time.monotonic() >= deadline:
                    return {
                        "status": "timeout",
                        "dialog_present": False,
                        "slot": args.slot,
                        "profile": args.profile,
                    }, 2
                time.sleep(max(0.1, args.poll))
        if args.bridge_command == "dialog-action":
            response = request(
                "dialog_action",
                {
                    "dialog_fingerprint": args.fingerprint,
                    "button_id": args.button_id,
                    "decision": {
                        "risk": args.risk,
                        "authorization": args.authorization,
                        "reason": args.reason,
                    },
                },
                args.slot,
                args.profile,
            )
            return response, 0 if response.get("ok") else 2
        if args.bridge_command in {"eval", "exec", "exec-file"}:
            if not args.unsafe:
                raise ValueError("Arbitrary embedded Python requires the explicit --unsafe flag")
            command = "exec" if args.bridge_command == "exec-file" else args.bridge_command
            field = "expression" if command == "eval" else "code"
            value = args.path.read_text(encoding="utf-8") if args.bridge_command == "exec-file" else getattr(args, field)
            response = request(command, {field: value}, args.slot, args.profile, timeout=args.timeout)
            return response, 0 if response.get("ok") else 2
        if args.bridge_command == "ael-call":
            if not args.unsafe:
                raise ValueError("Dynamic AEL calls require the explicit --unsafe flag")
            response = request(
                "ael_call",
                {"name": args.name, "args": [json.loads(value) for value in args.arg]},
                args.slot,
                args.profile,
            )
            return response, 0 if response.get("ok") else 2
    raise ValueError("Unhandled command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload, code = run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _emit({"status": "error", "error": str(exc)}, args.pretty)
        return 1
    _emit(payload, args.pretty)
    return code


if __name__ == "__main__":
    sys.exit(main())
