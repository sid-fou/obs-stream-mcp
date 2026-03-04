"""MCP tool definitions and handlers for obs-stream-mcp."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from obs_stream_mcp.errors import ErrorCode, error_response
from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.orchestrator import SceneOrchestrator
from obs_stream_mcp.schemas import (
    ADD_SOURCE_SCHEMA,
    BUILD_GAMING_SCENE_SCHEMA,
    BUILD_STARTING_SOON_SCENE_SCHEMA,
    CONNECT_SCHEMA,
    CREATE_SCENE_SCHEMA,
    GET_SCENE_LIST_SCHEMA,
    GET_SOURCE_LIST_SCHEMA,
    GET_STATUS_SCHEMA,
    REMOVE_SOURCE_SCHEMA,
    SET_SOURCE_TRANSFORM_SCHEMA,
    SET_SOURCE_VISIBILITY_SCHEMA,
    START_STREAM_SCHEMA,
    STOP_STREAM_SCHEMA,
    SWITCH_SCENE_SCHEMA,
)

# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # Phase 1: Connection, scenes, streaming
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
    # Phase 2: Source / scene item management
    Tool(
        name="obs_add_source",
        description=(
            "Add a new source (input) to a scene. "
            "Common source_type values: image_source, color_source_v3, "
            "browser_source, ffmpeg_source, text_gdiplus_v3, "
            "monitor_capture, window_capture, game_capture, dshow_input."
        ),
        inputSchema=ADD_SOURCE_SCHEMA,
    ),
    Tool(
        name="obs_remove_source",
        description="Remove a source from a scene by name.",
        inputSchema=REMOVE_SOURCE_SCHEMA,
    ),
    Tool(
        name="obs_get_source_list",
        description="List all sources (scene items) in a scene with their properties.",
        inputSchema=GET_SOURCE_LIST_SCHEMA,
    ),
    Tool(
        name="obs_set_source_transform",
        description=(
            "Set transform properties (position, scale, rotation, crop, bounds) "
            "on a source in a scene. Only provided keys are updated."
        ),
        inputSchema=SET_SOURCE_TRANSFORM_SCHEMA,
    ),
    Tool(
        name="obs_set_source_visibility",
        description="Show or hide a source in a scene.",
        inputSchema=SET_SOURCE_VISIBILITY_SCHEMA,
    ),
    # Phase 3: Scene orchestration
    Tool(
        name="build_gaming_scene",
        description=(
            "Build a complete gaming scene with Game Capture, Display Capture, "
            "Webcam, and Stream Title overlay. Supports overwrite and auto-switch."
        ),
        inputSchema=BUILD_GAMING_SCENE_SCHEMA,
    ),
    Tool(
        name="build_starting_soon_scene",
        description=(
            "Build a 'Starting Soon' scene with color background, title text, "
            "optional countdown browser source, and optional image overlay. "
            "Supports overwrite and auto-switch."
        ),
        inputSchema=BUILD_STARTING_SOON_SCENE_SCHEMA,
    ),
]

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def _json_text(data: dict[str, Any]) -> list[TextContent]:
    """Wrap a dict as a single TextContent JSON blob."""
    return [TextContent(type="text", text=json.dumps(data, default=str))]


async def _run_sync(func, *args):
    """Run a synchronous controller method on a thread."""
    return await asyncio.to_thread(func, *args)


def register_tools(server: Server, controller: OBSController) -> None:
    """Register list_tools and call_tool handlers on the MCP server."""
    orchestrator = SceneOrchestrator(controller)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[TextContent]:
        arguments = arguments or {}

        dispatch = {
            # Phase 1
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
            # Phase 2
            "obs_add_source": lambda: _run_sync(
                controller.add_source,
                arguments.get("scene_name", ""),
                arguments.get("source_name", ""),
                arguments.get("source_type", ""),
                arguments.get("source_settings"),
                arguments.get("enabled", True),
            ),
            "obs_remove_source": lambda: _run_sync(
                controller.remove_source,
                arguments.get("scene_name", ""),
                arguments.get("source_name", ""),
            ),
            "obs_get_source_list": lambda: _run_sync(
                controller.get_source_list,
                arguments.get("scene_name", ""),
            ),
            "obs_set_source_transform": lambda: _run_sync(
                controller.set_source_transform,
                arguments.get("scene_name", ""),
                arguments.get("source_name", ""),
                arguments.get("transform", {}),
            ),
            "obs_set_source_visibility": lambda: _run_sync(
                controller.set_source_visibility,
                arguments.get("scene_name", ""),
                arguments.get("source_name", ""),
                arguments.get("visible", True),
            ),
            # Phase 3
            "build_gaming_scene": lambda: _run_sync(
                orchestrator.build_gaming_scene,
                arguments.get("scene_name", "Gaming"),
                arguments.get("overwrite", False),
                arguments.get("switch_to", True),
            ),
            "build_starting_soon_scene": lambda: _run_sync(
                orchestrator.build_starting_soon_scene,
                arguments.get("scene_name", "Starting Soon"),
                arguments.get("overwrite", False),
                arguments.get("switch_to", True),
                arguments.get("background_color", 4281348144),
                arguments.get("title_text", "Starting Soon..."),
                arguments.get("countdown_url"),
                arguments.get("image_path"),
            ),
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
