from __future__ import annotations

import unittest

from ansys_connector.core.execution import WorkflowExecutor
from ansys_connector.core.registry import AdapterRegistry

from tests.support import FakeAdapter, build_env


class WorkflowExecutorTests(unittest.TestCase):
    def test_invalid_action_is_rejected_before_open(self) -> None:
        adapter = FakeAdapter()
        registry = AdapterRegistry(adapters={"fake": adapter})
        executor = WorkflowExecutor(build_env(), registry)

        with self.assertRaisesRegex(Exception, "requires the expert profile"):
            executor.call("fake", "danger", params={"script": "rm -rf /"})

        self.assertEqual(adapter.opened_sessions, [])


if __name__ == "__main__":
    unittest.main()
