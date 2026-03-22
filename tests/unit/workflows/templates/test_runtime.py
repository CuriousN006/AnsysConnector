from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.workflows.templates import WorkflowProgress, WorkflowRunRecord, WorkflowService


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._temp_dir.name) / "broker"
        self.workspace = Path(self._temp_dir.name) / "workspace"
        self.service = WorkflowService(
            state_dir=self.state_dir,
            worker_launcher=lambda run_id, state_dir: _FakeProcess(4242),
        )

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_start_workflow_persists_run_metadata_and_program(self) -> None:
        run = self.service.start_workflow(
            "fluent.steady_run",
            {
                "source": {"kind": "case", "path": "sample.cas.h5"},
                "setup": {},
                "solve": {"iterations": 20},
                "outputs": {"transcript": False, "final_case_data": False},
            },
            workspace=self.workspace,
        )

        run_dir = self.state_dir / "workflow-runs" / run["run_id"]
        self.assertEqual(run["status"], "queued")
        self.assertEqual(run["worker_pid"], 4242)
        self.assertTrue((run_dir / "run.json").exists())
        self.assertTrue((run_dir / "spec.yaml").exists())
        self.assertTrue((run_dir / "program.json").exists())
        self.assertEqual(run["recent_events"][-1]["type"], "worker_spawned")

    def test_cancel_run_marks_cancel_requested(self) -> None:
        run = self.service.start_workflow(
            "fluent.steady_run",
            {
                "source": {"kind": "case", "path": "sample.cas.h5"},
                "setup": {},
                "solve": {"iterations": 20},
                "outputs": {"transcript": False, "final_case_data": False},
            },
            workspace=self.workspace,
        )

        cancelled = self.service.cancel_run(run["run_id"])

        self.assertEqual(cancelled["status"], "cancel_requested")
        self.assertEqual(cancelled["recent_events"][-1]["type"], "cancel_requested")

    def test_mark_starting_preserves_cancel_requested_state(self) -> None:
        run = self.service.start_workflow(
            "fluent.steady_run",
            {
                "source": {"kind": "case", "path": "sample.cas.h5"},
                "setup": {},
                "solve": {"iterations": 20},
                "outputs": {"transcript": False, "final_case_data": False},
            },
            workspace=self.workspace,
        )

        self.service.cancel_run(run["run_id"])
        starting = self.service.mark_starting(run["run_id"], pid=888)

        self.assertEqual(starting.status, "cancel_requested")
        self.assertEqual(starting.phase, "starting")
        self.assertEqual(starting.progress.message, "cancel requested before launch")

    def test_run_state_machine_transitions_are_persisted(self) -> None:
        run = self.service.start_workflow(
            "fluent.steady_run",
            {
                "source": {"kind": "case", "path": "sample.cas.h5"},
                "setup": {},
                "solve": {"iterations": 20},
                "outputs": {"transcript": False, "final_case_data": False},
            },
            workspace=self.workspace,
        )

        self.service.mark_starting(run["run_id"], pid=777)
        self.service.mark_running(
            run["run_id"],
            phase="solve",
            progress=WorkflowProgress(percent=50.0, message="solve: completed 10/20 iterations", completed_iterations=10, target_iterations=20),
        )
        terminal = self.service.mark_terminal(
            run["run_id"],
            status="succeeded",
            phase="completed",
            progress=WorkflowProgress(percent=100.0, message="completed"),
            error=None,
            summary={"outputs": ["out.cas.h5"], "reports": {}, "checkpoints": [], "last_health": None},
        )

        fetched = self.service.get_run(run["run_id"])
        self.assertEqual(terminal.status, "succeeded")
        self.assertEqual(fetched["status"], "succeeded")
        self.assertEqual(fetched["phase"], "completed")
        self.assertEqual(fetched["summary"]["outputs"], ["out.cas.h5"])

    def test_wait_for_run_returns_terminal_state(self) -> None:
        run = self.service.start_workflow(
            "fluent.steady_run",
            {
                "source": {"kind": "case", "path": "sample.cas.h5"},
                "setup": {},
                "solve": {"iterations": 5},
                "outputs": {"transcript": False, "final_case_data": False},
            },
            workspace=self.workspace,
        )

        self.service.mark_terminal(
            run["run_id"],
            status="failed",
            phase="failed",
            progress=WorkflowProgress(percent=20.0, message="failed"),
            error="boom",
            summary={"outputs": [], "reports": {}, "checkpoints": [], "last_health": None},
        )

        fetched = self.service.wait_for_run(run["run_id"], poll_interval=0.01, timeout_seconds=0.2)
        self.assertEqual(fetched["status"], "failed")
        self.assertEqual(fetched["error"], "boom")


if __name__ == "__main__":
    unittest.main()
