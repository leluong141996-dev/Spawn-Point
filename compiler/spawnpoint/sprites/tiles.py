"""Pixel-art tile atlas: [solid with exposed top, solid inner, one-way] in one row.

Drawn on a half-resolution grid and scaled 2x (same look as the sprites). Platformers get dirt with
a grassy top and wooden planks; top-down games get stone-brick walls with a lit top edge.
"""

from __future__ import annotations

import random

import numpy as np
from PIL import Image

from .generate import _hex, _rgba, ramp

TILES = ("solid_top", "solid", "oneway")


def _shade(color: str, k: float) -> tuple:
    r, g, b = _hex(color)
    return _rgba(r * k, g * k, b * k)


def tileset(genre: str, solid: str, top: str, oneway: str, tile_size: int = 32, seed: int = 0) -> Image.Image:
    n = max(tile_size // 2, 4)
    canvas = np.zeros((n, n * 3, 4), dtype=np.uint8)
    rng = random.Random(f"tiles:{seed}")
    if genre == "topdown":
        _bricks(canvas[:, 0:n], solid, top, rng, lit_top=True)
        _bricks(canvas[:, n:2 * n], solid, top, rng, lit_top=False)
    else:
        _dirt(canvas[:, n:2 * n], solid, rng)
        _dirt(canvas[:, 0:n], solid, rng)
        _grass(canvas[:, 0:n], top, rng)
    _plank(canvas[:, 2 * n:3 * n], oneway, rng)
    img = Image.fromarray(canvas, "RGBA")
    return img.resize((tile_size * 3, tile_size), Image.NEAREST)


def _dirt(px: np.ndarray, color: str, rng: random.Random) -> None:
    n = px.shape[0]
    r = ramp(color)
    px[:, :] = r.base
    for _ in range(n * n // 10):  # pebbles and specks
        x, y = rng.randrange(n), rng.randrange(n)
        px[y, x] = r.shadow if rng.random() < 0.7 else r.light
        if rng.random() < 0.3 and x + 1 < n:
            px[y, x + 1] = r.shadow
    px[n - 1, :] = _shade(color, 0.6)  # seam between tiles reads as depth
    px[:, n - 1] = _shade(color, 0.7)


def _grass(px: np.ndarray, color: str, rng: random.Random) -> None:
    n = px.shape[0]
    r = ramp(color)
    depth = max(2, n // 4)
    for x in range(n):
        d = depth + (1 if rng.random() < 0.45 else 0)
        px[0:d, x] = r.base
        px[0, x] = r.light
        px[d, x] = r.shadow  # drop shadow under the turf
        if rng.random() < 0.25:
            px[d + 1 if d + 1 < n else d, x] = r.shadow
    for _ in range(n // 3):  # a few bright blades
        px[rng.randrange(1, depth), rng.randrange(n)] = r.light


def _bricks(px: np.ndarray, color: str, cap: str, rng: random.Random, lit_top: bool) -> None:
    n = px.shape[0]
    r = ramp(color)
    mortar = _shade(color, 0.55)
    px[:, :] = r.base
    row_h = max(3, n // 4)
    for row, y0 in enumerate(range(0, n, row_h)):
        px[y0, :] = mortar
        offset = (n // 4) if row % 2 else 0
        for x in range(offset, n + offset, max(4, n // 2)):
            px[y0:y0 + row_h, x % n] = mortar
        for x in range(n):  # light the top row of each brick
            if y0 + 1 < n and px[y0 + 1, x].tolist() != list(mortar):
                px[y0 + 1, x] = r.light
    for _ in range(n * n // 16):
        x, y = rng.randrange(n), rng.randrange(n)
        if px[y, x].tolist() == list(r.base):
            px[y, x] = r.shadow
    if lit_top:
        c = ramp(cap)
        px[0:2, :] = c.base
        px[0, :] = c.light


def _plank(px: np.ndarray, color: str, rng: random.Random) -> None:
    n = px.shape[0]
    r = ramp(color)
    h = max(3, int(n * 0.3))
    px[0:h, :] = r.base
    px[0, :] = r.light
    px[h - 1, :] = r.shadow
    for x in range(0, n, max(3, n // 3)):  # grain and joints
        px[1:h - 1, x] = r.shadow
    for x in (1, n - 2):
        px[h // 2, x] = (230, 220, 200, 255)  # nails
