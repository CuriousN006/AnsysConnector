from __future__ import annotations

import unittest
from unittest import mock

from ansys_connector.products.fluent.session import FluentSession


class FluentSessionWrapperTests(unittest.TestCase):
    def test_file_actions_forward_params_as_kwargs(self) -> None:
        session = FluentSession(object())
        with mock.patch.object(session, "_run_command", return_value={"result": None}) as run_command:
            session.execute("read_mesh", {"file_name": "sample.msh.h5"})
            session.execute("start_transcript", {"file_name": "transcript.log"})
            session.execute("write_case_data", {"file_name": "final.cas.h5"})

        self.assertEqual(
            [call.kwargs for call in run_command.call_args_list],
            [
                {},
                {},
                {},
            ],
        )
        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            [
                {"path": "file.read_mesh", "kwargs": {"file_name": "sample.msh.h5"}},
                {"path": "file.start_transcript", "kwargs": {"file_name": "transcript.log"}},
                {"path": "file.write_case_data", "kwargs": {"file_name": "final.cas.h5"}},
            ],
        )

    def test_iterate_forwards_validated_params_as_kwargs(self) -> None:
        session = FluentSession(object())
        with mock.patch.object(session, "_run_command", return_value={"result": None}) as run_command:
            session.execute("iterate", {"iter_count": 10})

        run_command.assert_called_once_with(
            {"path": "solution.run_calculation.iterate", "kwargs": {"iter_count": 10}}
        )


if __name__ == "__main__":
    unittest.main()
