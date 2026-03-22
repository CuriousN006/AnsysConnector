from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.core.execution.managed_session import PolicyEnforcedSession
from ansys_connector.products.fluent import FluentAdapter
from ansys_connector.products.mechanical import MechanicalAdapter

from tests.support import FakeAdapter, RecordingSession, build_env


class PolicyTests(unittest.TestCase):
    def test_safe_fluent_session_rejects_raw_scheme(self) -> None:
        raw = RecordingSession()
        session = PolicyEnforcedSession(
            adapter=FluentAdapter(),
            session=raw,
            env=build_env(),
            profile="safe",
            allowed_roots=(Path.cwd().resolve(strict=False),),
        )

        with self.assertRaisesRegex(Exception, "requires the expert profile"):
            session.execute("scheme", {"mode": "string_eval", "command": "(cx-version)"})

    def test_expert_fluent_session_allows_raw_scheme(self) -> None:
        raw = RecordingSession()
        with self.assertRaisesRegex(Exception, "allow_raw_actions=true"):
            PolicyEnforcedSession(
                adapter=FluentAdapter(),
                session=raw,
                env=build_env(),
                profile="expert",
                allowed_roots=(Path.cwd().resolve(strict=False),),
            ).execute("scheme", {"mode": "string_eval", "command": "(cx-version)"})

    def test_expert_fluent_session_allows_raw_scheme_with_explicit_opt_in(self) -> None:
        raw = RecordingSession()
        with tempfile.TemporaryDirectory() as state_dir:
            session = PolicyEnforcedSession(
                adapter=FluentAdapter(),
                session=raw,
                env=build_env(),
                profile="expert",
                allowed_roots=(Path.cwd().resolve(strict=False),),
                session_options={
                    "allow_raw_actions": True,
                    "broker_state_dir": state_dir,
                },
                session_label="policy-test",
            )

            result = session.execute("scheme", {"mode": "string_eval", "command": "(cx-version)"})

            self.assertEqual(result["action"], "scheme")
            self.assertEqual(raw.calls[0][1]["command"], "(cx-version)")
            audit_log = Path(state_dir) / "raw-actions.jsonl"
            self.assertTrue(audit_log.exists())
            self.assertIn("policy-test", audit_log.read_text(encoding="utf-8"))

    def test_safe_mechanical_session_rejects_python(self) -> None:
        raw = RecordingSession()
        session = PolicyEnforcedSession(
            adapter=MechanicalAdapter(),
            session=raw,
            env=build_env(),
            profile="safe",
            allowed_roots=(Path.cwd().resolve(strict=False),),
        )

        with self.assertRaisesRegex(Exception, "requires the expert profile"):
            session.execute("python", {"script": "ExtAPI.ApplicationVersion"})

    def test_safe_file_action_rejects_outside_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            workspace = Path(workspace_dir)
            outside = Path(outside_dir) / "case.cas.h5"
            raw = RecordingSession()
            session = PolicyEnforcedSession(
                adapter=FakeAdapter(),
                session=raw,
                env=build_env(),
                profile="safe",
                allowed_roots=(workspace.resolve(strict=False),),
                cwd=workspace,
            )

            with self.assertRaisesRegex(Exception, "outside the allowed roots"):
                session.execute("write_case", {"file_name": str(outside)})

    def test_iterate_requires_positive_integer(self) -> None:
        raw = RecordingSession()
        session = PolicyEnforcedSession(
            adapter=FluentAdapter(),
            session=raw,
            env=build_env(),
            profile="safe",
            allowed_roots=(Path.cwd().resolve(strict=False),),
        )

        with self.assertRaisesRegex(Exception, "positive integer"):
            session.execute("iterate", {"iter_count": 0})

    def test_fluent_command_rejects_implicit_top_level_kwargs(self) -> None:
        raw = RecordingSession()
        session = PolicyEnforcedSession(
            adapter=FluentAdapter(),
            session=raw,
            env=build_env(),
            profile="expert",
            allowed_roots=(Path.cwd().resolve(strict=False),),
            session_options={"allow_raw_actions": True},
        )

        with self.assertRaisesRegex(Exception, "Unsupported parameters"):
            session.execute("command", {"path": "file.start_transcript", "file_name": "outputs/test.trn"})


if __name__ == "__main__":
    unittest.main()
