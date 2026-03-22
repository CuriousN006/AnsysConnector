from __future__ import annotations

import threading
from pathlib import Path

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products.base import ActionDefinition, ActionParameter, Adapter, AdapterSession, AdapterStatus


def build_env() -> EnvironmentInfo:
    return EnvironmentInfo(
        python_executable="python",
        python_version="3.12",
        version="261",
        awp_root_env="AWP_ROOT261",
        awp_root=Path("D:/ANSYS"),
        fluent_exe=Path("D:/ANSYS/fluent.exe"),
        workbench_exe=Path("D:/ANSYS/RunWB2.exe"),
        workbench_bat=Path("D:/ANSYS/runwb2.bat"),
        mechanical_exe=Path("D:/ANSYS/AnsysWBU.exe"),
        module_versions={
            "ansys.fluent.core": "ok",
            "ansys.mechanical.core": "ok",
            "ansys.workbench.core": "ok",
        },
    )


class RecordingSession(AdapterSession):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.closed = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.block_on_execute = False

    def execute(self, action: str, params: dict) -> dict:
        self.calls.append((action, dict(params)))
        self.started.set()
        if self.block_on_execute:
            self.release.wait(timeout=5)
        return {"action": action, "params": dict(params)}

    def close(self) -> None:
        self.closed += 1


class FakeAdapter(Adapter):
    name = "fake"
    actions = (
        ActionDefinition("version", "safe", "Return version."),
        ActionDefinition(
            "write_case",
            "safe",
            "Write a file within allowed roots.",
            parameters=(ActionParameter("file_name", kind="path", required=True, is_path=True),),
            path_fields=("file_name",),
        ),
        ActionDefinition(
            "danger",
            "expert",
            "Expert-only raw action.",
            is_raw=True,
            parameters=(ActionParameter("script", kind="string", required=True),),
        ),
    )

    def __init__(self) -> None:
        self.opened_sessions: list[RecordingSession] = []
        self.opened_workspaces: list[Path] = []

    def inspect(self, env: EnvironmentInfo) -> AdapterStatus:
        return AdapterStatus(name=self.name, available=True, actions=self.actions)

    def open_session(self, env: EnvironmentInfo, options: dict, *, workspace: Path) -> AdapterSession:
        session = RecordingSession()
        if options.get("block_on_execute"):
            session.block_on_execute = True
        self.opened_sessions.append(session)
        self.opened_workspaces.append(workspace)
        return session
