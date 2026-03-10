"""MCP tool definitions and handlers for obs-stream-mcp."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from obs_stream_mcp.errors import ErrorCode, error_response, success_response
from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.orchestrator import SceneOrchestrator
from obs_stream_mcp.schemas import (
    ADD_SOURCE_SCHEMA,
    BUILD_GAMING_SCENE_SCHEMA,
    BUILD_STARTING_SOON_SCENE_SCHEMA,
    CONNECT_SCHEMA,
    CREATE_SCENE_SCHEMA,
    REMOVE_SCENE_SCHEMA,
    GET_SCENE_LIST_SCHEMA,
    GET_SOURCE_LIST_SCHEMA,
    GET_STATUS_SCHEMA,
    GET_STREAM_SETTINGS_SCHEMA,
    HEALTH_CHECK_SCHEMA,
    LIST_DEVICES_SCHEMA,
    REMOVE_SOURCE_SCHEMA,
    SET_SOURCE_TRANSFORM_SCHEMA,
    SET_SOURCE_VISIBILITY_SCHEMA,
    SET_STREAM_SETTINGS_SCHEMA,
    START_STREAM_SCHEMA,
    STOP_STREAM_SCHEMA,
    SWITCH_SCENE_SCHEMA,
    # Multi-RTMP UI automation schemas
    DETECT_MULTI_RTMP_SCHEMA,
    LIST_RTMP_TARGETS_SCHEMA,
    ADD_RTMP_TARGET_SCHEMA,
    MODIFY_RTMP_TARGET_SCHEMA,
    REMOVE_RTMP_TARGET_SCHEMA,
    START_RTMP_TARGET_SCHEMA,
    STOP_RTMP_TARGET_SCHEMA,
    START_ALL_RTMP_TARGETS_SCHEMA,
    STOP_ALL_RTMP_TARGETS_SCHEMA,
    # Cluster coordination schemas
    CLUSTER_STATUS_SCHEMA,
    CLUSTER_NODES_LIST_SCHEMA,
    CLUSTER_NODE_STATUS_SCHEMA,
    REMOTE_EXECUTE_SCHEMA,
    # Teleport plugin schemas
    TELEPORT_CONFIGURE_HOST_SCHEMA,
    TELEPORT_CONFIGURE_CLIENT_SCHEMA,
    TELEPORT_GET_STATUS_SCHEMA,
    SETUP_DUAL_PC_TELEPORT_SCHEMA,
)

_BASE_TOOLS: list[Tool] = [
    Tool(name="obs_connect", description="Connect to OBS WebSocket. Must be called before any other tool.", inputSchema=CONNECT_SCHEMA),
    Tool(name="obs_get_status", description="Get current OBS connection and streaming status.", inputSchema=GET_STATUS_SCHEMA),
    Tool(name="obs_health_check", description="Comprehensive OBS diagnostics: connection, streaming, recording, scene, version, latency.", inputSchema=HEALTH_CHECK_SCHEMA),
    Tool(name="obs_list_devices", description="List available video and audio devices to prevent device name guessing.", inputSchema=LIST_DEVICES_SCHEMA),
    Tool(name="obs_get_scene_list", description="List all scenes and the current active program scene.", inputSchema=GET_SCENE_LIST_SCHEMA),
    Tool(name="obs_create_scene", description="Create a new empty scene in OBS.", inputSchema=CREATE_SCENE_SCHEMA),
    Tool(name="obs_remove_scene", description="Remove a scene from OBS. Cannot remove the active program scene. Requires confirmed=true.", inputSchema=REMOVE_SCENE_SCHEMA),
    Tool(name="obs_switch_scene", description="Switch the active program scene.", inputSchema=SWITCH_SCENE_SCHEMA),
    Tool(name="obs_get_stream_settings", description="Get current stream service settings. Never exposes stream key.", inputSchema=GET_STREAM_SETTINGS_SCHEMA),
    Tool(name="obs_set_stream_settings", description="Configure stream service. Presets: youtube, twitch, kick. Or provide custom server URL. Stream key from parameter or OBS_STREAM_KEY env var.", inputSchema=SET_STREAM_SETTINGS_SCHEMA),
    Tool(name="obs_start_stream", description="Start the OBS stream output.", inputSchema=START_STREAM_SCHEMA),
    Tool(name="obs_stop_stream", description="Stop the OBS stream output. Requires confirmed=true.", inputSchema=STOP_STREAM_SCHEMA),
    Tool(name="obs_add_source", description="Add a new source (input) to a scene. Common source_type values: image_source, color_source_v3, browser_source, ffmpeg_source, text_gdiplus_v3, monitor_capture, window_capture, game_capture, dshow_input.", inputSchema=ADD_SOURCE_SCHEMA),
    Tool(name="obs_remove_source", description="Remove a source from a scene by name.", inputSchema=REMOVE_SOURCE_SCHEMA),
    Tool(name="obs_get_source_list", description="List all sources (scene items) in a scene with their properties.", inputSchema=GET_SOURCE_LIST_SCHEMA),
    Tool(name="obs_set_source_transform", description="Set transform properties (position, scale, rotation, crop, bounds) on a source in a scene. Only provided keys are updated.", inputSchema=SET_SOURCE_TRANSFORM_SCHEMA),
    Tool(name="obs_set_source_visibility", description="Show or hide a source in a scene.", inputSchema=SET_SOURCE_VISIBILITY_SCHEMA),
    Tool(name="build_gaming_scene", description="Build a complete gaming scene with Game Capture, Display Capture, Webcam, and Stream Title overlay. Supports overwrite and auto-switch.", inputSchema=BUILD_GAMING_SCENE_SCHEMA),
    Tool(name="build_starting_soon_scene", description="Build a 'Starting Soon' scene with color background, title text, optional countdown browser source, and optional image overlay. Supports overwrite and auto-switch.", inputSchema=BUILD_STARTING_SOON_SCENE_SCHEMA),
    # Multi-RTMP UI automation tools (requires obs-multi-rtmp plugin)
    Tool(name="obs_detect_multi_rtmp_plugin", description="Check if the obs-multi-rtmp plugin is installed and its dock is visible in OBS.", inputSchema=DETECT_MULTI_RTMP_SCHEMA),
    Tool(name="obs_list_rtmp_targets", description="List all configured RTMP targets from the Multiple Output dock, including active/inactive state.", inputSchema=LIST_RTMP_TARGETS_SCHEMA),
    Tool(name="obs_add_rtmp_target", description="Add a new RTMP streaming target via the plugin UI. Requires name, server URL, and stream key.", inputSchema=ADD_RTMP_TARGET_SCHEMA),
    Tool(name="obs_modify_rtmp_target", description="Modify an existing RTMP target's name, server, or stream key via the plugin UI.", inputSchema=MODIFY_RTMP_TARGET_SCHEMA),
    Tool(name="obs_remove_rtmp_target", description="Remove an RTMP target. Requires confirmed=true.", inputSchema=REMOVE_RTMP_TARGET_SCHEMA),
    Tool(name="obs_start_rtmp_target", description="Start streaming to a specific RTMP target. Main OBS stream must be running first (shared encoder).", inputSchema=START_RTMP_TARGET_SCHEMA),
    Tool(name="obs_stop_rtmp_target", description="Stop streaming to a specific RTMP target. Requires confirmed=true.", inputSchema=STOP_RTMP_TARGET_SCHEMA),
    Tool(name="obs_start_all_rtmp_targets", description="Start all configured RTMP targets simultaneously.", inputSchema=START_ALL_RTMP_TARGETS_SCHEMA),
    Tool(name="obs_stop_all_rtmp_targets", description="Stop all active RTMP targets. Requires confirmed=true.", inputSchema=STOP_ALL_RTMP_TARGETS_SCHEMA),
    # Teleport plugin tools
    Tool(name="teleport_configure_host", description="Configure the OBS Teleport output on the host (sender) machine. Opens Tools -> Teleport dialog, sets enabled state, identifier, port, and quality via UI automation.", inputSchema=TELEPORT_CONFIGURE_HOST_SCHEMA),
    Tool(name="teleport_configure_client", description="Add a Teleport source to a scene on the client (receiver) machine. Connects to the specified host identifier via the teleport-source input kind.", inputSchema=TELEPORT_CONFIGURE_CLIENT_SCHEMA),
    Tool(name="teleport_get_status", description="Check if the OBS Teleport output exists and get its settings. Uses WebSocket — no UI automation required.", inputSchema=TELEPORT_GET_STATUS_SCHEMA),
]

_CLUSTER_TOOLS: list[Tool] = [
    Tool(name="cluster_status", description="Check reachability of all cluster nodes. Shows online/offline status for each configured node.", inputSchema=CLUSTER_STATUS_SCHEMA),
    Tool(name="cluster_nodes_list", description="List all configured cluster nodes with their host and port.", inputSchema=CLUSTER_NODES_LIST_SCHEMA),
    Tool(name="cluster_node_status", description="Detailed status of a specific cluster node. Verifies: MCP reachable, OBS reachable, tool discovery.", inputSchema=CLUSTER_NODE_STATUS_SCHEMA),
    Tool(name="remote_execute", description="Execute an MCP tool on a remote cluster node. Only allows existing MCP tools — no arbitrary commands.", inputSchema=REMOTE_EXECUTE_SCHEMA),
    Tool(name="setup_dual_pc_teleport", description="Orchestrate full dual-PC Teleport setup: verify OBS on both nodes, configure host output on sender, add teleport-source on receiver, validate connection.", inputSchema=SETUP_DUAL_PC_TELEPORT_SCHEMA),
]


# ------------------------------------------------------------------
# Remote tool prefix helpers
# ------------------------------------------------------------------

_REMOTE_PREFIX_SEP = "__"
"""Separator between node name and tool name in prefixed remote tools.

Example: streaming_pc__obs_connect -> node='streaming-pc', tool='obs_connect'
"""


def _node_to_prefix(node_name: str) -> str:
    """Convert a node name like 'streaming-pc' to a safe tool prefix 'streaming_pc'."""
    return node_name.replace("-", "_").replace(".", "_")


def _build_remote_tools(cluster_manager) -> list[Tool]:
    """Generate prefixed Tool definitions for every base tool on each remote node.

    For a node named 'streaming-pc' and a base tool 'obs_get_scene_list',
    this produces a tool named 'streaming_pc__obs_get_scene_list' with the
    same schema and a description noting it runs on that remote node.
    """
    remote_tools: list[Tool] = []
    for node_name in cluster_manager._nodes:
        prefix = _node_to_prefix(node_name)
        for base_tool in _BASE_TOOLS:
            remote_tools.append(Tool(
                name=f"{prefix}{_REMOTE_PREFIX_SEP}{base_tool.name}",
                description=f"[Remote: {node_name}] {base_tool.description}",
                inputSchema=base_tool.inputSchema,
            ))
    return remote_tools


def _parse_remote_tool(name: str, cluster_manager) -> tuple[str, str] | None:
    """If *name* is a prefixed remote tool, return (node_name, original_tool).

    Returns None if *name* is not a remote-prefixed tool.
    """
    if _REMOTE_PREFIX_SEP not in name:
        return None
    prefix, _, tool_name = name.partition(_REMOTE_PREFIX_SEP)
    # Reverse-lookup: find the node whose prefix matches.
    for node_name in cluster_manager._nodes:
        if _node_to_prefix(node_name) == prefix:
            return node_name, tool_name
    return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _json_text(data: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


async def _run_sync(func, *args):
    return await asyncio.to_thread(func, *args)


def _teleport_configure_client(
    controller: OBSController,
    scene_name: str,
    source_name: str,
    identifier: str,
    ui_controller=None,
) -> dict[str, Any]:
    """Add a teleport-source to a scene on the client machine.

    Creates the scene if it doesn't exist. Uses obs_add_source internally
    with source_type='teleport-source' and teleport_list=identifier.
    After creation, opens the source properties dialog and selects the
    matching host from the Teleport dropdown via UI automation.
    """
    if not scene_name:
        return error_response(ErrorCode.INVALID_PARAMETER, "scene_name must not be empty")
    if not identifier:
        return error_response(ErrorCode.INVALID_PARAMETER, "identifier must not be empty")

    if not controller._require_connection():
        return controller._not_connected()

    # Create scene if needed (ignore DUPLICATE_SCENE error)
    create_result = controller.create_scene(scene_name)
    if not create_result["success"] and create_result.get("code") != ErrorCode.DUPLICATE_SCENE.value:
        return create_result

    # Add teleport-source
    source_created = True
    result = controller.add_source(
        scene_name=scene_name,
        source_name=source_name,
        source_type="teleport-source",
        source_settings={"teleport_list": identifier},
        enabled=True,
    )
    if not result["success"]:
        # Source might already exist — that's OK, we still need to
        # select the host in the properties dialog
        if "already exists" in result.get("error", ""):
            source_created = False
        else:
            return result

    # Select the host from the properties dropdown via UI automation.
    # WebSocket source creation does NOT auto-open the properties dialog
    # (only manual UI creation does), so we always open it explicitly.
    host_selected = False
    if ui_controller is not None:
        import time
        time.sleep(0.5)
        open_result = controller.open_input_properties_dialog(source_name)
        if open_result["success"]:
            time.sleep(1.0)
            select_result = ui_controller.teleport_select_source_host(
                source_name, identifier,
            )
            host_selected = select_result.get("success", False)

    return success_response({
        "scene_name": scene_name,
        "source_name": source_name,
        "source_type": "teleport-source",
        "identifier": identifier,
        "source_created": source_created,
        "host_selected": host_selected,
        "configured": True,
    })


async def _setup_dual_pc_teleport(
    cluster_manager,
    host_node: str,
    client_node: str,
    identifier: str,
    scene_name: str,
    quality: int,
) -> dict[str, Any]:
    """Orchestrate full dual-PC Teleport setup across cluster nodes.

    Steps:
    1. Verify OBS is reachable on both nodes
    2. Configure Teleport host on sender
    3. Configure Teleport client on receiver
    4. Validate by checking status on both nodes
    """
    if not cluster_manager:
        return error_response(ErrorCode.CLUSTER_CONFIG_ERROR, "Cluster manager not available")

    steps_completed = []
    errors = []

    # Step 1: Verify both nodes are reachable
    for node in (host_node, client_node):
        status = await cluster_manager.cluster_node_status(node)
        if not status.get("success"):
            return error_response(
                ErrorCode.NODE_UNREACHABLE,
                f"Node '{node}' is not reachable: {status.get('error', 'unknown')}",
            )
        steps_completed.append(f"verified_{node}")

    # Step 2: Configure host
    host_result = await cluster_manager.remote_execute(
        host_node,
        "teleport_configure_host",
        {"enabled": True, "identifier": identifier, "port": 0, "quality": quality},
    )
    if not host_result.get("success"):
        return error_response(
            ErrorCode.REMOTE_EXECUTION_FAILED,
            f"Failed to configure Teleport host on '{host_node}': {host_result.get('error', 'unknown')}",
        )
    steps_completed.append("host_configured")

    # Step 3: Configure client
    client_result = await cluster_manager.remote_execute(
        client_node,
        "teleport_configure_client",
        {"scene_name": scene_name, "source_name": "Teleport Feed", "identifier": identifier},
    )
    if not client_result.get("success"):
        errors.append(f"Client setup on '{client_node}': {client_result.get('error', 'unknown')}")

    if not errors:
        steps_completed.append("client_configured")

    # Step 4: Validate — check Teleport status on host
    validate_result = await cluster_manager.remote_execute(
        host_node,
        "teleport_get_status",
        {},
    )
    if validate_result.get("success") and validate_result.get("data", {}).get("teleport_available"):
        steps_completed.append("validated")

    return success_response({
        "host_node": host_node,
        "client_node": client_node,
        "identifier": identifier,
        "scene_name": scene_name,
        "quality": quality,
        "steps_completed": steps_completed,
        "errors": errors if errors else None,
        "fully_configured": len(errors) == 0,
    })


# ------------------------------------------------------------------
# Tool registration
# ------------------------------------------------------------------

def register_tools(
    server: Server,
    controller: OBSController,
    ui_controller=None,
    cluster_manager=None,
) -> None:
    orchestrator = SceneOrchestrator(controller)

    # Build tool list: base + cluster management + prefixed remote tools.
    tools: list[Tool] = list(_BASE_TOOLS)
    if cluster_manager is not None:
        tools.extend(_CLUSTER_TOOLS)
        tools.extend(_build_remote_tools(cluster_manager))

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        arguments = arguments or {}

        # ------- Check for prefixed remote tool first -------
        if cluster_manager is not None:
            remote = _parse_remote_tool(name, cluster_manager)
            if remote is not None:
                node_name, tool_name = remote
                result = await cluster_manager.remote_execute(
                    node_name, tool_name, arguments or None,
                )
                return _json_text(result)

        # ------- Local dispatch -------
        dispatch = {
            "obs_connect": lambda: _run_sync(controller.connect),
            "obs_get_status": lambda: _run_sync(controller.get_status),
            "obs_health_check": lambda: _run_sync(controller.health_check),
            "obs_list_devices": lambda: _run_sync(controller.list_devices),
            "obs_get_scene_list": lambda: _run_sync(controller.get_scene_list),
            "obs_create_scene": lambda: _run_sync(controller.create_scene, arguments.get("scene_name", "")),
            "obs_remove_scene": lambda: _run_sync(controller.remove_scene, arguments.get("scene_name", ""), arguments.get("confirmed", False)),
            "obs_switch_scene": lambda: _run_sync(controller.switch_scene, arguments.get("scene_name", "")),
            "obs_get_stream_settings": lambda: _run_sync(controller.get_stream_settings),
            "obs_set_stream_settings": lambda: _run_sync(
                controller.set_stream_settings,
                arguments.get("service"),
                arguments.get("server"),
                arguments.get("stream_key"),
            ),
            "obs_start_stream": lambda: _run_sync(controller.start_stream),
            "obs_stop_stream": lambda: _run_sync(controller.stop_stream, arguments.get("confirmed", False)),
            "obs_add_source": lambda: _run_sync(
                controller.add_source,
                arguments.get("scene_name", ""),
                arguments.get("source_name", ""),
                arguments.get("source_type", ""),
                arguments.get("source_settings"),
                arguments.get("enabled", True),
            ),
            "obs_remove_source": lambda: _run_sync(controller.remove_source, arguments.get("scene_name", ""), arguments.get("source_name", "")),
            "obs_get_source_list": lambda: _run_sync(controller.get_source_list, arguments.get("scene_name", "")),
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
            "build_gaming_scene": lambda: _run_sync(
                orchestrator.build_gaming_scene,
                arguments.get("scene_name", "Gaming"),
                arguments.get("overwrite", False),
                arguments.get("switch_to", True),
                arguments.get("force", False),
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
                arguments.get("force", False),
            ),
            # Teleport tools (WebSocket-based)
            "teleport_get_status": lambda: _run_sync(controller.teleport_get_status),
            "teleport_configure_client": lambda: _run_sync(
                _teleport_configure_client,
                controller,
                arguments.get("scene_name", ""),
                arguments.get("source_name", "Teleport Feed"),
                arguments.get("identifier", ""),
                ui_controller,
            ),
        }

        # UI automation dispatch (only if ui_controller is available)
        if ui_controller is not None:
            dispatch.update({
                "obs_detect_multi_rtmp_plugin": lambda: _run_sync(ui_controller.detect_plugin),
                "obs_list_rtmp_targets": lambda: _run_sync(ui_controller.list_rtmp_targets),
                "obs_add_rtmp_target": lambda: _run_sync(
                    ui_controller.add_rtmp_target,
                    arguments.get("name", ""),
                    arguments.get("server", ""),
                    arguments.get("stream_key", ""),
                ),
                "obs_modify_rtmp_target": lambda: _run_sync(
                    ui_controller.modify_rtmp_target,
                    arguments.get("target_name", ""),
                    arguments.get("new_name"),
                    arguments.get("server"),
                    arguments.get("stream_key"),
                ),
                "obs_remove_rtmp_target": lambda: _run_sync(
                    ui_controller.remove_rtmp_target,
                    arguments.get("target_name", ""),
                    arguments.get("confirmed", False),
                ),
                "obs_start_rtmp_target": lambda: _run_sync(
                    ui_controller.start_rtmp_target,
                    arguments.get("target_name", ""),
                ),
                "obs_stop_rtmp_target": lambda: _run_sync(
                    ui_controller.stop_rtmp_target,
                    arguments.get("target_name", ""),
                    arguments.get("confirmed", False),
                ),
                "obs_start_all_rtmp_targets": lambda: _run_sync(ui_controller.start_all_rtmp_targets),
                "obs_stop_all_rtmp_targets": lambda: _run_sync(
                    ui_controller.stop_all_rtmp_targets,
                    arguments.get("confirmed", False),
                ),
                "teleport_configure_host": lambda: _run_sync(
                    ui_controller.teleport_configure_host,
                    arguments.get("enabled", True),
                    arguments.get("identifier", "OBSTeleport"),
                    arguments.get("port", 0),
                    arguments.get("quality", 90),
                ),
            })

        # Cluster coordination dispatch (only if cluster_manager is available)
        if cluster_manager is not None:
            dispatch.update({
                "cluster_status": lambda: cluster_manager.cluster_status(),
                "cluster_nodes_list": lambda: _run_sync(cluster_manager.cluster_nodes_list),
                "cluster_node_status": lambda: cluster_manager.cluster_node_status(
                    arguments.get("node", ""),
                ),
                "remote_execute": lambda: cluster_manager.remote_execute(
                    arguments.get("node", ""),
                    arguments.get("tool", ""),
                    arguments.get("args"),
                ),
                "setup_dual_pc_teleport": lambda: _setup_dual_pc_teleport(
                    cluster_manager,
                    arguments.get("host_node", "gaming-pc"),
                    arguments.get("client_node", "streaming-pc"),
                    arguments.get("identifier", "OBSTeleport"),
                    arguments.get("scene_name", "Teleport Feed"),
                    arguments.get("quality", 90),
                ),
            })

        handler = dispatch.get(name)
        if handler is None:
            return _json_text(error_response(ErrorCode.INVALID_PARAMETER, f"Unknown tool: {name}"))

        result = await handler()
        return _json_text(result)
