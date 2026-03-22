from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ansys_connector.products.base import AdapterError
from ansys_connector.workflows.templates.fluent import (
    compile_fluent_reflow_melting,
    compile_fluent_steady_run,
    load_fluent_reflow_melting_spec,
    load_fluent_steady_run_spec,
)


class FluentWorkflowDefinitionTests(unittest.TestCase):
    def test_steady_spec_rejects_unknown_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with self.assertRaisesRegex(AdapterError, "unsupported fields"):
                load_fluent_steady_run_spec(
                    {
                        "source": {"kind": "case", "path": "sample.cas.h5"},
                        "setup": {},
                        "solve": {"iterations": 20},
                        "outputs": {},
                        "extra": {},
                    },
                    workspace,
                )

    def test_compile_steady_program_emits_expected_action_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output_dir = workspace / "outputs" / "workflow-runs" / "run-1"
            spec = load_fluent_steady_run_spec(
                {
                    "source": {"kind": "case", "path": "sample.cas.h5"},
                    "setup": {
                        "models": [{"path": "setup.models.energy", "state": {"enabled": True}}],
                        "boundary_conditions": [
                            {"path": 'setup.boundary_conditions.velocity_inlet["inlet"]', "state": {"vmag": 1.0}}
                        ],
                    },
                    "solve": {"iterations": 120, "iteration_chunk_size": 40},
                    "outputs": {
                        "transcript": True,
                        "reports": [
                            {
                                "name": "summary",
                                "command_path": "results.report.summary",
                            }
                        ],
                        "final_case_data": True,
                    },
                },
                workspace,
            )

            program = compile_fluent_steady_run(spec, output_dir)

        self.assertEqual(
            [operation.action for operation in program.operations],
            ["read_case", "set_state", "set_state", "initialize_solution", "run_iterations", "collect_reports", "write_case_data"],
        )
        self.assertEqual(program.operations[4].mode, "iterations")
        self.assertEqual(program.operations[4].chunk_size, 40)
        self.assertEqual(program.transcript["file_name"], str((output_dir / "transcript.log").resolve(strict=False)))

    def test_steady_spec_resolves_relative_source_and_applies_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            spec = load_fluent_steady_run_spec(
                {
                    "source": {"kind": "mesh", "path": "inputs/sample.msh.h5"},
                    "setup": {},
                    "solve": {"iterations": 25},
                    "outputs": {},
                },
                workspace,
            )

        self.assertEqual(spec["source"]["path"], str((workspace / "inputs" / "sample.msh.h5").resolve(strict=False)))
        self.assertEqual(spec["solve"]["iteration_chunk_size"], 50)
        self.assertTrue(spec["outputs"]["transcript"]["enabled"])
        self.assertFalse(spec["outputs"]["final_case"]["enabled"])
        self.assertTrue(spec["outputs"]["final_case_data"]["enabled"])

    def test_compile_reflow_program_includes_chunking_and_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output_dir = workspace / "outputs" / "workflow-runs" / "run-2"
            spec = load_fluent_reflow_melting_spec(
                {
                    "source": {"kind": "mesh", "path": "sample.msh.h5"},
                    "physics": {
                        "energy": [{"path": "setup.models.energy", "state": {"enabled": True}}],
                        "multiphase": [{"path": "setup.models.multiphase", "state": {"model": "vof"}}],
                    },
                    "zones": {
                        "boundary_conditions": [
                            {"path": 'setup.boundary_conditions.wall["pad"]', "state": {"thermal_bc": "coupled"}}
                        ]
                    },
                    "solve": {
                        "time_step_size": 0.05,
                        "step_count": 10,
                        "max_iterations_per_step": 25,
                    },
                    "outputs": {
                        "checkpoints": {"enabled": True, "every_chunks": 2},
                        "images": [
                            {
                                "name": "melt_front",
                                "kind": "picture",
                                "file_name": "melt-front.png",
                            }
                        ],
                    },
                },
                workspace,
            )

            program = compile_fluent_reflow_melting(spec, output_dir)

        self.assertEqual(
            [operation.action for operation in program.operations],
            [
                "read_mesh",
                "set_state",
                "set_state",
                "set_state",
                "initialize_solution",
                "run_time_steps",
                "export_results",
                "write_case_data",
            ],
        )
        solve_operation = program.operations[5]
        self.assertEqual(solve_operation.action, "run_time_steps")
        self.assertEqual(solve_operation.mode, "time_steps")
        self.assertEqual(solve_operation.chunk_size, 1)
        self.assertEqual(solve_operation.checkpoint_every, 2)
        self.assertIn("{completed_steps:04d}", solve_operation.checkpoint_template)
        self.assertEqual(program.operations[-2].action, "export_results")
        self.assertEqual(program.operations[-1].action, "write_case_data")

    def test_reflow_spec_rejects_non_positive_chunk_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with self.assertRaisesRegex(AdapterError, "positive integer"):
                load_fluent_reflow_melting_spec(
                    {
                        "source": {"kind": "mesh", "path": "sample.msh.h5"},
                        "physics": {},
                        "zones": {},
                        "solve": {
                            "time_step_size": 0.1,
                            "step_count": 3,
                            "max_iterations_per_step": 10,
                            "time_step_chunk_size": 0,
                        },
                        "outputs": {},
                    },
                    workspace,
                )


if __name__ == "__main__":
    unittest.main()
