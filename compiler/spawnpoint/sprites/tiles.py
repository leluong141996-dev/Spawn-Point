"""Pixel-art tile atlas: [solid with exposed top, solid inner, one-way] in one row.

Drawn on a half-resolution grid and scaled 2x (same look as the sprites). Platformers get dirt with
a grassy top and wooden planks; top-down games get stone-brick walls with a lit top edge.
"""

from __future__ import annotations

import random

import numpy as np
from PIL import Image

from . import palettes
from .generate import _hex, _rgba, ramp

TILES = ("solid_top", "solid", "oneway")


def _shade(color: str, k: float) -> tuple:
    r, g, b = _hex(color)
    return _rgba(r * k, g * k, b * k)


def tileset(genre: str, solid: str, top: str, oneway: str, tile_size: int = 32, seed: int = 0,
            palette: str | None = None) -> Image.Image:
    pal = palettes.get(palette)
    n = max(tile_size // 2, 4)
    canvas = np.zeros((n, n * 3, 4), dtype=np.uint8)
    rng = random.Random(f"tiles:{seed}")
    if genre == "topdown":
        _bricks(canvas[:, 0:n], solid, top, rng, True, pal)
        _bricks(canvas[:, n:2 * n], solid, top, rng, False, pal)
    else:
        _dirt(canvas[:, n:2 * n], solid, rng, pal)
        _dirt(canvas[:, 0:n], solid, rng, pal)
        _grass(canvas[:, 0:n], top, rng, pal)
    _plank(canvas[:, 2 * n:3 * n], oneway, rng, pal)
    if pal:
        canvas = pal.snap(canvas)
    img = Image.fromarray(canvas, "RGBA")
    return img.resize((tile_size * 3, tile_size), Image.NEAREST)


def _dirt(px: np.ndarray, color: str, rng: random.Random, pal=None) -> None:
    n = px.shape[0]
    r = ramp(color, pal)
    px[:, :] = r.base
    for _ in range(n * n // 10):  # pebbles and specks
        x, y = rng.randrange(n), rng.randrange(n)
        px[y, x] = r.shadow if rng.random() < 0.7 else r.light
        if rng.random() < 0.3 and x + 1 < n:
            px[y, x + 1] = r.shadow
    px[n - 1, :] = _shade(color, 0.6)  # seam between tiles reads as depth
    px[:, n - 1] = _shade(color, 0.7)


def _grass(px: np.ndarray, color: str, rng: random.Random, pal=None) -> None:
    n = px.shape[0]
    r = ramp(color, pal)
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


def _bricks(px: np.ndarray, color: str, cap: str, rng: random.Random, lit_top: bool, pal=None) -> None:
    n = px.shape[0]
    r = ramp(color, pal)
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
        c = ramp(cap, pal)
        px[0:2, :] = c.base
        px[0, :] = c.light


def _plank(px: np.ndarray, color: str, rng: random.Random, pal=None) -> None:
    n = px.shape[0]
    r = ramp(color, pal)
    h = max(3, int(n * 0.3))
    px[0:h, :] = r.base
    px[0, :] = r.light
    px[h - 1, :] = r.shadow
    for x in range(0, n, max(3, n // 3)):  # grain and joints
        px[1:h - 1, x] = r.shadow
    for x in (1, n - 2):
        px[h // 2, x] = (230, 220, 200, 255)  # nails


# --- neighbour-aware pixel tiles --------------------------------------------------------------
# Instead of one repeated block, every ground cell is drawn for the neighbours it really has: grass on top, a
# dark outline on exposed edges, rounded outer corners, a notch in inner corners, and a few interior variants so
# big areas do not look stamped. Only the combinations that occur in the level are drawn.

Cell = tuple[int, int]
Key = tuple[bool, bool, bool, bool, bool, bool, bool, bool]  # N E S W NE SE SW NW: is that neighbour ground?
INTERIOR_VARIANTS = 3


def neighbour_key(cells: dict[Cell, str], x: int, y: int, w: int, h: int) -> Key:
    def ground(cx: int, cy: int) -> bool:
        if cy < 0:
            return False  # open sky above the level
        if cx < 0 or cx >= w or cy >= h:
            return True  # beyond the other edges counts as ground, so the level border shows no seam
        return cells.get((cx, cy)) == "solid"

    n, e, s, wst = ground(x, y - 1), ground(x + 1, y), ground(x, y + 1), ground(x - 1, y)
    # A diagonal only shows when both of its sides are ground (an inner corner); otherwise it does not matter.
    ne = ground(x + 1, y - 1) if n and e else True
    se = ground(x + 1, y + 1) if s and e else True
    sw = ground(x - 1, y + 1) if s and wst else True
    nw = ground(x - 1, y - 1) if n and wst else True
    return (n, e, s, wst, ne, se, sw, nw)


def tileset_auto(genre: str, solid: str, top: str, oneway: str, tile_size: int, seed: int, palette: str | None,
                 cells: dict[Cell, str], w: int, h: int, px: int = 2) -> tuple[Image.Image, list[str], dict[Cell, int]]:
    """The atlas (one row of variants), the kind ("solid" / "oneway") of each variant, and each cell's variant."""
    pal = palettes.get(palette)
    n = max(tile_size // px, 4)
    rng_for = lambda *a: random.Random(f"tiles:{seed}:{a}")  # noqa: E731
    variants: list[tuple] = []
    index: dict[tuple, int] = {}
    mapping: dict[Cell, int] = {}
    tiles: list[np.ndarray] = []
    kinds: list[str] = []
    for (x, y), kind in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if kind == "solid":
            key = neighbour_key(cells, x, y, w, h)
            v = (x * 7 + y * 13 + seed) % INTERIOR_VARIANTS
            ident = ("solid", key, v)
        else:
            left, right = cells.get((x - 1, y)) == "oneway", cells.get((x + 1, y)) == "oneway"
            ident = ("oneway", left, right)
        if ident not in index:
            index[ident] = len(tiles)
            kinds.append(kind)
            if kind == "solid":
                tiles.append(_ground_tile(n, genre, solid, top, ident[1], ident[2], pal, rng_for(*ident)))
            else:
                tiles.append(_plank_tile(n, oneway, ident[1], ident[2], pal, rng_for(*ident)))
        mapping[(x, y)] = index[ident]
    if not tiles:  # a level without ground still needs a valid atlas
        tiles.append(np.zeros((n, n, 4), np.uint8))
        kinds.append("solid")
    atlas = np.concatenate(tiles, axis=1)
    if pal:
        atlas = pal.snap(atlas)
    img = Image.fromarray(atlas, "RGBA")
    return img.resize((img.width * px * tile_size // (n * px), tile_size), Image.NEAREST), kinds, mapping


def _specks(px: np.ndarray, r, rng: random.Random, n: int) -> None:
    """Soft texture: mostly shadow specks (some two wide), a few highlights. A big jump between the base and the
    shadow tone (a palette with no in-between colour) gets far fewer specks, or the ground turns to static."""
    gap = sum(r.base[:3]) / 3 - sum(r.shadow[:3]) / 3
    for _ in range(n * n // (11 if gap < 55 else 34)):
        x, y = rng.randrange(1, n - 1), rng.randrange(1, n - 1)
        roll = rng.random()
        if roll < 0.78:
            px[y, x] = r.shadow
            if roll < 0.2:
                px[y, x + 1] = r.shadow
        elif roll < 0.9:
            px[y, x] = r.light


def _ground_tile(n: int, genre: str, color: str, cap: str, key: Key, variant: int, pal, rng: random.Random) -> np.ndarray:
    north, east, south, west, ne, se, sw, nw = key
    r = ramp(color, pal)
    t = np.zeros((n, n, 4), np.uint8)
    if genre == "topdown":
        _bricks(t, color, cap, rng, lit_top=False, pal=pal)
    else:
        _dirt_flat(t, r, rng, n)
    c = ramp(cap, pal)
    out = np.array(r.outline, np.uint8)
    # exposed edges: a dark outline, with a 1px shadow inside along the bottom
    if not south:
        t[n - 2, :] = r.shadow
        t[n - 1, :] = out
    if not west:
        t[:, 0] = out
    if not east:
        t[:, n - 1] = out
    # the top: grass (platformer) or a lit cap (top-down)
    if not north:
        if genre == "topdown":
            t[0:2, :] = c.base
            t[0, :] = c.light
            t[2, :] = r.shadow
        else:
            depth = max(2, n // 4)
            for x in range(n):
                d = depth + (1 if rng.random() < 0.45 else 0)
                t[0:d, x] = c.base
                t[0, x] = c.light
                t[d, x] = c.shadow if not (x in (0, n - 1) and (not west or not east)) else out
                if rng.random() < 0.22 and d + 1 < n:
                    t[d + 1, x] = c.shadow
            for _ in range(n // 3):  # bright blades
                t[rng.randrange(1, depth), rng.randrange(n)] = c.light
            if not west:  # the turf wraps around the corner
                t[0:depth + 1, 0] = c.shadow
            if not east:
                t[0:depth + 1, n - 1] = c.shadow
    # rounded outer corners
    for (a, b), (cx, cy), (dx, dy) in (((north, west), (0, 0), (1, 1)), ((north, east), (n - 1, 0), (-1, 1)),
                                       ((south, west), (0, n - 1), (1, -1)), ((south, east), (n - 1, n - 1), (-1, -1))):
        if not a and not b:
            t[cy, cx] = 0
            t[cy, cx + dx] = out if cy in (0, n - 1) and False else t[cy, cx + dx]
            t[cy + dy, cx] = t[cy + dy, cx]
            t[cy, cx + dx] = out
            t[cy + dy, cx] = out
    # inner corners: a notch where the diagonal ground is missing
    for ok, (cx, cy), (dx, dy) in ((ne, (n - 1, 0), (-1, 1)), (se, (n - 1, n - 1), (-1, -1)),
                                   (sw, (0, n - 1), (1, -1)), (nw, (0, 0), (1, 1))):
        if not ok:
            t[cy, cx] = out
            t[cy, cx + dx] = r.shadow
            t[cy + dy, cx] = r.shadow
    return t


def _dirt_flat(t: np.ndarray, r, rng: random.Random, n: int) -> None:
    t[:, :] = r.base
    _specks(t, r, rng, n)


def _plank_tile(n: int, color: str, left: bool, right: bool, pal, rng: random.Random) -> np.ndarray:
    """A one-way plank; the ends of a run get a rounded cap and a nail, the middle a joint."""
    r = ramp(color, pal)
    t = np.zeros((n, n, 4), np.uint8)
    h = max(3, int(n * 0.3))
    t[0:h, :] = r.base
    t[0, :] = r.light
    t[h - 1, :] = r.shadow
    t[h, :] = np.array(r.outline, np.uint8)  # drop outline under the plank
    for x in range(0, n, max(3, n // 3)):  # grain
        t[1:h - 1, x] = r.shadow
    nail = (230, 220, 200, 255)
    if not left:
        t[0:h + 1, 0] = np.array(r.outline, np.uint8)
        t[0, 0] = 0
        t[h // 2, 2] = nail
    if not right:
        t[0:h + 1, n - 1] = np.array(r.outline, np.uint8)
        t[0, n - 1] = 0
        t[h // 2, n - 3] = nail
    return t


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
