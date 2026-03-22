from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from ansys_connector.core.environment import EnvironmentInfo, detect_environment
from ansys_connector.core.policy import normalize_allowed_roots, normalize_profile
from ansys_connector.core.registry import AdapterRegistry, build_registry

from .broker import broker_state_lock_file, exclusive_file_lock, pid_is_running, resolve_broker_state_dir, session_state_file
from .managed_session import ManagedSession, open_managed_session, resolve_workspace


DEFAULT_SESSION_TTL_SECONDS = 30 * 60
DEFAULT_MAX_SESSIONS = 4
DEFAULT_MAX_SESSIONS_PER_ADAPTER = 2
_TERMINAL_SESSION_STATUSES = {"closed", "expired", "orphaned"}


def _parse_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return fallback


class SessionStore:
    def __init__(
        self,
        *,
        detect_environment_fn: Callable[[str | None], EnvironmentInfo] = detect_environment,
        registry_factory: Callable[[], AdapterRegistry] = build_registry,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_sessions_per_adapter: int = DEFAULT_MAX_SESSIONS_PER_ADAPTER,
        state_dir: str | Path | None = None,
    ) -> None:
        self._detect_environment = detect_environment_fn
        self._registry_factory = registry_factory
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_sessions_per_adapter = max_sessions_per_adapter
        self._state_dir = resolve_broker_state_dir(state_dir)
        self._state_file = session_state_file(self._state_dir)
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = threading.RLock()
        self._load_state()

    def _state_lock(self) -> Iterator[Path]:
        return exclusive_file_lock(
            broker_state_lock_file(self._state_dir),
            timeout_seconds=30.0,
            poll_interval=0.1,
        )

    def _persist_state_locked(self) -> None:
        payload = {
            "sessions": [session.to_dict() for session in self._sessions.values()],
        }
        temp_file = self._state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_file.replace(self._state_file)

    def _deserialize_session(self, item: Any) -> tuple[str, ManagedSession] | None:
        if not isinstance(item, dict):
            return None
        session_id = item.get("session_id")
        adapter = item.get("adapter")
        profile = item.get("profile", "safe")
        workspace = item.get("workspace")
        if not isinstance(session_id, str) or not isinstance(adapter, str):
            return None
        if not isinstance(workspace, str):
            return None

        raw_status = str(item.get("status", "open"))
        if raw_status == "closed":
            return None

        created_at = _parse_datetime(item.get("created_at"), datetime.now(timezone.utc))
        last_used_at = _parse_datetime(item.get("last_used_at"), created_at)
        expires_at = _parse_datetime(item.get("expires_at"), last_used_at)
        env_payload = item.get("environment", {})
        version = item.get("version")
        awp_root_value = env_payload.get("awp_root") if isinstance(env_payload, dict) else None
        env = self._detect_environment(version)
        if awp_root_value:
            env = EnvironmentInfo(
                python_executable=env.python_executable,
                python_version=env.python_version,
                version=env.version,
                awp_root_env=env.awp_root_env,
                awp_root=Path(awp_root_value),
                fluent_exe=env.fluent_exe,
                workbench_exe=env.workbench_exe,
                workbench_bat=env.workbench_bat,
                mechanical_exe=env.mechanical_exe,
                module_versions=env.module_versions,
            )

        owner_pid_value = item.get("owner_pid")
        owner_pid = owner_pid_value if isinstance(owner_pid_value, int) else None
        if owner_pid in (None, os.getpid()):
            status = "orphaned"
        elif pid_is_running(owner_pid):
            status = raw_status
        else:
            status = "orphaned"

        managed = ManagedSession(
            session_id=session_id,
            adapter=adapter,
            version=version,
            profile=str(profile),
            workspace=Path(workspace),
            options=dict(item.get("options", {})) if isinstance(item.get("options", {}), dict) else {},
            allowed_roots=tuple(Path(root) for root in item.get("allowed_roots", []) if isinstance(root, str)),
            env=env,
            session=None,
            created_at=created_at,
            last_used_at=last_used_at,
            expires_at=expires_at,
            owner_pid=owner_pid,
            status=status,
        )
        return session_id, managed

    def _read_persisted_sessions_locked(self) -> dict[str, ManagedSession]:
        if not self._state_file.exists():
            return {}
        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            return {}

        loaded: dict[str, ManagedSession] = {}
        for item in sessions:
            parsed = self._deserialize_session(item)
            if parsed is None:
                continue
            session_id, managed = parsed
            loaded[session_id] = managed
        return loaded

    def _sync_from_disk_locked(self) -> None:
        disk_sessions = self._read_persisted_sessions_locked()
        local_owned = {
            session_id: managed
            for session_id, managed in self._sessions.items()
            if managed.owner_pid == os.getpid()
        }
        disk_sessions.update(local_owned)
        self._sessions = disk_sessions

    def _load_state(self) -> None:
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()

    def _shutdown_managed(self, managed: ManagedSession, *, final_status: str) -> None:
        managed.status = final_status
        try:
            if managed.session is not None:
                managed.session.close()
        finally:
            managed.session = None
            managed.status = "closed"

    def _lookup_locked(self, session_id: str) -> ManagedSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session: {session_id}") from exc

    def _counts_toward_capacity(self, managed: ManagedSession) -> bool:
        return managed.status not in _TERMINAL_SESSION_STATUSES

    def _is_remote_owned_live(self, managed: ManagedSession) -> bool:
        return (
            managed.session is None
            and managed.owner_pid not in (None, os.getpid())
            and managed.status not in {"closed", "expired", "orphaned"}
            and pid_is_running(managed.owner_pid)
        )

    def _reserve_capacity_locked(self, adapter_name: str) -> None:
        total = sum(1 for session in self._sessions.values() if self._counts_toward_capacity(session))
        if total >= self._max_sessions:
            raise RuntimeError(f"Session limit reached: {self._max_sessions} open or pending sessions.")

        adapter_total = sum(
            1
            for session in self._sessions.values()
            if session.adapter == adapter_name and self._counts_toward_capacity(session)
        )
        if adapter_total >= self._max_sessions_per_adapter:
            raise RuntimeError(
                f"Session limit reached for adapter '{adapter_name}': {self._max_sessions_per_adapter}"
            )

    def _mark_close_failure(self, session_id: str, managed: ManagedSession) -> None:
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                current = self._sessions.get(session_id)
                if current is managed:
                    managed.touch(self._ttl_seconds)
                    managed.status = "degraded" if managed.session is not None else "orphaned"
                    self._persist_state_locked()

    def _remove_metadata(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._persist_state_locked()

    def _purge_orphaned_record(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                managed = self._lookup_locked(session_id)
                if self._is_remote_owned_live(managed):
                    raise RuntimeError(
                        f"Session '{session_id}' is owned by process {managed.owner_pid} and cannot be closed "
                        "from this process without adapter-specific reattach support."
                    )
                managed.status = "closed"
                self._remove_metadata(session_id)
                return {
                    "closed": True,
                    "session": managed.to_dict(),
                }

    def _expire_metadata(self, session_id: str) -> None:
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                managed = self._sessions.get(session_id)
                if managed is None:
                    return
                if self._is_remote_owned_live(managed) or managed.status == "busy":
                    return
                if managed.expires_at > datetime.now(timezone.utc):
                    return
                if managed.session is None:
                    managed.status = "expired"
                    self._remove_metadata(session_id)
                    return
                managed.status = "expired"
                self._persist_state_locked()

        with managed.lock:
            try:
                self._shutdown_managed(managed, final_status="expired")
            except Exception:
                self._mark_close_failure(session_id, managed)
                return

        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                current = self._sessions.get(session_id)
                if current is managed:
                    self._remove_metadata(session_id)

    def _cleanup_expired(self) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                expired_ids = [
                    session_id
                    for session_id, managed in self._sessions.items()
                    if managed.status != "busy"
                    and managed.expires_at <= now
                    and not self._is_remote_owned_live(managed)
                ]
        for session_id in expired_ids:
            self._expire_metadata(session_id)

    def open(
        self,
        adapter_name: str,
        version: str | None,
        options: dict[str, Any] | None = None,
        *,
        profile: str | None = "safe",
        allowed_roots: list[str] | tuple[str, ...] | str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        self._cleanup_expired()
        env = self._detect_environment(version)
        registry = self._registry_factory()
        adapter = registry.get(adapter_name)
        normalized_profile = normalize_profile(profile)
        workspace_path = resolve_workspace(workspace)
        normalized_roots = normalize_allowed_roots(allowed_roots, cwd=workspace_path)
        session_options = dict(options or {})
        session_id = str(uuid4())
        pending = ManagedSession.create_pending(
            session_id=session_id,
            adapter=adapter_name,
            version=env.version,
            profile=normalized_profile,
            workspace=workspace_path,
            options=session_options,
            allowed_roots=normalized_roots,
            env=env,
            ttl_seconds=self._ttl_seconds,
        )

        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                self._reserve_capacity_locked(adapter_name)
                self._sessions[session_id] = pending
                self._persist_state_locked()

        try:
            session = open_managed_session(
                adapter=adapter,
                env=env,
                options=session_options,
                profile=normalized_profile,
                allowed_roots=[str(root) for root in normalized_roots],
                workspace=workspace_path,
                session_label=session_id,
            )
        except Exception:
            with self._lock:
                with self._state_lock():
                    self._sync_from_disk_locked()
                    current = self._sessions.get(session_id)
                    if current is pending:
                        self._remove_metadata(session_id)
            raise

        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                pending.session = session
                pending.touch(self._ttl_seconds)
                pending.status = "open"
                self._sessions[session_id] = pending
                self._persist_state_locked()
                return pending.to_dict()

    def list(self) -> list[dict[str, Any]]:
        self._cleanup_expired()
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                return [session.to_dict() for session in self._sessions.values()]

    def get(self, session_id: str) -> ManagedSession:
        self._cleanup_expired()
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                return self._lookup_locked(session_id)

    def describe(self, session_id: str) -> dict[str, Any]:
        self._cleanup_expired()
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                return self._lookup_locked(session_id).to_dict()

    def execute(self, session_id: str, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._cleanup_expired()
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                managed = self._lookup_locked(session_id)

        with managed.lock:
            with self._lock:
                with self._state_lock():
                    self._sync_from_disk_locked()
                    managed = self._lookup_locked(session_id)
                    if not managed.can_execute:
                        raise RuntimeError(
                            f"Session '{session_id}' is {managed.status} and cannot execute. "
                            "Re-open the session or reattach support must be implemented for this adapter."
                        )
                    managed.status = "busy"
                    self._persist_state_locked()
            try:
                result = managed.session.execute(action, dict(params or {}))
            except Exception:
                with self._lock:
                    with self._state_lock():
                        self._sync_from_disk_locked()
                        current = self._sessions.get(session_id)
                        if current is managed:
                            managed.touch(self._ttl_seconds)
                            managed.status = "open"
                            self._persist_state_locked()
                raise

            with self._lock:
                with self._state_lock():
                    self._sync_from_disk_locked()
                    current = self._sessions.get(session_id)
                    if current is managed:
                        managed.touch(self._ttl_seconds)
                        managed.status = "open"
                        self._persist_state_locked()
                    session_payload = managed.to_dict()
            return {
                "session": session_payload,
                "adapter": managed.adapter,
                "action": action,
                "result": result,
            }

    def close(self, session_id: str) -> dict[str, Any]:
        self._cleanup_expired()
        purge_only = False
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                managed = self._lookup_locked(session_id)
                if managed.session is None:
                    purge_only = True

        if purge_only:
            return self._purge_orphaned_record(session_id)

        with managed.lock:
            purge_after_wait = False
            with self._lock:
                with self._state_lock():
                    self._sync_from_disk_locked()
                    managed = self._lookup_locked(session_id)
                    if managed.session is None:
                        purge_after_wait = True
                    else:
                        managed.status = "closing"
                        self._persist_state_locked()
            if purge_after_wait:
                return self._purge_orphaned_record(session_id)
            try:
                self._shutdown_managed(managed, final_status="closing")
            except Exception:
                self._mark_close_failure(session_id, managed)
                raise

            with self._lock:
                with self._state_lock():
                    self._sync_from_disk_locked()
                    current = self._sessions.get(session_id)
                    if current is managed:
                        self._remove_metadata(session_id)
            return {
                "closed": True,
                "session": managed.to_dict(),
            }

    def close_all(self) -> None:
        with self._lock:
            with self._state_lock():
                self._sync_from_disk_locked()
                session_ids = list(self._sessions)

        for session_id in session_ids:
            try:
                self.close(session_id)
            except Exception:
                pass
