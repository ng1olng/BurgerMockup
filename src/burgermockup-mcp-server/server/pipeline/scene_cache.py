"""Scene persistence by scene_id — the mechanism that makes design-only
refines deterministic: the cached BLANK scene (garment + background, no
design) is reloaded and the design re-composited, so the background the
seller approved never changes on a turn that isn't about the scene.

Index writes are atomic (tmp + rename) so a crash never corrupts it."""

from __future__ import annotations

import json
import logging
import os
import threading

import numpy as np
from PIL import Image

from server.contracts import SceneAsset
from server.storage import file_store

_lock = threading.Lock()

_log = logging.getLogger(__name__)


def _index_path() -> str:
    return os.path.join(file_store.FILES_DIR, "scene_index.json")


def _load_index() -> dict:
    path = _index_path()
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_scene(scene_id: str, scene: Image.Image, *, garment_type: str,
               color: str, quad: list[tuple[float, float]]) -> SceneAsset:
    file_id, path = file_store.save_image(scene)
    asset = SceneAsset(scene_id=scene_id, image_path=path, garment_type=garment_type,
                       color=color, print_quad=[[float(x), float(y)] for x, y in quad])
    with _lock:
        index = _load_index()
        index[scene_id] = asset.model_dump()
        tmp = _index_path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(index, f)
        os.replace(tmp, _index_path())
    return asset


def load_scene(scene_id: str) -> tuple[SceneAsset, np.ndarray] | None:
    with _lock:
        entry = _load_index().get(scene_id)
    if entry is None or not os.path.exists(entry["image_path"]):
        _log.debug("scene cache MISS %s", scene_id)
        return None
    _log.debug("scene cache HIT %s", scene_id)
    asset = SceneAsset(**entry)
    rgba = np.array(Image.open(asset.image_path).convert("RGBA"))
    return asset, rgba
