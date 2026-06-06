"""UUID-keyed file store for designs and mockups.

Files are served ONLY by UUID through an index lookup — a request path is
never joined into a filesystem path (path-traversal hardening). Design ingest
normalizes to RGBA, enforces a decoded-pixel ceiling (a small-on-wire
decompression bomb cannot OOM the server), and persists per-design metadata
(text_heavy drives a stricter integrity threshold downstream).

Thread-safety: renders run in worker threads, so all index/metadata mutations
go through a lock.
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import uuid

import numpy as np
from PIL import Image

from server.contracts import MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES, DesignAsset

# Raise = hard error instead of Pillow's default warning-then-allocate.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

FILES_DIR = os.environ.get("FILES_DIR", "files")

_FILE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

_lock = threading.Lock()
_index: dict[str, str] = {}   # file_id -> absolute path
_assets: dict[str, dict] = {}  # design file_id -> {text_heavy, has_alpha, ...}

_ALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# Designs whose opaque area is dominated by hard edges (text, fine line art)
# lose the most detail to warping, so they get a stricter threshold.
_TEXT_EDGE_RATIO = 0.10


class IngestError(Exception):
    """code attribute carries the structured-error code; message is fixed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def init(files_dir: str | None = None) -> None:
    global FILES_DIR
    if files_dir:
        FILES_DIR = files_dir
    os.makedirs(FILES_DIR, exist_ok=True)
    with _lock:
        _index.clear()   # re-init must not serve stale ids from a previous dir
        _assets.clear()
        for name in os.listdir(FILES_DIR):
            stem, ext = os.path.splitext(name)
            if _FILE_ID_RE.match(stem) and ext == ".png":
                _index[stem] = os.path.join(FILES_DIR, name)
            elif name.endswith(".meta.json"):
                with open(os.path.join(FILES_DIR, name)) as f:
                    _assets[name[: -len(".meta.json")]] = json.load(f)


def _is_text_heavy(rgba: Image.Image) -> bool:
    arr = np.asarray(rgba.convert("L"), dtype=np.float32)
    alpha = np.asarray(rgba.split()[-1])
    gx = np.abs(np.diff(arr, axis=1, prepend=arr[:, :1]))
    gy = np.abs(np.diff(arr, axis=0, prepend=arr[:1, :]))
    edges = (np.maximum(gx, gy) > 60) & (alpha > 16)
    opaque = int((alpha > 16).sum())
    return bool(opaque > 0 and edges.sum() / opaque > _TEXT_EDGE_RATIO)


def ingest_design(data: bytes, filename: str) -> DesignAsset:
    """Validate + normalize an uploaded design to RGBA PNG, stored by UUID."""
    head = data[:256].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if filename.lower().endswith(".svg") or head.startswith((b"<svg", b"<?xml")):
        raise IngestError("unsupported_format", "SVG designs are not accepted")
    if not filename.lower().endswith(_ALLOWED_SUFFIXES):
        raise IngestError("unsupported_format", "Design must be PNG, JPG, or WebP")
    if len(data) > MAX_UPLOAD_BYTES:
        raise IngestError("file_too_large", "Design exceeds the 25MB limit")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Image.DecompressionBombError:
        raise IngestError("image_too_large", "Design dimensions exceed the allowed size")
    except Exception:
        raise IngestError("invalid_image", "File could not be decoded as an image")

    has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    rgba = im.convert("RGBA")
    meta = {"text_heavy": _is_text_heavy(rgba), "has_alpha": has_alpha,
            "width": rgba.width, "height": rgba.height}

    file_id = str(uuid.uuid4())
    path = os.path.join(FILES_DIR, f"{file_id}.png")
    rgba.save(path, "PNG")
    with open(os.path.join(FILES_DIR, f"{file_id}.meta.json"), "w") as f:
        json.dump(meta, f)
    with _lock:
        _index[file_id] = path
        _assets[file_id] = meta
    return DesignAsset(design_id=file_id, path=path, width=rgba.width,
                       height=rgba.height, has_alpha=has_alpha,
                       text_heavy=meta["text_heavy"])


def save_image(im: Image.Image) -> tuple[str, str]:
    """Store a generated image (scene/mockup); returns (file_id, path)."""
    file_id = str(uuid.uuid4())
    path = os.path.join(FILES_DIR, f"{file_id}.png")
    im.save(path, "PNG")
    with _lock:
        _index[file_id] = path
    return file_id, path


def resolve(file_id: str) -> str | None:
    """UUID-validated index lookup. Never joins request input into a path."""
    stem = file_id[:-4] if file_id.endswith(".png") else file_id
    if not _FILE_ID_RE.match(stem):
        return None
    with _lock:
        return _index.get(stem)


def design_meta(design_id: str) -> dict | None:
    with _lock:
        return _assets.get(design_id)


def url_for(file_id: str) -> str:
    base = os.environ.get("PUBLIC_FILES_BASE", "http://127.0.0.1:8100")
    return f"{base}/files/{file_id}.png"
