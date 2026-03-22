"""Compatibility shim for the relocated Workbench adapter package."""

from ansys_connector.products.workbench import WORKBENCH_ACTIONS, WorkbenchAdapter, WorkbenchSession

__all__ = ["WORKBENCH_ACTIONS", "WorkbenchAdapter", "WorkbenchSession"]
