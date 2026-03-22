from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from ansys_connector.core import build_registry, detect_environment
from ansys_connector.core.execution import WorkflowExecutor
from ansys_connector.workflows.plans import load_plan


def _parse_key_value(values: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"Expected KEY=VALUE format, got: {raw}")
        key, raw_value = raw.split("=", 1)
        parsed[key] = yaml.safe_load(raw_value)
    return parsed


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=_json_default))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ansysctl", description="Generic Ansys automation CLI")
    parser.add_argument("--version", dest="ansys_version", help="Prefer a specific AWP_ROOT version.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    env_parser = subparsers.add_parser("env", help="Show detected environment")
    env_parser.add_argument("--json", action="store_true", help="Emit JSON")

    adapters_parser = subparsers.add_parser("adapters", help="List adapter availability")
    adapters_parser.add_argument("--json", action="store_true", help="Emit JSON")

    call_parser = subparsers.add_parser("call", help="Run one adapter action")
    call_parser.add_argument("adapter", help="Adapter name, such as fluent or workbench")
    call_parser.add_argument("action", help="Action name, such as version or script")
    call_parser.add_argument(
        "--profile",
        choices=("safe", "expert"),
        default="safe",
        help="Execution profile. Safe is default; expert unlocks raw script and TUI actions.",
    )
    call_parser.add_argument("--option", action="append", help="Adapter session option in KEY=VALUE format")
    call_parser.add_argument(
        "--workspace",
        help="Explicit per-session workspace. Defaults to the current directory when omitted.",
    )
    call_parser.add_argument("--allowed-root", action="append", help="Additional allowed root for safe file actions.")
    call_parser.add_argument("--param", action="append", help="Action parameter in KEY=VALUE format")
    call_parser.add_argument("--json", action="store_true", help="Emit JSON")

    plan_parser = subparsers.add_parser("run-plan", help="Run a YAML or JSON execution plan")
    plan_parser.add_argument("path", help="Path to the plan file")
    plan_parser.add_argument("--json", action="store_true", help="Emit JSON")

    return parser


def _format_env_human(payload: dict[str, Any]) -> str:
    ansys = payload["ansys"]
    modules = payload["modules"]
    lines = [
        f"Python: {payload['python']['executable']}",
        f"Ansys version: {ansys['version'] or 'not found'}",
        f"AWP root: {ansys['awp_root'] or 'not found'}",
        f"Fluent: {ansys['fluent_exe'] or 'not found'}",
        f"Workbench: {ansys['workbench_exe'] or 'not found'}",
        f"Mechanical: {ansys['mechanical_exe'] or 'not found'}",
        "Modules:",
    ]
    for name, version in modules.items():
        lines.append(f"  - {name}: {version}")
    return "\n".join(lines)


def _format_adapter_statuses_human(statuses: list[dict[str, Any]]) -> str:
    lines = []
    for item in statuses:
        state = "available" if item["available"] else "unavailable"
        maturity = item.get("maturity", "stable")
        safe_actions = [action["name"] for action in item["actions"] if action["profile"] == "safe"]
        expert_actions = [action["name"] for action in item["actions"] if action["profile"] == "expert"]
        sections = [f"safe: {', '.join(safe_actions) if safe_actions else '-'}"]
        if expert_actions:
            sections.append(f"expert: {', '.join(expert_actions)}")
        line = f"{item['name']}: {state} ({maturity}) [{' | '.join(sections)}]"
        if item["reason"]:
            line += f" - {item['reason']}"
        elif item["details"].get("note"):
            line += f" - {item['details']['note']}"
        lines.append(line)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = detect_environment(args.ansys_version)
        registry = build_registry()
        executor = WorkflowExecutor(env, registry)

        if args.command == "env":
            payload = env.to_dict()
            if args.json:
                _print_json(payload)
            else:
                print(_format_env_human(payload))
            return 0

        if args.command == "adapters":
            statuses = [status.to_dict() for status in registry.statuses(env)]
            if args.json:
                _print_json(statuses)
            else:
                print(_format_adapter_statuses_human(statuses))
            return 0

        if args.command == "call":
            result = executor.call(
                args.adapter,
                args.action,
                params=_parse_key_value(args.param),
                adapter_options=_parse_key_value(args.option),
                profile=args.profile,
                allowed_roots=args.allowed_root,
                workspace=args.workspace,
            )
            _print_json(result)
            return 0

        if args.command == "run-plan":
            summary = executor.run_plan(load_plan(args.path))
            _print_json(summary.to_dict())
            return 0 if summary.ok else 1

        parser.error(f"Unhandled command: {args.command}")
        return 2
    except Exception as exc:  # pragma: no cover - runtime and environment dependent
        if getattr(args, "command", None) in {"call", "run-plan"} or getattr(args, "json", False):
            _print_json({"ok": False, "error": str(exc)})
        else:
            print(f"Error: {exc}")
        return 1
