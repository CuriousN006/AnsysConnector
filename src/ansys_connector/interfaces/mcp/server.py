from __future__ import annotations

import atexit
import threading
from typing import Any

from mcp.server.fastmcp import FastMCP

from ansys_connector.core import AdapterRegistry, EnvironmentInfo, build_registry, detect_environment
from ansys_connector.core.execution import SessionStore, WorkflowExecutor
from ansys_connector.core.policy import normalize_profile
from ansys_connector.workflows.plans import load_plan


_STORE: SessionStore | None = None
_STORE_LOCK = threading.Lock()

mcp = FastMCP(
    "AnsysConnector",
    instructions=(
        "Use this server to inspect the local Ansys installation, discover safe and expert adapter actions, "
        "open managed product sessions, inspect session health, execute adapter actions, and run declarative plans. "
        "Safe sessions only permit typed actions. Expert sessions are required for raw script, Scheme, or TUI, "
        "and raw expert surfaces also require options.allow_raw_actions=true."
    ),
)


def _build_executor(version: str | None = None) -> tuple[EnvironmentInfo, AdapterRegistry, WorkflowExecutor]:
    env = detect_environment(version)
    registry = build_registry()
    return env, registry, WorkflowExecutor(env, registry)


def get_store() -> SessionStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = SessionStore()
                atexit.register(_STORE.close_all)
    return _STORE


@mcp.tool(description="Detect the local Python and Ansys environment.")
def environment(version: str | None = None) -> dict[str, Any]:
    env = detect_environment(version)
    return env.to_dict()


@mcp.tool(description="List available adapters and their safe/expert actions.")
def adapters(version: str | None = None) -> list[dict[str, Any]]:
    env = detect_environment(version)
    registry = build_registry()
    return [status.to_dict() for status in registry.statuses(env)]


@mcp.tool(description="Describe the safe or expert actions exposed by one adapter.")
def describe_actions(
    adapter: str,
    profile: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    env = detect_environment(version)
    registry = build_registry()
    normalized_profile = normalize_profile(profile) if profile is not None else None
    return {
        "adapter": adapter,
        "profile": normalized_profile,
        "available": registry.get(adapter).inspect(env).available,
        "actions": registry.describe_actions(adapter, normalized_profile),
    }


@mcp.tool(description="Open a persistent adapter session and return managed session metadata.")
def open_session(
    adapter: str,
    version: str | None = None,
    profile: str = "safe",
    options: dict[str, Any] | None = None,
    allowed_roots: list[str] | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    return get_store().open(adapter, version, options, profile=profile, allowed_roots=allowed_roots, workspace=workspace)


@mcp.tool(description="List open persistent adapter sessions.")
def list_sessions() -> list[dict[str, Any]]:
    return get_store().list()


@mcp.tool(description="Describe one persistent adapter session, including orphaned or non-executable state.")
def get_session(session_id: str) -> dict[str, Any]:
    return get_store().describe(session_id)


@mcp.tool(description="Execute one action on an already-open managed session.")
def execute_session(
    session_id: str,
    action: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_store().execute(session_id, action, params)


@mcp.tool(description="Close a persistent managed adapter session.")
def close_session(session_id: str) -> dict[str, Any]:
    return get_store().close(session_id)


@mcp.tool(description="Run one adapter action without keeping the session alive.")
def call_once(
    adapter: str,
    action: str,
    version: str | None = None,
    profile: str = "safe",
    options: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    allowed_roots: list[str] | None = None,
    workspace: str | None = None,
) -> dict[str, Any]:
    _, _, executor = _build_executor(version)
    return {
        "adapter": adapter,
        "action": action,
        "profile": normalize_profile(profile),
        "result": executor.call(
            adapter,
            action,
            params=params,
            adapter_options=options,
            profile=profile,
            allowed_roots=allowed_roots,
            workspace=workspace,
        ),
    }


@mcp.tool(description="Run a YAML or JSON execution plan on the local machine.")
def run_plan(
    path: str,
    version: str | None = None,
) -> dict[str, Any]:
    _, _, executor = _build_executor(version)
    summary = executor.run_plan(load_plan(path))
    return summary.to_dict()


def main() -> None:
    mcp.run("stdio")
