from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from ansys_connector.products.base import AdapterError
from ansys_connector.products.mechanical import MechanicalAdapter

from tests.support import build_env


class MechanicalAdapterTests(unittest.TestCase):
    def _mock_mechanical_module(self, *, launch_side_effect=None, launch_return=None):
        fake_module = types.SimpleNamespace(
            connect_to_mechanical=mock.Mock(),
            launch_mechanical=mock.Mock(side_effect=launch_side_effect, return_value=launch_return),
        )
        return mock.patch.dict("sys.modules", {"ansys.mechanical.core": fake_module}), fake_module

    def test_open_session_prefers_local_instance_defaults(self) -> None:
        adapter = MechanicalAdapter()
        env = build_env()
        fake_client = object()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            module_patch, fake_module = self._mock_mechanical_module(launch_return=fake_client)
            with module_patch:
                session = adapter.open_session(env, {}, workspace=workspace)

        self.assertIsNotNone(session)
        kwargs = fake_module.launch_mechanical.call_args.kwargs
        self.assertTrue(kwargs["start_instance"])
        self.assertNotIn("port", kwargs)
        self.assertNotIn("transport_mode", kwargs)

    def test_open_session_surfaces_clear_launch_error(self) -> None:
        adapter = MechanicalAdapter()
        env = build_env()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            module_patch, _ = self._mock_mechanical_module(launch_side_effect=OSError("boom"))
            with module_patch:
                with self.assertRaisesRegex(AdapterError, "Automatic retries default to 1"):
                    adapter.open_session(env, {}, workspace=workspace)

    def test_open_session_cleans_up_spawned_processes_after_failed_launch(self) -> None:
        adapter = MechanicalAdapter()
        env = build_env()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            module_patch, _ = self._mock_mechanical_module(launch_side_effect=OSError("boom"))
            with module_patch:
                with mock.patch(
                    "ansys_connector.products.mechanical.adapter._list_windows_process_ids",
                    side_effect=[{101}, {101, 202}],
                ), mock.patch(
                    "ansys_connector.products.mechanical.adapter._terminate_process_ids",
                    return_value=[202],
                ) as terminate_mock:
                    with self.assertRaisesRegex(AdapterError, "Cleaned up spawned Mechanical PIDs: \\[202\\]"):
                        adapter.open_session(env, {}, workspace=workspace)

        terminate_mock.assert_called_once_with({202})


if __name__ == "__main__":
    unittest.main()
