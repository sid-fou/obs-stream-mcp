"""OBS WebSocket v5 controller. Handles raw OBS calls via obsws-python."""

from __future__ import annotations

import os
from typing import Any

import obsws_python as obs

from obs_stream_mcp.errors import (
    ErrorCode,
    classify_obs_error,
    error_response,
    success_response,
)


class OBSController:
    """Manages a single OBS WebSocket connection and exposes control methods.

    All public methods return structured JSON dicts.
    No exceptions propagate to callers.
    """

    def __init__(self) -> None:
        self._client: obs.ReqClient | None = None

    @property
    def connected(self) -> bool:
        """Return True if a live client connection exists."""
        return self._client is not None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """Establish connection to OBS WebSocket.

        Host defaults to localhost:4455.
        Password is read from the OBS_PASSWORD environment variable.
        """
        password = os.environ.get("OBS_PASSWORD", "")
        host = os.environ.get("OBS_HOST", "localhost")
        port = int(os.environ.get("OBS_PORT", "4455"))

        try:
            self._client = obs.ReqClient(
                host=host,
                port=port,
                password=password,
                timeout=10,
            )
            version = self._client.get_version()
            return success_response(
                {
                    "message": "Connected to OBS",
                    "obs_version": version.obs_version,
                    "ws_version": version.obs_web_socket_version,
                    "platform": version.platform_description,
                }
            )
        except Exception as exc:
            self._client = None
            return error_response(
                ErrorCode.CONNECTION_FAILED,
                f"Failed to connect to OBS: {exc}",
            )

    def disconnect(self) -> dict[str, Any]:
        """Disconnect from OBS WebSocket."""
        if self._client is not None:
            try:
                self._client.base_client.ws.close()
            except Exception:
                pass
            self._client = None
        return success_response({"message": "Disconnected from OBS"})

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current OBS connection and streaming status."""
        if not self._require_connection():
            return self._not_connected()

        try:
            stream = self._client.get_stream_status()  # type: ignore[union-attr]
            return success_response(
                {
                    "streaming": stream.output_active,
                    "stream_timecode": stream.output_timecode,
                    "stream_bytes": stream.output_bytes,
                    "reconnecting": stream.output_reconnecting,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    # ------------------------------------------------------------------
    # Scene management
    # ------------------------------------------------------------------

    def get_scene_list(self) -> dict[str, Any]:
        """Return the list of scenes and the current active scene."""
        if not self._require_connection():
            return self._not_connected()

        try:
            resp = self._client.get_scene_list()  # type: ignore[union-attr]
            scenes = [s["sceneName"] for s in resp.scenes]
            return success_response(
                {
                    "current_program_scene": resp.current_program_scene_name,
                    "scenes": scenes,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def create_scene(self, scene_name: str) -> dict[str, Any]:
        """Create a new scene in OBS.

        Returns DUPLICATE_SCENE if a scene with that name already exists.
        """
        if not self._require_connection():
            return self._not_connected()

        if not scene_name or not scene_name.strip():
            return error_response(
                ErrorCode.INVALID_PARAMETER, "scene_name must not be empty"
            )

        # Check for duplicates explicitly before creating.
        try:
            resp = self._client.get_scene_list()  # type: ignore[union-attr]
            existing = {s["sceneName"] for s in resp.scenes}
            if scene_name in existing:
                return error_response(
                    ErrorCode.DUPLICATE_SCENE,
                    f"Scene '{scene_name}' already exists",
                )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

        try:
            self._client.create_scene(scene_name)  # type: ignore[union-attr]
            return success_response({"scene_name": scene_name})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def switch_scene(self, scene_name: str) -> dict[str, Any]:
        """Switch the active program scene.

        Returns SCENE_NOT_FOUND if the scene does not exist.
        """
        if not self._require_connection():
            return self._not_connected()

        if not scene_name or not scene_name.strip():
            return error_response(
                ErrorCode.INVALID_PARAMETER, "scene_name must not be empty"
            )

        # Validate scene exists before switching.
        try:
            resp = self._client.get_scene_list()  # type: ignore[union-attr]
            existing = {s["sceneName"] for s in resp.scenes}
            if scene_name not in existing:
                return error_response(
                    ErrorCode.SCENE_NOT_FOUND,
                    f"Scene '{scene_name}' not found",
                )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

        try:
            self._client.set_current_program_scene(scene_name)  # type: ignore[union-attr]
            return success_response({"scene_name": scene_name})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def start_stream(self) -> dict[str, Any]:
        """Start the OBS stream output."""
        if not self._require_connection():
            return self._not_connected()

        try:
            self._client.start_stream()  # type: ignore[union-attr]
            return success_response({"message": "Stream started"})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def stop_stream(self) -> dict[str, Any]:
        """Stop the OBS stream output."""
        if not self._require_connection():
            return self._not_connected()

        try:
            self._client.stop_stream()  # type: ignore[union-attr]
            return success_response({"message": "Stream stopped"})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connection(self) -> bool:
        """Return True if the client is connected."""
        return self._client is not None

    @staticmethod
    def _not_connected() -> dict[str, Any]:
        """Return a standard not-connected error."""
        return error_response(
            ErrorCode.OBS_NOT_CONNECTED,
            "Not connected to OBS. Call obs_connect first.",
        )
