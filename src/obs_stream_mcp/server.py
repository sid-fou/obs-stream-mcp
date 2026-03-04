"""MCP server entrypoint for obs-stream-mcp."""

from __future__ import annotations

import asyncio
import threading

from mcp.server import Server
from mcp.server.stdio import stdio_server

from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.tools import register_tools

# UI automation is optional — requires pywinauto (Windows only).
try:
    from obs_stream_mcp.obs_ui_controller import OBSUIController

    _UI_AVAILABLE = True
except ImportError:
    _UI_AVAILABLE = False


def create_server() -> tuple[Server, OBSController]:
    """Create and configure the MCP server and OBS controller."""
    server = Server("obs-stream-mcp")
    controller = OBSController()

    # Shared lock prevents concurrent UI automation and WebSocket operations.
    ui_lock = threading.Lock()
    ui_controller = None

    if _UI_AVAILABLE:
        ui_controller = OBSUIController(ui_lock=ui_lock)

    register_tools(server, controller, ui_controller=ui_controller)
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
