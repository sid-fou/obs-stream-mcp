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
    "properties": {},
    "additionalProperties": False,
}
