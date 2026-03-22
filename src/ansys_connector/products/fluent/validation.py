from __future__ import annotations

from typing import Any

from ansys_connector.core.policy.paths import normalize_path_value
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


def validate_initialize_solution_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    method = str(params.get("method", "hybrid"))
    if method not in {"hybrid", "standard"}:
        raise AdapterError("Fluent initialize_solution method must be one of: hybrid, standard.")
    params["method"] = method
    return params


def validate_run_iterations_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    return _ensure_positive_int(params, ("count",), "run_iterations")


def validate_run_time_steps_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    params = _ensure_positive_int(params, ("step_count", "max_iterations_per_step"), "run_time_steps")
    if "time_step_size" in params:
        value = params["time_step_size"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise AdapterError("Fluent run_time_steps parameter 'time_step_size' must be a positive number.")
    return params


def validate_collect_reports_params(params: dict[str, Any], _: ActionExecutionContext) -> dict[str, Any]:
    reports = params.get("reports")
    if not isinstance(reports, list) or not reports:
        raise AdapterError("Fluent collect_reports requires a non-empty 'reports' list.")
    normalized: list[dict[str, Any]] = []
    for index, report in enumerate(reports, start=1):
        if not isinstance(report, dict):
            raise AdapterError(f"Fluent collect_reports item {index} must be an object.")
        name = report.get("name")
        command_path = report.get("command_path")
        if not isinstance(name, str) or not name.strip():
            raise AdapterError(f"Fluent collect_reports item {index} requires a non-empty 'name'.")
        if not isinstance(command_path, str) or not command_path.startswith("results.report."):
            raise AdapterError(
                f"Fluent collect_reports item {index} must use a 'command_path' under 'results.report.'."
            )
        args = report.get("args", [])
        kwargs = report.get("kwargs", {})
        if not isinstance(args, list):
            raise AdapterError(f"Fluent collect_reports item {index} field 'args' must be a list.")
        if not isinstance(kwargs, dict):
            raise AdapterError(f"Fluent collect_reports item {index} field 'kwargs' must be an object.")
        normalized.append(
            {
                "name": name.strip(),
                "command_path": command_path,
                "args": list(args),
                "kwargs": dict(kwargs),
            }
        )
    params["reports"] = normalized
    return params


def validate_export_results_params(params: dict[str, Any], context: ActionExecutionContext) -> dict[str, Any]:
    images = params.get("images")
    if not isinstance(images, list) or not images:
        raise AdapterError("Fluent export_results requires a non-empty 'images' list.")

    normalized: list[dict[str, Any]] = []
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            raise AdapterError(f"Fluent export_results image {index} must be an object.")
        name = image.get("name")
        file_name = image.get("file_name")
        kind = str(image.get("kind", "picture"))
        if not isinstance(name, str) or not name.strip():
            raise AdapterError(f"Fluent export_results image {index} requires a non-empty 'name'.")
        if not isinstance(file_name, str) or not file_name.strip():
            raise AdapterError(f"Fluent export_results image {index} requires a non-empty 'file_name'.")
        if kind not in {"picture", "contour"}:
            raise AdapterError(f"Fluent export_results image {index} kind must be 'picture' or 'contour'.")

        picture_state = image.get("picture_state", {})
        if not isinstance(picture_state, dict):
            raise AdapterError(f"Fluent export_results image {index} field 'picture_state' must be an object.")

        normalized_image: dict[str, Any] = {
            "name": name.strip(),
            "kind": kind,
            "file_name": normalize_path_value(file_name, context),
            "picture_state": dict(picture_state),
        }

        if "contour" in image:
            contour = image["contour"]
            if not isinstance(contour, dict):
                raise AdapterError(f"Fluent export_results image {index} field 'contour' must be an object.")
            object_name = contour.get("object_name", f"{name}_contour")
            state = contour.get("state", {})
            if not isinstance(object_name, str) or not object_name.strip():
                raise AdapterError(f"Fluent export_results image {index} contour requires 'object_name'.")
            if not isinstance(state, dict):
                raise AdapterError(f"Fluent export_results image {index} contour 'state' must be an object.")
            normalized_image["contour"] = {
                "object_name": object_name.strip(),
                "state": dict(state),
            }
        normalized.append(normalized_image)

    params["images"] = normalized
    return params


def validate_checkpoint_case_data_params(params: dict[str, Any], context: ActionExecutionContext) -> dict[str, Any]:
    file_name = params.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        raise AdapterError("Fluent checkpoint_case_data requires a non-empty 'file_name'.")
    params["file_name"] = normalize_path_value(file_name, context)
    return params
