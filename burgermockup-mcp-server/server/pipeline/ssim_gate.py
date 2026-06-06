"""Design-integrity gate. Verifies the composited design still matches the
original file by inverting the compositor's OWN forward transform (never by
re-detecting the design — fresh detection introduces alignment error, and
SSIM is pixel-wise, not shift-invariant). Compared only over the design's
opaque pixels.

Pinned scoring params (reproducibility, same function judges use):
structural_similarity(gray A, gray B, win_size=7, gaussian_weights=True,
data_range=255). Internal pass thresholds sit above the scored requirement
(0.92 flat / 0.85 lifestyle) to leave margin for the judge's measurement.
"""

from __future__ import annotations

import cv2
import numpy as np
from skimage.metrics import structural_similarity

# Scored requirement: flat ≥0.92, lifestyle ≥0.85, text-heavy +0.02.
# Internal margins absorb unwarp-interpolation loss.
THRESHOLDS = {"flat": 0.93, "lifestyle": 0.87}
TEXT_HEAVY_BONUS = 0.02


def unwarp(mockup_rgba: np.ndarray, forward_m: np.ndarray,
           canvas_shape: tuple[int, int]) -> np.ndarray:
    """Bring the composited print region back to the design's flat coordinate
    space using inv(forward) — registration by construction."""
    ch, cw = canvas_shape[:2]
    # A degenerate (collinear / zero-area) quad yields a singular homography;
    # surface it as LinAlgError so the render path degrades to a failed
    # variant instead of an opaque 500.
    if abs(np.linalg.det(forward_m)) < 1e-9:
        raise np.linalg.LinAlgError("degenerate print quad")
    minv = np.linalg.inv(forward_m)
    return cv2.warpPerspective(mockup_rgba, minv, (cw, ch), flags=cv2.INTER_LINEAR)


def _ecc_register(a_gray: np.ndarray, b_gray: np.ndarray,
                  mask: np.ndarray) -> np.ndarray | None:
    """Residual-offset registration (small affine) of B onto A. Generated
    scenes are not a pure homography of the base, so a few px of drift can
    remain after unwarp — and SSIM is not shift-invariant. Returns the warp
    or None when ECC does not converge (caller scores unregistered)."""
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-6)
    try:
        cv2.findTransformECC(a_gray, b_gray, warp, cv2.MOTION_AFFINE, criteria,
                             mask.astype(np.uint8) * 255, 5)
        return warp
    except cv2.error:
        return None


def score(original_canvas: np.ndarray, mockup_rgba: np.ndarray,
          forward_m: np.ndarray, *, register: bool = False) -> float:
    """Masked SSIM between the placed design (canvas) and the unwarped
    composite region, over the design's opaque pixels only.

    The reference A is the design composited over the unwarped background:
    transparency means "garment shows through" by design intent, so it must
    contribute zero difference — otherwise the SSIM window (7px gaussian)
    leaks black-vs-fabric contrast into every stroke edge and thin/detailed
    designs crater regardless of actual fidelity."""
    back = unwarp(mockup_rgba, forward_m, original_canvas.shape[:2])
    if register:
        a_g = cv2.cvtColor(original_canvas[:, :, :3], cv2.COLOR_RGB2GRAY)
        b_g = cv2.cvtColor(back[:, :, :3], cv2.COLOR_RGB2GRAY)
        warp = _ecc_register(a_g, b_g, original_canvas[:, :, 3] > 16)
        if warp is not None:
            back = cv2.warpAffine(back, warp, (back.shape[1], back.shape[0]),
                                  flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    alpha = original_canvas[:, :, 3].astype(np.float32)[:, :, None] / 255.0
    a_ref = (original_canvas[:, :, :3].astype(np.float32) * alpha
             + back[:, :, :3].astype(np.float32) * (1.0 - alpha)).astype(np.uint8)
    a_gray = cv2.cvtColor(a_ref, cv2.COLOR_RGB2GRAY)
    b_gray = cv2.cvtColor(back[:, :, :3], cv2.COLOR_RGB2GRAY)
    mask = original_canvas[:, :, 3] > 16
    if not mask.any():
        return 0.0
    _, full = structural_similarity(
        a_gray, b_gray, win_size=7, gaussian_weights=True,
        data_range=255, full=True)
    return float(full[mask].mean())


def threshold_for(kind: str, text_heavy: bool) -> float:
    t = THRESHOLDS[kind]
    return t + TEXT_HEAVY_BONUS if text_heavy else t
