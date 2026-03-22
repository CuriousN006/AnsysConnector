from __future__ import annotations

from ansys_connector.products.base import ActionDefinition, ActionParameter


WORKBENCH_ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        name="version",
        profile="safe",
        description="Return the Workbench server version.",
    ),
    ActionDefinition(
        name="script",
        profile="expert",
        description="Execute raw Workbench scripting text. This bypasses typed safeguards.",
        is_raw=True,
        parameters=(
            ActionParameter("script", kind="string", required=True, description="Workbench script body."),
            ActionParameter("args", kind="any", description="Optional script arguments."),
            ActionParameter("log_level", kind="string", description="Workbench log level."),
        ),
    ),
)
