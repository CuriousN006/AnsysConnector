from __future__ import annotations

from ansys_connector.products.base import ActionDefinition, ActionParameter


MECHANICAL_ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        name="version",
        profile="safe",
        description="Return the Mechanical application version.",
    ),
    ActionDefinition(
        name="python",
        profile="expert",
        description="Execute raw Mechanical Python. This bypasses typed safeguards.",
        parameters=(
            ActionParameter("script", kind="string", required=True, description="Mechanical Python script body."),
        ),
    ),
)
