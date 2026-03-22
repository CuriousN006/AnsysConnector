"""Compatibility shim for the relocated MCP server module."""

from ansys_connector.interfaces.mcp.server import (
    STORE,
    adapters,
    call_once,
    close_session,
    describe_actions,
    environment,
    execute_session,
    list_sessions,
    main,
    mcp,
    open_session,
    run_plan,
)
from ansys_connector.core.execution.session_store import (
    DEFAULT_MAX_SESSIONS,
    DEFAULT_MAX_SESSIONS_PER_ADAPTER,
    DEFAULT_SESSION_TTL_SECONDS,
    SessionStore,
)
from ansys_connector.core.execution.managed_session import ManagedSession

__all__ = [
    "DEFAULT_MAX_SESSIONS",
    "DEFAULT_MAX_SESSIONS_PER_ADAPTER",
    "DEFAULT_SESSION_TTL_SECONDS",
    "ManagedSession",
    "STORE",
    "SessionStore",
    "adapters",
    "call_once",
    "close_session",
    "describe_actions",
    "environment",
    "execute_session",
    "list_sessions",
    "main",
    "mcp",
    "open_session",
    "run_plan",
]
