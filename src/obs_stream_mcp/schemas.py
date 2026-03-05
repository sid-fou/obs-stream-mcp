"""JSON schemas for MCP tool input validation."""

from __future__ import annotations

CONNECT_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

GET_STATUS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

GET_SCENE_LIST_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CREATE_SCENE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene to create.",
            "minLength": 1,
        },
    },
    "required": ["scene_name"],
    "additionalProperties": False,
}

SWITCH_SCENE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene to switch to.",
            "minLength": 1,
        },
    },
    "required": ["scene_name"],
    "additionalProperties": False,
}

START_STREAM_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

STOP_STREAM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "confirmed": {
            "type": "boolean",
            "description": (
                "Must be true to stop the stream. "
                "Prevents accidental stream stops."
            ),
        },
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Phase 2: Source / scene item schemas
# ---------------------------------------------------------------------------

ADD_SOURCE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene to add the source to.",
            "minLength": 1,
        },
        "source_name": {
            "type": "string",
            "description": "Unique name for the new source.",
            "minLength": 1,
        },
        "source_type": {
            "type": "string",
            "description": (
                "OBS input kind. Common types: image_source, color_source_v3, "
                "browser_source, ffmpeg_source, text_gdiplus_v3, monitor_capture, "
                "window_capture, game_capture, dshow_input."
            ),
            "minLength": 1,
        },
        "source_settings": {
            "type": "object",
            "description": (
                "Optional input-specific settings as key-value pairs. "
                "Example for image_source: {\"file\": \"C:/path/to/image.png\"}. "
                "Example for browser_source: {\"url\": \"https://example.com\", \"width\": 1920, \"height\": 1080}. "
                "Example for color_source_v3: {\"color\": 4278190335, \"width\": 1920, \"height\": 1080}."
            ),
            "additionalProperties": True,
        },
        "enabled": {
            "type": "boolean",
            "description": "Whether the source is visible when added. Defaults to true.",
        },
    },
    "required": ["scene_name", "source_name", "source_type"],
    "additionalProperties": False,
}

REMOVE_SOURCE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene containing the source.",
            "minLength": 1,
        },
        "source_name": {
            "type": "string",
            "description": "Name of the source to remove.",
            "minLength": 1,
        },
    },
    "required": ["scene_name", "source_name"],
    "additionalProperties": False,
}

GET_SOURCE_LIST_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene to list sources for.",
            "minLength": 1,
        },
    },
    "required": ["scene_name"],
    "additionalProperties": False,
}

SET_SOURCE_TRANSFORM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene containing the source.",
            "minLength": 1,
        },
        "source_name": {
            "type": "string",
            "description": "Name of the source to transform.",
            "minLength": 1,
        },
        "transform": {
            "type": "object",
            "description": (
                "Transform properties to set. Supported keys: "
                "positionX (float), positionY (float), "
                "scaleX (float), scaleY (float), "
                "rotation (float, degrees), "
                "cropTop (int), cropBottom (int), cropLeft (int), cropRight (int), "
                "boundsType (string, e.g. 'OBS_BOUNDS_STRETCH'), "
                "boundsWidth (float), boundsHeight (float), "
                "boundsAlignment (int). "
                "Only provided keys are updated; others remain unchanged."
            ),
            "additionalProperties": True,
        },
    },
    "required": ["scene_name", "source_name", "transform"],
    "additionalProperties": False,
}

SET_SOURCE_VISIBILITY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name of the scene containing the source.",
            "minLength": 1,
        },
        "source_name": {
            "type": "string",
            "description": "Name of the source to show or hide.",
            "minLength": 1,
        },
        "visible": {
            "type": "boolean",
            "description": "True to show the source, false to hide it.",
        },
    },
    "required": ["scene_name", "source_name", "visible"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Phase 3: Scene orchestration schemas
# ---------------------------------------------------------------------------

BUILD_GAMING_SCENE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name for the gaming scene. Defaults to 'Gaming'.",
        },
        "overwrite": {
            "type": "boolean",
            "description": (
                "If true, clear and rebuild the scene if it already exists. "
                "If false (default), return DUPLICATE_SCENE error."
            ),
        },
        "switch_to": {
            "type": "boolean",
            "description": "If true (default), switch to the scene after building.",
        },
        "force": {
            "type": "boolean",
            "description": "If true, allow scene rebuild while streaming. Default false.",
        },
    },
    "additionalProperties": False,
}

BUILD_STARTING_SOON_SCENE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scene_name": {
            "type": "string",
            "description": "Name for the scene. Defaults to 'Starting Soon'.",
        },
        "overwrite": {
            "type": "boolean",
            "description": (
                "If true, clear and rebuild the scene if it already exists. "
                "If false (default), return DUPLICATE_SCENE error."
            ),
        },
        "switch_to": {
            "type": "boolean",
            "description": "If true (default), switch to the scene after building.",
        },
        "background_color": {
            "type": "integer",
            "description": "ABGR color integer for the background. Defaults to dark gray.",
        },
        "title_text": {
            "type": "string",
            "description": "Text to display. Defaults to 'Starting Soon...'.",
        },
        "countdown_url": {
            "type": "string",
            "description": "Optional URL for a browser source countdown widget.",
        },
        "image_path": {
            "type": "string",
            "description": "Optional file path for a background/overlay image.",
        },
        "force": {
            "type": "boolean",
            "description": "If true, allow scene rebuild while streaming. Default false.",
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Phase 4: Diagnostics and safety schemas
# ---------------------------------------------------------------------------

HEALTH_CHECK_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

LIST_DEVICES_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


GET_STREAM_SETTINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

SET_STREAM_SETTINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "service": {
            "type": "string",
            "description": (
                "Streaming service preset: 'youtube', 'twitch', 'kick'. "
                "Omit for custom RTMP server."
            ),
        },
        "server": {
            "type": "string",
            "description": (
                "Custom RTMP/RTMPS server URL. "
                "Required if service is not provided. "
                "Ignored if a service preset is used."
            ),
        },
        "stream_key": {
            "type": "string",
            "description": (
                "Stream key. If omitted, falls back to OBS_STREAM_KEY "
                "environment variable."
            ),
        },
    },
    "additionalProperties": False,
}



# ---------------------------------------------------------------------------
# Phase 4 Extended: Multi-RTMP UI automation schemas
# ---------------------------------------------------------------------------

DETECT_MULTI_RTMP_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

LIST_RTMP_TARGETS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

ADD_RTMP_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Display name for the RTMP target.",
            "minLength": 1,
        },
        "server": {
            "type": "string",
            "description": "RTMP/RTMPS server URL (e.g., rtmp://live.twitch.tv/app).",
            "minLength": 1,
        },
        "stream_key": {
            "type": "string",
            "description": "Stream key for the target. Never stored or logged.",
            "minLength": 1,
        },
    },
    "required": ["name", "server", "stream_key"],
    "additionalProperties": False,
}

MODIFY_RTMP_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "target_name": {
            "type": "string",
            "description": "Current name of the RTMP target to modify.",
            "minLength": 1,
        },
        "new_name": {
            "type": "string",
            "description": "New display name. Omit to keep current name.",
        },
        "server": {
            "type": "string",
            "description": "New RTMP/RTMPS server URL. Omit to keep current.",
        },
        "stream_key": {
            "type": "string",
            "description": "New stream key. Omit to keep current. Never stored or logged.",
        },
    },
    "required": ["target_name"],
    "additionalProperties": False,
}

REMOVE_RTMP_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "target_name": {
            "type": "string",
            "description": "Name of the RTMP target to remove.",
            "minLength": 1,
        },
        "confirmed": {
            "type": "boolean",
            "description": "Must be true to confirm deletion. Prevents accidental removal.",
        },
    },
    "required": ["target_name"],
    "additionalProperties": False,
}

START_RTMP_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "target_name": {
            "type": "string",
            "description": "Name of the RTMP target to start.",
            "minLength": 1,
        },
    },
    "required": ["target_name"],
    "additionalProperties": False,
}

STOP_RTMP_TARGET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "target_name": {
            "type": "string",
            "description": "Name of the RTMP target to stop.",
            "minLength": 1,
        },
        "confirmed": {
            "type": "boolean",
            "description": "Must be true to stop the target. Prevents accidental stops.",
        },
    },
    "required": ["target_name"],
    "additionalProperties": False,
}

START_ALL_RTMP_TARGETS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

STOP_ALL_RTMP_TARGETS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "confirmed": {
            "type": "boolean",
            "description": "Must be true to stop all targets. Prevents accidental stops.",
        },
    },
    "additionalProperties": False,
}


# ------------------------------------------------------------------
# Cluster coordination schemas
# ------------------------------------------------------------------

CLUSTER_STATUS_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CLUSTER_NODES_LIST_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CLUSTER_NODE_STATUS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "node": {
            "type": "string",
            "description": "Name of the cluster node to check.",
        },
    },
    "required": ["node"],
    "additionalProperties": False,
}

REMOTE_EXECUTE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "node": {
            "type": "string",
            "description": "Name of the remote cluster node (e.g. 'streaming-pc').",
        },
        "tool": {
            "type": "string",
            "description": "Name of the MCP tool to execute on the remote node.",
        },
        "args": {
            "type": "object",
            "description": "Arguments to pass to the remote tool.",
            "additionalProperties": True,
        },
    },
    "required": ["node", "tool"],
    "additionalProperties": False,
}
