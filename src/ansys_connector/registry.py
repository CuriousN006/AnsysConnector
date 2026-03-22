"""Compatibility shim for the relocated registry module."""

from ansys_connector.core.registry import AdapterRegistry, build_registry

__all__ = ["AdapterRegistry", "build_registry"]
