from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.core.policy import prepare_action
from ansys_connector.core.registry import AdapterRegistry
from ansys_connector.workflows.plans.models import ExecutionPlan, PlanSessionConfig, PlanStep

from .managed_session import open_managed_session, resolve_workspace
from ansys_connector.products.base import AdapterSession


_REFERENCE_PATTERN = re.compile(r"\$\{([^{}]+)\}")


@dataclass(frozen=True)
class StepExecutionResult:
    index: int
    session: str
    adapter: str
    action: str
    ok: bool
    label: str | None = None
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "session": self.session,
            "adapter": self.adapter,
            "action": self.action,
            "ok": self.ok,
            "label": self.label,
            "data": self.data,
            "error": self.error,
        }


@dataclass(frozen=True)
class ExecutionSummary:
    plan: str
    ok: bool
    results: list[StepExecutionResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "ok": self.ok,
            "results": [result.to_dict() for result in self.results],
        }


class WorkflowExecutor:
    """Run adapter actions either directly or from a plan."""

    def __init__(self, env: EnvironmentInfo, registry: AdapterRegistry) -> None:
        self._env = env
        self._registry = registry

    def call(
        self,
        adapter_name: str,
        action: str,
        params: dict[str, Any] | None = None,
        adapter_options: dict[str, Any] | None = None,
        profile: str | None = "safe",
        allowed_roots: list[str] | tuple[str, ...] | None = None,
        workspace: str | Path | None = None,
    ) -> Any:
        adapter = self._registry.get(adapter_name)
        workspace_path = resolve_workspace(workspace, create=False) if workspace is not None else None
        validated = prepare_action(
            adapter=adapter,
            env=self._env,
            action=action,
            params=params,
            profile=profile,
            raw_actions_enabled=bool((adapter_options or {}).get("allow_raw_actions", False)),
            allowed_roots=allowed_roots,
            cwd=workspace_path,
        )
        session = open_managed_session(
            adapter=adapter,
            env=self._env,
            options=adapter_options or {},
            profile=profile,
            allowed_roots=allowed_roots,
            workspace=workspace_path,
            session_label=f"call:{adapter_name}:{uuid4()}",
        )
        try:
            return session.execute(action, validated)
        finally:
            session.close()

    def run_plan(self, plan: ExecutionPlan) -> ExecutionSummary:
        sessions: dict[str, AdapterSession] = {}
        results: list[StepExecutionResult] = []
        labeled_results: dict[str, StepExecutionResult] = {}
        keep_going = True

        try:
            for index, step in enumerate(plan.steps, start=1):
                if not keep_going:
                    break
                result = self._run_step(index, step, plan, sessions, labeled_results)
                results.append(result)
                if step.label:
                    labeled_results[step.label] = result
                if not result.ok and not (plan.continue_on_error or step.continue_on_error):
                    keep_going = False
        finally:
            for session in sessions.values():
                try:
                    session.close()
                except Exception:  # pragma: no cover - runtime product shutdown
                    pass

        return ExecutionSummary(
            plan=plan.name,
            ok=all(result.ok for result in results),
            results=results,
        )

    def _run_step(
        self,
        index: int,
        step: PlanStep,
        plan: ExecutionPlan,
        sessions: dict[str, AdapterSession],
        labeled_results: dict[str, StepExecutionResult],
    ) -> StepExecutionResult:
        try:
            config = plan.sessions.get(step.session, PlanSessionConfig(adapter=step.session))
            adapter = self._registry.get(config.adapter)
            workspace_path = resolve_workspace(config.workspace, create=False) if config.workspace is not None else None
            resolved_params = self._resolve_plan_value(
                step.params,
                plan=plan,
                labeled_results=labeled_results,
            )
            validated = prepare_action(
                adapter=adapter,
                env=self._env,
                action=step.action,
                params=resolved_params,
                profile=config.profile,
                raw_actions_enabled=bool(config.options.get("allow_raw_actions", False)),
                allowed_roots=list(config.allowed_roots),
                cwd=workspace_path,
            )
            if step.session not in sessions:
                sessions[step.session] = open_managed_session(
                    adapter=adapter,
                    env=self._env,
                    options=dict(config.options),
                    profile=config.profile,
                    allowed_roots=list(config.allowed_roots),
                    workspace=workspace_path,
                    session_label=step.session,
                )
            data = sessions[step.session].execute(step.action, validated)
            return StepExecutionResult(
                index=index,
                session=step.session,
                adapter=config.adapter,
                action=step.action,
                ok=True,
                label=step.label,
                data=data,
            )
        except Exception as exc:  # pragma: no cover - runtime product errors
            return StepExecutionResult(
                index=index,
                session=step.session,
                adapter=config.adapter if "config" in locals() else step.session,
                action=step.action,
                ok=False,
                label=step.label,
                error=str(exc),
            )

    def _session_reference_map(self, plan: ExecutionPlan) -> dict[str, dict[str, Any]]:
        session_map: dict[str, dict[str, Any]] = {}
        for handle, config in plan.sessions.items():
            workspace = resolve_workspace(config.workspace, create=False) if config.workspace is not None else resolve_workspace(None, create=False)
            session_map[handle] = {
                "name": handle,
                "adapter": config.adapter,
                "profile": config.profile,
                "workspace": str(workspace),
                "options": dict(config.options),
                "allowed_roots": list(config.allowed_roots),
            }
        return session_map

    def _resolve_reference(
        self,
        expression: str,
        *,
        plan: ExecutionPlan,
        labeled_results: dict[str, StepExecutionResult],
    ) -> Any:
        parts = expression.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid plan reference: {expression}")

        namespace, key = parts[0], parts[1]
        remainder = parts[2:]
        if namespace == "steps":
            if key not in labeled_results:
                raise ValueError(f"Unknown plan step reference: {key}")
            current: Any = labeled_results[key].to_dict()
        elif namespace == "sessions":
            session_map = self._session_reference_map(plan)
            if key not in session_map:
                raise ValueError(f"Unknown plan session reference: {key}")
            current = session_map[key]
        else:
            raise ValueError(f"Unsupported plan reference root: {namespace}")

        for segment in remainder:
            if isinstance(current, dict):
                if segment not in current:
                    raise ValueError(f"Unknown field '{segment}' in plan reference: {expression}")
                current = current[segment]
                continue
            if isinstance(current, list):
                try:
                    index = int(segment)
                except ValueError as exc:
                    raise ValueError(f"List reference segment must be an integer in: {expression}") from exc
                try:
                    current = current[index]
                except IndexError as exc:
                    raise ValueError(f"List reference index out of range in: {expression}") from exc
                continue
            raise ValueError(f"Cannot descend into '{segment}' for plan reference: {expression}")
        return current

    def _resolve_plan_value(
        self,
        value: Any,
        *,
        plan: ExecutionPlan,
        labeled_results: dict[str, StepExecutionResult],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._resolve_plan_value(item, plan=plan, labeled_results=labeled_results)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_plan_value(item, plan=plan, labeled_results=labeled_results) for item in value]
        if not isinstance(value, str):
            return value

        exact_match = _REFERENCE_PATTERN.fullmatch(value)
        if exact_match:
            return self._resolve_reference(exact_match.group(1), plan=plan, labeled_results=labeled_results)

        def replace(match: re.Match[str]) -> str:
            resolved = self._resolve_reference(match.group(1), plan=plan, labeled_results=labeled_results)
            return str(resolved)

        return _REFERENCE_PATTERN.sub(replace, value)
