from __future__ import annotations

from ansys_connector.products.base import ActionDefinition, ActionParameter

from .validation import (
    validate_command_params,
    validate_iterate_params,
    validate_scheme_params,
    validate_tui_params,
)


FLUENT_ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        name="version",
        profile="safe",
        description="Return the Fluent product version for the current session.",
    ),
    ActionDefinition(
        name="describe",
        profile="safe",
        description="Describe a Fluent settings path and list its child nodes and commands.",
        parameters=(
            ActionParameter("path", kind="string", description="Python-style Fluent settings path."),
        ),
    ),
    ActionDefinition(
        name="get_state",
        profile="safe",
        description="Read the state at a Fluent settings path.",
        parameters=(
            ActionParameter("path", kind="string", description="Python-style Fluent settings path."),
            ActionParameter("with_units", kind="boolean", description="Return values with units when supported."),
        ),
    ),
    ActionDefinition(
        name="set_state",
        profile="safe",
        description="Set the state at a Fluent settings path using a typed payload.",
        parameters=(
            ActionParameter("path", kind="string", description="Python-style Fluent settings path."),
            ActionParameter("state", kind="any", required=True, description="State payload passed to set_state()."),
        ),
    ),
    ActionDefinition(
        name="read_case",
        profile="safe",
        description="Read a Fluent case file from an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Case file path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="read_case_data",
        profile="safe",
        description="Read a Fluent case-data file from an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Case-data file path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="read_mesh",
        profile="safe",
        description="Read a Fluent mesh file from an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Mesh file path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="write_case",
        profile="safe",
        description="Write the current case to an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Output case path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="write_case_data",
        profile="safe",
        description="Write the current case-data to an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Output case-data path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="write_data",
        profile="safe",
        description="Write the current data file to an allowed path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Output data path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="start_transcript",
        profile="safe",
        description="Start a Fluent transcript at an allowed output path.",
        parameters=(
            ActionParameter("file_name", kind="path", required=True, is_path=True, description="Transcript output path."),
        ),
        path_fields=("file_name",),
    ),
    ActionDefinition(
        name="stop_transcript",
        profile="safe",
        description="Stop the current Fluent transcript.",
    ),
    ActionDefinition(
        name="hybrid_initialize",
        profile="safe",
        description="Run Fluent hybrid initialization.",
    ),
    ActionDefinition(
        name="iterate",
        profile="safe",
        description="Run a Fluent iteration command with validated iteration counts.",
        parameters=(
            ActionParameter("iter_count", kind="integer", description="Number of solver iterations."),
            ActionParameter("count", kind="integer", description="Alias for the number of solver iterations."),
            ActionParameter("number_of_iterations", kind="integer", description="Alternative iteration count field."),
        ),
        validator=validate_iterate_params,
    ),
    ActionDefinition(
        name="scheme",
        profile="expert",
        description="Execute raw Scheme in Fluent. This bypasses typed safeguards.",
        is_raw=True,
        parameters=(
            ActionParameter("mode", kind="string", description="One of eval, string_eval, or exec."),
            ActionParameter("command", kind="string", description="Single Scheme expression."),
            ActionParameter("commands", kind="string", repeated=True, description="Multiple Scheme expressions."),
            ActionParameter("wait", kind="boolean", description="Wait for command completion."),
            ActionParameter("silent", kind="boolean", description="Suppress transcript output."),
            ActionParameter("suppress_prompts", kind="boolean", description="Suppress prompts for eval mode."),
        ),
        validator=validate_scheme_params,
    ),
    ActionDefinition(
        name="tui",
        profile="expert",
        description="Execute raw Fluent TUI commands. This bypasses typed safeguards.",
        is_raw=True,
        parameters=(
            ActionParameter("command", kind="string", description="Single TUI command."),
            ActionParameter("commands", kind="string", repeated=True, description="Multiple TUI commands."),
            ActionParameter("wait", kind="boolean", description="Wait for command completion."),
            ActionParameter("silent", kind="boolean", description="Suppress transcript output."),
        ),
        validator=validate_tui_params,
    ),
    ActionDefinition(
        name="command",
        profile="expert",
        description="Invoke a raw Fluent callable path with explicit args/kwargs only.",
        is_raw=True,
        parameters=(
            ActionParameter("path", kind="string", required=True, description="Callable Fluent settings path."),
            ActionParameter("args", kind="array", description="Positional arguments."),
            ActionParameter("kwargs", kind="object", description="Keyword arguments."),
        ),
        validator=validate_command_params,
    ),
)
