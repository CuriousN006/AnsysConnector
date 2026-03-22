"""Compatibility shim for the relocated MCP server module."""

from ansys_connector.interfaces.mcp.server import (
    adapters,
    cancel_workflow_run,
    call_once,
    close_session,
    describe_actions,
    describe_workflow,
    environment,
    execute_session,
    get_store,
    get_session,
    get_workflow_run,
    get_workflow_service,
    list_workflow_runs,
    list_workflows,
    list_sessions,
    main,
    mcp,
    open_session,
    start_workflow,
    run_plan,
)

__all__ = [
    "adapters",
    "cancel_workflow_run",
    "call_once",
    "close_session",
    "describe_actions",
    "describe_workflow",
    "environment",
    "execute_session",
    "get_store",
    "get_session",
    "get_workflow_run",
    "get_workflow_service",
    "list_workflow_runs",
    "list_workflows",
    "list_sessions",
    "main",
    "mcp",
    "open_session",
    "start_workflow",
    "run_plan",
]


def __getattr__(name: str):
    if name == "STORE":
        return get_store()
    raise AttributeError(name)
