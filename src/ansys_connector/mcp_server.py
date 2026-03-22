"""Compatibility shim for the relocated MCP server module."""

from ansys_connector.interfaces.mcp.server import (
    adapters,
    call_once,
    close_session,
    describe_actions,
    environment,
    execute_session,
    get_store,
    get_session,
    list_sessions,
    main,
    mcp,
    open_session,
    run_plan,
)

__all__ = [
    "adapters",
    "call_once",
    "close_session",
    "describe_actions",
    "environment",
    "execute_session",
    "get_store",
    "get_session",
    "list_sessions",
    "main",
    "mcp",
    "open_session",
    "run_plan",
]


def __getattr__(name: str):
    if name == "STORE":
        return get_store()
    raise AttributeError(name)
