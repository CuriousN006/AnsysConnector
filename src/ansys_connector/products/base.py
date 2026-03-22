from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from ansys_connector.core.environment import EnvironmentInfo


class AdapterError(RuntimeError):
    """Base adapter failure."""


ActionProfile = Literal["safe", "expert"]
AdapterMaturity = Literal["stable", "beta", "experimental"]
ParameterKind = Literal["string", "integer", "number", "boolean", "object", "array", "path", "any"]


@dataclass(frozen=True)
class ActionParameter:
    """Typed parameter description for one adapter action."""

    name: str
    kind: ParameterKind = "any"
    required: bool = False
    description: str | None = None
    is_path: bool = False
    repeated: bool = False
    choices: tuple[Any, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "description": self.description,
            "is_path": self.is_path,
            "repeated": self.repeated,
            "choices": list(self.choices) if self.choices is not None else None,
        }


@dataclass(frozen=True)
class ActionExecutionContext:
    """Execution context used for validation and path policy."""

    adapter: str
    profile: ActionProfile
    allowed_roots: tuple[Path, ...]
    cwd: Path
    env: EnvironmentInfo


ActionValidator = Callable[[dict[str, Any], ActionExecutionContext], dict[str, Any]]


@dataclass(frozen=True)
class ActionDefinition:
    """Structured adapter action metadata."""

    name: str
    profile: ActionProfile
    description: str
    parameters: tuple[ActionParameter, ...] = ()
    path_fields: tuple[str, ...] = ()
    allow_extra: bool = False
    validator: ActionValidator | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "profile": self.profile,
            "description": self.description,
            "path_fields": list(self.path_fields),
            "allow_extra": self.allow_extra,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


@dataclass(frozen=True)
class AdapterStatus:
    """Runtime availability snapshot for an adapter."""

    name: str
    available: bool
    actions: tuple[ActionDefinition, ...]
    maturity: AdapterMaturity = "stable"
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(action.name for action in self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "maturity": self.maturity,
            "capabilities": list(self.capabilities),
            "actions": [action.to_dict() for action in self.actions],
            "reason": self.reason,
            "details": dict(self.details),
        }


class AdapterSession(ABC):
    """Live product session."""

    @abstractmethod
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Execute one action on the live product session."""

    @abstractmethod
    def close(self) -> None:
        """Cleanly close the live product session."""


class Adapter(ABC):
    """Base class for product adapters."""

    name: str = ""
    actions: tuple[ActionDefinition, ...] = ()

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(action.name for action in self.actions)

    def get_action(self, name: str) -> ActionDefinition:
        for action in self.actions:
            if action.name == name:
                return action
        raise AdapterError(f"Unsupported {self.name} action: {name}")

    def available_actions(self, profile: ActionProfile | None = None) -> tuple[ActionDefinition, ...]:
        if profile == "safe":
            return tuple(action for action in self.actions if action.profile == "safe")
        return self.actions

    def describe_actions(self, profile: ActionProfile | None = None) -> list[dict[str, Any]]:
        return [action.to_dict() for action in self.available_actions(profile)]

    @abstractmethod
    def inspect(self, env: EnvironmentInfo) -> AdapterStatus:
        """Report whether the adapter can run in the current environment."""

    @abstractmethod
    def open_session(self, env: EnvironmentInfo, options: dict[str, Any], *, workspace: Path) -> AdapterSession:
        """Open a session for this adapter."""
