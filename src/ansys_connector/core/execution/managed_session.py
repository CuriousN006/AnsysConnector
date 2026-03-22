from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.core.policy import normalize_allowed_roots, normalize_profile, prepare_action
from ansys_connector.core.execution.broker import append_raw_audit_record
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


def _split_runtime_session_options(options: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_keys = {"allow_raw_actions", "audit_raw_actions", "broker_state_dir"}
    runtime_options: dict[str, Any] = {}
    adapter_options: dict[str, Any] = {}
    for key, value in options.items():
        if key in runtime_keys:
            runtime_options[key] = value
        else:
            adapter_options[key] = value
    return runtime_options, adapter_options


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
        session_options: dict[str, Any] | None = None,
        session_label: str | None = None,
    ) -> None:
        self._adapter = adapter
        self._session = session
        self._env = env
        self._profile = profile
        self._allowed_roots = allowed_roots
        self._cwd = (cwd or Path.cwd()).resolve(strict=False)
        runtime_options = dict(session_options or {})
        self._raw_actions_enabled = bool(runtime_options.get("allow_raw_actions", False))
        self._audit_raw_actions = bool(runtime_options.get("audit_raw_actions", True))
        self._broker_state_dir = runtime_options.get("broker_state_dir")
        self._session_label = session_label

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
        definition = self._adapter.get_action(action)
        validated = prepare_action(
            adapter=self._adapter,
            env=self._env,
            action=action,
            params=params,
            profile=self._profile,
            raw_actions_enabled=self._raw_actions_enabled,
            allowed_roots=[str(root) for root in self._allowed_roots],
            cwd=self._cwd,
        )
        if definition.is_raw and self._audit_raw_actions:
            append_raw_audit_record(
                {
                    "session": self._session_label,
                    "adapter": self._adapter.name,
                    "action": action,
                    "profile": self._profile,
                    "workspace": str(self._cwd),
                    "params": validated,
                },
                state_dir=self._broker_state_dir,
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
    session_label: str | None = None,
) -> PolicyEnforcedSession:
    workspace_path = resolve_workspace(workspace)
    original_options = dict(options or {})
    runtime_options, adapter_options = _split_runtime_session_options(original_options)
    raw_session = adapter.open_session(env, adapter_options, workspace=workspace_path)
    return PolicyEnforcedSession(
        adapter=adapter,
        session=raw_session,
        env=env,
        profile=normalize_profile(profile),
        allowed_roots=normalize_allowed_roots(allowed_roots, cwd=workspace_path),
        cwd=workspace_path,
        session_options=runtime_options,
        session_label=session_label,
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
    session: AdapterSession | None
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

    @property
    def live_session(self) -> bool:
        return self.session is not None

    @property
    def can_execute(self) -> bool:
        return self.session is not None and self.status not in {"closing", "closed", "expired", "orphaned"}

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
            "live_session": self.live_session,
            "can_execute": self.can_execute,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "environment": {
                "version": self.env.version,
                "awp_root": str(self.env.awp_root) if self.env.awp_root else None,
            },
        }
