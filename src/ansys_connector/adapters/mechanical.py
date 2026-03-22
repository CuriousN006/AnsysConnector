"""Compatibility shim for the relocated Mechanical adapter package."""

from ansys_connector.products.mechanical import MECHANICAL_ACTIONS, MechanicalAdapter, MechanicalSession

__all__ = ["MECHANICAL_ACTIONS", "MechanicalAdapter", "MechanicalSession"]
