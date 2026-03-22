from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    """Single adapter action."""

    adapter: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    continue_on_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "adapter": self.adapter,
            "action": self.action,
            "params": dict(self.params),
            "continue_on_error": self.continue_on_error,
        }
        if self.label:
            payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class PlanAdapterConfig:
    """Per-adapter session settings used by plan execution."""

    profile: str = "safe"
    options: dict[str, Any] = field(default_factory=dict)
    allowed_roots: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile": self.profile,
            "options": dict(self.options),
        }
        if self.allowed_roots:
            payload["allowed_roots"] = list(self.allowed_roots)
        return payload


@dataclass(frozen=True)
class ExecutionPlan:
    """Declarative multi-step workflow."""

    name: str
    adapters: dict[str, PlanAdapterConfig]
    steps: list[PlanStep]
    continue_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapters": {name: config.to_dict() for name, config in self.adapters.items()},
            "continue_on_error": self.continue_on_error,
            "metadata": self.metadata,
            "steps": [step.to_dict() for step in self.steps],
        }
