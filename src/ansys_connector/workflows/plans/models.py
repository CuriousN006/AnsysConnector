from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    """Single adapter action."""

    session: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    continue_on_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "session": self.session,
            "action": self.action,
            "params": dict(self.params),
            "continue_on_error": self.continue_on_error,
        }
        if self.label:
            payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class PlanSessionConfig:
    """Per-session settings used by plan execution."""

    adapter: str
    profile: str = "safe"
    workspace: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    allowed_roots: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "adapter": self.adapter,
            "profile": self.profile,
            "options": dict(self.options),
        }
        if self.workspace is not None:
            payload["workspace"] = self.workspace
        if self.allowed_roots:
            payload["allowed_roots"] = list(self.allowed_roots)
        return payload


PlanAdapterConfig = PlanSessionConfig


@dataclass(frozen=True)
class ExecutionPlan:
    """Declarative multi-step workflow."""

    name: str
    sessions: dict[str, PlanSessionConfig]
    steps: list[PlanStep]
    continue_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def adapters(self) -> dict[str, PlanSessionConfig]:
        """Compatibility alias for older callers."""
        return self.sessions

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sessions": {name: config.to_dict() for name, config in self.sessions.items()},
            "continue_on_error": self.continue_on_error,
            "metadata": self.metadata,
            "steps": [step.to_dict() for step in self.steps],
        }
