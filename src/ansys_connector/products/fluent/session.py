from __future__ import annotations

from typing import Any

import yaml

from ansys_connector.products.base import AdapterError, AdapterSession

from .runtime import suppress_fluent_launcher_noise


def _escape_scheme_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _tokenize_path(path: str) -> list[str]:
    normalized = path.strip().replace("/", ".")
    if normalized.startswith("settings."):
        normalized = normalized[len("settings.") :]
    if not normalized:
        return []

    tokens: list[str] = []
    current = []
    bracket_depth = 0
    for char in normalized:
        if char == "." and bracket_depth == 0:
            token = "".join(current).strip()
            if token:
                tokens.append(token)
            current = []
            continue
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        current.append(char)

    token = "".join(current).strip()
    if token:
        tokens.append(token)
    return tokens


def _parse_token(token: str) -> tuple[str, list[Any]]:
    name, _, remainder = token.partition("[")
    indexes: list[Any] = []
    while remainder:
        item, _, tail = remainder.partition("]")
        indexes.append(yaml.safe_load(item))
        remainder = tail[1:] if tail.startswith("[") else tail
    return name, indexes


def _safe_call(value: Any) -> Any:
    if callable(value):
        return value()
    return value


class FluentSession(AdapterSession):
    def __init__(self, session: Any) -> None:
        self._session = session

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        match action:
            case "version":
                return {"version": self._session.get_fluent_version()}
            case "scheme":
                return self._run_scheme(params)
            case "tui":
                return self._run_tui(params)
            case "describe":
                return self._describe(params)
            case "get_state":
                return self._get_state(params)
            case "set_state":
                return self._set_state(params)
            case "command":
                return self._run_command(params)
            case "read_case":
                return self._run_command({"path": "file.read_case", **params})
            case "read_case_data":
                return self._run_command({"path": "file.read_case_data", **params})
            case "read_mesh":
                return self._run_command({"path": "file.read_mesh", **params})
            case "write_case":
                return self._run_command({"path": "file.write_case", **params})
            case "write_case_data":
                return self._run_command({"path": "file.write_case_data", **params})
            case "write_data":
                return self._run_command({"path": "file.write_data", **params})
            case "start_transcript":
                return self._run_command({"path": "file.start_transcript", **params})
            case "stop_transcript":
                return self._run_command({"path": "file.stop_transcript", **params})
            case "hybrid_initialize":
                return self._run_command({"path": "solution.initialization.hybrid_initialize", **params})
            case "iterate":
                return self._run_command({"path": "solution.run_calculation.iterate", **params})
            case _:
                raise AdapterError(f"Unsupported Fluent action: {action}")

    def close(self) -> None:
        with suppress_fluent_launcher_noise():
            self._session.exit(timeout=30, timeout_force=True, wait=45)

    def _resolve_path(self, path: str | None) -> Any:
        obj: Any = self._session.settings
        if path is None or not str(path).strip():
            return obj

        for token in _tokenize_path(str(path)):
            name, indexes = _parse_token(token)
            if name:
                obj = getattr(obj, name)
            for index in indexes:
                try:
                    obj = obj[index]
                except Exception:
                    if isinstance(index, str) and hasattr(obj, index):
                        obj = getattr(obj, index)
                    else:  # pragma: no cover - runtime object-specific pathing
                        raise
        return obj

    def _describe(self, params: dict[str, Any]) -> Any:
        obj = self._resolve_path(params.get("path"))
        return {
            "path": getattr(obj, "path", None),
            "python_path": getattr(obj, "python_path", None),
            "type": type(obj).__name__,
            "children": _safe_call(getattr(obj, "child_names", [])),
            "commands": _safe_call(getattr(obj, "command_names", [])),
            "queries": _safe_call(getattr(obj, "query_names", [])),
            "active_children": _safe_call(getattr(obj, "get_active_child_names", lambda: [])),
            "active_commands": _safe_call(getattr(obj, "get_active_command_names", lambda: [])),
            "active_queries": _safe_call(getattr(obj, "get_active_query_names", lambda: [])),
        }

    def _get_state(self, params: dict[str, Any]) -> Any:
        obj = self._resolve_path(params.get("path"))
        with_units = bool(params.get("with_units", False))
        getter = getattr(obj, "state_with_units" if with_units else "get_state", None)
        if not callable(getter):
            raise AdapterError(f"Object at path '{params.get('path', '')}' does not expose state.")
        return {
            "path": getattr(obj, "path", None),
            "with_units": with_units,
            "state": getter(),
        }

    def _set_state(self, params: dict[str, Any]) -> Any:
        obj = self._resolve_path(params.get("path"))
        if "state" not in params:
            raise AdapterError("Fluent set_state action requires a 'state' payload.")
        setter = getattr(obj, "set_state", None)
        if not callable(setter):
            raise AdapterError(f"Object at path '{params.get('path', '')}' does not support set_state().")
        setter(params["state"])
        return {
            "path": getattr(obj, "path", None),
            "ok": True,
        }

    def _run_command(self, params: dict[str, Any]) -> Any:
        if "path" not in params:
            raise AdapterError("Fluent command action requires a 'path'.")
        command = self._resolve_path(str(params["path"]))
        if not callable(command):
            raise AdapterError(f"Object at path '{params['path']}' is not callable.")

        args = params.get("args", [])
        if not isinstance(args, list):
            raise AdapterError("'args' must be a list when provided.")

        kwargs = {}
        nested_kwargs = params.get("kwargs", {})
        if nested_kwargs is not None:
            if not isinstance(nested_kwargs, dict):
                raise AdapterError("'kwargs' must be an object when provided.")
            kwargs.update(nested_kwargs)

        result = command(*args, **kwargs)
        return {
            "path": getattr(command, "path", params["path"]),
            "args": list(args),
            "kwargs": dict(kwargs),
            "result": result,
        }

    def _run_scheme(self, params: dict[str, Any]) -> Any:
        mode = str(params.get("mode", "eval"))
        if mode == "exec":
            commands = params.get("commands") or params.get("command")
            if isinstance(commands, str):
                commands = [commands]
            if not isinstance(commands, list) or not commands:
                raise AdapterError("Fluent scheme exec requires 'command' or 'commands'.")
            result = self._session.scheme_eval.exec(
                commands,
                wait=bool(params.get("wait", True)),
                silent=bool(params.get("silent", True)),
            )
            return {"mode": mode, "result": result}

        command = params.get("command")
        if not isinstance(command, str) or not command.strip():
            raise AdapterError("Fluent scheme action requires a non-empty 'command'.")

        if mode == "string_eval":
            result = self._session.scheme_eval.string_eval(command)
        elif mode == "eval":
            result = self._session.scheme_eval.eval(
                command,
                suppress_prompts=bool(params.get("suppress_prompts", True)),
            )
        else:
            raise AdapterError(f"Unsupported Fluent scheme mode: {mode}")

        return {"mode": mode, "result": result}

    def _run_tui(self, params: dict[str, Any]) -> Any:
        commands = params.get("commands") or params.get("command")
        if isinstance(commands, str):
            commands = [commands]
        if not isinstance(commands, list) or not commands:
            raise AdapterError("Fluent tui action requires 'command' or 'commands'.")

        scheme_commands = [
            f'(ti-menu-load-string "{_escape_scheme_string(str(command))}")'
            for command in commands
        ]
        result = self._session.scheme_eval.exec(
            scheme_commands,
            wait=bool(params.get("wait", True)),
            silent=bool(params.get("silent", True)),
        )
        return {"commands": list(commands), "result": result}
