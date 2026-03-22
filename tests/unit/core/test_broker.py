from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.core.execution.broker import exclusive_file_lock, session_state_file


class BrokerUtilitiesTests(unittest.TestCase):
    def test_exclusive_file_lock_times_out_until_released(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "launch.lock"
            with exclusive_file_lock(lock_path, timeout_seconds=0.2, poll_interval=0.05):
                with self.assertRaises(TimeoutError):
                    with exclusive_file_lock(lock_path, timeout_seconds=0.1, poll_interval=0.02):
                        self.fail("nested lock unexpectedly acquired")

            self.assertFalse(lock_path.exists())

            with exclusive_file_lock(lock_path, timeout_seconds=0.2, poll_interval=0.05):
                self.assertTrue(lock_path.exists())

    def test_session_state_file_uses_explicit_state_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = session_state_file(temp_dir)
            self.assertEqual(state_file.parent, Path(temp_dir).resolve(strict=False))
            self.assertEqual(state_file.name, "sessions.json")


if __name__ == "__main__":
    unittest.main()
