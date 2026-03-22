from __future__ import annotations

from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products.base import Adapter, AdapterError, AdapterSession, AdapterStatus

from .actions import WORKBENCH_ACTIONS
from .session import WorkbenchSession


class WorkbenchAdapter(Adapter):
    name = "workbench"
    actions = WORKBENCH_ACTIONS

    def inspect(self, env: EnvironmentInfo) -> AdapterStatus:
        module_state = env.module_versions.get("ansys.workbench.core", "missing")
        available = env.workbench_exe is not None and not module_state.startswith("error:")
        reason = None if available else "Workbench executable or ansys.workbench.core is unavailable."
        return AdapterStatus(
            name=self.name,
            available=available,
            actions=self.actions,
            reason=reason,
            details={
                "workbench_exe": str(env.workbench_exe) if env.workbench_exe else None,
                "module_version": module_state,
            },
        )

    def open_session(self, env: EnvironmentInfo, options: dict[str, Any], *, workspace: Path) -> AdapterSession:
        status = self.inspect(env)
        if not status.available:
            raise AdapterError(status.reason or "Workbench is unavailable.")

        from ansys.workbench.core import launch_workbench

        workdir = workspace / "outputs" / "workbench"
        workdir.mkdir(parents=True, exist_ok=True)

        launch_options = {
            "show_gui": False,
            "version": env.version,
            "client_workdir": str(workdir),
            "server_workdir": str(workdir),
        }
        launch_options.update(options)
        client = launch_workbench(**launch_options)
        return WorkbenchSession(client)
