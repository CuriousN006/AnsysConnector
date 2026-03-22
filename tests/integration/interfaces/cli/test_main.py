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


if __name__ == "__main__":
    unittest.main()
