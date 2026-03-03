"""MCP server entrypoint for obs-stream-mcp."""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server

from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.tools import register_tools


def create_server() -> tuple[Server, OBSController]:
    """Create and configure the MCP server and OBS controller."""
    server = Server("obs-stream-mcp")
    controller = OBSController()
    register_tools(server, controller)
    return server, controller


async def run() -> None:
    """Run the MCP server over stdio."""
    server, _controller = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI entrypoint."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
