"""OBS WebSocket v5 controller. Handles raw OBS calls via obsws-python."""

from __future__ import annotations

import os
import time
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
    # Diagnostics (Phase 4)
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Return comprehensive OBS health and diagnostics.

        Includes connection status, streaming/recording state, current scene,
        OBS version info, and WebSocket round-trip latency.
        """
        if not self._require_connection():
            return self._not_connected()

        try:
            # Measure latency.
            start = time.perf_counter()
            version = self._client.get_version()  # type: ignore[union-attr]
            latency_ms = round((time.perf_counter() - start) * 1000, 1)

            stream = self._client.get_stream_status()  # type: ignore[union-attr]
            record = self._client.get_record_status()  # type: ignore[union-attr]
            scenes = self._client.get_scene_list()  # type: ignore[union-attr]

            return success_response(
                {
                    "connected": True,
                    "obs_version": version.obs_version,
                    "ws_version": version.obs_web_socket_version,
                    "platform": version.platform_description,
                    "ws_latency_ms": latency_ms,
                    "streaming": stream.output_active,
                    "stream_timecode": stream.output_timecode,
                    "recording": record.output_active,
                    "recording_paused": record.output_paused,
                    "current_scene": scenes.current_program_scene_name,
                    "scene_count": len(scenes.scenes),
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def list_devices(self) -> dict[str, Any]:
        """Return available video and audio devices.

        Creates temporary inputs to probe device lists, then cleans up.
        Prevents device name guessing.
        """
        if not self._require_connection():
            return self._not_connected()

        probe_scene = "__device_probe_scene"
        created_scene = False
        probes_created: list[str] = []

        try:
            # Create a temporary scene for probing.
            self._client.create_scene(probe_scene)  # type: ignore[union-attr]
            created_scene = True

            devices: dict[str, Any] = {"video": [], "audio_input": [], "audio_output": []}

            # Probe video devices (dshow_input).
            vname = "__probe_video"
            self._client.create_input(probe_scene, vname, "dshow_input", {}, False)  # type: ignore[union-attr]
            probes_created.append(vname)
            try:
                resp = self._client.get_input_properties_list_property_items(vname, "video_device_id")  # type: ignore[union-attr]
                devices["video"] = [
                    {"name": d["itemName"], "id": d["itemValue"]}
                    for d in resp.property_items
                    if d.get("itemEnabled", True)
                ]
            except Exception:
                pass

            # Probe audio input devices (wasapi_input_capture).
            aname = "__probe_audio_in"
            self._client.create_input(probe_scene, aname, "wasapi_input_capture", {}, False)  # type: ignore[union-attr]
            probes_created.append(aname)
            try:
                resp = self._client.get_input_properties_list_property_items(aname, "device_id")  # type: ignore[union-attr]
                devices["audio_input"] = [
                    {"name": d["itemName"], "id": d["itemValue"]}
                    for d in resp.property_items
                    if d.get("itemEnabled", True)
                ]
            except Exception:
                pass

            # Probe audio output devices (wasapi_output_capture).
            aoname = "__probe_audio_out"
            self._client.create_input(probe_scene, aoname, "wasapi_output_capture", {}, False)  # type: ignore[union-attr]
            probes_created.append(aoname)
            try:
                resp = self._client.get_input_properties_list_property_items(aoname, "device_id")  # type: ignore[union-attr]
                devices["audio_output"] = [
                    {"name": d["itemName"], "id": d["itemValue"]}
                    for d in resp.property_items
                    if d.get("itemEnabled", True)
                ]
            except Exception:
                pass

            return success_response(devices)

        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)
        finally:
            # Cleanup probes and scene.
            for pname in probes_created:
                try:
                    self._client.remove_input(pname)  # type: ignore[union-attr]
                except Exception:
                    pass
            if created_scene:
                try:
                    self._client.remove_scene(probe_scene)  # type: ignore[union-attr]
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Streaming helpers (Phase 4)
    # ------------------------------------------------------------------

    def is_streaming(self) -> bool:
        """Return True if OBS is currently streaming."""
        if not self._require_connection():
            return False
        try:
            return self._client.get_stream_status().output_active  # type: ignore[union-attr]
        except Exception:
            return False

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
        """Start the OBS stream output.

        Returns STREAM_ALREADY_ACTIVE if already streaming.
        """
        if not self._require_connection():
            return self._not_connected()

        if self.is_streaming():
            return error_response(
                ErrorCode.STREAM_ALREADY_ACTIVE,
                "Stream is already active",
            )

        try:
            self._client.start_stream()  # type: ignore[union-attr]
            return success_response({"message": "Stream started"})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def stop_stream(self, confirmed: bool = False) -> dict[str, Any]:
        """Stop the OBS stream output.

        Requires confirmed=True to prevent accidental stops.
        Returns STREAM_NOT_ACTIVE if not currently streaming.
        """
        if not self._require_connection():
            return self._not_connected()

        if not confirmed:
            return error_response(
                ErrorCode.CONFIRMATION_REQUIRED,
                "Stopping a stream requires confirmed=true to prevent accidental stops",
            )

        if not self.is_streaming():
            return error_response(
                ErrorCode.STREAM_NOT_ACTIVE,
                "Stream is not active",
            )

        try:
            self._client.stop_stream()  # type: ignore[union-attr]
            return success_response({"message": "Stream stopped"})
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    # ------------------------------------------------------------------
    # Source / scene item management (Phase 2)
    # ------------------------------------------------------------------

    def _validate_scene(self, scene_name: str) -> dict[str, Any] | None:
        """Return an error response if the scene does not exist, else None."""
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
        return None

    def _get_scene_item_id(
        self, scene_name: str, source_name: str
    ) -> int | None:
        """Return the scene item ID for a source in a scene, or None."""
        try:
            resp = self._client.get_scene_item_id(scene_name, source_name)  # type: ignore[union-attr]
            return resp.scene_item_id
        except Exception:
            return None

    def _validate_input_kind(self, source_type: str) -> dict[str, Any] | None:
        """Return an error response if the input kind is invalid, else None."""
        try:
            resp = self._client.get_input_kind_list(False)  # type: ignore[union-attr]
            if source_type not in resp.input_kinds:
                return error_response(
                    ErrorCode.INVALID_SOURCE_TYPE,
                    f"Invalid source type '{source_type}'. "
                    f"Available: {resp.input_kinds}",
                )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)
        return None

    def add_source(
        self,
        scene_name: str,
        source_name: str,
        source_type: str,
        source_settings: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add a new source (input) to a scene.

        Validates scene existence, input kind, and duplicate source name.
        """
        if not self._require_connection():
            return self._not_connected()

        for param, val in [("scene_name", scene_name), ("source_name", source_name), ("source_type", source_type)]:
            if not val or not val.strip():
                return error_response(ErrorCode.INVALID_PARAMETER, f"{param} must not be empty")

        err = self._validate_scene(scene_name)
        if err:
            return err

        err = self._validate_input_kind(source_type)
        if err:
            return err

        # Check for duplicate source name in this scene.
        if self._get_scene_item_id(scene_name, source_name) is not None:
            return error_response(
                ErrorCode.DUPLICATE_SOURCE,
                f"Source '{source_name}' already exists in scene '{scene_name}'",
            )

        try:
            resp = self._client.create_input(  # type: ignore[union-attr]
                scene_name,
                source_name,
                source_type,
                source_settings or {},
                enabled,
            )
            return success_response(
                {
                    "scene_name": scene_name,
                    "source_name": source_name,
                    "source_type": source_type,
                    "scene_item_id": resp.scene_item_id,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def remove_source(self, scene_name: str, source_name: str) -> dict[str, Any]:
        """Remove a source from a scene by name.

        Validates scene and source existence before removal.
        """
        if not self._require_connection():
            return self._not_connected()

        for param, val in [("scene_name", scene_name), ("source_name", source_name)]:
            if not val or not val.strip():
                return error_response(ErrorCode.INVALID_PARAMETER, f"{param} must not be empty")

        err = self._validate_scene(scene_name)
        if err:
            return err

        item_id = self._get_scene_item_id(scene_name, source_name)
        if item_id is None:
            return error_response(
                ErrorCode.SOURCE_NOT_FOUND,
                f"Source '{source_name}' not found in scene '{scene_name}'",
            )

        try:
            self._client.remove_scene_item(scene_name, item_id)  # type: ignore[union-attr]
            return success_response(
                {
                    "scene_name": scene_name,
                    "source_name": source_name,
                    "removed_item_id": item_id,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def get_source_list(self, scene_name: str) -> dict[str, Any]:
        """List all sources (scene items) in a scene."""
        if not self._require_connection():
            return self._not_connected()

        if not scene_name or not scene_name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "scene_name must not be empty")

        err = self._validate_scene(scene_name)
        if err:
            return err

        try:
            resp = self._client.get_scene_item_list(scene_name)  # type: ignore[union-attr]
            sources = [
                {
                    "source_name": item["sourceName"],
                    "source_type": item.get("inputKind"),
                    "scene_item_id": item["sceneItemId"],
                    "enabled": item["sceneItemEnabled"],
                    "locked": item["sceneItemLocked"],
                }
                for item in resp.scene_items
            ]
            return success_response(
                {
                    "scene_name": scene_name,
                    "sources": sources,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def set_source_transform(
        self, scene_name: str, source_name: str, transform: dict[str, Any]
    ) -> dict[str, Any]:
        """Set transform properties on a source in a scene.

        Only provided keys are updated. Validates scene and source existence.
        """
        if not self._require_connection():
            return self._not_connected()

        for param, val in [("scene_name", scene_name), ("source_name", source_name)]:
            if not val or not val.strip():
                return error_response(ErrorCode.INVALID_PARAMETER, f"{param} must not be empty")

        if not transform:
            return error_response(ErrorCode.INVALID_PARAMETER, "transform must not be empty")

        err = self._validate_scene(scene_name)
        if err:
            return err

        item_id = self._get_scene_item_id(scene_name, source_name)
        if item_id is None:
            return error_response(
                ErrorCode.SOURCE_NOT_FOUND,
                f"Source '{source_name}' not found in scene '{scene_name}'",
            )

        try:
            self._client.set_scene_item_transform(scene_name, item_id, transform)  # type: ignore[union-attr]
            # Read back the applied transform.
            updated = self._client.get_scene_item_transform(scene_name, item_id)  # type: ignore[union-attr]
            return success_response(
                {
                    "scene_name": scene_name,
                    "source_name": source_name,
                    "scene_item_id": item_id,
                    "transform": updated.scene_item_transform,
                }
            )
        except Exception as exc:
            code, msg = classify_obs_error(exc)
            return error_response(code, msg)

    def set_source_visibility(
        self, scene_name: str, source_name: str, visible: bool
    ) -> dict[str, Any]:
        """Show or hide a source in a scene.

        Validates scene and source existence before toggling.
        """
        if not self._require_connection():
            return self._not_connected()

        for param, val in [("scene_name", scene_name), ("source_name", source_name)]:
            if not val or not val.strip():
                return error_response(ErrorCode.INVALID_PARAMETER, f"{param} must not be empty")

        err = self._validate_scene(scene_name)
        if err:
            return err

        item_id = self._get_scene_item_id(scene_name, source_name)
        if item_id is None:
            return error_response(
                ErrorCode.SOURCE_NOT_FOUND,
                f"Source '{source_name}' not found in scene '{scene_name}'",
            )

        try:
            self._client.set_scene_item_enabled(scene_name, item_id, visible)  # type: ignore[union-attr]
            return success_response(
                {
                    "scene_name": scene_name,
                    "source_name": source_name,
                    "scene_item_id": item_id,
                    "visible": visible,
                }
            )
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
