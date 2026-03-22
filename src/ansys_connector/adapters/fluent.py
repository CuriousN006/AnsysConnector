"""Compatibility shim for the relocated Fluent adapter package."""

from ansys_connector.products.fluent import FLUENT_ACTIONS, FluentAdapter, FluentSession

__all__ = ["FLUENT_ACTIONS", "FluentAdapter", "FluentSession"]
