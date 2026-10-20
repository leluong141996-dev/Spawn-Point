"""Cozy farm art: the ground of a whole farm map and the farm's objects, animals and crops, drawn in a
16-pixel tile language and shown at 2 screen pixels per art pixel (one 16 px art tile = one 32 px world tile).

The look: soft green grass with tufts and little flowers, dirt paths with rounded, bumpy edges and a dark rim,
water with a light shore line and sparkles, and a brown cliff face wherever land drops into the water to the south
(islands). Everything is drawn here from code; no image files are read.

    terrain_image(rows, seed)   -> RGBA array of the whole map ground (16 px per cell)
    paint_*(...)                -> the object painters used through generate.py's farm kinds
    crop_sheet(kind, color)     -> the growth stages of one crop (5 frames of 16x16) for FarmPlot
"""

from __future__ import annotations

import random
import zlib

import numpy as np

RGBA = tuple[int, int, int, int]
CELL = 16  # art pixels per map cell


def _c(h: str, a: int = 255) -> RGBA:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


# --- the palette --------------------------------------------------------------------------------
GRASS, GRASS_LIGHT, GRASS_DARK = _c("#6cbf4a"), _c("#7bca52"), _c("#62b444")
GRASS_EDGE, TUFT, TUFT_LIGHT = _c("#2f6e3c"), _c("#3f8f3a"), _c("#9ee06a")
DIRT, DIRT_LIGHT, DIRT_DARK, DIRT_EDGE = _c("#d8a062"), _c("#e8bb80"), _c("#b57a45"), _c("#8a5530")
WATER, WATER_DEEP, WATER_LIGHT, FOAM = _c("#3aa0e8"), _c("#2a82d0"), _c("#7fd0ff"), _c("#e6fbff")
CLIFF, CLIFF_DARK, CLIFF_LIGHT = _c("#b4683c"), _c("#7c4228"), _c("#d08c56")
SAND, SAND_DARK = _c("#f0d79a"), _c("#d9b878")
FLOWERS = [_c("#f8f4ea"), _c("#ffd84a"), _c("#ff8fb4"), _c("#8ab0ff"), _c("#c48ae0")]
OUTLINE = _c("#2a1e2e")

# Terrain characters (one per map cell).
GRASS_C, PATH_C, WATER_C, FIELD_C, SAND_C = ".", ":", "~", ",", "_"


# --- small helpers ------------------------------------------------------------------------------

def _noise(h: int, w: int, cell: int, rng: np.random.Generator, smooth: float) -> np.ndarray:
    """Low-frequency value noise in 0..1: a coarse random grid, upscaled and blurred."""
    from scipy.ndimage import gaussian_filter
    gh, gw = h // cell + 2, w // cell + 2
    grid = rng.random((gh, gw))
    up = np.kron(grid, np.ones((cell, cell)))[:h, :w]
    return gaussian_filter(up, smooth)


def _soft_mask(cells: np.ndarray, sigma: float, jitter: np.ndarray, k: float = 0.16) -> np.ndarray:
    """Cell mask -> pixel mask with rounded corners and bumpy edges."""
    from scipy.ndimage import gaussian_filter
    up = np.kron(cells.astype(float), np.ones((CELL, CELL)))
    return gaussian_filter(up, sigma) > 0.5 + (jitter - 0.5) * k


def _shift(m: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """m moved by (dy, dx); pixels shifted in from outside are False."""
    out = np.zeros_like(m)
    h, w = m.shape
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = m[ys, xs]
    return out


def _ring(m: np.ndarray) -> np.ndarray:
    """Pixels outside m that touch it (4-neighbourhood)."""
    return (_shift(m, 1, 0) | _shift(m, -1, 0) | _shift(m, 0, 1) | _shift(m, 0, -1)) & ~m


def _rng(*key) -> random.Random:
    return random.Random(zlib.crc32(":".join(str(k) for k in key).encode()))


# --- the ground ---------------------------------------------------------------------------------

def terrain_image(rows: list[str], seed: int = 0) -> np.ndarray:
    """The ground of a farm map, 16 art pixels per cell. Unknown characters count as grass."""
    hh, ww = len(rows), max((len(r) for r in rows), default=1)
    grid = np.array([[(r[x] if x < len(r) else GRASS_C) for x in range(ww)] for r in rows])
    H, W = hh * CELL, ww * CELL
    nrng = np.random.default_rng(zlib.crc32(f"terrain:{seed}".encode()))
    jitter = _noise(H, W, 3, nrng, 1.0)
    water = _soft_mask(grid == WATER_C, 4.0, jitter)
    from scipy.ndimage import binary_opening
    water = binary_opening(water, iterations=2) | (np.kron(grid == WATER_C, np.ones((CELL, CELL), dtype=bool)) & water)
    sand = _soft_mask((grid == SAND_C) | (grid == WATER_C), 4.0, jitter) & ~water
    path = _soft_mask(grid == PATH_C, 4.0, jitter) & ~water & ~sand
    land = ~water
    img = np.zeros((H, W, 4), dtype=np.uint8)

    # grass: two tones in soft patches, specks of darker green
    img[:] = GRASS
    patches = _noise(H, W, 24, nrng, 6.0)
    img[patches > 0.60] = GRASS_LIGHT
    img[patches < 0.36] = GRASS_DARK
    specks = nrng.random((H, W)) < 0.012
    img[specks & land] = GRASS_DARK

    # tufts and flowers on plain grass cells (fields stay tidy)
    rnd = _rng("tufts", seed)
    for y in range(hh):
        for x in range(ww):
            if grid[y, x] != GRASS_C:
                continue
            for _ in range(rnd.choice((1, 2, 2, 3))):
                _tuft(img, x * CELL + rnd.randint(2, 12), y * CELL + rnd.randint(4, 13), rnd)
            if rnd.random() < 0.16:
                col = rnd.choice(FLOWERS)
                for _ in range(rnd.randint(1, 3)):
                    _flower(img, x * CELL + rnd.randint(2, 13), y * CELL + rnd.randint(2, 13), col)

    # sand (beaches)
    img[sand] = SAND
    img[sand & (nrng.random((H, W)) < 0.05)] = SAND_DARK

    # dirt paths: speckled fill, a darker rim, a dark outline on the grass around them
    img[path] = DIRT
    dots = nrng.random((H, W))
    img[path & (dots < 0.035)] = DIRT_LIGHT
    img[path & (dots > 0.975)] = DIRT_DARK
    rim = path & (_ring(~path) | _shift(~path, -1, 0))
    img[rim & ~_shift(~path, 1, 0)] = DIRT_DARK          # shadow under the grass lip on the top and sides
    img[path & _shift(~path & land, 1, 0)] = DIRT_DARK    # under a grass edge, the dirt is in shade
    img[_ring(path) & land & ~sand] = GRASS_EDGE
    for y, x in zip(*np.nonzero(path & (dots > 0.993))):  # a few pebbles
        _pebble(img, x, y)

    # water: deep middle, light shore line, sparkles; a brown cliff where land drops into it to the south
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(water)
    img[water] = WATER
    deep = water & (dist > 9) & (_noise(H, W, 14, nrng, 4.0) > 0.52)
    img[deep] = WATER_DEEP
    img[water & (dist <= 2)] = WATER_LIGHT
    cliff = np.zeros_like(water)
    for k in range(1, 7):
        cliff |= water & _shift(land, k, 0)
    face = cliff & ~_shift(water & ~cliff, -1, 0) | cliff
    img[face] = CLIFF
    img[face & _shift(land, 1, 0)] = CLIFF_LIGHT                     # the lit top of the face
    img[cliff & ~_shift(cliff, -1, 0)] = CLIFF_DARK                  # the bottom of the face
    stripes = cliff & ((np.arange(W)[None, :] + (np.arange(H)[:, None] // 3)) % 7 == 0)
    img[stripes] = CLIFF_DARK
    img[water & ~cliff & _shift(cliff, 1, 0)] = FOAM                 # foam at the foot of the cliff
    img[_ring(water) & land & ~cliff] = GRASS_EDGE                   # the grass lip around the water
    img[_ring(land) & water & ~cliff] = FOAM                         # a thin light line on the water side
    sparkle = water & ~cliff & (dist > 3) & (nrng.random((H, W)) < 0.004)
    for y, x in zip(*np.nonzero(sparkle)):
        _sparkle(img, x, y)
    # lily pads out on the water, reeds along the shore, the odd mushroom in the grass
    rnd = _rng("details", seed)
    for y in range(hh):
        for x in range(ww):
            cx, cy = x * CELL + 8, y * CELL + 8
            if grid[y, x] == WATER_C and 0 < cy < H and 0 < cx < W and water[cy, cx] and not cliff[cy, cx]:
                if dist[cy, cx] > 6 and rnd.random() < 0.05:
                    _lily(img, cx + rnd.randint(-3, 3), cy + rnd.randint(-3, 3), rnd)
                elif 2 < dist[cy, cx] <= 6 and rnd.random() < 0.12:
                    _reeds(img, cx + rnd.randint(-5, 5), cy + rnd.randint(-2, 4))
            elif grid[y, x] == GRASS_C and rnd.random() < 0.025:
                _mushroom(img, x * CELL + rnd.randint(3, 12), y * CELL + rnd.randint(5, 13))
    return img


def _lily(img: np.ndarray, x: int, y: int, rnd: random.Random) -> None:
    h, w = img.shape[:2]
    for dy in range(-3, 4):
        for dx in range(-4, 5):
            if (dx / 4.4) ** 2 + (dy / 3.2) ** 2 <= 1 and not (dx > 0 and abs(dy) <= dx // 2) and 0 <= y + dy < h and 0 <= x + dx < w:
                img[y + dy, x + dx] = _c("#4aa040") if dy > 0 else _c("#62bf4a")
    if rnd.random() < 0.4 and 0 <= y - 1 < h and 0 <= x - 1 < w:
        img[y - 1, x - 1] = _c("#ff9ac0")
        img[y - 1, x - 2] = _c("#ffd0e0")


def _reeds(img: np.ndarray, x: int, y: int) -> None:
    h, w = img.shape[:2]
    for k, (dx, top) in enumerate(((-1, 5), (0, 7), (1, 4), (2, 6))):
        for dy in range(top):
            if 0 <= y - dy < h and 0 <= x + dx < w:
                img[y - dy, x + dx] = _c("#3f8f3a") if dy < top - 2 else _c("#86d25a")
        if k == 1 and 0 <= y - top - 1 < h and 0 <= x + dx < w:
            img[y - top, x + dx] = _c("#8a5530")
            img[y - top - 1, x + dx] = _c("#8a5530")


def _mushroom(img: np.ndarray, x: int, y: int) -> None:
    h, w = img.shape[:2]
    for dx, dy, col in ((0, 0, _c("#f4ece0")), (0, -1, _c("#f4ece0")), (-1, -2, _c("#e83a3a")), (0, -2, _c("#e83a3a")),
                        (1, -2, _c("#e83a3a")), (0, -3, _c("#e83a3a")), (-1, -3, _c("#ffffff")), (1, -1, _c("#2a1e2e")),
                        (-1, -1, _c("#2a1e2e"))):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = col


def _tuft(img: np.ndarray, x: int, y: int, rnd: random.Random) -> None:
    h, w = img.shape[:2]
    for dx, dy, col in ((0, 0, TUFT), (-1, -1, TUFT), (1, -1, TUFT), (-2, -2, TUFT_LIGHT), (2, -2, TUFT_LIGHT),
                        (0, -2, TUFT_LIGHT if rnd.random() < 0.5 else TUFT)):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = col


def _flower(img: np.ndarray, x: int, y: int, col: RGBA) -> None:
    h, w = img.shape[:2]
    for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = col
    if 0 <= y < h and 0 <= x < w:
        img[y, x] = _c("#ffcf3a") if col != FLOWERS[1] else _c("#e07a2a")


def _pebble(img: np.ndarray, x: int, y: int) -> None:
    h, w = img.shape[:2]
    for dx, dy, col in ((0, 0, _c("#c9c0b0")), (1, 0, _c("#c9c0b0")), (0, 1, _c("#8f8478")), (1, 1, _c("#8f8478"))):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = col


def _sparkle(img: np.ndarray, x: int, y: int) -> None:
    h, w = img.shape[:2]
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = FOAM if (dx, dy) == (0, 0) else WATER_LIGHT


# --- objects, animals and people (painted at art size, shown at 2x) -----------------------------

from .chibi import Fig  # noqa: E402  (a small numpy canvas with an outline pass)

WOOD, WOOD_DARK, WOOD_LIGHT = _c("#9a5e36"), _c("#6e3e24"), _c("#c07e4a")
PLANK, PLANK_DARK, PLANK_LIGHT = _c("#f0d8b0"), _c("#cfae82"), _c("#fff0d0")
STONE, STONE_DARK, STONE_LIGHT = _c("#a8a8b8"), _c("#6e6e82"), _c("#d4d4e0")
GLASS, GLASS_LIGHT = _c("#7fd0f0"), _c("#d8f6ff")
LEAF, LEAF_DARK, LEAF_LIGHT, LEAF_DEEP = _c("#5cb84a"), _c("#3e8e3c"), _c("#8ad860"), _c("#2c6a38")
WHITE, BLACK = _c("#fffaf0"), _c("#2a1e2e")
SKIN, SKIN_DARK = _c("#f6c9a4"), _c("#d89c78")


def _out(g: Fig) -> None:
    """A dark outline around the solid pixels (soft shadows on the ground are left alone)."""
    a = g.px[..., 3] == 255
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    g.px[ring] = OUTLINE


def _ramp(color: str) -> tuple[RGBA, RGBA, RGBA]:
    """(shadow, base, light) of a colour."""
    r, g, b, _ = _c(color)
    dark = (int(r * 0.68), int(g * 0.62), int(b * 0.7), 255)
    light = (min(255, int(r + (255 - r) * 0.35)), min(255, int(g + (255 - g) * 0.35)), min(255, int(b + (255 - b) * 0.3)), 255)
    return dark, (r, g, b, 255), light


def paint_farmhouse(g: Fig, color: str, anim: str, i: int) -> None:
    roof_d, roof, roof_l = _ramp(color)
    # chimney behind the roof
    g.rect(58, 4, 66, 26, STONE)
    g.rect(58, 4, 66, 6, STONE_DARK)
    for y in range(9, 26, 4):
        g.rect(58, y, 66, y, STONE_DARK)
        g.set(62 if (y // 4) % 2 else 60, y + 2, STONE_DARK)
    g.rect(57, 2, 67, 4, STONE_LIGHT)
    # walls with planks
    g.rect(6, 34, 73, 66, PLANK)
    for y in range(37, 66, 4):
        g.rect(6, y, 73, y, PLANK_DARK)
    g.rect(6, 34, 8, 66, WOOD)
    g.rect(71, 34, 73, 66, WOOD)
    g.rect(6, 64, 73, 66, WOOD_DARK)
    # the roof: a gable, shingle rows, a trim and a ridge cap
    g.poly([(40, 1), (0, 36), (80, 36)], roof)
    for k, y in enumerate(range(8, 36, 5)):
        half = (y - 1) * 40 / 35
        g.rect(40 - half, y, 40 + half, y, roof_d)
        off = 2 if k % 2 else 0
        for x in range(int(40 - half) + off, int(40 + half), 5):
            g.set(x, y + 1, roof_d)
            g.set(x, y + 2, roof_d)
    for y in range(2, 36):
        half = (y - 1) * 40 / 35
        g.set(40 - half, y, roof_l)
        g.set(40 - half + 1, y, roof_l)
    g.rect(0, 35, 80, 37, WOOD_DARK)
    g.rect(37, 0, 43, 3, roof_d)
    # gable window
    g.ellipse(40, 22, 5, 5, WOOD)
    g.ellipse(40, 22, 3.5, 3.5, GLASS)
    g.rect(40, 18, 40, 26, WOOD)
    g.rect(36, 22, 44, 22, WOOD)
    g.set(38, 20, GLASS_LIGHT)
    # door and step
    g.rect(33, 44, 46, 65, WOOD_DARK)
    g.rect(34, 45, 45, 65, WOOD)
    g.rect(35, 47, 39, 54, WOOD_LIGHT)
    g.rect(40, 47, 44, 54, WOOD_LIGHT)
    g.rect(35, 57, 39, 63, WOOD_DARK)
    g.rect(40, 57, 44, 63, WOOD_DARK)
    g.rect(43, 55, 44, 56, _c("#ffd84a"))
    g.rect(31, 66, 48, 69, STONE)
    g.rect(31, 68, 48, 69, STONE_DARK)
    # windows with a flower box
    for x0 in (13, 54):
        g.rect(x0 - 1, 42, x0 + 13, 54, WOOD_DARK)
        g.rect(x0, 43, x0 + 12, 53, GLASS)
        g.rect(x0 + 6, 43, x0 + 6, 53, WOOD)
        g.rect(x0, 48, x0 + 12, 48, WOOD)
        g.rect(x0 + 1, 44, x0 + 3, 45, GLASS_LIGHT)
        g.rect(x0 - 2, 55, x0 + 14, 57, WOOD)
        for k, fx in enumerate(range(x0, x0 + 13, 3)):
            g.set(fx, 54, FLOWERS[(k + x0) % len(FLOWERS)])
            g.set(fx + 1, 54, LEAF)
    _out(g)


def paint_coop(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.poly([(20, 2), (0, 16), (40, 16)], d)
    for y in range(6, 16, 3):
        half = (y - 2) * 20 / 14
        g.rect(20 - half, y, 20 + half, y, _ramp(color)[0])
    g.rect(3, 15, 36, 34, b)
    for x in range(6, 36, 4):
        g.rect(x, 16, x, 34, d)
    g.rect(3, 15, 36, 17, WOOD_DARK)
    g.rect(15, 22, 24, 34, BLACK)
    g.rect(16, 23, 23, 34, _c("#3a2a30"))
    g.poly([(14, 34), (25, 34), (30, 39), (9, 39)], WOOD)
    g.rect(10, 36, 29, 36, WOOD_DARK)
    g.rect(26, 20, 32, 25, GLASS)
    _out(g)


def _fence_post(g: Fig, x: int, y: int) -> None:
    g.rect(x, y, x + 3, y + 10, WOOD)
    g.rect(x + 3, y + 1, x + 3, y + 10, WOOD_DARK)
    g.rect(x, y, x + 3, y, WOOD_LIGHT)
    g.set(x + 1, y + 1, _c("#ffb050"))


def paint_fence_h(g: Fig, color: str, anim: str, i: int) -> None:
    g.rect(0, 6, 15, 7, WOOD)
    g.rect(0, 10, 15, 11, WOOD)
    g.rect(0, 7, 15, 7, WOOD_DARK)
    g.rect(0, 11, 15, 11, WOOD_DARK)
    _fence_post(g, 6, 3)
    _out(g)


def paint_fence_v(g: Fig, color: str, anim: str, i: int) -> None:
    g.rect(6, 0, 7, 15, WOOD)
    g.rect(7, 0, 7, 15, WOOD_DARK)
    _fence_post(g, 5, 3)
    _out(g)


def paint_fence_post(g: Fig, color: str, anim: str, i: int) -> None:
    _fence_post(g, 6, 3)
    _out(g)


def _canopy(g: Fig, cx: float, cy: float, r: float, base: RGBA, dark: RGBA, light: RGBA, rnd: random.Random,
            sway: int = 0) -> None:
    """A round, lumpy tree crown: overlapping blobs, a shaded underside, lit leaf clusters."""
    blobs = [(cx + sway, cy - r * 0.35, r * 0.75), (cx - r * 0.5 + sway, cy, r * 0.62), (cx + r * 0.5 + sway, cy, r * 0.62),
             (cx + sway, cy + r * 0.25, r * 0.7)]
    for bx, by, br in blobs:
        g.ellipse(bx, by + 1, br, br * 0.9, dark)
    for bx, by, br in blobs:
        g.ellipse(bx, by - 1, br * 0.92, br * 0.82, base)
    for _ in range(int(r * 1.6)):  # little lit leaf clumps toward the top-left
        a = rnd.random() * 3.14
        lx, ly = cx - r * 0.55 * abs(np.cos(a)) + rnd.random() * r * 0.6 + sway, cy - r * 0.7 + rnd.random() * r * 0.8
        g.ellipse(lx, ly, 1.6, 1.2, light)
    for _ in range(int(r)):  # dark leaf notches
        g.set(cx - r + rnd.random() * r * 2 + sway, cy - r * 0.2 + rnd.random() * r * 0.9, dark)


def _trunk(g: Fig, x: int, top: int, bottom: int) -> None:
    g.ellipse(x, bottom, 7, 2, _c("#2c5a30", 120))  # shadow on the grass
    g.rect(x - 3, top, x + 2, bottom - 1, WOOD)
    g.rect(x + 1, top, x + 2, bottom - 1, WOOD_DARK)
    g.rect(x - 3, top, x - 3, bottom - 1, WOOD_LIGHT)
    g.poly([(x - 6, bottom), (x - 3, bottom - 4), (x - 2, bottom)], WOOD)  # roots
    g.poly([(x + 6, bottom), (x + 2, bottom - 4), (x + 1, bottom)], WOOD_DARK)


def paint_tree(g: Fig, color: str, anim: str, i: int, kind: str = "oak", seed: int = 0) -> None:
    rnd = _rng("tree", kind, seed)
    sway = (0, 0, 1, 0)[i % 4] if anim == "idle" else 0
    w = g.w
    cx = w // 2
    if kind == "pine":
        _trunk(g, cx, 30, 39)
        d, b, l = _ramp(color)
        for k, (y, half) in enumerate(((4, 4), (10, 7), (17, 10), (24, 12))):
            g.poly([(cx + sway, y - 4), (cx - half - 1 + sway * (k < 2), y + 7), (cx + half + 1 + sway * (k < 2), y + 7)], d)
            g.poly([(cx + sway, y - 4), (cx - half + sway * (k < 2), y + 6), (cx + half - 2 + sway * (k < 2), y + 6)], b)
            g.line(cx - 1 + sway, y - 2, cx - half + 2, y + 5, l)
        _out(g)
        return
    _trunk(g, cx, 24, 39)
    if kind == "blossom":
        d, b, l = _ramp(color)
    else:
        d, b, l = _ramp(color)
    _canopy(g, cx, 15, 14, b, d, l, rnd, sway)
    if kind == "fruit":
        fruit = _ramp(FRUIT_COLORS[seed % len(FRUIT_COLORS)])
        for _ in range(7):
            fx, fy = cx - 10 + rnd.random() * 20 + sway, 8 + rnd.random() * 14
            g.ellipse(fx, fy, 1.6, 1.6, fruit[1])
            g.set(fx - 0.5, fy - 0.5, fruit[2])
    if kind == "blossom":
        for _ in range(12):
            g.set(cx - 12 + rnd.random() * 24 + sway, 4 + rnd.random() * 20, WHITE)
    _out(g)


FRUIT_COLORS = ["#ff9a2a", "#e83a3a", "#ffd84a"]


def paint_stump(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(8, 13, 7, 2.2, _c("#2c5a30", 110))
    g.rect(3, 6, 12, 12, WOOD)
    g.rect(10, 6, 12, 12, WOOD_DARK)
    g.ellipse(7.5, 6, 5, 2.4, _c("#e0b47a"))
    g.ellipse(7.5, 6, 2.5, 1.2, _c("#c08a52"))
    g.poly([(1, 13), (4, 9), (5, 13)], WOOD)
    g.poly([(14, 13), (11, 9), (10, 13)], WOOD_DARK)
    _out(g)


def paint_boulder(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.ellipse(8, 13, 7, 2, _c("#2c5a30", 110))
    g.ellipse(8, 9, 7, 5.5, d)
    g.ellipse(7.5, 8, 6.4, 4.8, b)
    g.ellipse(6, 6.5, 3, 2, l)
    g.set(10, 10, d)
    g.set(11, 9, d)
    _out(g)


def paint_bin(g: Fig, color: str, anim: str, i: int) -> None:
    open_ = anim == "idle" and i == 1
    g.ellipse(8, 15, 8, 1.6, _c("#2c5a30", 110))
    g.rect(1, 6, 14, 14, WOOD)
    for y in (8, 11):
        g.rect(1, y, 14, y, WOOD_DARK)
    g.rect(1, 6, 1, 14, WOOD_LIGHT)
    g.rect(13, 6, 14, 14, WOOD_DARK)
    if open_:
        g.rect(0, 1, 15, 4, WOOD_LIGHT)
        g.rect(2, 5, 13, 6, BLACK)
    else:
        g.rect(0, 3, 15, 6, WOOD_LIGHT)
        g.rect(0, 6, 15, 6, WOOD_DARK)
    g.rect(6, 8, 9, 10, _c("#ffd84a"))
    _out(g)


def paint_well(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.poly([(12, 0), (0, 8), (24, 8)], b)
    g.rect(0, 8, 24, 9, d)
    g.rect(3, 9, 4, 22, WOOD)
    g.rect(19, 9, 20, 22, WOOD_DARK)
    g.rect(10, 9, 13, 14, WOOD_LIGHT)  # bucket rope + bucket
    g.rect(11, 9, 11, 12, WHITE)
    g.ellipse(12, 23, 10, 4, STONE_DARK)
    g.rect(2, 20, 22, 28, STONE)
    for x in range(4, 22, 5):
        g.rect(x, 21, x, 28, STONE_DARK)
    g.rect(2, 24, 22, 24, STONE_DARK)
    g.ellipse(12, 20, 10, 3.2, STONE_LIGHT)
    g.ellipse(12, 20, 8, 2.2, _c("#1f5a9a"))
    _out(g)


def paint_scarecrow(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    tilt = (0, 1, 0, -1)[i % 4] if anim == "idle" else 0
    g.rect(7, 10, 8, 23, WOOD)
    g.rect(1, 11, 14, 12, WOOD)
    g.rect(4, 10 + tilt, 11, 17, b)  # shirt
    g.rect(4, 15, 11, 15, d)
    g.ellipse(7.5, 6, 3.8, 3.8, _c("#f0d79a"))  # sack head
    g.set(6, 6, BLACK)
    g.set(9, 6, BLACK)
    g.rect(6, 8, 9, 8, WOOD_DARK)
    g.poly([(1, 4), (14, 4), (11, 0), (4, 0)], _c("#d8a84a"))  # straw hat
    g.rect(0, 4, 15, 4, _c("#b88a3a"))
    g.rect(1, 13, 2, 15, _c("#f0d79a"))
    g.rect(13, 13, 14, 15, _c("#f0d79a"))
    _out(g)


def paint_hay(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(8, 14, 8, 1.8, _c("#2c5a30", 110))
    g.rect(1, 4, 14, 13, _c("#e8c25a"))
    g.rect(1, 4, 14, 5, _c("#f8de8a"))
    g.rect(1, 12, 14, 13, _c("#b8902e"))
    for x in (5, 10):
        g.rect(x, 4, x, 13, _c("#9a6a2a"))
    for k in range(6):
        g.set(2 + k * 2, 7 + (k % 3), _c("#b8902e"))
    _out(g)


def paint_barrel(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(8, 15, 7, 1.6, _c("#2c5a30", 110))
    g.rect(2, 3, 13, 14, WOOD)
    g.rect(2, 3, 3, 14, WOOD_LIGHT)
    g.rect(11, 3, 13, 14, WOOD_DARK)
    for y in (5, 11):
        g.rect(2, y, 13, y, STONE_DARK)
    g.ellipse(7.5, 3, 5.5, 1.6, WOOD_DARK)
    _out(g)


def paint_sign(g: Fig, color: str, anim: str, i: int) -> None:
    g.rect(7, 8, 8, 15, WOOD_DARK)
    g.rect(1, 2, 14, 9, WOOD)
    g.rect(1, 2, 14, 2, WOOD_LIGHT)
    g.rect(1, 9, 14, 9, WOOD_DARK)
    g.rect(4, 5, 11, 5, WOOD_DARK)
    g.rect(4, 7, 9, 7, WOOD_DARK)
    _out(g)


def paint_flower_bush(g: Fig, color: str, anim: str, i: int) -> None:
    rnd = _rng("bush", color)
    g.ellipse(8, 13, 7, 1.6, _c("#2c5a30", 110))
    g.ellipse(8, 9, 7, 5, LEAF_DARK)
    g.ellipse(7.5, 8, 6.4, 4.4, LEAF)
    g.ellipse(6, 6.5, 2.5, 1.5, LEAF_LIGHT)
    d, b, l = _ramp(color)
    for _ in range(5):
        fx, fy = 2 + rnd.random() * 11, 5 + rnd.random() * 6
        g.set(fx, fy, b)
        g.set(fx + 1, fy, l)
    _out(g)


# animals ------------------------------------------------------------------------------------------

def paint_chicken(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    k = i % 4
    peck = anim == "idle" and i % 2 == 1
    hop = (0, 1, 0, 1)[k] if anim == "run" else 0
    g.ellipse(8, 15, 5, 1.2, _c("#2c5a30", 110))
    g.rect(6, 12, 6, 14, _c("#f0a030"))  # legs
    g.rect(9, 12 + (hop if anim == "run" else 0), 9, 14, _c("#f0a030"))
    g.ellipse(7, 9 - hop, 5.4, 4, b)  # body
    g.ellipse(3, 7 - hop, 2.4, 2.8, d)  # tail
    g.ellipse(6, 10 - hop, 3.4, 2.2, d)  # wing
    g.rect(5, 9 - hop, 8, 9 - hop, l)
    hx, hy = (12, 7 - hop) if not peck else (13, 10 - hop)
    g.ellipse(hx, hy - 1, 2.6, 2.6, b)
    g.rect(hx - 1, hy - 4, hx, hy - 3, _c("#e83a3a"))  # comb
    g.set(hx + 2, hy - 1, _c("#f0a030"))
    g.set(hx + 3, hy - 1, _c("#f0a030"))
    g.set(hx + 1, hy - 2, BLACK)
    g.set(hx + 1, hy, _c("#e83a3a"))
    _out(g)


def paint_chick(g: Fig, color: str, anim: str, i: int) -> None:
    hop = (0, 1)[i % 2] if anim == "run" else 0
    g.ellipse(6, 10, 3.5, 1, _c("#2c5a30", 110))
    g.ellipse(5.5, 7 - hop, 3.6, 3, _c("#ffd84a"))
    g.ellipse(7.5, 4.5 - hop, 2.4, 2.2, _c("#ffd84a"))
    g.ellipse(4.5, 7 - hop, 1.8, 1.2, _c("#f0b830"))
    g.set(8, 4 - hop, BLACK)
    g.set(10, 5 - hop, _c("#f08a20"))
    g.rect(4, 9, 4, 10, _c("#f08a20"))
    g.rect(7, 9, 7, 10, _c("#f08a20"))
    _out(g)


def paint_cow(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    k = i % 4
    step = ((1, -1), (0, 0), (-1, 1), (0, 0))[k] if anim == "run" else (0, 0)
    chew = anim == "idle" and i % 2 == 1
    g.ellipse(16, 23, 12, 1.6, _c("#2c5a30", 110))
    for x, s, col in ((7, step[0], _c("#e8e0d8")), (11, step[1], _c("#d8d0c8")), (20, step[1], _c("#e8e0d8")), (24, step[0], _c("#d8d0c8"))):
        g.rect(x + s, 16, x + 1 + s, 21, col)
        g.rect(x + s, 21, x + 1 + s, 22, BLACK)
    g.ellipse(15, 12, 11, 6, WHITE)  # body
    g.ellipse(11, 10, 4, 3, b)  # patches in the coat colour
    g.ellipse(19, 14, 3.4, 2.4, b)
    g.ellipse(16, 8, 2, 1.4, b)
    g.ellipse(14, 17, 2.5, 1, _c("#ffb0b8"))  # udder
    g.line(4, 10, 2, 15, d)  # tail
    g.set(2, 16, b)
    hy = 9 + (1 if chew else 0)
    g.ellipse(26, hy, 4.4, 4, WHITE)  # head
    g.ellipse(25, hy - 2, 2.2, 1.6, b)
    g.ellipse(28.5, hy + 2, 2.6, 2, _c("#ffb0b8"))  # muzzle
    g.set(28, hy + 2, d)
    g.set(30, hy + 2, d)
    g.set(26, hy - 1, BLACK)
    g.rect(22, hy - 4, 23, hy - 3, _c("#f0e6c8"))  # horns
    g.rect(28, hy - 5, 29, hy - 4, _c("#f0e6c8"))
    g.rect(21, hy - 2, 22, hy - 1, b)  # ear
    _out(g)


# the farmer: four directions -------------------------------------------------------------------

FARMER_W, FARMER_H = 16, 24


def paint_farmer(g: Fig, color: str, anim: str, i: int, facing: str = "down", hair: RGBA = _c("#4a2e22")) -> None:
    """A 16x24 top-down farmer in the classic RPG grid: down, up and side (the side faces right; the
    game flips it for left). `color` is the shirt; the trousers are denim and the hat is straw."""
    sh_d, sh, sh_l = _ramp(color)
    pants, pants_d = _c("#3a5aa0"), _c("#2a4078")
    k = i % 4
    walking = anim.startswith("run")
    bob = (0, 1, 0, 1)[k] if walking else (0, 0, 0, 1)[i % 4] if anim.startswith("idle") else 0
    legs = ((1, -1), (0, 0), (-1, 1), (0, 0))[k] if walking else (0, 0)
    g.ellipse(8, 23, 5, 1.2, _c("#2c5a30", 110))
    # legs and boots
    if facing == "side":
        g.rect(6 + legs[0], 17, 7 + legs[0], 21, pants_d)
        g.rect(8 + legs[1], 17, 9 + legs[1], 21, pants)
        g.rect(6 + legs[0], 21, 8 + legs[0], 22, WOOD_DARK)
        g.rect(8 + legs[1], 21, 10 + legs[1], 22, WOOD_DARK)
    else:
        g.rect(5, 17, 7, 21 - max(0, legs[0]), pants)
        g.rect(9, 17, 11, 21 - max(0, legs[1]), pants_d)
        g.rect(5, 21 - max(0, legs[0]), 7, 22 - max(0, legs[0]), WOOD_DARK)
        g.rect(9, 21 - max(0, legs[1]), 11, 22 - max(0, legs[1]), WOOD_DARK)
    # body
    top = 11 + bob
    g.rect(4, top, 11, 17, sh)
    g.rect(4, 16, 11, 17, pants)  # overall bib bottom
    if facing == "down":
        g.rect(6, top + 1, 9, 17, pants)  # overall bib
        g.set(6, top + 1, _c("#ffd84a"))
        g.set(9, top + 1, _c("#ffd84a"))
        g.rect(4, top, 4, 15, sh_l)
    elif facing == "up":
        g.rect(5, top + 1, 5, 16, pants)
        g.rect(10, top + 1, 10, 16, pants)
    else:
        g.rect(9, top + 1, 11, 16, pants)
    # arms swing opposite the legs
    sw = legs[0]
    if facing == "side":
        g.rect(6 - sw, top + 1, 8 - sw, top + 5, sh_d)
        g.rect(6 - sw, top + 5, 8 - sw, top + 6, SKIN)
    else:
        g.rect(2, top + 1 + max(0, sw), 3, top + 5 + max(0, sw), sh_d)
        g.rect(12, top + 1 + max(0, -sw), 13, top + 5 + max(0, -sw), sh_d)
        g.rect(2, top + 5 + max(0, sw), 3, top + 6 + max(0, sw), SKIN)
        g.rect(12, top + 5 + max(0, -sw), 13, top + 6 + max(0, -sw), SKIN)
    # head
    hy = 2 + bob
    g.rect(3, hy + 2, 12, hy + 9, SKIN)
    if facing == "down":
        g.rect(3, hy + 2, 12, hy + 4, hair)
        g.rect(3, hy + 2, 4, hy + 6, hair)
        g.rect(11, hy + 2, 12, hy + 6, hair)
        blink = anim.startswith("idle") and i % 4 == 3
        for ex in (5, 9):
            if blink:
                g.rect(ex, hy + 7, ex + 1, hy + 7, BLACK)
            else:
                g.rect(ex, hy + 6, ex, hy + 7, BLACK)
                g.set(ex + 1, hy + 6, WHITE)
        g.set(4, hy + 8, _c("#f0a0a0"))
        g.set(11, hy + 8, _c("#f0a0a0"))
    elif facing == "up":
        g.rect(3, hy + 2, 12, hy + 9, hair)
        g.rect(4, hy + 8, 11, hy + 9, _c("#3a2418"))
    else:
        g.rect(3, hy + 2, 12, hy + 4, hair)
        g.rect(3, hy + 2, 7, hy + 8, hair)
        g.rect(10, hy + 6, 10, hy + 7, BLACK)
        g.set(11, hy + 6, WHITE)
        g.set(12, hy + 7, SKIN_DARK)
    # straw hat
    g.rect(1, hy + 2, 14, hy + 3, _c("#e8c25a"))
    g.rect(4, hy - 1, 11, hy + 2, _c("#f2d27a"))
    g.rect(4, hy + 1, 11, hy + 1, _c("#c84a3a"))  # hat band
    g.rect(1, hy + 3, 14, hy + 3, _c("#b8902e"))
    _out(g)


# crops -----------------------------------------------------------------------------------------

CROP_KINDS = ("strawberry", "potato", "carrot", "tomato", "pumpkin", "corn", "cabbage", "wheat", "onion", "eggplant",
              "blueberry", "turnip", "berry")
CROP_WORDS = {"strawberry": "strawberry", "strawberries": "strawberry", "potato": "potato", "potatoes": "potato",
              "carrot": "carrot", "tomato": "tomato", "pumpkin": "pumpkin", "corn": "corn", "maize": "corn",
              "cabbage": "cabbage", "lettuce": "cabbage", "cauliflower": "cabbage", "wheat": "wheat", "rice": "wheat",
              "onion": "onion", "leek": "onion", "garlic": "onion", "eggplant": "eggplant", "aubergine": "eggplant",
              "blueberry": "blueberry", "grape": "blueberry", "turnip": "turnip", "radish": "turnip", "beet": "turnip",
              "melon": "pumpkin", "watermelon": "pumpkin", "pepper": "tomato", "chili": "tomato", "pea": "berry",
              "bean": "berry", "berry": "berry", "sunflower": "wheat", "flower": "berry"}


def crop_kind(name: str) -> str:
    import re
    for w in reversed([w.lower() for w in re.findall(r"[A-Z][a-z]*|[a-z]+", name)]):
        if w in CROP_WORDS:
            return CROP_WORDS[w]
        if w.rstrip("s") in CROP_WORDS:
            return CROP_WORDS[w.rstrip("s")]
    return "berry"


def _sprout(g: Fig, h: int) -> None:
    g.rect(7, 14 - h, 8, 14, LEAF_DARK)
    g.ellipse(5.5, 13 - h, 2, 1.2, LEAF)
    g.ellipse(9.5, 12 - h, 2, 1.2, LEAF_LIGHT)


def paint_crop(g: Fig, kind: str, color: str, stage: int) -> None:
    """One growth stage (0 seeds .. 4 ripe) of a crop, standing on a 16x16 soil tile."""
    d, b, l = _ramp(color)
    if stage == 0:  # seeds in the furrow
        for x in (4, 8, 11):
            g.rect(x, 11, x + 1, 11, _c("#e8d2a0"))
        return
    if stage == 1:
        _sprout(g, 2)
        return
    tall = kind in ("corn", "wheat")
    if kind == "corn":
        hgt = (6, 10, 13)[stage - 2]
        g.rect(7, 15 - hgt, 8, 15, LEAF_DARK)
        for y in range(15 - hgt + 2, 15, 3):
            g.line(8, y, 12, y - 2, LEAF)
            g.line(7, y + 1, 3, y - 1, LEAF_LIGHT)
        if stage == 4:
            g.ellipse(10, 15 - hgt + 4, 1.6, 3, b)
            g.set(10, 15 - hgt + 1, LEAF_LIGHT)
        return
    if kind == "wheat":
        hgt = (5, 8, 11)[stage - 2]
        for x in (4, 7, 10, 12):
            col = (b if stage == 4 else LEAF)
            g.rect(x, 15 - hgt, x, 15, LEAF_DARK if stage < 4 else d)
            g.rect(x - 1 if x > 4 else x, 15 - hgt, x, 15 - hgt + 3, col)
        return
    if stage == 2:
        g.ellipse(8, 11, 4, 2.4, LEAF)
        g.rect(7, 9, 8, 13, LEAF_DARK)
        g.ellipse(6, 10, 1.6, 1, LEAF_LIGHT)
        return
    # a leafy plant
    if kind in ("carrot", "onion", "turnip", "potato"):
        g.line(8, 13, 5, 5, LEAF_DARK)
        g.line(8, 13, 8, 4, LEAF)
        g.line(8, 13, 11, 5, LEAF)
        g.ellipse(5, 6, 1.5, 1.5, LEAF_LIGHT)
        g.ellipse(11, 6, 1.5, 1.5, LEAF_LIGHT)
        if stage == 4:
            if kind == "carrot":
                g.poly([(5, 12), (11, 12), (8, 16)], b)
                g.rect(6, 12, 10, 12, l)
            elif kind == "onion":
                g.ellipse(8, 13, 3, 2.2, _c("#f4ece0"))
                g.set(7, 12, WHITE)
            elif kind == "turnip":
                g.ellipse(8, 13, 3, 2.4, b)
                g.ellipse(8, 11.5, 2.4, 1.2, WHITE)
            else:
                g.ellipse(5, 13, 2.2, 1.6, _c("#b8885a"))
                g.ellipse(11, 13.5, 2.2, 1.6, _c("#a87a4a"))
        return
    if kind in ("cabbage",):
        g.ellipse(8, 11, 5.4, 4, LEAF_DARK)
        g.ellipse(8, 10.5, 4.6, 3.4, LEAF)
        if stage == 4:
            g.ellipse(8, 10, 3.2, 2.6, _c("#c8f0a0"))
            g.rect(7, 9, 8, 11, LEAF_LIGHT)
        return
    if kind == "pumpkin":
        g.line(3, 10, 13, 10, LEAF_DARK)
        g.ellipse(4, 8, 2.4, 1.8, LEAF)
        g.ellipse(12, 8, 2.4, 1.8, LEAF)
        if stage == 4:
            g.ellipse(8, 11, 5, 3.6, b)
            g.rect(7, 8, 8, 14, d)
            g.rect(4, 10, 4, 12, d)
            g.rect(11, 10, 11, 12, d)
            g.ellipse(6, 10, 1.4, 1, l)
            g.rect(7, 6, 8, 7, LEAF_DARK)
        else:
            g.ellipse(8, 11, 2, 1.6, LEAF_LIGHT)
        return
    # bushes and vines with fruit: strawberry, tomato, eggplant, blueberry, berry
    g.ellipse(8, 10, 5.5, 4.4, LEAF_DARK)
    g.ellipse(8, 9.5, 4.8, 3.8, LEAF)
    g.ellipse(6, 8, 2, 1.4, LEAF_LIGHT)
    if kind == "tomato":
        g.rect(7, 3, 8, 14, WOOD)  # a stake
    if stage == 4:
        spots = [(5, 11), (10, 10), (8, 7), (11, 13), (4, 8)]
        for fx, fy in spots[: (3 if kind in ("eggplant", "tomato") else 5)]:
            if kind == "eggplant":
                g.ellipse(fx, fy + 1, 1.4, 2.2, b)
            else:
                g.ellipse(fx, fy, 1.5, 1.5, b)
            g.set(fx - 0.6, fy - 0.6, l)
            if kind == "strawberry":
                g.set(fx, fy - 2, LEAF_LIGHT)
    else:
        g.set(5, 11, WHITE)
        g.set(10, 9, WHITE)


def crop_sheet(name: str, color: str) -> np.ndarray:
    """Five 16x16 growth stages side by side (seeds, sprout, young, grown, ripe), transparent background, outlined."""
    kind = crop_kind(name)
    out = np.zeros((CELL, CELL * 5, 4), dtype=np.uint8)
    for stage in range(5):
        g = Fig(CELL, CELL)
        paint_crop(g, kind, color, stage)
        if stage > 0:
            _outline_dark(g)
        out[:, stage * CELL:(stage + 1) * CELL] = g.px
    return out


def _outline_dark(g: Fig, col: RGBA = _c("#1e3a24")) -> None:
    a = g.px[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    g.px[ring] = col


def soil_tile(wet: bool) -> np.ndarray:
    """A 16x16 tilled patch: rounded, with furrows; darker when watered."""
    base, dark, light = (_c("#6a3e24"), _c("#4a2a18"), _c("#7e4c2c")) if wet else (_c("#9a6238"), _c("#74462a"), _c("#b47a48"))
    g = Fig(CELL, CELL)
    g.rect(1, 1, 14, 14, base)
    for p in ((1, 1), (14, 1), (1, 14), (14, 14)):
        g.px[p[1], p[0]] = (0, 0, 0, 0)
    for y in (4, 8, 12):
        g.rect(2, y, 13, y, dark)
        g.rect(2, y - 1, 13, y - 1, light)
    g.rect(1, 14, 14, 14, dark)
    return g.px


def crop_icon(name: str, color: str) -> np.ndarray:
    """A 16x16 produce icon (the harvested crop) with a light outline, for the hotbar and pop-ups."""
    kind = crop_kind(name)
    d, b, l = _ramp(color)
    g = Fig(CELL, CELL)
    if kind == "carrot":
        g.poly([(4, 5), (11, 5), (8, 15)], b)
        g.rect(5, 6, 9, 6, l)
        g.line(7, 5, 5, 1, LEAF)
        g.line(8, 5, 10, 1, LEAF_DARK)
    elif kind == "corn":
        g.ellipse(8, 8, 3, 6, b)
        g.rect(7, 3, 7, 13, l)
        g.poly([(3, 15), (6, 6), (8, 15)], LEAF)
        g.poly([(13, 15), (10, 6), (8, 15)], LEAF_DARK)
    elif kind == "wheat":
        for x in (5, 8, 11):
            g.line(x, 14, 8, 6, d)
            g.ellipse(x, 5, 1.4, 3, b)
    elif kind == "pumpkin":
        g.ellipse(8, 9, 6.5, 5, b)
        for x in (5, 8, 11):
            g.rect(x, 5, x, 13, d)
        g.ellipse(6, 7, 1.6, 1.2, l)
        g.rect(7, 2, 8, 4, LEAF_DARK)
    elif kind == "cabbage":
        g.ellipse(8, 9, 6, 5, LEAF)
        g.ellipse(8, 8, 3.6, 3, _c("#c8f0a0"))
        g.line(8, 5, 8, 13, LEAF_DARK)
    elif kind == "onion":
        g.ellipse(8, 10, 4.4, 4, _c("#f4ece0"))
        g.line(8, 6, 6, 1, LEAF)
        g.line(8, 6, 10, 1, LEAF_DARK)
        g.set(6, 9, WHITE)
    elif kind in ("potato",):
        g.ellipse(8, 9, 5.4, 4, _c("#c8986a"))
        g.set(6, 8, _c("#8a6040"))
        g.set(10, 10, _c("#8a6040"))
        g.ellipse(6, 7, 1.4, 1, _c("#e0b888"))
    elif kind == "eggplant":
        g.ellipse(8, 10, 3.6, 5, b)
        g.rect(6, 3, 10, 5, LEAF)
        g.ellipse(7, 8, 1, 1.6, l)
    elif kind == "turnip":
        g.ellipse(8, 10, 4.6, 4, b)
        g.ellipse(8, 8, 3.6, 2, WHITE)
        g.line(8, 6, 6, 1, LEAF)
        g.line(8, 6, 10, 1, LEAF_DARK)
    else:  # strawberry, tomato, berries
        g.ellipse(8, 9.5, 5.4, 5, b)
        g.ellipse(6, 7.5, 1.6, 1.4, l)
        g.rect(6, 3, 10, 4, LEAF)
        g.rect(8, 1, 8, 3, LEAF_DARK)
        if kind == "strawberry":
            for p in ((6, 10), (9, 9), (8, 12), (10, 12)):
                g.set(p[0], p[1], _c("#ffe0a0"))
    _outline_dark(g, _c("#2a1e2e"))
    a = g.px[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    g.px[ring] = WHITE
    return g.px


def item_icon(item: str) -> np.ndarray:
    """16x16 icons for animal products and gathered materials: egg, milk, wood, stone."""
    g = Fig(CELL, CELL)
    if item == "egg":
        g.ellipse(8, 9, 4, 5, _c("#f8f0e0"))
        g.ellipse(6.5, 7, 1.4, 1.8, WHITE)
        g.rect(9, 12, 10, 12, _c("#d8c8b0"))
    elif item == "milk":
        g.rect(5, 5, 10, 14, WHITE)
        g.rect(6, 2, 9, 5, _c("#e8e0d8"))
        g.rect(5, 8, 10, 10, _c("#5a9ae0"))
        g.rect(9, 5, 10, 14, _c("#d8d0c8"))
    elif item == "wood":
        g.rect(2, 6, 13, 10, WOOD)
        g.rect(2, 10, 13, 10, WOOD_DARK)
        g.ellipse(13, 8, 2, 2.4, _c("#e0b47a"))
        g.set(13, 8, _c("#c08a52"))
        g.rect(4, 3, 11, 6, WOOD_LIGHT)
        g.ellipse(11, 4.5, 1.6, 1.8, _c("#e0b47a"))
    else:  # stone
        g.ellipse(8, 9, 5.4, 4.4, STONE)
        g.ellipse(6.5, 7.5, 2.4, 1.6, STONE_LIGHT)
        g.set(10, 11, STONE_DARK)
    _outline_dark(g, _c("#2a1e2e"))
    a = g.px[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    g.px[ring] = WHITE
    return g.px


# --- the farm sprite kinds (generate.py routes these here) ---------------------------------------

def _tree(kind: str):
    return lambda g, color, anim, i, seed=0: paint_tree(g, color, anim, i, kind=kind, seed=seed)


def _farmer(g: Fig, color: str, anim: str, i: int, seed: int = 0) -> None:
    hair = [_c("#4a2e22"), _c("#2b2230"), _c("#e8c060"), _c("#b84a2a")][seed % 4]
    name, _, facing = anim.partition("_")
    paint_farmer(g, color, name if name in ("idle", "run") else "idle", i, facing=facing or "down", hair=hair)


# kind -> (size, {anim: (frames, fps, loop)}, painter, default colour)
SPRITES: dict[str, tuple[tuple[int, int], dict[str, tuple[int, float, bool]], object, str]] = {
    "farmhouse": ((80, 72), {"idle": (1, 1, False)}, paint_farmhouse, "#b4472e"),
    "coop": ((40, 40), {"idle": (1, 1, False)}, paint_coop, "#c0503a"),
    "tree_oak": ((32, 40), {"idle": (4, 2, True)}, _tree("oak"), "#5cb84a"),
    "tree_fruit": ((32, 40), {"idle": (4, 2, True)}, _tree("fruit"), "#5cb84a"),
    "tree_blossom": ((32, 40), {"idle": (4, 2, True)}, _tree("blossom"), "#ffa8c8"),
    "tree_pine": ((24, 40), {"idle": (4, 2, True)}, _tree("pine"), "#2f8a5a"),
    "well": ((24, 30), {"idle": (1, 1, False)}, paint_well, "#b4472e"),
    "scarecrow": ((16, 24), {"idle": (4, 2, True)}, paint_scarecrow, "#4a7ad0"),
    "stump": ((16, 16), {"idle": (1, 1, False)}, paint_stump, "#9a5e36"),
    "boulder": ((16, 16), {"idle": (1, 1, False)}, paint_boulder, "#a8a8b8"),
    "bin": ((16, 16), {"idle": (1, 1, False)}, paint_bin, "#9a5e36"),
    "hay": ((16, 16), {"idle": (1, 1, False)}, paint_hay, "#e8c25a"),
    "barrel": ((16, 16), {"idle": (1, 1, False)}, paint_barrel, "#9a5e36"),
    "signpost": ((16, 16), {"idle": (1, 1, False)}, paint_sign, "#9a5e36"),
    "flower_bush": ((16, 16), {"idle": (1, 1, False)}, paint_flower_bush, "#ff8fb4"),
    "fence_h": ((16, 16), {"idle": (1, 1, False)}, paint_fence_h, "#9a5e36"),
    "fence_v": ((16, 16), {"idle": (1, 1, False)}, paint_fence_v, "#9a5e36"),
    "fence_post": ((16, 16), {"idle": (1, 1, False)}, paint_fence_post, "#9a5e36"),
    "chicken": ((16, 16), {"idle": (2, 2, True), "run": (4, 8, True)}, paint_chicken, "#f4ece0"),
    "chick": ((12, 12), {"idle": (2, 3, True), "run": (2, 8, True)}, paint_chick, "#ffd84a"),
    "cow": ((32, 24), {"idle": (2, 1, True), "run": (4, 6, True)}, paint_cow, "#a0582e"),
    "farmer": ((FARMER_W, FARMER_H), {"idle": (4, 3, True), "run": (4, 8, True), "idle_up": (4, 3, True),
                                       "run_up": (4, 8, True), "idle_side": (4, 3, True), "run_side": (4, 8, True),
                                       "hurt": (1, 1, False)}, _farmer, "#e8503a"),
}


def frames(kind: str, color: str, seed: int = 0) -> dict[str, list[np.ndarray]]:
    """Every animation frame of a farm kind at art size (16 px tiles)."""
    (w, h), anims, painter, _default = SPRITES[kind]
    out: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in anims.items():
        out[anim] = []
        for i in range(n):
            g = Fig(w, h)
            painter(g, color, "idle" if anim == "hurt" else anim, i, **({"seed": seed} if kind.startswith(("tree", "farmer")) else {}))
            if anim == "hurt":  # a light flash of the idle pose
                solid = g.px[..., 3] == 255
                g.px[solid, :3] = (g.px[solid, :3].astype(int) + 255) // 2
            out[anim].append(g.px)
    return out
