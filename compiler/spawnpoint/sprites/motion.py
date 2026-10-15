"""Animations derived from a sprite's own frames: an attack pulse and a death sequence.

They work on any kind and in both art styles (pixel frames are resampled with nearest-neighbour so they stay
crisp, cartoon frames with Lanczos), so a new sprite kind gets `attack` and `die` for free. Hand-drawn poses
(the hero's sword swing, breathing and blinking) live in the painters instead.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

FLASH = (255, 250, 240)


def _opaque_box(f: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(f[..., 3] > 0)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def scaled(f: np.ndarray, sx: float, sy: float, anchor: str, pixel: bool) -> np.ndarray:
    """The frame's content resized about its bottom centre (anchor "bottom") or centre, kept inside the frame."""
    h, w = f.shape[:2]
    box = _opaque_box(f)
    if box is None:
        return f
    x0, y0, x1, y1 = box
    content = Image.fromarray(f[y0:y1, x0:x1], "RGBA")
    nw = min(w, max(1, round((x1 - x0) * sx)))  # never wider than the frame
    nh = min(h, max(1, round((y1 - y0) * sy)))
    content = content.resize((nw, nh), Image.NEAREST if pixel else Image.LANCZOS)
    out = np.zeros_like(f)
    cx = (x0 + x1) / 2
    ox = int(round(min(max(cx - nw / 2, 0), w - nw)))
    oy = (y1 - nh) if anchor == "bottom" else int(round((y0 + y1) / 2 - nh / 2))
    oy = min(max(oy, 0), h - nh)
    out[oy:oy + nh, ox:ox + nw] = np.asarray(content)
    return out


def flash(f: np.ndarray, color: tuple[int, int, int] = FLASH) -> np.ndarray:
    out = f.copy()
    out[out[..., 3] > 0, :3] = color
    return out


def dissolve(f: np.ndarray, keep: float, pixel: bool, seed: int = 0) -> np.ndarray:
    """Randomly removes pixels (cartoon: blobs of 4x4) so only about `keep` of them remain."""
    h, w = f.shape[:2]
    cell = 1 if pixel else 4
    rng = np.random.default_rng(seed)
    mask = rng.random(((h + cell - 1) // cell, (w + cell - 1) // cell)) < keep
    mask = np.kron(mask, np.ones((cell, cell), bool))[:h, :w]
    out = f.copy()
    out[~mask] = 0
    return out


def attack_frames(idle: np.ndarray, anchor: str, pixel: bool) -> list[np.ndarray]:
    """Wind up, strike (stretched toward the target), recover."""
    return [scaled(idle, 0.9, 1.06, anchor, pixel), scaled(idle, 1.25, 0.9, anchor, pixel), scaled(idle, 1.1, 0.97, anchor, pixel)]


def die_frames(hurt: np.ndarray, anchor: str, pixel: bool, flash_color: tuple[int, int, int] = FLASH,
               seed: int = 0) -> list[np.ndarray]:
    """White flash, squash, flatten and dissolve, then nothing."""
    f1 = scaled(hurt, 1.2, 0.75, anchor, pixel)
    f2 = dissolve(scaled(hurt, 1.3, 0.45, anchor, pixel), 0.6, pixel, seed)
    f3 = dissolve(scaled(hurt, 1.4, 0.25, anchor, pixel), 0.25, pixel, seed + 1)
    return [flash(hurt, flash_color), f1, f2, f3, np.zeros_like(hurt)]
