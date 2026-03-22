from __future__ import annotations

from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.core.policy.paths import normalize_allowed_roots, normalize_path_value
from ansys_connector.core.policy.profiles import normalize_profile
from ansys_connector.products.base import (
    ActionDefinition,
    ActionExecutionContext,
    ActionParameter,
    Adapter,
    AdapterError,
)


def _validate_scalar_kind(spec: ActionParameter, value: Any) -> None:
    if spec.kind == "any":
        valid = True
    elif spec.kind == "string":
        valid = isinstance(value, str)
    elif spec.kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif spec.kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif spec.kind == "boolean":
        valid = isinstance(value, bool)
    elif spec.kind == "object":
        valid = isinstance(value, dict)
    elif spec.kind == "array":
        valid = isinstance(value, list)
    elif spec.kind == "path":
        valid = isinstance(value, (str, Path))
    else:  # pragma: no cover - defensive branch
        valid = False

    if not valid:
        raise AdapterError(
            f"Parameter '{spec.name}' for action expects {spec.kind}, got {type(value).__name__}."
        )

    if spec.choices is not None and value not in spec.choices:
        choices = ", ".join(repr(choice) for choice in spec.choices)
        raise AdapterError(f"Parameter '{spec.name}' must be one of: {choices}")


def validate_action_params(
    definition: ActionDefinition,
    params: dict[str, Any] | None,
    context: ActionExecutionContext,
) -> dict[str, Any]:
    if params is None:
        payload: dict[str, Any] = {}
    elif isinstance(params, dict):
        payload = dict(params)
    else:
        raise AdapterError(f"Action parameters for {context.adapter}.{definition.name} must be an object.")

    spec_map = {parameter.name: parameter for parameter in definition.parameters}
    extras = sorted(set(payload) - set(spec_map))
    if extras and not definition.allow_extra:
        joined = ", ".join(extras)
        raise AdapterError(f"Unsupported parameters for {context.adapter}.{definition.name}: {joined}")

    validated: dict[str, Any] = {}
    for spec in definition.parameters:
        if spec.name not in payload:
            if spec.required:
                raise AdapterError(f"Missing required parameter '{spec.name}' for {context.adapter}.{definition.name}")
            continue

        value = payload[spec.name]
        if spec.repeated:
            if not isinstance(value, list):
                raise AdapterError(f"Parameter '{spec.name}' must be a list.")
            for item in value:
                item_spec = ActionParameter(
                    name=spec.name,
                    kind="path" if spec.is_path else spec.kind,
                    choices=spec.choices,
                )
                _validate_scalar_kind(item_spec, item)
            validated[spec.name] = (
                normalize_path_value(value, context) if spec.is_path or spec.kind == "path" else list(value)
            )
            continue

        _validate_scalar_kind(spec, value)
        if spec.is_path or spec.kind == "path" or spec.name in definition.path_fields:
            validated[spec.name] = normalize_path_value(value, context)
        else:
            validated[spec.name] = value

    if definition.allow_extra:
        for key, value in payload.items():
            if key not in validated:
                validated[key] = value

    for field_name in definition.path_fields:
        if field_name in validated:
            continue
        if field_name in payload:
            validated[field_name] = normalize_path_value(payload[field_name], context)

    if definition.validator is not None:
        validated = definition.validator(dict(validated), context)

    return validated


def prepare_action(
    *,
    adapter: Adapter,
    env: EnvironmentInfo,
    action: str,
    params: dict[str, Any] | None,
    profile: str | None = None,
    allowed_roots: list[str] | tuple[str, ...] | str | Path | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    workspace = (cwd or Path.cwd()).resolve(strict=False)
    normalized_profile = normalize_profile(profile)
    context = ActionExecutionContext(
        adapter=adapter.name,
        profile=normalized_profile,
        allowed_roots=normalize_allowed_roots(allowed_roots, cwd=workspace),
        cwd=workspace,
        env=env,
    )
    definition = adapter.get_action(action)
    if normalized_profile == "safe" and definition.profile != "safe":
        raise AdapterError(
            f"Action '{adapter.name}.{action}' requires the expert profile. "
            "Open the session with profile='expert' to use raw script or TUI execution."
        )
    return validate_action_params(definition, params, context)
