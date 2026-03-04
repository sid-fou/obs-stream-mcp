"""Layout preset loader for scene orchestration.

Loads transform presets from JSON files. Falls back to bundled defaults.
External layout files override bundled defaults when provided.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_LAYOUTS_DIR = Path(__file__).parent / "layouts"
_DEFAULT_FILE = _LAYOUTS_DIR / "default.json"

_cache: dict[str, dict[str, Any]] | None = None


def _load_bundled() -> dict[str, dict[str, Any]]:
    """Load the bundled default layout file."""
    global _cache
    if _cache is not None:
        return _cache
    with open(_DEFAULT_FILE, "r") as f:
        _cache = json.load(f)
    return _cache


def load_layout(
    scene_type: str,
    source_key: str,
    override_file: str | None = None,
) -> dict[str, Any]:
    """Load a transform preset for a source in a scene type.

    Args:
        scene_type: e.g. "gaming", "starting_soon"
        source_key: e.g. "webcam", "game_capture", "title"
        override_file: Optional path to external JSON layout file.

    Returns:
        Transform dict. Empty dict if key not found.
    """
    data: dict[str, dict[str, Any]]

    if override_file:
        path = Path(override_file)
        if path.is_file():
            with open(path, "r") as f:
                data = json.load(f)
        else:
            data = _load_bundled()
    else:
        data = _load_bundled()

    scene_layouts = data.get(scene_type, {})
    return dict(scene_layouts.get(source_key, {}))
