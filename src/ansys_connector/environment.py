"""Compatibility shim for the relocated environment module."""

from ansys_connector.core.environment import EnvironmentInfo, detect_environment

__all__ = ["EnvironmentInfo", "detect_environment"]
