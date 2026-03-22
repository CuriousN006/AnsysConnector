"""Compatibility shim for relocated product base contracts."""

from ansys_connector.products.base import (
    ActionDefinition,
    ActionExecutionContext,
    AdapterMaturity,
    ActionParameter,
    ActionProfile,
    Adapter,
    AdapterError,
    AdapterSession,
    AdapterStatus,
)

__all__ = [
    "ActionDefinition",
    "ActionExecutionContext",
    "AdapterMaturity",
    "ActionParameter",
    "ActionProfile",
    "Adapter",
    "AdapterError",
    "AdapterSession",
    "AdapterStatus",
]
