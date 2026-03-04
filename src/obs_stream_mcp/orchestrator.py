"""High-level scene orchestration using only controller primitives.

This module NEVER calls OBS WebSocket directly.
All operations go through OBSController public methods.
"""

from __future__ import annotations

from typing import Any

from obs_stream_mcp.errors import ErrorCode, error_response, success_response
from obs_stream_mcp.layout_loader import load_layout
from obs_stream_mcp.obs_controller import OBSController


class SceneOrchestrator:
    """Builds complete scenes by composing controller primitives.

    Provides rollback safety: if any step fails after scene creation,
    all partially added sources are removed before returning the error.
    """

    def __init__(self, controller: OBSController) -> None:
        self._ctrl = controller

    # ------------------------------------------------------------------
    # Internal: stream guard
    # ------------------------------------------------------------------

    def _check_stream_guard(self, force: bool) -> dict[str, Any] | None:
        """Block scene rebuilds while streaming unless force=True."""
        if self._ctrl.is_streaming() and not force:
            return error_response(
                ErrorCode.STREAM_GUARD,
                "Cannot rebuild scene while streaming. Set force=true to override.",
            )
        return None

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
        force: bool = False,
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
            force: If True, allow rebuild while streaming.
        """
        if not self._ctrl.connected:
            return self._ctrl._not_connected()

        guard = self._check_stream_guard(force)
        if guard:
            return guard

        # Prepare scene.
        err = self._prepare_scene(scene_name, overwrite)
        scene_created = err is None and not overwrite or (
            overwrite and err is None
        )
        if err:
            return err

        # Load transforms from layout presets.
        lt = "gaming"
        source_specs = [
            {
                "name": f"{scene_name} - Game Capture",
                "type": "game_capture",
                "settings": {},
                "transform": load_layout(lt, "game_capture"),
            },
            {
                "name": f"{scene_name} - Display Capture",
                "type": "monitor_capture",
                "settings": {},
                "enabled": False,
                "transform": load_layout(lt, "display_capture"),
            },
            {
                "name": f"{scene_name} - Webcam",
                "type": "dshow_input",
                "settings": {},
                "transform": load_layout(lt, "webcam"),
            },
            {
                "name": f"{scene_name} - Stream Title",
                "type": "text_gdiplus_v3",
                "settings": {
                    "text": "Stream Title",
                    "font": {"face": "Arial", "size": 48},
                    "color": 16777215,
                },
                "transform": load_layout(lt, "stream_title"),
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
        force: bool = False,
    ) -> dict[str, Any]:
        """Build a 'Starting Soon' scene with background, title, optional countdown and image.

        Args:
            scene_name: Name for the scene.
            overwrite: If True, clear existing scene sources.
            switch_to: If True, switch to the scene after building.
            background_color: ABGR color integer for background.
            title_text: Text to display.
            countdown_url: Optional URL for a browser source countdown widget.
            image_path: Optional file path for a background/overlay image.
            force: If True, allow rebuild while streaming.
        """
        if not self._ctrl.connected:
            return self._ctrl._not_connected()

        guard = self._check_stream_guard(force)
        if guard:
            return guard

        err = self._prepare_scene(scene_name, overwrite)
        scene_created = err is None
        if err:
            return err

        lt = "starting_soon"
        source_specs: list[dict[str, Any]] = [
            {
                "name": f"{scene_name} - Background",
                "type": "color_source_v3",
                "settings": {
                    "color": background_color,
                    "width": 1920,
                    "height": 1080,
                },
                "transform": load_layout(lt, "background"),
            },
        ]

        if image_path:
            source_specs.append(
                {
                    "name": f"{scene_name} - Image",
                    "type": "image_source",
                    "settings": {"file": image_path},
                    "transform": load_layout(lt, "image"),
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
                    "transform": load_layout(lt, "countdown"),
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
                "transform": load_layout(lt, "title"),
            }
        )

        result = self._add_sources_with_rollback(scene_name, source_specs)
        if not result["success"]:
            return result

        return self._finalize_scene(
            scene_name, switch_to, scene_created, result["data"]["sources_added"]
        )
