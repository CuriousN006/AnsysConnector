from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ansys_connector.core.registry import AdapterRegistry
from ansys_connector.interfaces.cli.main import _parse_key_value, main

from tests.support import FakeAdapter, build_env


class CliMainTests(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> tuple[int, str]:
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = main(argv)
        return exit_code, stream.getvalue()

    def test_call_defaults_to_yaml_without_json_flag(self) -> None:
        registry = AdapterRegistry(adapters={"fake": FakeAdapter()})
        with mock.patch("ansys_connector.interfaces.cli.main.detect_environment", return_value=build_env()):
            with mock.patch("ansys_connector.interfaces.cli.main.build_registry", return_value=registry):
                exit_code, output = self._run_main(["call", "fake", "version"])

        self.assertEqual(exit_code, 0)
        self.assertIn("action: version", output)
        self.assertFalse(output.lstrip().startswith("{"))

    def test_call_json_flag_emits_json(self) -> None:
        registry = AdapterRegistry(adapters={"fake": FakeAdapter()})
        with mock.patch("ansys_connector.interfaces.cli.main.detect_environment", return_value=build_env()):
            with mock.patch("ansys_connector.interfaces.cli.main.build_registry", return_value=registry):
                exit_code, output = self._run_main(["call", "fake", "version", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(output.lstrip().startswith("{"))

    def test_parse_key_value_avoids_yaml_truthy_surprises(self) -> None:
        parsed = _parse_key_value(["mode=on", "label=yes", "count=2", "flag=true", "tags=[1, 2]"])

        self.assertEqual(parsed["mode"], "on")
        self.assertEqual(parsed["label"], "yes")
        self.assertEqual(parsed["count"], 2)
        self.assertIs(parsed["flag"], True)
        self.assertEqual(parsed["tags"], [1, 2])

    def test_list_workflows_does_not_require_env_detection(self) -> None:
        service = mock.Mock()
        service.list_workflows.return_value = [{"name": "fluent.steady_run"}]

        with mock.patch("ansys_connector.interfaces.cli.main.WorkflowService", return_value=service):
            with mock.patch("ansys_connector.interfaces.cli.main.detect_environment", side_effect=AssertionError("env")):
                with mock.patch("ansys_connector.interfaces.cli.main.build_registry", side_effect=AssertionError("registry")):
                    exit_code, output = self._run_main(["list-workflows", "fluent", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn("fluent.steady_run", output)
        service.list_workflows.assert_called_once_with("fluent")

    def test_start_workflow_wait_uses_service_and_subcommand_version(self) -> None:
        service = mock.Mock()
        service.start_workflow.return_value = {"run_id": "run-123", "status": "queued"}
        service.wait_for_run.return_value = {"run_id": "run-123", "status": "succeeded"}

        with mock.patch("ansys_connector.interfaces.cli.main.WorkflowService", return_value=service):
            with mock.patch("ansys_connector.interfaces.cli.main.detect_environment", side_effect=AssertionError("env")):
                with mock.patch("ansys_connector.interfaces.cli.main.build_registry", side_effect=AssertionError("registry")):
                    exit_code, output = self._run_main(
                        [
                            "start-workflow",
                            "fluent.steady_run",
                            "--spec",
                            "spec.yaml",
                            "--version",
                            "252",
                            "--workspace",
                            "runs/fluent-v1",
                            "--wait",
                            "--json",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "succeeded"', output)
        service.start_workflow.assert_called_once_with(
            "fluent.steady_run",
            "spec.yaml",
            version="252",
            workspace="runs/fluent-v1",
        )
        service.wait_for_run.assert_called_once_with("run-123")


if __name__ == "__main__":
    unittest.main()
