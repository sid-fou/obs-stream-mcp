"""MCP tool definitions and handlers for obs-stream-mcp."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from obs_stream_mcp.errors import ErrorCode, error_response
from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.schemas import (
    CONNECT_SCHEMA,
    CREATE_SCENE_SCHEMA,
    GET_SCENE_LIST_SCHEMA,
    GET_STATUS_SCHEMA,
    START_STREAM_SCHEMA,
    STOP_STREAM_SCHEMA,
    SWITCH_SCENE_SCHEMA,
)

# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="obs_connect",
        description="Connect to OBS WebSocket. Must be called before any other tool.",
        inputSchema=CONNECT_SCHEMA,
    ),
    Tool(
        name="obs_get_status",
        description="Get current OBS connection and streaming status.",
        inputSchema=GET_STATUS_SCHEMA,
    ),
    Tool(
        name="obs_get_scene_list",
        description="List all scenes and the current active program scene.",
        inputSchema=GET_SCENE_LIST_SCHEMA,
    ),
    Tool(
        name="obs_create_scene",
        description="Create a new empty scene in OBS.",
        inputSchema=CREATE_SCENE_SCHEMA,
    ),
    Tool(
        name="obs_switch_scene",
        description="Switch the active program scene.",
        inputSchema=SWITCH_SCENE_SCHEMA,
    ),
    Tool(
        name="obs_start_stream",
        description="Start the OBS stream output.",
        inputSchema=START_STREAM_SCHEMA,
    ),
    Tool(
        name="obs_stop_stream",
        description="Stop the OBS stream output.",
        inputSchema=STOP_STREAM_SCHEMA,
    ),
]

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def _json_text(data: dict[str, Any]) -> list[TextContent]:
    """Wrap a dict as a single TextContent JSON blob."""
    return [TextContent(type="text", text=json.dumps(data))]


async def _run_sync(func, *args):
    """Run a synchronous controller method on a thread."""
    return await asyncio.to_thread(func, *args)


def register_tools(server: Server, controller: OBSController) -> None:
    """Register list_tools and call_tool handlers on the MCP server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent]:
        arguments = arguments or {}

        dispatch = {
            "obs_connect": lambda: _run_sync(controller.connect),
            "obs_get_status": lambda: _run_sync(controller.get_status),
            "obs_get_scene_list": lambda: _run_sync(controller.get_scene_list),
            "obs_create_scene": lambda: _run_sync(
                controller.create_scene, arguments.get("scene_name", "")
            ),
            "obs_switch_scene": lambda: _run_sync(
                controller.switch_scene, arguments.get("scene_name", "")
            ),
            "obs_start_stream": lambda: _run_sync(controller.start_stream),
            "obs_stop_stream": lambda: _run_sync(controller.stop_stream),
        }

        handler = dispatch.get(name)
        if handler is None:
            return _json_text(
                error_response(
                    ErrorCode.INVALID_PARAMETER,
                    f"Unknown tool: {name}",
                )
            )

        result = await handler()
        return _json_text(result)
