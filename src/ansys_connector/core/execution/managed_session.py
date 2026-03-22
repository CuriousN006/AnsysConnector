from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.core.policy import normalize_allowed_roots, normalize_profile, prepare_action
from ansys_connector.products.base import ActionProfile, Adapter, AdapterSession


def resolve_workspace(workspace: str | Path | None = None, *, create: bool = True) -> Path:
    if workspace is None:
        base = Path.cwd()
    else:
        base = Path(workspace).expanduser()
        if not base.is_absolute():
            base = Path.cwd() / base
    resolved = base.resolve(strict=False)
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "outputs").mkdir(parents=True, exist_ok=True)
    return resolved


class PolicyEnforcedSession(AdapterSession):
    """Apply profile and filesystem policy to adapter actions."""

    def __init__(
        self,
        *,
        adapter: Adapter,
        session: AdapterSession,
        env: EnvironmentInfo,
        profile: ActionProfile,
        allowed_roots: tuple[Path, ...],
        cwd: Path | None = None,
    ) -> None:
        self._adapter = adapter
        self._session = session
        self._env = env
        self._profile = profile
        self._allowed_roots = allowed_roots
        self._cwd = (cwd or Path.cwd()).resolve(strict=False)

    @property
    def profile(self) -> ActionProfile:
        return self._profile

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return self._allowed_roots

    @property
    def workspace(self) -> Path:
        return self._cwd

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        validated = prepare_action(
            adapter=self._adapter,
            env=self._env,
            action=action,
            params=params,
            profile=self._profile,
            allowed_roots=[str(root) for root in self._allowed_roots],
            cwd=self._cwd,
        )
        return self._session.execute(action, validated)

    def close(self) -> None:
        self._session.close()


def open_managed_session(
    *,
    adapter: Adapter,
    env: EnvironmentInfo,
    options: dict[str, Any] | None = None,
    profile: str | None = None,
    allowed_roots: list[str] | tuple[str, ...] | str | Path | None = None,
    workspace: str | Path | None = None,
) -> PolicyEnforcedSession:
    workspace_path = resolve_workspace(workspace)
    session_options = dict(options or {})
    raw_session = adapter.open_session(env, session_options, workspace=workspace_path)
    return PolicyEnforcedSession(
        adapter=adapter,
        session=raw_session,
        env=env,
        profile=normalize_profile(profile),
        allowed_roots=normalize_allowed_roots(allowed_roots, cwd=workspace_path),
        cwd=workspace_path,
    )


@dataclass
class ManagedSession:
    session_id: str
    adapter: str
    version: str | None
    profile: str
    workspace: Path
    options: dict[str, Any]
    allowed_roots: tuple[Path, ...]
    env: EnvironmentInfo
    session: AdapterSession
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    status: str = "open"
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        adapter: str,
        version: str | None,
        profile: str,
        workspace: Path,
        options: dict[str, Any],
        allowed_roots: tuple[Path, ...],
        env: EnvironmentInfo,
        session: AdapterSession,
        ttl_seconds: int,
    ) -> "ManagedSession":
        now = datetime.now(timezone.utc)
        return cls(
            session_id=session_id,
            adapter=adapter,
            version=version,
            profile=profile,
            workspace=workspace,
            options=options,
            allowed_roots=allowed_roots,
            env=env,
            session=session,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    def touch(self, ttl_seconds: int) -> None:
        now = datetime.now(timezone.utc)
        self.last_used_at = now
        self.expires_at = now + timedelta(seconds=ttl_seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "adapter": self.adapter,
            "version": self.version,
            "profile": self.profile,
            "workspace": str(self.workspace),
            "options": dict(self.options),
            "allowed_roots": [str(root) for root in self.allowed_roots],
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "environment": {
                "version": self.env.version,
                "awp_root": str(self.env.awp_root) if self.env.awp_root else None,
            },
        }
