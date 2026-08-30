import json
import unittest

from mcp import JsonRpcHttpTransport, McpToolSpec, PermissionedMcpClient
from runtime import PermissionPolicy


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def call(self, method, params):
        self.calls.append((method, params))
        return {"content": [{"type": "text", "text": "ok"}]}


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_permissioned_tool_call(self):
        transport = FakeTransport()
        client = PermissionedMcpClient(
            transport=transport,
            permission_policy=PermissionPolicy(frozenset({"read"})),
            tools={"search": McpToolSpec("search", "read")},
        )
        result = await client.call_tool("search", {"query": "AI"})
        self.assertEqual(result["content"][0]["text"], "ok")
        self.assertEqual(transport.calls[0][0], "tools/call")

    async def test_permission_block_and_unknown_tool(self):
        client = PermissionedMcpClient(
            transport=FakeTransport(),
            permission_policy=PermissionPolicy(frozenset({"read"})),
            tools={"publish": McpToolSpec("publish", "external-write")},
        )
        with self.assertRaises(PermissionError):
            await client.call_tool("publish", {})
        with self.assertRaises(KeyError):
            await client.call_tool("missing", {})

    async def test_json_rpc_transport(self):
        def transport(request, timeout):
            self.assertEqual(timeout, 3)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["jsonrpc"], "2.0")
            self.assertEqual(body["method"], "tools/call")
            return json.dumps(
                {"jsonrpc": "2.0", "id": body["id"], "result": {"ok": True}}
            ).encode()

        rpc = JsonRpcHttpTransport("https://mcp.example.test/rpc", 3, transport)
        result = await rpc.call("tools/call", {"name": "search"})
        self.assertTrue(result["ok"])

    async def test_json_rpc_error(self):
        def transport(_request, _timeout):
            return json.dumps(
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -1}}
            ).encode()

        rpc = JsonRpcHttpTransport("https://mcp.example.test/rpc", transport=transport)
        with self.assertRaises(RuntimeError):
            await rpc.call("tools/call", {})


if __name__ == "__main__":
    unittest.main()
