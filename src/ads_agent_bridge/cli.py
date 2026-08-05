from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .addon_installer import addon_status, install_addon, uninstall_addon
from .bridge_client import list_sessions, request
from .compatibility import explain
from .config import configured_instances, load_config, select_instance, set_default, update_instances
from .discovery import discover
from .docs_kb import build_full_index, ensure_fast_index, query, start_background_build, status
from .doctor import diagnose
from .examples import run_example, list_examples, show_example
from .onboarding import quickstart, setup
from .skill_installer import install_docs_skill, skill_status, uninstall_docs_skill


def _emit(payload: Any, pretty: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


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
    docs_query.add_argument("--limit", type=int, default=10)

    setup_parser = commands.add_parser("setup")
    setup_parser.add_argument("--ads-root", action="append", type=Path, default=[])
    setup_parser.add_argument("--search-root", action="append", type=Path, default=[])
    setup_parser.add_argument("--non-interactive", action="store_true")
    setup_parser.add_argument("--config-dir", type=Path, help="Explicit ADS hpeesof/config directory.")
    setup_parser.add_argument("--skip-skill", action="store_true", help="Do not install the portable Docs Skill for Codex.")
    setup_parser.add_argument("--no-background-docs", action="store_true", help="Do not enrich local docs in the background.")

    quickstart_parser = commands.add_parser("quickstart")
    quickstart_parser.add_argument("--ads")
    quickstart_parser.add_argument("--workspace", type=Path)
    quickstart_parser.add_argument("--timeout", type=float, default=300)
    quickstart_parser.add_argument("--config-dir", type=Path, help="Explicit ADS hpeesof/config directory.")

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
        item.add_argument("docs", nargs="?", default="docs", choices=("docs",))
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
    return parser


def run(args: argparse.Namespace) -> tuple[Any, int]:
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
            return query(instance, args.query, args.limit), 0
    if args.command == "setup":
        return setup(
            roots=args.ads_root,
            search_roots=args.search_root,
            non_interactive=args.non_interactive,
            config_dir=args.config_dir,
            install_skill=not args.skip_skill,
            start_docs_build=not args.no_background_docs,
        ), 0
    if args.command == "quickstart":
        return quickstart(args.ads, args.workspace, args.timeout, args.config_dir)
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
            return skill_status(target=args.target, root=args.root), 0
        if args.skill_command == "install":
            payload = install_docs_skill(target=args.target, root=args.root, force=args.force)
            return payload, 0 if payload.get("status") == "ready" else 2
        if args.skill_command == "uninstall":
            return uninstall_docs_skill(target=args.target, root=args.root), 0
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
