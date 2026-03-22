from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products.base import Adapter, AdapterError, AdapterSession, AdapterStatus

from .actions import FLUENT_ACTIONS
from .session import FluentSession


_FLUENT_LAUNCH_LOCK = threading.Lock()


class FluentAdapter(Adapter):
    name = "fluent"
    actions = FLUENT_ACTIONS

    def inspect(self, env: EnvironmentInfo) -> AdapterStatus:
        module_state = env.module_versions.get("ansys.fluent.core", "missing")
        available = env.fluent_exe is not None and not module_state.startswith("error:")
        reason = None if available else "Fluent executable or ansys.fluent.core is unavailable."
        return AdapterStatus(
            name=self.name,
            available=available,
            actions=self.actions,
            maturity="beta",
            reason=reason,
            details={
                "fluent_exe": str(env.fluent_exe) if env.fluent_exe else None,
                "module_version": module_state,
                "note": (
                    "Fluent is the most complete adapter today, but raw expert actions remain "
                    "advanced surfaces intended for supervised use."
                ),
            },
        )

    def open_session(self, env: EnvironmentInfo, options: dict[str, Any], *, workspace: Path) -> AdapterSession:
        status = self.inspect(env)
        if not status.available:
            raise AdapterError(status.reason or "Fluent is unavailable.")

        import ansys.fluent.core as pyfluent

        launch_options = {
            "product_version": int(env.version) if env.version else None,
            "mode": "solver",
            "dimension": 3,
            "precision": "double",
            "processor_count": 2,
            "ui_mode": "no_gui",
            "start_timeout": 180,
            "start_transcript": False,
            "cleanup_on_exit": True,
            "cwd": str(workspace),
            "fluent_path": str(env.fluent_exe),
        }
        launch_options.update(options)
        last_error: Exception | None = None
        retry_count = int(launch_options.pop("retry_count", 3))
        retry_delay = float(launch_options.pop("retry_delay", 2.0))
        with _FLUENT_LAUNCH_LOCK:
            for attempt in range(1, retry_count + 1):
                try:
                    session = pyfluent.launch_fluent(**launch_options)
                    return FluentSession(session)
                except Exception as exc:  # pragma: no cover - product startup timing
                    last_error = exc
                    if attempt == retry_count:
                        break
                    time.sleep(retry_delay)

        raise AdapterError(f"Unable to launch Fluent after {retry_count} attempts: {last_error}")
