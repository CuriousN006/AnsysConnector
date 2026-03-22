from __future__ import annotations

from typing import Any

from ansys_connector.products.base import ActionExecutionContext, AdapterError


def _ensure_positive_int(params: dict[str, Any], keys: tuple[str, ...], action_name: str) -> dict[str, Any]:
    for key in keys:
        if key not in params:
            continue
        value = params[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AdapterError(f"Fluent {action_name} parameter '{key}' must be a positive integer.")
    return params


def validate_scheme_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    mode = str(params.get("mode", "eval"))
    if mode == "exec":
        commands = params.get("commands")
        command = params.get("command")
        if commands is None and isinstance(command, str):
            params["commands"] = [command]
            params.pop("command", None)
            return params
        if not isinstance(commands, list) or not commands:
            raise AdapterError("Fluent scheme exec requires 'command' or 'commands'.")
        return params

    command = params.get("command")
    if not isinstance(command, str) or not command.strip():
        raise AdapterError("Fluent scheme action requires a non-empty 'command'.")
    return params


def validate_tui_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    commands = params.get("commands")
    command = params.get("command")
    if commands is None and isinstance(command, str):
        params["commands"] = [command]
        params.pop("command", None)
        return params
    if not isinstance(commands, list) or not commands:
        raise AdapterError("Fluent tui action requires 'command' or 'commands'.")
    return params


def validate_command_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    path = params.get("path")
    if not isinstance(path, str) or not path.strip():
        raise AdapterError("Fluent command action requires a non-empty 'path'.")
    args = params.get("args")
    if args is not None and not isinstance(args, list):
        raise AdapterError("Fluent command action 'args' must be a list when provided.")
    kwargs = params.get("kwargs")
    if kwargs is not None and not isinstance(kwargs, dict):
        raise AdapterError("Fluent command action 'kwargs' must be an object when provided.")
    return params


def validate_iterate_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    return _ensure_positive_int(params, ("iter_count", "count", "number_of_iterations"), "iterate")
