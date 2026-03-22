from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from ansys_connector.products.fluent import FluentAdapter

from tests.support import build_env


class FluentAdapterTests(unittest.TestCase):
    def test_open_session_uses_quieter_launch_defaults(self) -> None:
        adapter = FluentAdapter()
        env = build_env()
        fake_session = object()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            lock_path = workspace / "fluent.lock"
            with mock.patch("ansys.fluent.core.launch_fluent", return_value=fake_session) as launch_mock:
                with mock.patch(
                    "ansys_connector.core.execution.broker.adapter_lock_file",
                    return_value=lock_path,
                ), mock.patch(
                    "ansys_connector.core.execution.broker.exclusive_file_lock",
                    return_value=nullcontext(lock_path),
                ):
                    session = adapter.open_session(env, {}, workspace=workspace)

        self.assertIsNotNone(session)
        kwargs = launch_mock.call_args.kwargs
        self.assertTrue(kwargs["cleanup_on_exit"])
        self.assertTrue(kwargs["start_watchdog"])
        self.assertEqual(kwargs["cwd"], str(workspace))


if __name__ == "__main__":
    unittest.main()
