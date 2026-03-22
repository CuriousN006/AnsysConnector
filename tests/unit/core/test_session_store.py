from __future__ import annotations

import threading
import time
import unittest

from ansys_connector.core.execution.session_store import SessionStore
from ansys_connector.core.registry import AdapterRegistry

from tests.support import FakeAdapter, build_env


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_adapter = FakeAdapter()
        self.registry = AdapterRegistry(adapters={"fake": self.fake_adapter})

    def build_store(self, **kwargs) -> SessionStore:
        return SessionStore(
            detect_environment_fn=lambda version=None: build_env(),
            registry_factory=lambda: self.registry,
            **kwargs,
        )

    def test_store_enforces_session_limits(self) -> None:
        store = self.build_store(max_sessions=1, max_sessions_per_adapter=1)
        opened = store.open("fake", None)
        self.assertEqual(opened["profile"], "safe")

        with self.assertRaisesRegex(RuntimeError, "Session limit reached"):
            store.open("fake", None)

        store.close(opened["session_id"])

    def test_store_cleans_up_expired_sessions(self) -> None:
        store = self.build_store(ttl_seconds=1)
        opened = store.open("fake", None)

        time.sleep(1.2)
        sessions = store.list()

        self.assertEqual(sessions, [])
        self.assertEqual(self.fake_adapter.opened_sessions[0].closed, 1)
        self.assertNotIn(opened["session_id"], store._sessions)

    def test_close_waits_for_execute_and_returns_metadata(self) -> None:
        store = self.build_store()
        opened = store.open("fake", None, {"block_on_execute": True})
        session_id = opened["session_id"]
        raw_session = self.fake_adapter.opened_sessions[0]
        execute_done: list[dict] = []
        close_result: list[dict] = []

        def run_execute() -> None:
            execute_done.append(store.execute(session_id, "version"))

        worker = threading.Thread(target=run_execute)
        worker.start()
        raw_session.started.wait(timeout=5)

        closer = threading.Thread(target=lambda: close_result.append(store.close(session_id)))
        closer.start()
        time.sleep(0.2)
        self.assertTrue(closer.is_alive())

        raw_session.release.set()
        worker.join(timeout=5)
        closer.join(timeout=5)

        self.assertEqual(execute_done[0]["session"]["status"], "open")
        self.assertTrue(close_result[0]["closed"])
        self.assertEqual(close_result[0]["session"]["status"], "closed")
        self.assertEqual(raw_session.closed, 1)


if __name__ == "__main__":
    unittest.main()
