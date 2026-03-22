"""Compatibility shim for the relocated execution module."""

from ansys_connector.core.execution.executor import ExecutionSummary, StepExecutionResult, WorkflowExecutor

__all__ = ["ExecutionSummary", "StepExecutionResult", "WorkflowExecutor"]
