"""Lightweight MCP client for connecting to remote obs-stream-mcp nodes.

Uses the official MCP Python SDK's SSE client transport to establish
proper MCP-to-MCP communication. Each operation creates a fresh
connection for reliability over persistent connection complexity.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from obs_stream_mcp.errors import (
    ErrorCode,
    error_response,
    success_response,
)


class RemoteMCPClient:
    """MCP client that connects to a remote obs-stream-mcp SSE endpoint."""

    def __init__(self, name: str, host: str, port: int, token: str = "") -> None:
        self.name = name
        self.host = host
        self.port = port
        self._token = token
        self._url = f"http://{host}:{port}/sse"

    @property
    def _headers(self) -> dict[str, str] | None:
        """Build auth headers if a token is configured."""
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return None

    async def ping(self) -> dict[str, Any]:
        """Check if the remote MCP server is reachable and responding."""
        try:
            async with sse_client(
                url=self._url,
                headers=self._headers,
                timeout=5,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    result = await session.initialize()
                    return success_response({
                        "node": self.name,
                        "reachable": True,
                        "server_name": getattr(result, "serverInfo", {}).get("name", "unknown")
                            if isinstance(getattr(result, "serverInfo", None), dict)
                            else str(getattr(getattr(result, "serverInfo", None), "name", "unknown")),
                    })
        except Exception as exc:
            return error_response(
                ErrorCode.NODE_UNREACHABLE,
                f"Cannot reach node '{self.name}' at {self._url}: {exc}",
            )

    async def list_tools(self) -> dict[str, Any]:
        """Discover all tools available on the remote node."""
        try:
            async with sse_client(
                url=self._url,
                headers=self._headers,
                timeout=10,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                        }
                        for t in result.tools
                    ]
                    return success_response({
                        "node": self.name,
                        "tools": tools,
                        "tool_count": len(tools),
                    })
        except Exception as exc:
            return error_response(
                ErrorCode.NODE_UNREACHABLE,
                f"Failed to list tools on '{self.name}': {exc}",
            )

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a tool on the remote node and return its response.

        The response is parsed from the remote MCP TextContent and returned
        as a structured dict matching the local response format.
        """
        try:
            async with sse_client(
                url=self._url,
                headers=self._headers,
                timeout=30,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    # Verify the tool exists on the remote node.
                    tools_result = await session.list_tools()
                    remote_tool_names = {t.name for t in tools_result.tools}
                    if tool_name not in remote_tool_names:
                        return error_response(
                            ErrorCode.REMOTE_TOOL_NOT_FOUND,
                            f"Tool '{tool_name}' not found on node '{self.name}'. "
                            f"Available: {sorted(remote_tool_names)}",
                        )

                    result = await session.call_tool(tool_name, arguments or {})

                    # Parse the response — our server returns JSON in TextContent.
                    for content_block in result.content:
                        if hasattr(content_block, "text"):
                            try:
                                return json.loads(content_block.text)
                            except json.JSONDecodeError:
                                return success_response({
                                    "node": self.name,
                                    "tool": tool_name,
                                    "raw_response": content_block.text,
                                })

                    return success_response({
                        "node": self.name,
                        "tool": tool_name,
                        "result": "empty_response",
                    })
        except Exception as exc:
            return error_response(
                ErrorCode.REMOTE_EXECUTION_FAILED,
                f"Remote execution of '{tool_name}' on '{self.name}' failed: {exc}",
            )
