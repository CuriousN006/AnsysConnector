from __future__ import annotations

from typing import Any

from ansys_connector.products.base import AdapterError, AdapterSession


class MechanicalSession(AdapterSession):
    def __init__(self, client: Any) -> None:
        self._client = client

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        match action:
            case "version":
                return {"application_version": self._client.run_python_script("ExtAPI.ApplicationVersion")}
            case "python":
                script = params.get("script")
                if not isinstance(script, str) or not script.strip():
                    raise AdapterError("Mechanical python action requires a non-empty 'script'.")
                result = self._client.run_python_script(script)
                return {"result": result}
            case _:
                raise AdapterError(f"Unsupported Mechanical action: {action}")

    def close(self) -> None:
        exit_fn = getattr(self._client, "exit", None)
        if callable(exit_fn):
            exit_fn()
