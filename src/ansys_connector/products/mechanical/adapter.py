from __future__ import annotations

import csv
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products.base import Adapter, AdapterError, AdapterSession, AdapterStatus

from .actions import MECHANICAL_ACTIONS
from .session import MechanicalSession


def _list_windows_process_ids(image_name: str) -> set[int]:
    if os.name != "nt":
        return set()
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {image_name}"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return set()

    pids: set[int] = set()
    reader = csv.reader(line for line in result.stdout.splitlines() if line.strip())
    for row in reader:
        if len(row) < 2 or row[0].startswith("INFO:"):
            continue
        try:
            pids.add(int(row[1]))
        except ValueError:
            continue
    return pids


def _terminate_process_ids(pids: set[int]) -> list[int]:
    terminated: list[int] = []
    if os.name != "nt":
        return terminated
    for pid in sorted(pids):
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            terminated.append(pid)
    return terminated


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
            maturity="experimental",
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
            "start_instance": True,
        }
        launch_options.update(options)
        retry_count = int(launch_options.pop("retry_count", 1))
        retry_delay = float(launch_options.pop("retry_delay", 2.0))
        explicit_port = launch_options.get("port")
        last_error: Exception | None = None
        last_port: int | None = None
        cleaned_pids: list[int] = []

        for attempt in range(1, retry_count + 1):
            attempt_options = dict(launch_options)
            if explicit_port is not None:
                last_port = int(attempt_options["port"])
            else:
                last_port = None
            before_launch = _list_windows_process_ids("AnsysWBU.exe")
            try:
                client = launch_mechanical(**attempt_options)
                return MechanicalSession(client)
            except Exception as exc:
                last_error = exc
                cleaned_pids = _terminate_process_ids(_list_windows_process_ids("AnsysWBU.exe") - before_launch)
                if attempt == retry_count:
                    break
                time.sleep(retry_delay)

        cleanup_note = f" Cleaned up spawned Mechanical PIDs: {cleaned_pids}." if cleaned_pids else ""
        port_note = f" Last attempt used port {last_port}." if last_port is not None else ""
        raise AdapterError(
            "Unable to launch Mechanical locally. "
            f"{port_note}"
            f"{cleanup_note}"
            " Automatic retries default to 1 because partially started launches can consume a demo seat. "
            "Try connect_only mode with a known running server, or override "
            "'port', 'transport_mode', or 'retry_count' in session options if this installation needs a specific setup. "
            f"Underlying error: {last_error}"
        )
