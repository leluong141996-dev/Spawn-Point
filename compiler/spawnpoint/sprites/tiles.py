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


# --- cartoon style ----------------------------------------------------------------------------

def tileset_cartoon(genre: str, solid: str, top: str, oneway: str, tile_size: int = 32, seed: int = 0) -> Image.Image:
    """Smooth tiles for the cartoon art style: drawn 4x larger, then downsampled with anti-aliasing."""
    from PIL import ImageDraw

    from .cartoon import _shade

    k = 4
    n = tile_size * k
    img = Image.new("RGBA", (n * 3, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(f"ctiles:{seed}")

    def soil(x0: int) -> None:
        base, dark = _shade(solid, 1.0), _shade(solid, 0.72)
        for y in range(n):  # soft vertical gradient
            t = y / n
            c = tuple(round(base[i] + (dark[i] - base[i]) * t) for i in range(3))
            d.line([(x0, y), (x0 + n - 1, y)], fill=(*c, 255))
        for _ in range(5):  # rounded pebbles with a lit edge
            px, py, r = x0 + rng.uniform(n * 0.15, n * 0.85), rng.uniform(n * 0.35, n * 0.9), rng.uniform(n * 0.05, n * 0.09)
            d.ellipse([px - r, py - r * 0.7, px + r, py + r * 0.7], fill=(*_shade(solid, 0.6), 255))
            d.ellipse([px - r * 0.6, py - r * 0.55, px + r * 0.2, py - r * 0.1], fill=(*_shade(solid, 1.25), 200))

    def stone(x0: int, lit: bool) -> None:
        d.rectangle([x0, 0, x0 + n - 1, n - 1], fill=(*_shade(solid, 0.55), 255))  # mortar
        half = n // 2
        for row, y0 in enumerate((0, half)):
            off = 0 if row == 0 else half // 2
            for x in range(x0 - half + off, x0 + n, half):
                bx0, bx1 = max(x0, x + k * 2), min(x0 + n - 1, x + half - k * 2)
                if bx1 - bx0 < k * 3:
                    continue
                d.rounded_rectangle([bx0, y0 + k * 2, bx1, y0 + half - k * 2], radius=k * 4, fill=(*_shade(solid, 1.0), 255))
                d.rounded_rectangle([bx0 + k, y0 + k * 3, bx1 - k, y0 + k * 6], radius=k * 2, fill=(*_shade(solid, 1.2), 255))
        if lit:
            d.rounded_rectangle([x0, 0, x0 + n - 1, k * 7], radius=k * 3, fill=(*_shade(top, 1.0), 255))
            d.rounded_rectangle([x0 + k, k, x0 + n - 1 - k, k * 3], radius=k * 2, fill=(*_shade(top, 1.25), 255))

    if genre == "topdown":
        stone(0, True)
        stone(n, False)
    else:
        soil(0)
        soil(n)
        g, gl, gd = _shade(top, 1.0), _shade(top, 1.3), _shade(top, 0.7)
        depth = n * 0.3
        pts = [(0, 0), (n, 0)]
        for i in range(9, -1, -1):  # a wavy lower edge for the grass cap
            x = n * i / 9
            pts.append((x, depth + (k * 3 if i % 2 else 0)))
        d.polygon([(x + 2, y + k * 2) for x, y in pts], fill=(*gd, 255))  # shade under the turf
        d.polygon(pts, fill=(*g, 255))
        d.rectangle([0, 0, n - 1, k * 3], fill=(*gl, 255))
        for _ in range(4):  # blades
            bx = rng.uniform(k * 4, n - k * 4)
            d.polygon([(bx - k * 2, k * 3), (bx, -k), (bx + k * 2, k * 3)], fill=(*gl, 255))
    # one-way: a rounded wooden plank with grain and two nails
    x0 = n * 2
    ph = max(k * 6, round(n * 0.3))
    d.rounded_rectangle([x0 + k, 0, x0 + n - k, ph], radius=k * 3, fill=(*_shade(oneway, 0.7), 255))
    d.rounded_rectangle([x0 + k, 0, x0 + n - k, ph - k * 2], radius=k * 3, fill=(*_shade(oneway, 1.0), 255))
    d.line([(x0 + k * 4, ph * 0.45), (x0 + n - k * 4, ph * 0.45)], fill=(*_shade(oneway, 0.75), 255), width=k)
    for nx in (x0 + k * 5, x0 + n - k * 5):
        d.ellipse([nx - k * 1.5, ph * 0.25 - k * 1.5, nx + k * 1.5, ph * 0.25 + k * 1.5], fill=(235, 225, 205, 255))
    # Downsample each tile on its own: resampling the strip at once would bleed neighbours into the edges.
    small = Image.new("RGBA", (tile_size * 3, tile_size), (0, 0, 0, 0))
    for i in range(3):
        small.paste(img.crop((i * n, 0, (i + 1) * n, n)).resize((tile_size, tile_size), Image.LANCZOS), (i * tile_size, 0))
    return _with_gaps(small, tile_size, CARTOON_GAP)


CARTOON_GAP = 4  # px between atlas tiles (filled with each tile's edge), so smooth filtering never bleeds


def _with_gaps(atlas: Image.Image, ts: int, gap: int) -> Image.Image:
    n = atlas.width // ts
    out = Image.new("RGBA", (n * ts + (n - 1) * gap, ts), (0, 0, 0, 0))
    for i in range(n):
        tile = atlas.crop((i * ts, 0, (i + 1) * ts, ts))
        x = i * (ts + gap)
        out.paste(tile, (x, 0))
        if i > 0:  # extend the left edge into the gap before it
            out.paste(tile.crop((0, 0, 1, ts)).resize((gap // 2 + gap % 2, ts)), (x - gap // 2 - gap % 2, 0))
        if i < n - 1:  # and the right edge into the gap after it
            out.paste(tile.crop((ts - 1, 0, ts, ts)).resize((gap // 2, ts)), (x + ts, 0))
    return out
