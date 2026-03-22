from __future__ import annotations

import unittest
from unittest import mock

import ansys_connector.interfaces.mcp.server as mcp_server


class MCPServerTests(unittest.TestCase):
    def test_get_store_is_lazy_singleton(self) -> None:
        original_store = mcp_server._STORE
        mcp_server._STORE = None
        try:
            with mock.patch("ansys_connector.interfaces.mcp.server.SessionStore") as store_cls:
                store_cls.return_value = mock.Mock()
                first = mcp_server.get_store()
                second = mcp_server.get_store()
        finally:
            mcp_server._STORE = original_store

        store_cls.assert_called_once_with()
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
