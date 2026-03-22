from __future__ import annotations

from typing import Any

from ansys_connector.products.base import AdapterError, AdapterSession


class WorkbenchSession(AdapterSession):
    def __init__(self, client: Any) -> None:
        self._client = client

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        match action:
            case "version":
                return {"server_version": self._client.server_version}
            case "script":
                script = params.get("script")
                if not isinstance(script, str) or not script.strip():
                    raise AdapterError("Workbench script action requires a non-empty 'script'.")
                result = self._client.run_script_string(
                    script,
                    args=params.get("args"),
                    log_level=str(params.get("log_level", "error")),
                )
                return {"result": result}
            case _:
                raise AdapterError(f"Unsupported Workbench action: {action}")

    def close(self) -> None:
        close = getattr(self._client, "exit", None) or getattr(self._client, "close", None)
        if callable(close):
            close()
