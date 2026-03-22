from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from ansys_connector.core import build_registry, detect_environment
from ansys_connector.core.execution import WorkflowExecutor
from ansys_connector.workflows.plans import load_plan
from ansys_connector.workflows.templates import WorkflowService


_INTEGER_PATTERN = re.compile(r"^-?\d+$")
_NUMBER_PATTERN = re.compile(r"^-?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")


def _parse_cli_value(raw_value: str) -> Any:
    stripped = raw_value.strip()
    lowered = stripped.lower()
    if lowered in {"true", "false", "null"}:
        return yaml.safe_load(stripped)
    if _INTEGER_PATTERN.fullmatch(stripped) or _NUMBER_PATTERN.fullmatch(stripped):
        return yaml.safe_load(stripped)
    if stripped.startswith(("{", "[", "\"", "'")):
        return yaml.safe_load(stripped)
    return raw_value


def _parse_key_value(values: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"Expected KEY=VALUE format, got: {raw}")
        key, raw_value = raw.split("=", 1)
        parsed[key] = _parse_cli_value(raw_value)
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


def _normalize_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=_json_default))


def _print_structured(payload: Any, *, as_json: bool) -> None:
    if as_json:
        _print_json(payload)
        return
    print(yaml.safe_dump(_normalize_payload(payload), sort_keys=False).rstrip())


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
        help="Execution profile. Expert enables raw actions, which also require --option allow_raw_actions=true.",
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

    list_workflows_parser = subparsers.add_parser("list-workflows", help="List high-level workflow templates")
    list_workflows_parser.add_argument("product", nargs="?", help="Optional product filter, such as fluent")
    list_workflows_parser.add_argument("--json", action="store_true", help="Emit JSON")

    describe_workflow_parser = subparsers.add_parser("describe-workflow", help="Describe one workflow template")
    describe_workflow_parser.add_argument("name", help="Workflow name, such as fluent.steady_run")
    describe_workflow_parser.add_argument("--json", action="store_true", help="Emit JSON")

    start_workflow_parser = subparsers.add_parser("start-workflow", help="Start an asynchronous workflow run")
    start_workflow_parser.add_argument("name", help="Workflow name, such as fluent.steady_run")
    start_workflow_parser.add_argument("--spec", required=True, help="Path to the YAML or JSON workflow spec")
    start_workflow_parser.add_argument("--version", dest="workflow_version", help="Prefer a specific AWP_ROOT version.")
    start_workflow_parser.add_argument("--workspace", help="Explicit workflow workspace")
    start_workflow_parser.add_argument("--wait", action="store_true", help="Wait for the workflow to finish")
    start_workflow_parser.add_argument("--json", action="store_true", help="Emit JSON")

    get_workflow_run_parser = subparsers.add_parser("get-workflow-run", help="Inspect one workflow run")
    get_workflow_run_parser.add_argument("run_id", help="Workflow run identifier")
    get_workflow_run_parser.add_argument("--json", action="store_true", help="Emit JSON")

    cancel_workflow_run_parser = subparsers.add_parser("cancel-workflow-run", help="Request workflow cancellation")
    cancel_workflow_run_parser.add_argument("run_id", help="Workflow run identifier")
    cancel_workflow_run_parser.add_argument("--json", action="store_true", help="Emit JSON")

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
        env = None
        registry = None
        executor = None
        workflow_service = None

        def get_env():
            nonlocal env
            if env is None:
                env = detect_environment(args.ansys_version)
            return env

        def get_registry():
            nonlocal registry
            if registry is None:
                registry = build_registry()
            return registry

        def get_executor():
            nonlocal executor
            if executor is None:
                executor = WorkflowExecutor(get_env(), get_registry())
            return executor

        def get_workflow_service() -> WorkflowService:
            nonlocal workflow_service
            if workflow_service is None:
                workflow_service = WorkflowService()
            return workflow_service

        if args.command == "env":
            payload = get_env().to_dict()
            if args.json:
                _print_json(payload)
            else:
                print(_format_env_human(payload))
            return 0

        if args.command == "adapters":
            statuses = [status.to_dict() for status in get_registry().statuses(get_env())]
            if args.json:
                _print_json(statuses)
            else:
                print(_format_adapter_statuses_human(statuses))
            return 0

        if args.command == "call":
            result = get_executor().call(
                args.adapter,
                args.action,
                params=_parse_key_value(args.param),
                adapter_options=_parse_key_value(args.option),
                profile=args.profile,
                allowed_roots=args.allowed_root,
                workspace=args.workspace,
            )
            _print_structured(result, as_json=args.json)
            return 0

        if args.command == "run-plan":
            summary = get_executor().run_plan(load_plan(args.path))
            _print_structured(summary.to_dict(), as_json=args.json)
            return 0 if summary.ok else 1

        if args.command == "list-workflows":
            workflows = get_workflow_service().list_workflows(args.product)
            _print_structured(workflows, as_json=args.json)
            return 0

        if args.command == "describe-workflow":
            workflow = get_workflow_service().describe_workflow(args.name)
            _print_structured(workflow, as_json=args.json)
            return 0

        if args.command == "start-workflow":
            run = get_workflow_service().start_workflow(
                args.name,
                args.spec,
                version=args.workflow_version or args.ansys_version,
                workspace=args.workspace,
            )
            if args.wait:
                run = get_workflow_service().wait_for_run(run["run_id"])
            _print_structured(run, as_json=args.json)
            return 0 if run["status"] == "succeeded" else (1 if args.wait else 0)

        if args.command == "get-workflow-run":
            run = get_workflow_service().get_run(args.run_id)
            _print_structured(run, as_json=args.json)
            return 0

        if args.command == "cancel-workflow-run":
            run = get_workflow_service().cancel_run(args.run_id)
            _print_structured(run, as_json=args.json)
            return 0

        parser.error(f"Unhandled command: {args.command}")
        return 2
    except Exception as exc:  # pragma: no cover - runtime and environment dependent
        if getattr(args, "json", False):
            _print_json({"ok": False, "error": str(exc)})
        elif getattr(args, "command", None) in {"call", "run-plan"}:
            print(f"Error: {exc}")
        else:
            print(f"Error: {exc}")
        return 1
