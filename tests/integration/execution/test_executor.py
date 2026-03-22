from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.core.execution import WorkflowExecutor
from ansys_connector.core.registry import AdapterRegistry
from ansys_connector.workflows.plans.models import ExecutionPlan, PlanSessionConfig, PlanStep

from tests.support import FakeAdapter, build_env


class WorkflowExecutorTests(unittest.TestCase):
    def test_invalid_action_is_rejected_before_open(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        with self.assertRaisesRegex(Exception, "requires the expert profile"):
            executor.call("fake", "danger", params={"script": "rm -rf /"})

        self.assertEqual(adapter.opened_sessions, [])

    def test_workspace_is_passed_to_adapter_session_open(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        with tempfile.TemporaryDirectory() as temp_dir:
            executor.call("fake", "version", workspace=temp_dir)
            self.assertEqual(adapter.opened_workspaces[0], Path(temp_dir).resolve(strict=False))

    def test_plan_can_open_multiple_sessions_for_one_adapter(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        plan = ExecutionPlan(
            name="multi-session",
            sessions={
                "source": PlanSessionConfig(adapter="fake", workspace="runs/source"),
                "target": PlanSessionConfig(adapter="fake", workspace="runs/target"),
            },
            steps=[
                PlanStep(session="source", action="version"),
                PlanStep(session="target", action="version"),
            ],
        )

        summary = executor.run_plan(plan)

        self.assertTrue(summary.ok)
        self.assertEqual(len(adapter.opened_sessions), 2)
        self.assertEqual(summary.results[0].session, "source")
        self.assertEqual(summary.results[1].session, "target")


if __name__ == "__main__":
    unittest.main()
