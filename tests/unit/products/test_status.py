from __future__ import annotations

import unittest

from ansys_connector.products.fluent import FluentAdapter
from ansys_connector.products.mechanical import MechanicalAdapter
from ansys_connector.products.workbench import WorkbenchAdapter

from tests.support import build_env


class AdapterStatusTests(unittest.TestCase):
    def test_adapter_maturity_is_exposed(self) -> None:
        env = build_env()

        self.assertEqual(FluentAdapter().inspect(env).maturity, "beta")
        self.assertEqual(WorkbenchAdapter().inspect(env).maturity, "experimental")
        self.assertEqual(MechanicalAdapter().inspect(env).maturity, "experimental")


if __name__ == "__main__":
    unittest.main()
