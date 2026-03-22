from __future__ import annotations

from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products.base import Adapter, AdapterError, AdapterSession, AdapterStatus

from .actions import MECHANICAL_ACTIONS
from .session import MechanicalSession


class MechanicalAdapter(Adapter):
    name = "mechanical"
    actions = MECHANICAL_ACTIONS

    def inspect(self, env: EnvironmentInfo) -> AdapterStatus:
        module_state = env.module_versions.get("ansys.mechanical.core", "missing")
        available = env.mechanical_exe is not None and not module_state.startswith("error:")
        reason = None if available else "Mechanical executable or ansys.mechanical.core is unavailable."
        return AdapterStatus(
            name=self.name,
            available=available,
            actions=self.actions,
            reason=reason,
            details={
                "mechanical_exe": str(env.mechanical_exe) if env.mechanical_exe else None,
                "module_version": module_state,
                "note": (
                    "Local launch can still fail if this installation does not expose a reachable "
                    "gRPC server. Connecting to an already-running Mechanical server is also supported."
                ),
            },
        )

    def open_session(self, env: EnvironmentInfo, options: dict[str, Any], *, workspace: Path) -> AdapterSession:
        status = self.inspect(env)
        if not status.available:
            raise AdapterError(status.reason or "Mechanical is unavailable.")

        from ansys.mechanical.core import connect_to_mechanical, launch_mechanical

        connect_only = bool(options.get("connect_only") or options.get("start_instance") is False)
        if connect_only:
            client = connect_to_mechanical(
                ip=options.get("ip"),
                port=options.get("port"),
                loglevel=str(options.get("loglevel", "ERROR")),
                connect_timeout=int(options.get("connect_timeout", 120)),
                clear_on_connect=bool(options.get("clear_on_connect", False)),
                cleanup_on_exit=bool(options.get("cleanup_on_exit", False)),
                keep_connection_alive=bool(options.get("keep_connection_alive", True)),
                transport_mode=options.get("transport_mode"),
                certs_dir=options.get("certs_dir"),
            )
            return MechanicalSession(client)

        launch_options = {
            "exec_file": str(env.mechanical_exe),
            "batch": True,
            "cleanup_on_exit": True,
            "start_timeout": 180,
            "version": int(env.version) if env.version else None,
            "transport_mode": options.get("transport_mode", "insecure"),
        }
        launch_options.update(options)
        client = launch_mechanical(**launch_options)
        return MechanicalSession(client)
