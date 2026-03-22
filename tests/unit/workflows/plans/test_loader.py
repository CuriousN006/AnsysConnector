from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.workflows.plans import load_plan


class PlanLoaderTests(unittest.TestCase):
    def test_plan_rejects_unknown_step_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: invalid-plan",
                        "steps:",
                        "  - session: fluent",
                        "    action: version",
                        "    command: unexpected",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_plan(plan_path)

    def test_plan_supports_named_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: fluent-safe-plan",
                        "sessions:",
                        "  source:",
                        "    adapter: fluent",
                        "    profile: expert",
                        "    workspace: runs/fluent-session",
                        "    allowed_roots:",
                        "      - outputs",
                        "    options:",
                        "      processor_count: 2",
                        "steps:",
                        "  - session: source",
                        "    action: version",
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_plan(plan_path)

            self.assertEqual(plan.sessions["source"].adapter, "fluent")
            self.assertEqual(plan.sessions["source"].profile, "expert")
            self.assertEqual(plan.sessions["source"].workspace, "runs/fluent-session")
            self.assertEqual(plan.sessions["source"].options["processor_count"], 2)
            self.assertEqual(plan.sessions["source"].allowed_roots, ("outputs",))
            self.assertEqual(plan.steps[0].session, "source")

    def test_legacy_adapters_format_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: legacy-plan",
                        "adapters:",
                        "  fluent:",
                        "    profile: safe",
                        "steps:",
                        "  - adapter: fluent",
                        "    action: version",
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_plan(plan_path)

            self.assertEqual(plan.sessions["fluent"].adapter, "fluent")
            self.assertEqual(plan.steps[0].session, "fluent")

    def test_plan_rejects_duplicate_step_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: duplicate-labels",
                        "steps:",
                        "  - session: fluent",
                        "    action: version",
                        "    label: inspect",
                        "  - session: fluent",
                        "    action: version",
                        "    label: inspect",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate step labels"):
                load_plan(plan_path)

    def test_plan_rejects_implicit_session_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: hidden-options",
                        "sessions:",
                        "  source:",
                        "    adapter: fluent",
                        "    processor_count: 2",
                        "steps:",
                        "  - session: source",
                        "    action: version",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_plan(plan_path)

    def test_plan_rejects_step_labels_with_dots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: dotted-label",
                        "steps:",
                        "  - session: fluent",
                        "    action: version",
                        "    label: step.one",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "may not contain"):
                load_plan(plan_path)


if __name__ == "__main__":
    unittest.main()
