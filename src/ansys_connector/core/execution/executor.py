from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.core.policy import prepare_action
from ansys_connector.core.registry import AdapterRegistry
from ansys_connector.workflows.plans.models import ExecutionPlan, PlanSessionConfig, PlanStep

from .managed_session import open_managed_session, resolve_workspace
from ansys_connector.products.base import AdapterSession


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
        )
        try:
            return session.execute(action, validated)
        finally:
            session.close()

    def run_plan(self, plan: ExecutionPlan) -> ExecutionSummary:
        sessions: dict[str, AdapterSession] = {}
        results: list[StepExecutionResult] = []
        keep_going = True

        try:
            for index, step in enumerate(plan.steps, start=1):
                if not keep_going:
                    break
                result = self._run_step(index, step, plan, sessions)
                results.append(result)
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
    ) -> StepExecutionResult:
        try:
            config = plan.sessions.get(step.session, PlanSessionConfig(adapter=step.session))
            adapter = self._registry.get(config.adapter)
            workspace_path = resolve_workspace(config.workspace, create=False) if config.workspace is not None else None
            validated = prepare_action(
                adapter=adapter,
                env=self._env,
                action=step.action,
                params=step.params,
                profile=config.profile,
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
