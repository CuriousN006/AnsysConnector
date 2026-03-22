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
                        "  - adapter: fluent",
                        "    action: version",
                        "    command: unexpected",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_plan(plan_path)

    def test_plan_supports_profile_and_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yaml"
            plan_path.write_text(
                "\n".join(
                    [
                        "name: fluent-safe-plan",
                        "adapters:",
                        "  fluent:",
                        "    profile: expert",
                        "    workspace: runs/fluent-session",
                        "    allowed_roots:",
                        "      - outputs",
                        "    options:",
                        "      processor_count: 2",
                        "steps:",
                        "  - adapter: fluent",
                        "    action: version",
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_plan(plan_path)

            self.assertEqual(plan.adapters["fluent"].profile, "expert")
            self.assertEqual(plan.adapters["fluent"].workspace, "runs/fluent-session")
            self.assertEqual(plan.adapters["fluent"].options["processor_count"], 2)
            self.assertEqual(plan.adapters["fluent"].allowed_roots, ("outputs",))


if __name__ == "__main__":
    unittest.main()
