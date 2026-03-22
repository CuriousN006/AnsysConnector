from __future__ import annotations

import unittest
from unittest import mock

import ansys_connector.interfaces.mcp.server as mcp_server


class MCPServerTests(unittest.TestCase):
    def test_get_store_is_lazy_singleton(self) -> None:
        original_store = mcp_server._STORE
        mcp_server._STORE = None
        try:
            with mock.patch("ansys_connector.interfaces.mcp.server.SessionStore") as store_cls:
                store_cls.return_value = mock.Mock()
                first = mcp_server.get_store()
                second = mcp_server.get_store()
        finally:
            mcp_server._STORE = original_store

        store_cls.assert_called_once_with()
        self.assertIs(first, second)

    def test_get_workflow_service_is_lazy_singleton(self) -> None:
        original_service = mcp_server._WORKFLOW_SERVICE
        mcp_server._WORKFLOW_SERVICE = None
        try:
            with mock.patch("ansys_connector.interfaces.mcp.server.WorkflowService") as service_cls:
                service_cls.return_value = mock.Mock()
                first = mcp_server.get_workflow_service()
                second = mcp_server.get_workflow_service()
        finally:
            mcp_server._WORKFLOW_SERVICE = original_service

        service_cls.assert_called_once_with()
        self.assertIs(first, second)

    def test_workflow_tools_delegate_to_service(self) -> None:
        service = mock.Mock()
        service.list_workflows.return_value = [{"name": "fluent.steady_run"}]
        service.describe_workflow.return_value = {"name": "fluent.steady_run"}
        service.start_workflow.return_value = {"run_id": "run-1", "status": "queued"}
        service.list_runs.return_value = [{"run_id": "run-1"}]
        service.get_run.return_value = {"run_id": "run-1", "status": "running"}
        service.cancel_run.return_value = {"run_id": "run-1", "status": "cancel_requested"}

        with mock.patch("ansys_connector.interfaces.mcp.server.get_workflow_service", return_value=service):
            self.assertEqual(mcp_server.list_workflows("fluent"), [{"name": "fluent.steady_run"}])
            self.assertEqual(mcp_server.describe_workflow("fluent.steady_run"), {"name": "fluent.steady_run"})
            self.assertEqual(
                mcp_server.start_workflow("fluent.steady_run", {"source": {}}, version="261", workspace="runs/demo"),
                {"run_id": "run-1", "status": "queued"},
            )
            self.assertEqual(mcp_server.list_workflow_runs(), [{"run_id": "run-1"}])
            self.assertEqual(mcp_server.get_workflow_run("run-1"), {"run_id": "run-1", "status": "running"})
            self.assertEqual(
                mcp_server.cancel_workflow_run("run-1"),
                {"run_id": "run-1", "status": "cancel_requested"},
            )

        service.list_workflows.assert_called_once_with("fluent")
        service.describe_workflow.assert_called_once_with("fluent.steady_run")
        service.start_workflow.assert_called_once_with(
            "fluent.steady_run",
            {"source": {}},
            version="261",
            workspace="runs/demo",
        )
        service.list_runs.assert_called_once_with()
        service.get_run.assert_called_once_with("run-1")
        service.cancel_run.assert_called_once_with("run-1")


if __name__ == "__main__":
    unittest.main()
