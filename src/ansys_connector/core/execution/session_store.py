from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from ansys_connector.core.environment import EnvironmentInfo, detect_environment
from ansys_connector.core.policy import normalize_allowed_roots, normalize_profile
from ansys_connector.core.registry import AdapterRegistry, build_registry

from .managed_session import ManagedSession, open_managed_session, resolve_workspace


DEFAULT_SESSION_TTL_SECONDS = 30 * 60
DEFAULT_MAX_SESSIONS = 4
DEFAULT_MAX_SESSIONS_PER_ADAPTER = 2


class SessionStore:
    def __init__(
        self,
        *,
        detect_environment_fn: Callable[[str | None], EnvironmentInfo] = detect_environment,
        registry_factory: Callable[[], AdapterRegistry] = build_registry,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_sessions_per_adapter: int = DEFAULT_MAX_SESSIONS_PER_ADAPTER,
    ) -> None:
        self._detect_environment = detect_environment_fn
        self._registry_factory = registry_factory
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_sessions_per_adapter = max_sessions_per_adapter
        self._sessions: dict[str, ManagedSession] = {}
        self._pending_opens: dict[str, int] = {}
        self._lock = threading.RLock()

    def _shutdown_managed(self, managed: ManagedSession, *, final_status: str) -> None:
        managed.status = final_status
        try:
            managed.session.close()
        finally:
            managed.status = "closed"

    def _lookup_locked(self, session_id: str) -> ManagedSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session: {session_id}") from exc

    def _cleanup_expired(self) -> None:
        expired: list[ManagedSession] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            for session_id, managed in list(self._sessions.items()):
                if managed.status == "busy":
                    continue
                if managed.expires_at <= now:
                    managed.status = "expired"
                    expired.append(self._sessions.pop(session_id))
        for managed in expired:
            with managed.lock:
                self._shutdown_managed(managed, final_status="expired")

    def _reserve_capacity(self, adapter_name: str) -> None:
        with self._lock:
            total = len(self._sessions) + sum(self._pending_opens.values())
            if total >= self._max_sessions:
                raise RuntimeError(f"Session limit reached: {self._max_sessions} open or pending sessions.")

            adapter_total = sum(1 for session in self._sessions.values() if session.adapter == adapter_name)
            adapter_total += self._pending_opens.get(adapter_name, 0)
            if adapter_total >= self._max_sessions_per_adapter:
                raise RuntimeError(
                    f"Session limit reached for adapter '{adapter_name}': {self._max_sessions_per_adapter}"
                )

            self._pending_opens[adapter_name] = self._pending_opens.get(adapter_name, 0) + 1

    def _release_capacity(self, adapter_name: str) -> None:
        with self._lock:
            pending = self._pending_opens.get(adapter_name, 0)
            if pending <= 1:
                self._pending_opens.pop(adapter_name, None)
            else:
                self._pending_opens[adapter_name] = pending - 1

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

        self._reserve_capacity(adapter_name)
        try:
            session = open_managed_session(
                adapter=adapter,
                env=env,
                options=session_options,
                profile=normalized_profile,
                allowed_roots=[str(root) for root in normalized_roots],
                workspace=workspace_path,
            )
        finally:
            self._release_capacity(adapter_name)

        managed = ManagedSession.create(
            session_id=str(uuid4()),
            adapter=adapter_name,
            version=env.version,
            profile=normalized_profile,
            workspace=workspace_path,
            options=session_options,
            allowed_roots=normalized_roots,
            env=env,
            session=session,
            ttl_seconds=self._ttl_seconds,
        )
        with self._lock:
            self._sessions[managed.session_id] = managed
            return managed.to_dict()

    def list(self) -> list[dict[str, Any]]:
        self._cleanup_expired()
        with self._lock:
            return [session.to_dict() for session in self._sessions.values()]

    def get(self, session_id: str) -> ManagedSession:
        self._cleanup_expired()
        with self._lock:
            return self._lookup_locked(session_id)

    def execute(self, session_id: str, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._cleanup_expired()
        with self._lock:
            managed = self._lookup_locked(session_id)
        with managed.lock:
            with self._lock:
                if session_id not in self._sessions:
                    raise KeyError(f"Unknown session: {session_id}")
                managed.status = "busy"
            try:
                result = managed.session.execute(action, dict(params or {}))
                with self._lock:
                    if session_id in self._sessions:
                        managed.touch(self._ttl_seconds)
                        managed.status = "open"
                    session_payload = managed.to_dict()
                return {
                    "session": session_payload,
                    "adapter": managed.adapter,
                    "action": action,
                    "result": result,
                }
            except Exception:
                with self._lock:
                    if session_id in self._sessions:
                        managed.touch(self._ttl_seconds)
                        managed.status = "open"
                raise

    def close(self, session_id: str) -> dict[str, Any]:
        self._cleanup_expired()
        with self._lock:
            managed = self._lookup_locked(session_id)
        with managed.lock:
            with self._lock:
                if session_id not in self._sessions:
                    raise KeyError(f"Unknown session: {session_id}")
                self._sessions.pop(session_id, None)
                managed.status = "closing"
            self._shutdown_managed(managed, final_status="closing")
            return {
                "closed": True,
                "session": managed.to_dict(),
            }

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for managed in sessions:
            try:
                with managed.lock:
                    self._shutdown_managed(managed, final_status="closing")
            except Exception:
                pass
