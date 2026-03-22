from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from ansys_connector.core.execution.session_store import SessionStore
from ansys_connector.core.registry import AdapterRegistry

from tests.support import FakeAdapter, build_env


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_adapter = FakeAdapter()
        self.registry = AdapterRegistry(adapters={"fake": self.fake_adapter})
        self._state_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._state_dir.cleanup()

    def build_store(self, **kwargs) -> SessionStore:
        kwargs.setdefault("state_dir", self._state_dir.name)
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

    def test_busy_session_is_not_expired_during_execute(self) -> None:
        store = self.build_store(ttl_seconds=1)
        opened = store.open("fake", None, {"block_on_execute": True})
        session_id = opened["session_id"]
        raw_session = self.fake_adapter.opened_sessions[0]
        execute_done: list[dict] = []

        def run_execute() -> None:
            execute_done.append(store.execute(session_id, "version"))

        worker = threading.Thread(target=run_execute)
        worker.start()
        raw_session.started.wait(timeout=5)

        store._sessions[session_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        sessions = store.list()

        self.assertEqual([session["session_id"] for session in sessions], [session_id])
        self.assertEqual(store._sessions[session_id].status, "busy")
        self.assertEqual(raw_session.closed, 0)

        raw_session.release.set()
        worker.join(timeout=5)

        self.assertEqual(execute_done[0]["session"]["status"], "open")
        self.assertIn(session_id, store._sessions)

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

    def test_store_tracks_explicit_workspace(self) -> None:
        store = self.build_store()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            opened = store.open("fake", None, workspace=str(workspace))

        resolved = str(workspace.resolve(strict=False))
        self.assertEqual(opened["workspace"], resolved)
        self.assertEqual(str(self.fake_adapter.opened_workspaces[0]), resolved)
        self.assertIn(resolved, opened["allowed_roots"])
        self.assertIn(str((workspace / "outputs").resolve(strict=False)), opened["allowed_roots"])

    def test_store_reload_marks_live_sessions_as_orphaned(self) -> None:
        store = self.build_store(max_sessions=1, max_sessions_per_adapter=1)
        opened = store.open("fake", None)

        reloaded = self.build_store(max_sessions=1, max_sessions_per_adapter=1)
        described = reloaded.describe(opened["session_id"])

        self.assertEqual(described["status"], "orphaned")
        self.assertFalse(described["live_session"])
        self.assertFalse(described["can_execute"])

        store.close_all()
        reloaded.close_all()

    def test_orphaned_sessions_do_not_consume_live_capacity(self) -> None:
        store = self.build_store(max_sessions=1, max_sessions_per_adapter=1)
        opened = store.open("fake", None)
        reloaded = self.build_store(max_sessions=1, max_sessions_per_adapter=1)

        replacement = reloaded.open("fake", None)
        sessions = {session["session_id"]: session for session in reloaded.list()}

        self.assertEqual(sessions[opened["session_id"]]["status"], "orphaned")
        self.assertEqual(sessions[replacement["session_id"]]["status"], "open")

        store.close_all()
        reloaded.close_all()

    def test_orphaned_session_cannot_execute(self) -> None:
        store = self.build_store()
        opened = store.open("fake", None)
        reloaded = self.build_store()

        with self.assertRaisesRegex(RuntimeError, "orphaned and cannot execute"):
            reloaded.execute(opened["session_id"], "version")

        store.close_all()
        reloaded.close_all()

    def test_close_all_keeps_failed_shutdown_record(self) -> None:
        store = self.build_store()
        opened = store.open("fake", None, {"fail_on_close": True})

        store.close_all()

        described = store.describe(opened["session_id"])
        self.assertEqual(described["status"], "orphaned")
        self.assertFalse(described["live_session"])
        self.assertEqual(self.fake_adapter.opened_sessions[0].closed, 1)

    def test_store_persist_merges_existing_remote_sessions(self) -> None:
        existing_session_id = "remote-session"
        state_file = Path(self._state_dir.name) / "sessions.json"
        state_file.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": existing_session_id,
                            "adapter": "fake",
                            "version": "261",
                            "profile": "safe",
                            "workspace": str(Path(self._state_dir.name) / "remote"),
                            "options": {},
                            "allowed_roots": [],
                            "status": "open",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "last_used_at": datetime.now(timezone.utc).isoformat(),
                            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                            "owner_pid": 999999,
                            "environment": {"version": "261", "awp_root": "D:/ANSYS"},
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        with mock.patch("ansys_connector.core.execution.session_store.pid_is_running", return_value=True):
            store = self.build_store()
            opened = store.open("fake", None)

        payload = json.loads(state_file.read_text(encoding="utf-8"))
        session_ids = {session["session_id"] for session in payload["sessions"]}
        self.assertEqual(session_ids, {existing_session_id, opened["session_id"]})

    def test_remote_live_sessions_still_consume_capacity(self) -> None:
        state_file = Path(self._state_dir.name) / "sessions.json"
        state_file.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": "remote-session",
                            "adapter": "fake",
                            "version": "261",
                            "profile": "safe",
                            "workspace": str(Path(self._state_dir.name) / "remote"),
                            "options": {},
                            "allowed_roots": [],
                            "status": "open",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "last_used_at": datetime.now(timezone.utc).isoformat(),
                            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                            "owner_pid": 999999,
                            "environment": {"version": "261", "awp_root": "D:/ANSYS"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with mock.patch("ansys_connector.core.execution.session_store.pid_is_running", return_value=True):
            store = self.build_store(max_sessions=1, max_sessions_per_adapter=1)
            with self.assertRaisesRegex(RuntimeError, "Session limit reached"):
                store.open("fake", None)

    def test_close_rejects_remote_live_session(self) -> None:
        state_file = Path(self._state_dir.name) / "sessions.json"
        state_file.write_text(
            json.dumps(
                {
                    "sessions": [
                        {
                            "session_id": "remote-session",
                            "adapter": "fake",
                            "version": "261",
                            "profile": "safe",
                            "workspace": str(Path(self._state_dir.name) / "remote"),
                            "options": {},
                            "allowed_roots": [],
                            "status": "open",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "last_used_at": datetime.now(timezone.utc).isoformat(),
                            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                            "owner_pid": 999999,
                            "environment": {"version": "261", "awp_root": "D:/ANSYS"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with mock.patch("ansys_connector.core.execution.session_store.pid_is_running", return_value=True):
            store = self.build_store()
            with self.assertRaisesRegex(RuntimeError, "owned by process 999999"):
                store.close("remote-session")


if __name__ == "__main__":
    unittest.main()
