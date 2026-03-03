"""Centralized error codes and structured error response builders."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Standardized error codes for obs-stream-mcp."""

    OBS_NOT_CONNECTED = "OBS_NOT_CONNECTED"
    SCENE_NOT_FOUND = "SCENE_NOT_FOUND"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    DUPLICATE_SCENE = "DUPLICATE_SCENE"
    STREAM_ALREADY_ACTIVE = "STREAM_ALREADY_ACTIVE"
    STREAM_NOT_ACTIVE = "STREAM_NOT_ACTIVE"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    OBS_ERROR = "OBS_ERROR"


def error_response(code: ErrorCode, message: str) -> dict[str, Any]:
    """Build a structured error response."""
    return {
        "success": False,
        "error": message,
        "code": code.value,
    }


def success_response(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a structured success response."""
    return {
        "success": True,
        "data": data if data is not None else {},
    }


# Map known OBS WebSocket error substrings to our error codes.
OBS_ERROR_MAP: dict[str, ErrorCode] = {
    "No source was found": ErrorCode.SOURCE_NOT_FOUND,
    "No scene was found": ErrorCode.SCENE_NOT_FOUND,
    "already exists": ErrorCode.DUPLICATE_SCENE,
    "stream is already active": ErrorCode.STREAM_ALREADY_ACTIVE,
    "stream is not active": ErrorCode.STREAM_NOT_ACTIVE,
    "output is already active": ErrorCode.STREAM_ALREADY_ACTIVE,
    "output is not active": ErrorCode.STREAM_NOT_ACTIVE,
}


def classify_obs_error(exc: Exception) -> tuple[ErrorCode, str]:
    """Classify an OBS exception into a structured error code and message."""
    msg = str(exc).lower()
    for pattern, code in OBS_ERROR_MAP.items():
        if pattern.lower() in msg:
            return code, str(exc)
    return ErrorCode.OBS_ERROR, str(exc)
