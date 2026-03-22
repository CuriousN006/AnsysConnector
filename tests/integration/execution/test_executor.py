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

    def test_raw_action_requires_explicit_opt_in(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        with self.assertRaisesRegex(Exception, "allow_raw_actions=true"):
            executor.call(
                "fake",
                "danger",
                params={"script": "print('boom')"},
                profile="expert",
            )

    def test_plan_can_opt_into_raw_actions(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        plan = ExecutionPlan(
            name="raw-plan",
            sessions={
                "expert_fake": PlanSessionConfig(
                    adapter="fake",
                    profile="expert",
                    options={"allow_raw_actions": True},
                )
            },
            steps=[
                PlanStep(session="expert_fake", action="danger", params={"script": "print('ok')"}),
            ],
        )

        summary = executor.run_plan(plan)

        self.assertTrue(summary.ok)
        self.assertEqual(summary.results[0].data["action"], "danger")

    def test_plan_can_reference_previous_step_data_and_session_workspace(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        with tempfile.TemporaryDirectory() as temp_dir:
            plan = ExecutionPlan(
                name="referenced-plan",
                sessions={
                    "writer": PlanSessionConfig(adapter="fake", workspace=temp_dir),
                },
                steps=[
                    PlanStep(
                        session="writer",
                        action="write_case",
                        label="write_base",
                        params={"file_name": "${sessions.writer.workspace}/outputs/base.cas.h5"},
                    ),
                    PlanStep(
                        session="writer",
                        action="write_case",
                        params={"file_name": "${steps.write_base.data.params.file_name}.bak"},
                    ),
                ],
            )

            summary = executor.run_plan(plan)

            self.assertTrue(summary.ok)
            self.assertEqual(
                summary.results[0].data["params"]["file_name"],
                str((Path(temp_dir) / "outputs" / "base.cas.h5").resolve(strict=False)),
            )
            self.assertEqual(
                summary.results[1].data["params"]["file_name"],
                str((Path(temp_dir) / "outputs" / "base.cas.h5").resolve(strict=False)) + ".bak",
            )


if __name__ == "__main__":
    unittest.main()
