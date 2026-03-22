from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import ExecutionPlan, PlanSessionConfig, PlanStep


_ALLOWED_TOP_LEVEL_FIELDS = {"name", "adapters", "sessions", "steps", "continue_on_error", "metadata"}
_ALLOWED_STEP_FIELDS = {"adapter", "session", "action", "params", "label", "continue_on_error"}
_SESSION_META_FIELDS = {"adapter", "profile", "workspace", "allowed_roots", "options"}


def _load_serialized(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Plan file must deserialize to an object.")
    return data


def _validate_allowed_fields(payload: dict[str, Any], allowed: set[str], prefix: str) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        joined = ", ".join(extras)
        raise ValueError(f"{prefix} contains unsupported fields: {joined}")


def _load_session_config(
    name: str,
    payload: Any,
    *,
    default_adapter: str | None = None,
) -> PlanSessionConfig:
    if not isinstance(payload, dict):
        raise ValueError(f"Session config '{name}' must be an object.")

    raw_adapter = payload.get("adapter", default_adapter)
    if not isinstance(raw_adapter, str) or not raw_adapter.strip():
        raise ValueError(f"Session '{name}' must declare a non-empty 'adapter' field.")
    adapter = raw_adapter.strip()

    profile = str(payload.get("profile", "safe"))
    raw_workspace = payload.get("workspace")
    if raw_workspace is None:
        workspace: str | None = None
    elif isinstance(raw_workspace, (str, Path)):
        workspace = str(raw_workspace)
    else:
        raise ValueError(f"Adapter '{name}' has a non-string 'workspace' field.")

    raw_allowed_roots = payload.get("allowed_roots", [])
    if raw_allowed_roots in (None, []):
        allowed_roots: tuple[str, ...] = ()
    elif isinstance(raw_allowed_roots, list) and all(isinstance(item, (str, Path)) for item in raw_allowed_roots):
        allowed_roots = tuple(str(item) for item in raw_allowed_roots)
    else:
        raise ValueError(f"Session '{name}' has a non-list 'allowed_roots' field.")

    if "options" in payload:
        _validate_allowed_fields(payload, _SESSION_META_FIELDS, f"Session '{name}'")
        options = payload.get("options", {})
        if not isinstance(options, dict):
            raise ValueError(f"Session '{name}' has a non-object 'options' field.")
    else:
        options = {
            key: value
            for key, value in payload.items()
            if key not in {"adapter", "profile", "workspace", "allowed_roots"}
        }

    return PlanSessionConfig(
        adapter=adapter,
        profile=profile,
        workspace=workspace,
        options=dict(options),
        allowed_roots=allowed_roots,
    )


def _load_step(index: int, payload: Any) -> PlanStep:
    if not isinstance(payload, dict):
        raise ValueError(f"Step {index} must be an object.")
    _validate_allowed_fields(payload, _ALLOWED_STEP_FIELDS, f"Step {index}")

    adapter = payload.get("adapter")
    session = payload.get("session")
    action = payload.get("action")
    if adapter and session:
        raise ValueError(f"Step {index} must define only one of 'session' or legacy 'adapter'.")
    target_session = session or adapter
    if not target_session or not action:
        raise ValueError(f"Step {index} must define 'session' and 'action'.")

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(f"Step {index} has a non-object 'params' field.")

    label = payload.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(f"Step {index} has a non-string 'label' field.")
    if isinstance(label, str) and "." in label:
        raise ValueError(f"Step {index} label may not contain '.'.")

    return PlanStep(
        session=str(target_session),
        action=str(action),
        params=dict(params),
        label=label,
        continue_on_error=bool(payload.get("continue_on_error", False)),
    )


def load_plan(path: str | Path) -> ExecutionPlan:
    """Load a YAML or JSON execution plan."""

    plan_path = Path(path)
    payload = _load_serialized(plan_path)
    _validate_allowed_fields(payload, _ALLOWED_TOP_LEVEL_FIELDS, "Plan")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Plan must contain a non-empty 'steps' list.")

    raw_sessions = payload.get("sessions")
    raw_adapters = payload.get("adapters")
    if raw_sessions is not None and raw_adapters is not None:
        raise ValueError("Plan may define 'sessions' or legacy 'adapters', but not both.")
    raw_session_map = raw_sessions if raw_sessions is not None else (raw_adapters if raw_adapters is not None else {})
    if not isinstance(raw_session_map, dict):
        raise ValueError("'sessions' must be an object when provided.")

    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("'metadata' must be an object when provided.")

    default_adapter = None if raw_sessions is not None else "legacy"
    sessions = {
        str(name): _load_session_config(
            str(name),
            config,
            default_adapter=str(name) if default_adapter == "legacy" else None,
        )
        for name, config in raw_session_map.items()
    }
    steps = [_load_step(index, item) for index, item in enumerate(raw_steps, start=1)]
    labels = [step.label for step in steps if step.label]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(f"Plan contains duplicate step labels: {', '.join(duplicates)}")

    return ExecutionPlan(
        name=str(payload.get("name", plan_path.stem)),
        sessions=sessions,
        steps=steps,
        continue_on_error=bool(payload.get("continue_on_error", False)),
        metadata=dict(metadata),
    )
