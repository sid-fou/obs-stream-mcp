"""High-level scene orchestration using only controller primitives.

This module NEVER calls OBS WebSocket directly.
All operations go through OBSController public methods.
"""

from __future__ import annotations

from typing import Any

from obs_stream_mcp.errors import ErrorCode, error_response, success_response
from obs_stream_mcp.obs_controller import OBSController


class SceneOrchestrator:
    """Builds complete scenes by composing controller primitives.

    Provides rollback safety: if any step fails after scene creation,
    all partially added sources are removed before returning the error.
    """

    def __init__(self, controller: OBSController) -> None:
        self._ctrl = controller

    # ------------------------------------------------------------------
    # Internal: scene setup + rollback
    # ------------------------------------------------------------------

    def _prepare_scene(
        self, scene_name: str, overwrite: bool
    ) -> dict[str, Any] | None:
        """Create scene or handle overwrite logic.

        Returns an error dict if scene cannot be prepared, else None.
        On overwrite=True, removes all existing sources from the scene.
        """
        result = self._ctrl.create_scene(scene_name)
        if result["success"]:
            return None

        # Scene already exists.
        if result.get("code") == ErrorCode.DUPLICATE_SCENE.value:
            if not overwrite:
                return result
            # Overwrite: clear all existing sources.
            sources = self._ctrl.get_source_list(scene_name)
            if not sources["success"]:
                return sources
            for src in sources["data"].get("sources", []):
                rm = self._ctrl.remove_source(scene_name, src["source_name"])
                if not rm["success"]:
                    return rm
            return None

        # Some other error (connection, etc).
        return result

    def _add_sources_with_rollback(
        self,
        scene_name: str,
        source_specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Add a list of sources to a scene with rollback on failure.

        Each spec: {name, type, settings?, transform?, enabled?}
        Returns structured result with sources_added list.
        On failure, removes all sources added in this batch.
        """
        added: list[str] = []

        for spec in source_specs:
            # Add the source.
            result = self._ctrl.add_source(
                scene_name,
                spec["name"],
                spec["type"],
                spec.get("settings"),
                spec.get("enabled", True),
            )
            if not result["success"]:
                self._rollback_sources(scene_name, added)
                return error_response(
                    ErrorCode(result["code"]) if result.get("code") else ErrorCode.OBS_ERROR,
                    f"Failed adding source '{spec['name']}': {result['error']}",
                )
            added.append(spec["name"])

            # Apply transform if specified.
            if "transform" in spec:
                tr = self._ctrl.set_source_transform(
                    scene_name, spec["name"], spec["transform"]
                )
                if not tr["success"]:
                    self._rollback_sources(scene_name, added)
                    return error_response(
                        ErrorCode(tr["code"]) if tr.get("code") else ErrorCode.OBS_ERROR,
                        f"Failed transforming source '{spec['name']}': {tr['error']}",
                    )

        return success_response({"sources_added": added})

    def _rollback_sources(self, scene_name: str, source_names: list[str]) -> None:
        """Best-effort removal of sources added during a failed build."""
        for name in reversed(source_names):
            self._ctrl.remove_source(scene_name, name)

    def _finalize_scene(
        self,
        scene_name: str,
        switch_to: bool,
        scene_created: bool,
        sources_added: list[str],
    ) -> dict[str, Any]:
        """Optionally switch to the scene and return the final result."""
        switched = False
        if switch_to:
            sw = self._ctrl.switch_scene(scene_name)
            if not sw["success"]:
                return sw
            switched = True

        return success_response(
            {
                "scene_name": scene_name,
                "scene_created": scene_created,
                "sources_added": sources_added,
                "scene_switched": switched,
            }
        )

    # ------------------------------------------------------------------
    # Public: scene builders
    # ------------------------------------------------------------------

    def build_gaming_scene(
        self,
        scene_name: str = "Gaming",
        overwrite: bool = False,
        switch_to: bool = True,
    ) -> dict[str, Any]:
        """Build a gaming scene with game capture, display capture, webcam, and title overlay.

        Sources (back to front):
          1. Game Capture   — game_capture, full canvas
          2. Display Capture — monitor_capture, full canvas, disabled by default
          3. Webcam         — dshow_input, bottom-right corner
          4. Stream Title   — text_gdiplus_v3, top-left

        Args:
            scene_name: Name for the scene.
            overwrite: If True, clear existing scene sources. If False, fail on duplicate.
            switch_to: If True, switch to the scene after building.
        """
        if not self._ctrl.connected:
            return self._ctrl._not_connected()

        # Prepare scene.
        err = self._prepare_scene(scene_name, overwrite)
        scene_created = err is None and not overwrite or (
            overwrite and err is None
        )
        if err:
            return err

        # Define sources back-to-front.
        source_specs = [
            {
                "name": f"{scene_name} - Game Capture",
                "type": "game_capture",
                "settings": {},
                "transform": {
                    "boundsType": "OBS_BOUNDS_STRETCH",
                    "boundsWidth": 1920.0,
                    "boundsHeight": 1080.0,
                },
            },
            {
                "name": f"{scene_name} - Display Capture",
                "type": "monitor_capture",
                "settings": {},
                "enabled": False,
                "transform": {
                    "boundsType": "OBS_BOUNDS_STRETCH",
                    "boundsWidth": 1920.0,
                    "boundsHeight": 1080.0,
                },
            },
            {
                "name": f"{scene_name} - Webcam",
                "type": "dshow_input",
                "settings": {},
                "transform": {
                    "positionX": 1520.0,
                    "positionY": 780.0,
                    "boundsType": "OBS_BOUNDS_STRETCH",
                    "boundsWidth": 384.0,
                    "boundsHeight": 288.0,
                },
            },
            {
                "name": f"{scene_name} - Stream Title",
                "type": "text_gdiplus_v3",
                "settings": {
                    "text": "Stream Title",
                    "font": {"face": "Arial", "size": 48},
                    "color": 16777215,
                },
                "transform": {
                    "positionX": 20.0,
                    "positionY": 20.0,
                },
            },
        ]

        result = self._add_sources_with_rollback(scene_name, source_specs)
        if not result["success"]:
            return result

        return self._finalize_scene(
            scene_name, switch_to, scene_created, result["data"]["sources_added"]
        )

    def build_starting_soon_scene(
        self,
        scene_name: str = "Starting Soon",
        overwrite: bool = False,
        switch_to: bool = True,
        background_color: int = 4281348144,
        title_text: str = "Starting Soon...",
        countdown_url: str | None = None,
        image_path: str | None = None,
    ) -> dict[str, Any]:
        """Build a 'Starting Soon' scene with background, title, optional countdown and image.

        Sources (back to front):
          1. Background    — color_source_v3, full canvas
          2. Image         — image_source (only if image_path provided)
          3. Countdown     — browser_source (only if countdown_url provided)
          4. Title Text    — text_gdiplus_v3, centered

        Args:
            scene_name: Name for the scene.
            overwrite: If True, clear existing scene sources.
            switch_to: If True, switch to the scene after building.
            background_color: ABGR color integer for background.
            title_text: Text to display.
            countdown_url: Optional URL for a browser source countdown widget.
            image_path: Optional file path for a background/overlay image.
        """
        if not self._ctrl.connected:
            return self._ctrl._not_connected()

        err = self._prepare_scene(scene_name, overwrite)
        scene_created = err is None
        if err:
            return err

        # Build source list dynamically.
        source_specs: list[dict[str, Any]] = [
            {
                "name": f"{scene_name} - Background",
                "type": "color_source_v3",
                "settings": {
                    "color": background_color,
                    "width": 1920,
                    "height": 1080,
                },
                "transform": {
                    "boundsType": "OBS_BOUNDS_STRETCH",
                    "boundsWidth": 1920.0,
                    "boundsHeight": 1080.0,
                },
            },
        ]

        if image_path:
            source_specs.append(
                {
                    "name": f"{scene_name} - Image",
                    "type": "image_source",
                    "settings": {"file": image_path},
                    "transform": {
                        "boundsType": "OBS_BOUNDS_STRETCH",
                        "boundsWidth": 1920.0,
                        "boundsHeight": 1080.0,
                    },
                }
            )

        if countdown_url:
            source_specs.append(
                {
                    "name": f"{scene_name} - Countdown",
                    "type": "browser_source",
                    "settings": {
                        "url": countdown_url,
                        "width": 800,
                        "height": 200,
                    },
                    "transform": {
                        "positionX": 560.0,
                        "positionY": 700.0,
                    },
                }
            )

        source_specs.append(
            {
                "name": f"{scene_name} - Title",
                "type": "text_gdiplus_v3",
                "settings": {
                    "text": title_text,
                    "font": {"face": "Arial", "size": 96},
                    "color": 16777215,
                    "align": "center",
                },
                "transform": {
                    "positionX": 560.0,
                    "positionY": 450.0,
                },
            }
        )

        result = self._add_sources_with_rollback(scene_name, source_specs)
        if not result["success"]:
            return result

        return self._finalize_scene(
            scene_name, switch_to, scene_created, result["data"]["sources_added"]
        )
