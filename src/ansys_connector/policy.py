"""Compatibility shim for relocated policy and managed-session helpers."""

from ansys_connector.core.execution.managed_session import PolicyEnforcedSession, open_managed_session
from ansys_connector.core.policy import (
    DEFAULT_PROFILE,
    normalize_allowed_roots,
    normalize_path_value,
    normalize_profile,
    prepare_action,
    validate_action_params,
)

__all__ = [
    "DEFAULT_PROFILE",
    "PolicyEnforcedSession",
    "normalize_allowed_roots",
    "normalize_path_value",
    "normalize_profile",
    "open_managed_session",
    "prepare_action",
    "validate_action_params",
]
