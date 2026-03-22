from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


STATE_DIR_ENV_VAR = "ANSYS_CONNECTOR_STATE_DIR"


def _default_state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AnsysConnector" / "broker"

    return Path.home() / ".ansys_connector" / "broker"


def resolve_broker_state_dir(state_dir: str | Path | None = None, *, create: bool = True) -> Path:
    if state_dir is None:
        base = _default_state_dir()
    else:
        base = Path(state_dir).expanduser()
        if not base.is_absolute():
            base = Path.cwd() / base
    resolved = base.resolve(strict=False)
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def session_state_file(state_dir: str | Path | None = None, *, create: bool = True) -> Path:
    root = resolve_broker_state_dir(state_dir, create=create)
    return root / "sessions.json"


def adapter_lock_file(adapter_name: str, state_dir: str | Path | None = None, *, create: bool = True) -> Path:
    root = resolve_broker_state_dir(state_dir, create=create)
    lock_dir = root / "locks"
    if create:
        lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"{adapter_name}.launch.lock"


def raw_audit_log_file(state_dir: str | Path | None = None, *, create: bool = True) -> Path:
    root = resolve_broker_state_dir(state_dir, create=create)
    return root / "raw-actions.jsonl"


def append_raw_audit_record(record: dict[str, Any], state_dir: str | Path | None = None) -> Path:
    log_path = raw_audit_log_file(state_dir, create=True)
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, default=str))
        stream.write("\n")
    return log_path


@contextmanager
def exclusive_file_lock(
    path: str | Path,
    *,
    timeout_seconds: float = 180.0,
    poll_interval: float = 0.2,
) -> Iterator[Path]:
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            payload = f"pid={os.getpid()} time={time.time():.6f}\n".encode("utf-8")
            os.write(fd, payload)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for launch lock: {lock_path}")
            time.sleep(poll_interval)

    try:
        yield lock_path
    finally:
        try:
            os.close(fd)
        finally:
            lock_path.unlink(missing_ok=True)
