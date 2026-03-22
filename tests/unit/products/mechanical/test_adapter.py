from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ansys_connector.products.base import AdapterError
from ansys_connector.products.mechanical import MechanicalAdapter

from tests.support import build_env


class MechanicalAdapterTests(unittest.TestCase):
    def test_open_session_prefers_local_instance_with_dynamic_port(self) -> None:
        adapter = MechanicalAdapter()
        env = build_env()
        fake_client = object()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with mock.patch("ansys.mechanical.core.launch_mechanical", return_value=fake_client) as launch_mock:
                with mock.patch(
                    "ansys_connector.products.mechanical.adapter._find_free_local_port",
                    return_value=24567,
                ):
                    session = adapter.open_session(env, {}, workspace=workspace)

        self.assertIsNotNone(session)
        kwargs = launch_mock.call_args.kwargs
        self.assertTrue(kwargs["start_instance"])
        self.assertEqual(kwargs["port"], 24567)
        self.assertNotIn("transport_mode", kwargs)

    def test_open_session_surfaces_clear_launch_error(self) -> None:
        adapter = MechanicalAdapter()
        env = build_env()

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with mock.patch("ansys.mechanical.core.launch_mechanical", side_effect=OSError("boom")):
                with mock.patch(
                    "ansys_connector.products.mechanical.adapter._find_free_local_port",
                    side_effect=[24567, 24568],
                ):
                    with self.assertRaisesRegex(AdapterError, "Last attempt used port 24568"):
                        adapter.open_session(env, {}, workspace=workspace)


if __name__ == "__main__":
    unittest.main()
