"""Cozy farm art: the ground of a whole farm map and the farm's objects, animals and crops, drawn in a
16-pixel tile language and shown at 2 screen pixels per art pixel (one 16 px art tile = one 32 px world tile).

The look: green grass thick with clumps of blades and little flowers, dirt paths with rounded, bumpy edges and a
dark rim, a tilled garden bed under the crop plots, water with pools of deeper blue, a light shore line and sparkles,
and a brown earth edge wherever land meets the water (a cliff face to the south, on islands). Everything is drawn here from code; no image files are read.

    terrain_image(rows, seed)   -> RGBA array of the whole map ground (16 px per cell)
    paint_*(...)                -> the object painters used through generate.py's farm kinds
    crop_sheet(kind, color)     -> the growth stages of one crop (5 frames of 16x16) for FarmPlot
"""

from __future__ import annotations

import colorsys
import math
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
OUTLINE = _c("#1c0a18")

# The ground in each season: grass (snow, sand...), paths, water and what grows on it.
SEASONS: dict[str, dict] = {
    "spring": {"grass": GRASS, "light": GRASS_LIGHT, "dark": GRASS_DARK, "edge": GRASS_EDGE, "tuft": TUFT,
               "tuft_light": TUFT_LIGHT, "dirt": DIRT, "dirt_light": DIRT_LIGHT, "dirt_dark": DIRT_DARK,
               "water": WATER, "deep": WATER_DEEP, "shore": WATER_LIGHT, "foam": FOAM, "flowers": FLOWERS,
               "lilies": True, "mushrooms": True, "tufts": (1, 2, 2, 3), "clumps": (0, 1, 1, 2)},
    "autumn": {"grass": _c("#d8973f"), "light": _c("#e0a148"), "dark": _c("#d08d3a"), "edge": _c("#7a3f22"),
               "tuft": _c("#a8582a"), "tuft_light": _c("#f0b860"), "dirt": _c("#c98a52"), "dirt_light": _c("#dca06a"),
               "dirt_dark": _c("#a86a3a"), "water": WATER, "deep": WATER_DEEP, "shore": WATER_LIGHT, "foam": FOAM,
               "flowers": [_c("#ffd84a"), _c("#e85a3a"), _c("#f8f4ea")], "lilies": False, "mushrooms": True,
               "tufts": (1, 1, 2), "clumps": (0, 1, 1)},
    "winter": {"grass": _c("#e8f0f8"), "light": _c("#f2f7fc"), "dark": _c("#e0e9f4"), "edge": _c("#8a9ec0"),
               "tuft": _c("#b8c8dc"), "tuft_light": _c("#ffffff"), "dirt": _c("#b0a294"), "dirt_light": _c("#c8bcb0"),
               "dirt_dark": _c("#8e7e70"), "water": _c("#8cc8ec"), "deep": _c("#78b4e0"), "shore": _c("#c4e8fa"),
               "foam": _c("#f0faff"), "flowers": [], "lilies": False, "mushrooms": False, "tufts": (0, 1), "clumps": (0, 0, 1),
               "bed": (_c("#a08a7a"), _c("#7e6a5e"), _c("#bca898"))},
    "desert": {"grass": _c("#ecca8a"), "light": _c("#f0d29a"), "dark": _c("#e4c080"), "edge": _c("#a87a44"),
               "tuft": _c("#b8a050"), "tuft_light": _c("#d8c070"), "dirt": _c("#c98458"), "dirt_light": _c("#d89a6c"),
               "dirt_dark": _c("#a8683e"), "water": WATER, "deep": WATER_DEEP, "shore": WATER_LIGHT, "foam": FOAM,
               "flowers": [_c("#ff8fb4"), _c("#ffd84a")], "lilies": True, "mushrooms": False, "tufts": (0, 0, 1),
               "clumps": (0, 0, 1), "bed": (_c("#b4784a"), _c("#8a5434"), _c("#c88e5c"))},
}

BED = (_c("#9a6238"), _c("#74462a"), _c("#b07446"))  # a tilled garden bed: earth, its dark rim, light crumbs

# Terrain characters (one per map cell).
GRASS_C, PATH_C, WATER_C, FIELD_C, SAND_C = ".", ":", "~", ",", "_"
VOID_C, FLOOR_C, WALL_C, RUG_C, MAT_C = " ", "F", "W", "R", "M"  # indoors: darkness, floorboards, wall, rug, door mat
INDOOR = {VOID_C, FLOOR_C, WALL_C, RUG_C, MAT_C}


# --- small helpers ------------------------------------------------------------------------------

def _noise(h: int, w: int, cell: int, rng: np.random.Generator, smooth: float) -> np.ndarray:
    """Low-frequency value noise in 0..1: a coarse random grid, upscaled and blurred."""
    gh, gw = h // cell + 2, w // cell + 2
    grid = rng.random((gh, gw))
    up = np.kron(grid, np.ones((cell, cell)))[:h, :w]
    return _blur(up, smooth)


def _soft_mask(cells: np.ndarray, sigma: float, jitter: np.ndarray, k: float = 0.16) -> np.ndarray:
    """Cell mask -> pixel mask with rounded corners and bumpy edges."""
    up = np.kron(cells.astype(float), np.ones((CELL, CELL)))
    return _blur(up, sigma) > 0.5 + (jitter - 0.5) * k


def _blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur (separable, edges extended), numpy only."""
    r = max(1, int(3 * sigma))
    x = np.arange(-r, r + 1)
    k = np.exp(-(x ** 2) / (2 * sigma * sigma))
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def _erode(m: np.ndarray, n: int) -> np.ndarray:
    """Shrinks m by n pixels (4-neighbourhood); beyond the picture's edge counts as more of the same."""
    for _ in range(n):
        p = np.pad(m, 1, mode="edge")
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def _dilate(m: np.ndarray, n: int) -> np.ndarray:
    for _ in range(n):
        p = np.pad(m, 1, mode="edge")
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return m


def _depth(m: np.ndarray, most: int) -> np.ndarray:
    """How many pixels deep inside m each pixel is (1 at the edge), up to `most`."""
    out = np.zeros(m.shape, dtype=float)
    cur = m.copy()
    for k in range(1, most + 1):
        out[cur] = k
        cur = _erode(cur, 1)
        if not cur.any():
            break
    return out


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

def terrain_image(rows: list[str], seed: int = 0, season: str = "spring") -> np.ndarray:
    """The ground of a farm map, 16 art pixels per cell, in a season (see SEASONS). Unknown characters count as grass."""
    P = SEASONS.get(season, SEASONS["spring"])
    hh, ww = len(rows), max((len(r) for r in rows), default=1)
    grid = np.array([[(r[x] if x < len(r) else GRASS_C) for x in range(ww)] for r in rows])
    H, W = hh * CELL, ww * CELL
    nrng = np.random.default_rng(zlib.crc32(f"terrain:{seed}".encode()))
    jitter = _noise(H, W, 3, nrng, 1.0)
    water = _soft_mask(grid == WATER_C, 4.0, jitter)
    water = _dilate(_erode(water, 2), 2) | (np.kron(grid == WATER_C, np.ones((CELL, CELL), dtype=bool)) & water)
    sand = _soft_mask((grid == SAND_C) | (grid == WATER_C), 4.0, jitter) & ~water
    path = _soft_mask(grid == PATH_C, 4.0, jitter) & ~water & ~sand
    land = ~water
    img = np.zeros((H, W, 4), dtype=np.uint8)

    # grass: two tones in soft patches, specks of darker green
    img[:] = P["grass"]
    patches = _noise(H, W, 24, nrng, 6.0)
    img[patches > 0.64] = P["light"]
    img[patches < 0.32] = P["dark"]
    specks = nrng.random((H, W)) < 0.012
    img[specks & land] = P["dark"]

    # tufts, clumps of blades and flowers on plain grass cells (fields stay tidy)
    rnd = _rng("tufts", seed)
    for y in range(hh):
        for x in range(ww):
            if grid[y, x] != GRASS_C:
                continue
            for _ in range(rnd.choice(P["tufts"])):
                _tuft(img, x * CELL + rnd.randint(2, 12), y * CELL + rnd.randint(4, 13), rnd, P)
            for _ in range(rnd.choice(P["clumps"])):
                _clump(img, x * CELL + rnd.randint(3, 12), y * CELL + rnd.randint(6, 14), rnd, P)
            if P["flowers"] and rnd.random() < 0.2:
                col = rnd.choice(P["flowers"])
                fx, fy = x * CELL + rnd.randint(3, 12), y * CELL + rnd.randint(3, 12)
                for _ in range(rnd.randint(2, 4)):  # flowers grow in little patches
                    _flower(img, fx + rnd.randint(-3, 3), fy + rnd.randint(-3, 3), col)

    # the garden bed: tilled earth under the crop plots (the field minus its outer ring), with a bumpy edge
    field = grid == FIELD_C
    inner = field.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            inner &= np.roll(np.roll(field, dy, 0), dx, 1)
    if inner.any():
        earth, rim_c, crumb = P.get("bed", BED)
        bed = _dilate(_soft_mask(inner, 2.5, _noise(H, W, 2, nrng, 0.6), 0.55), 3)
        img[bed] = earth
        img[bed & (nrng.random((H, W)) < 0.06)] = crumb
        img[bed & (nrng.random((H, W)) < 0.04)] = rim_c
        img[bed & (_ring(~bed) | _shift(~bed, -1, 0))] = rim_c   # a dark rim, thicker under the top edge
        img[_ring(bed)] = P["edge"]

    # sand (beaches)
    img[sand] = SAND
    img[sand & (nrng.random((H, W)) < 0.05)] = SAND_DARK

    # dirt paths: speckled fill, a darker rim, a dark outline on the grass around them
    img[path] = P["dirt"]
    dots = nrng.random((H, W))
    img[path & (dots < 0.035)] = P["dirt_light"]
    img[path & (dots > 0.975)] = P["dirt_dark"]
    rim = path & (_ring(~path) | _shift(~path, -1, 0))
    img[rim & ~_shift(~path, 1, 0)] = P["dirt_dark"]          # shadow under the grass lip on the top and sides
    img[path & _shift(~path & land, 1, 0)] = P["dirt_dark"]    # under a grass edge, the dirt is in shade
    img[_ring(path) & land & ~sand] = P["edge"]
    for y, x in zip(*np.nonzero(path & (dots > 0.993))):  # a few pebbles
        _pebble(img, x, y)

    # water: deep middle, light shore line, sparkles; a brown cliff where land drops into it to the south
    dist = _depth(water, 12)
    img[water] = P["water"]
    deep = np.zeros_like(water)
    yy, xx = np.mgrid[0:H, 0:W]
    open_water = np.argwhere(water & (dist > 5))
    for k in nrng.choice(len(open_water), size=min(len(open_water), max(1, len(open_water) // 260)), replace=False) \
            if len(open_water) else []:
        cy, cx = open_water[k]
        r = nrng.uniform(1.5, 6.5)
        deep |= (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
    img[deep & water & (dist > 3)] = P["deep"]
    img[water & (dist <= 2)] = P["shore"]
    cliff = np.zeros_like(water)
    for k in range(1, 7):
        cliff |= water & _shift(land, k, 0)
    face = cliff & ~_shift(water & ~cliff, -1, 0) | cliff
    img[face] = CLIFF
    img[face & _shift(land, 1, 0)] = CLIFF_LIGHT                     # the lit top of the face
    img[cliff & ~_shift(cliff, -1, 0)] = CLIFF_DARK                  # the bottom of the face
    stripes = cliff & ((np.arange(W)[None, :] + (np.arange(H)[:, None] // 3)) % 7 == 0)
    img[stripes] = CLIFF_DARK
    img[water & ~cliff & _shift(cliff, 1, 0)] = P["foam"]                 # foam at the foot of the cliff
    img[_ring(water) & land & ~cliff] = P["edge"]                   # the grass lip around the water
    img[_ring(land) & water & ~cliff] = P["foam"]                         # a thin light line on the water side
    beside = _shift(land, 0, 1) | _shift(land, 0, -1)
    side = water & ~cliff & (beside | _shift(beside, 0, 1) | _shift(beside, 0, -1)) & ~_shift(land, -1, 0) & ~_shift(land, 1, 0)
    img[side] = CLIFF                                               # earth showing where the land ends east and west
    img[side & beside] = CLIFF_DARK
    sparkle = water & ~cliff & (dist > 3) & (nrng.random((H, W)) < 0.004)
    for y, x in zip(*np.nonzero(sparkle)):
        _sparkle(img, x, y, P)
    # lily pads out on the water, reeds along the shore, the odd mushroom in the grass
    rnd = _rng("details", seed)
    for y in range(hh):
        for x in range(ww):
            cx, cy = x * CELL + 8, y * CELL + 8
            if grid[y, x] == WATER_C and 0 < cy < H and 0 < cx < W and water[cy, cx] and not cliff[cy, cx]:
                if not P["lilies"]:
                    continue
                if dist[cy, cx] > 6 and rnd.random() < 0.05:
                    _lily(img, cx + rnd.randint(-3, 3), cy + rnd.randint(-3, 3), rnd)
                elif 2 < dist[cy, cx] <= 6 and rnd.random() < 0.12:
                    _reeds(img, cx + rnd.randint(-5, 5), cy + rnd.randint(-2, 4))
            elif grid[y, x] == GRASS_C:
                px, py, roll = x * CELL + rnd.randint(3, 12), y * CELL + rnd.randint(6, 13), rnd.random()
                if P["mushrooms"] and roll < 0.025:
                    for k in range(rnd.randint(1, 3)):  # a little ring of them
                        _mushroom(img, px + k * 3 - 2, py + (k % 2))
                elif roll < 0.045:
                    _stone(img, px, py, rnd.random() < 0.5)
                elif roll < 0.07 and season != "winter":
                    _sprig(img, px, py, P, rnd.random() < 0.4 and season == "spring")
    _indoors(img, grid)
    return img




FLOORBOARD, FLOORBOARD_DARK, FLOORBOARD_LIGHT, FLOORBOARD_SEAM = _c("#c8834e"), _c("#a86a3e"), _c("#dca068"), _c("#7e4a2e")
WALLPAPER, WALLPAPER_STRIPE, WALLPAPER_DOT = _c("#f2dcc0"), _c("#e6c8a6"), _c("#d89a7a")
WAINSCOT, WAINSCOT_DARK, WAINSCOT_LIGHT = _c("#8a3625"), _c("#4a2123"), _c("#ae4924")
RUG, RUG_EDGE, RUG_PATTERN = _c("#b8402e"), _c("#7a2420"), _c("#e8b048")
MAT, MAT_LIGHT, MAT_EDGE = _c("#38a129"), _c("#6ebd3c"), _c("#1a5a2a")
CURTAIN, CURTAIN_DARK = _c("#0092dd"), _c("#005ba7")


def _indoors(img: np.ndarray, grid: np.ndarray) -> None:
    """Rooms: darkness outside, honey floorboards, a papered back wall over wood panelling with windows hung with
    curtains, wall tops seen from above, a patterned rug and a striped mat by the door."""
    hh, ww = grid.shape
    floorish = (FLOOR_C, RUG_C, MAT_C)
    for y in range(hh):
        for x in range(ww):
            ch = grid[y, x]
            if ch not in INDOOR:
                continue
            px, py = x * CELL, y * CELL
            tile = img[py:py + CELL, px:px + CELL]
            if ch == VOID_C:
                tile[:] = _c("#14101c")
                continue
            if ch == WALL_C:
                below_floor = y + 1 < hh and grid[y + 1, x] in floorish
                back = below_floor or (y + 2 < hh and grid[y + 1, x] == WALL_C and grid[y + 2, x] in floorish)
                if not back:  # side and bottom walls, seen from above: a dark top with a lit lip by the floor
                    tile[:] = WAINSCOT_DARK
                    tile[::5, :] = F_DEEP
                    for nx, ny, sl in ((1, 0, np.s_[:, -3:]), (-1, 0, np.s_[:, :3]), (0, -1, np.s_[:3, :]), (0, 1, np.s_[-3:, :])):
                        if 0 <= x + nx < ww and 0 <= y + ny < hh and grid[y + ny, x + nx] in floorish:
                            tile[sl] = WAINSCOT
                    continue
                tile[:] = WALLPAPER  # wallpaper: stripes with a little dot between
                tile[:, 3::8] = WALLPAPER_STRIPE
                tile[:, 4::8] = WALLPAPER_STRIPE
                tile[4::8, 7::8] = WALLPAPER_DOT
                tile[0::8, 0::8] = WALLPAPER_DOT
                if below_floor:  # the lower part is panelling under a chair rail, a baseboard at the floor
                    tile[5] = WAINSCOT_LIGHT
                    tile[6] = WAINSCOT_DARK
                    tile[7:] = WAINSCOT
                    tile[7:, ::4] = WAINSCOT_DARK
                    tile[7:, 1::4] = WAINSCOT_LIGHT
                    tile[14:] = WAINSCOT_DARK
                else:
                    tile[0:2] = WAINSCOT  # the crown moulding
                    tile[2] = WAINSCOT_DARK
                    tile[0] = WAINSCOT_LIGHT
                    if (x * 7) % 4 == 1:  # a window hung with curtains
                        tile[4:15, 3:13] = WAINSCOT
                        tile[5:14, 4:12] = GLASS
                        tile[5:14, 8] = WAINSCOT
                        tile[9, 4:12] = WAINSCOT
                        tile[6:8, 5:7] = GLASS_LIGHT
                        tile[3:15, 1:4] = CURTAIN
                        tile[3:15, 12:15] = CURTAIN
                        tile[3:15, 3] = CURTAIN_DARK
                        tile[3:15, 12] = CURTAIN_DARK
                        tile[3, 0:16] = WAINSCOT_DARK  # the curtain rod
                continue
            tile[:] = FLOORBOARD  # floorboards: staggered ends, a lit edge, grain and the odd knot
            for row in range(0, CELL, 4):
                tile[row] = FLOORBOARD_SEAM
                tile[row + 1] = FLOORBOARD_LIGHT
                seam = (row * 3 + x * 5) % CELL
                tile[row + 1:row + 4, seam] = FLOORBOARD_SEAM
                tile[row + 2, (x * 3 + row) % 7::7] = FLOORBOARD_DARK
            if (x * 5 + y * 3) % 7 == 0:
                tile[10, 6] = FLOORBOARD_SEAM
            if y > 0 and grid[y - 1, x] == WALL_C:  # the wall's shadow on the floor
                tile[:3] = (tile[:3].astype(int) * 0.72).astype(np.uint8)
                tile[:3, :, 3] = 255
            if ch == RUG_C:  # a red rug: a gold border, a diamond in each tile, fringed ends
                tile[:] = RUG
                for d_ in range(4):
                    tile[8 - d_, 8 - 3 + d_] = RUG_PATTERN
                    tile[8 + d_, 8 - 3 + d_] = RUG_PATTERN
                    tile[8 - d_, 8 + 3 - d_] = RUG_PATTERN
                    tile[8 + d_, 8 + 3 - d_] = RUG_PATTERN
                tile[8, 8] = RUG_PATTERN
                for nx, ny, edge, line in ((0, -1, np.s_[:2], np.s_[2]), (0, 1, np.s_[-2:], np.s_[-3]),
                                           (-1, 0, np.s_[:, :2], np.s_[:, 2]), (1, 0, np.s_[:, -2:], np.s_[:, -3])):
                    if not (0 <= x + nx < ww and 0 <= y + ny < hh and grid[y + ny, x + nx] == RUG_C):
                        tile[edge] = RUG_EDGE
                        tile[line] = RUG_PATTERN
            elif ch == MAT_C:  # a striped green mat
                tile[3:13, 1:15] = MAT_EDGE
                tile[4:12, 2:14] = MAT
                tile[4:12:2, 2:14] = MAT_LIGHT


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


def _tuft(img: np.ndarray, x: int, y: int, rnd: random.Random, P: dict) -> None:
    h, w = img.shape[:2]
    t, tl = P["tuft"], P["tuft_light"]
    for dx, dy, col in ((0, 0, t), (-1, -1, t), (1, -1, t), (-2, -2, tl), (2, -2, tl), (0, -2, tl if rnd.random() < 0.5 else t)):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = col


CLUMP = ("...l...",
         ".l.d.l.",
         ".d.d.d.",
         "d.ddd.d",
         ".ddddd.")
CLUMP_SMALL = ("l...l",
               "d.l.d",
               ".ddd.")


def _clump(img: np.ndarray, x: int, y: int, rnd: random.Random, P: dict) -> None:
    """A clump of grass blades standing on (x, y): dark blades, light tips."""
    shape = CLUMP if rnd.random() < 0.5 else CLUMP_SMALL
    h, w = img.shape[:2]
    top, half = y - len(shape) + 1, len(shape[0]) // 2
    for r, row in enumerate(shape):
        for c, ch in enumerate(row):
            yy, xx = top + r, x - half + c
            if ch != "." and 0 <= yy < h and 0 <= xx < w:
                img[yy, xx] = P["tuft"] if ch == "d" else P["tuft_light"]


STONE_ART = {"big": ("..OOO..",
                     ".OLLSO.",
                     "OLSSSDO",
                     "OSSSDDO",
                     ".ODDDO."),
             "small": (".OO.",
                       "OLSO",
                       "ODDO")}


def _stone(img: np.ndarray, x: int, y: int, big: bool) -> None:
    """A grey stone sitting in the grass, lit from the top left."""
    col = {"O": OUTLINE, "L": _c("#e4e4ec"), "S": _c("#b4b4c4"), "D": _c("#7e7e94")}
    shape = STONE_ART["big" if big else "small"]
    h, w = img.shape[:2]
    for r, row in enumerate(shape):
        for c, ch in enumerate(row):
            yy, xx = y - len(shape) + 1 + r, x - len(row) // 2 + c
            if ch in col and 0 <= yy < h and 0 <= xx < w:
                img[yy, xx] = col[ch]


SPRIG = ("..L.L..",
         ".LDLDL.",
         "LDDLDDL",
         ".DDDDD.",
         "..DDD..")


def _sprig(img: np.ndarray, x: int, y: int, P: dict, bluebells: bool) -> None:
    """A leafy weed (a fern, or bluebells in spring) with a dark outline, a little bigger than a clump."""
    leaf, dark = P["tuft_light"], P["tuft"]
    h, w = img.shape[:2]
    top = y - len(SPRIG) + 1
    solid = set()
    for r, row in enumerate(SPRIG):
        for c, ch in enumerate(row):
            if ch != ".":
                solid.add((top + r, x - 3 + c))
                if 0 <= top + r < h and 0 <= x - 3 + c < w:
                    img[top + r, x - 3 + c] = leaf if ch == "L" else dark
    for yy, xx in {(a + dy, b + dx) for a, b in solid for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))} - solid:
        if 0 <= yy < h and 0 <= xx < w:
            img[yy, xx] = P["edge"]
    if bluebells:
        for bx, by in ((x - 2, top - 1), (x + 2, top), (x, top - 2)):
            if 0 <= by < h and 0 <= bx + 1 < w:
                img[by, bx] = _c("#6a7ae8")
                img[by, bx + 1] = _c("#9aa8ff")


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


def _sparkle(img: np.ndarray, x: int, y: int, P: dict) -> None:
    h, w = img.shape[:2]
    for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= y + dy < h and 0 <= x + dx < w:
            img[y + dy, x + dx] = P["foam"] if (dx, dy) == (0, 0) else P["shore"]


# --- objects, animals and people (painted at art size, shown at 2x) -----------------------------

from .chibi import Fig  # noqa: E402  (a small numpy canvas with an outline pass)

WOOD, WOOD_DARK, WOOD_LIGHT = _c("#ae4924"), _c("#6e2a22"), _c("#c46120")  # the fences' and trunks' wood
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


# Buildings and props share the fences' wood (F_*), a cream plank wall, tiled roofs ramped from the building's
# colour, cool grey stone and a dark plum outline over a soft shadow on the grass.
WALL, WALL_LIGHT, WALL_LINE, WALL_SHADE = _c("#e8c4a8"), _c("#f7dbc6"), _c("#b07e68"), _c("#c89c84")
METAL, METAL_LIGHT, METAL_DARK = _c("#93bab3"), _c("#bffff3"), _c("#60838a")
STRAW, STRAW_LIGHT, STRAW_SHADE, STRAW_DEEP = _c("#e8c25a"), _c("#f8e08a"), _c("#c09038"), _c("#8a6224")


def _roof_ramp(color: str) -> dict[str, RGBA]:
    """Roof tiles from one colour: a sunlit edge, the face, its shade, the gap under a course, the outline."""
    h, s, v = _hsv(_c(color))
    return {"hi": _from_hsv(_toward(h, 0.12, 0.03), s * 0.85, v * 1.25),
            "light": _from_hsv(h, s * 0.95, v * 1.05), "base": _from_hsv(_toward(h, 0.95, 0.01), s * 1.05, v * 0.82),
            "dark": _from_hsv(_toward(h, 0.95, 0.02), s * 1.1, v * 0.58), "deep": _from_hsv(_toward(h, 0.95, 0.03), s, v * 0.36)}


def _tiled(px: np.ndarray, mask: np.ndarray, along: tuple[float, float], R: dict[str, RGBA], course: int = 5,
           tile: int = 6, shade: bool = False) -> None:
    """Courses of roof tiles over `mask`: rows across `along` (the slope's run), staggered joints, a lit lip on
    each course and a dark gap under it. `shade` draws the slope turned away from the light."""
    h, w = mask.shape
    ys, xs = np.mgrid[0:h, 0:w]
    ax, ay = along
    n = math.hypot(ax, ay)
    ax, ay = ax / n, ay / n
    t = xs * ax + ys * ay            # along the run
    s = -xs * ay + ys * ax           # across the run
    k = np.floor(s / course)
    pos = s - k * course
    joint = np.mod(np.floor(t) + k * 3, tile) == 0
    face, lit = (R["dark"], R["base"]) if shade else (R["base"], R["light"])
    out = np.where((pos < 1)[..., None], np.array(R["hi"] if not shade else R["light"]),
                   np.where((pos >= course - 1)[..., None], np.array(R["deep"]),
                            np.where(joint[..., None], np.array(R["dark"] if not shade else R["deep"]),
                                     np.where((pos < 2)[..., None], np.array(lit), np.array(face)))))
    px[mask] = out[mask].astype(np.uint8)


def _planks(g: Fig, x0: int, y0: int, x1: int, y1: int, step: int = 4) -> None:
    """A wall of cream boards laid flat: a lit top to each board, a dark seam under it, joints staggered."""
    g.rect(x0, y0, x1, y1, WALL)
    for k, y in enumerate(range(y0 + step - 1, y1 + 1, step)):
        g.rect(x0, y, x1, y, WALL_LINE)
        if y + 1 <= y1:
            g.rect(x0, y + 1, x1, y + 1, WALL_LIGHT)
        for x in range(x0 + (k * 7) % 13 + 4, x1, 13):
            g.rect(x, y - step + 2, x, y - 1, WALL_LINE)


def _bricks(g: Fig, x0: int, y0: int, x1: int, y1: int, base: RGBA, light: RGBA, mortar: RGBA) -> None:
    g.rect(x0, y0, x1, y1, base)
    for k, y in enumerate(range(y0, y1 + 1, 3)):
        g.rect(x0, y + 2, x1, y + 2, mortar)
        for x in range(x0 + (2 if k % 2 else 0), x1 + 1, 5):
            g.rect(x, y, x, y + 1, mortar)
            if x + 1 <= x1:
                g.set(x + 1, y, light)


def _post(g: Fig, x0: int, y0: int, x1: int, y1: int) -> None:
    """An upright beam: lit on the left, shaded on the right."""
    g.rect(x0, y0, x1, y1, F_BASE)
    g.rect(x0, y0, x0, y1, F_LIGHT)
    g.rect(x1, y0, x1, y1, F_DARK)


def _beam(g: Fig, x0: int, y0: int, x1: int, y1: int) -> None:
    """A level beam: a lit top, a shaded underside."""
    g.rect(x0, y0, x1, y1, F_BASE)
    g.rect(x0, y0, x1, y0, F_LIGHT)
    g.rect(x0, y1, x1, y1, F_DARK)


def _window(g: Fig, x0: int, y0: int, w: int, h: int, flowers: bool = False) -> None:
    g.rect(x0, y0, x0 + w - 1, y0 + h - 1, F_DARK)
    g.rect(x0 + 1, y0 + 1, x0 + w - 2, y0 + h - 2, F_BASE)
    g.rect(x0 + 2, y0 + 2, x0 + w - 3, y0 + h - 3, GLASS)
    mx, my = x0 + w // 2, y0 + h // 2
    g.rect(mx, y0 + 2, mx, y0 + h - 3, F_BASE)
    g.rect(x0 + 2, my, x0 + w - 3, my, F_BASE)
    g.rect(x0 + 2, y0 + 2, x0 + 3, y0 + 2, GLASS_LIGHT)
    g.set(x0 + 2, y0 + 3, GLASS_LIGHT)
    g.set(mx + 1, my + 1, GLASS_LIGHT)
    if flowers:  # a window box of flowers under the sill
        g.rect(x0 - 1, y0 + h, x0 + w, y0 + h + 2, F_BASE)
        g.rect(x0 - 1, y0 + h, x0 + w, y0 + h, F_LIGHT)
        g.rect(x0 - 1, y0 + h + 2, x0 + w, y0 + h + 2, F_DARK)
        for k, fx in enumerate(range(x0, x0 + w, 2)):
            g.set(fx, y0 + h - 1, CROP_LEAF["B"] if k % 2 else FLOWERS[(k // 2 + x0) % len(FLOWERS)])
            g.set(fx + 1, y0 + h - 1, CROP_LEAF["L"])


def paint_farmhouse(g: Fig, color: str, anim: str, i: int) -> None:
    """A cottage with a front gable: two tiled slopes and a ridge beam, a stone chimney, a cream plank wall
    between dark corner posts, flower-box windows, a panelled door on a step."""
    R = _roof_ramp(color)
    w, h = g.w, g.h
    cx = w // 2
    g.ellipse(cx, h - 3, 38, 3, GROUND_SHADOW)
    # the chimney, behind the left slope
    g.rect(13, 6, 22, 30, STONE_DARK)
    _bricks(g, 14, 8, 21, 30, STONE, STONE_LIGHT, STONE_DARK)
    g.rect(12, 4, 23, 7, STONE_DARK)
    g.rect(12, 4, 23, 4, STONE_LIGHT)
    g.rect(14, 5, 21, 6, _c("#2a2230"))
    # walls, posts and the eave beam
    _planks(g, 8, 50, 71, 75)
    g.rect(8, 50, 71, 52, WALL_SHADE)  # in the eave's shadow
    for x0 in (4, 72):
        _post(g, x0, 46, x0 + 3, 75)
    # the gable: planks in a triangle under the slopes, a little window in it
    gable = Fig(w, h)
    _planks(gable, 10, 16, 69, 49)
    tri = np.zeros((h, w), dtype=bool)
    for y in range(16, 50):
        half = (y - 15) * 1.0
        tri[y, max(0, int(cx - half)):min(w, int(cx + half))] = True
    g.px[tri] = gable.px[tri]
    _window(g, cx - 6, 29, 12, 10)
    _beam(g, 2, 45, 77, 49)
    # the roof: two slopes running down from the ridge to the eaves
    ys, xs = np.mgrid[0:h, 0:w]
    X, Y = xs + 0.5, ys + 0.5
    left = (X < cx - 2) & (Y < 48) & (Y > (cx - 2 - X) * 0.95 - 3) & (Y < (cx - 2 - X) * 0.95 + 19)
    right = (X >= cx + 2) & (Y < 48) & (Y > (X - cx - 2) * 0.95 - 3) & (Y < (X - cx - 2) * 0.95 + 19)
    _tiled(g.px, left, (-1.0, 0.95), R)
    _tiled(g.px, right, (1.0, 0.95), R, shade=True)
    for side in (-1, 1):  # bargeboards along the gable's edges
        g.line(cx + side * 2, 17, cx + side * 33, 48, F_DARK, 2)
        g.line(cx + side * 2, 16, cx + side * 32, 47, F_BASE, 1)
    # the ridge beam, its end grain at the peak
    _post(g, cx - 3, 0, cx + 2, 18)
    g.ellipse(cx - 0.5, 16.5, 3.2, 2.6, F_CAP)
    g.ellipse(cx - 0.5, 16.5, 1.6, 1.2, F_LIGHT)
    g.set(cx, 16, F_DARK)
    # windows with flower boxes, the door and its step
    _window(g, 13, 56, 13, 11, flowers=True)
    _window(g, 54, 56, 13, 11, flowers=True)
    g.rect(cx - 7, 55, cx + 6, 75, F_DARK)
    g.rect(cx - 6, 56, cx + 5, 75, F_BASE)
    for y0, y1 in ((58, 64), (67, 73)):  # panels
        g.rect(cx - 4, y0, cx + 3, y1, F_DARK)
        g.rect(cx - 3, y0 + 1, cx + 2, y1, F_LIGHT)
        g.rect(cx - 3, y0 + 1, cx + 2, y0 + 1, F_CAP)
    g.rect(cx + 3, 65, cx + 4, 66, _c("#ffd84a"))
    g.rect(cx - 9, 76, cx + 8, 78, F_BASE)
    g.rect(cx - 9, 76, cx + 8, 76, F_LIGHT)
    g.rect(cx - 9, 78, cx + 8, 78, F_DARK)
    _out(g)


def paint_coop(g: Fig, color: str, anim: str, i: int) -> None:
    """A red hen house: board-and-batten walls with white trim, a tiled roof, a dark doorway with a ramp."""
    d, b, l = _ramp(color)
    R = _roof_ramp(_hex(d))
    w, h = g.w, g.h
    g.ellipse(20, 37, 18, 2.4, GROUND_SHADOW)
    g.poly([(20, 3), (2, 16), (38, 16)], b)  # the gable and the walls: boards with battens
    g.rect(3, 15, 36, 34, b)
    for x in range(5, 36, 4):
        top = int(3 + abs(x - 20) * 0.7)
        g.rect(x, max(top, 6), x, 34, d)
        g.set(x - 1, 17, l)
    g.rect(3, 15, 36, 15, d)  # under the eaves
    for x0 in (3, 35):  # white corner trim
        g.rect(x0, 15, x0 + 1, 34, WHITE)
    g.rect(3, 33, 36, 34, d)
    ys, xs = np.mgrid[0:h, 0:w]
    X, Y = xs + 0.5, ys + 0.5
    roof = (Y > 0.5 + np.abs(X - 20) * 0.62) & (Y < 8.0 + np.abs(X - 20) * 0.62) & (Y < 19)
    _tiled(g.px, roof & (X < 20), (-1.0, 0.62), R, course=4)
    _tiled(g.px, roof & (X >= 20), (1.0, 0.62), R, course=4, shade=True)
    g.rect(14, 21, 25, 34, WHITE)  # the doorway in its trim, a ramp up to it
    g.rect(15, 22, 24, 34, _c("#2a1e2e"))
    g.rect(16, 23, 23, 34, _c("#3e2a34"))
    g.poly([(14, 33), (25, 33), (29, 38.5), (10, 38.5)], F_BASE)
    for y in (35, 37):
        g.rect(11, y, 27, y, F_DARK)
    g.rect(28, 20, 33, 25, WHITE)  # a little window
    g.rect(29, 21, 32, 24, GLASS)
    g.set(29, 21, GLASS_LIGHT)
    g.rect(6, 21, 11, 24, _c("#f8e08a"))  # a straw nest box under a hatch
    g.rect(6, 20, 11, 20, WHITE)
    _out(g)


def _hex(c: RGBA) -> str:
    return "#%02x%02x%02x" % c[:3]


def paint_well(g: Fig, color: str, anim: str, i: int) -> None:
    """A stone well: a ring of blocks round dark water, two posts, a little tiled roof, a rope and bucket."""
    R = _roof_ramp(color)
    w, h = g.w, g.h
    g.ellipse(12, 28, 11, 2, GROUND_SHADOW)
    _post(g, 3, 7, 4, 21)
    _post(g, 19, 7, 20, 21)
    g.rect(3, 8, 20, 8, F_DARK)  # the crossbar and the rope
    g.rect(11, 9, 11, 13, _c("#d8c8a0"))
    g.rect(9, 13, 13, 16, METAL_DARK)  # the bucket
    g.rect(9, 13, 13, 13, METAL)
    g.rect(10, 14, 12, 15, F_BASE)
    ys, xs = np.mgrid[0:h, 0:w]
    X, Y = xs + 0.5, ys + 0.5
    roof = (Y > np.abs(X - 12) * 0.6 - 0.5) & (Y < np.abs(X - 12) * 0.6 + 4.5) & (X > 0) & (X < 24)
    _tiled(g.px, roof & (X < 12), (-1.0, 0.6), R, course=3, tile=4)
    _tiled(g.px, roof & (X >= 12), (1.0, 0.6), R, course=3, tile=4, shade=True)
    g.rect(2, 20, 21, 27, STONE)  # the stone ring
    for k, y in enumerate((20, 23)):
        g.rect(2, y + 2, 21, y + 2, STONE_DARK)
        for x in range(2 + (3 if k else 0), 22, 6):
            g.rect(x, y, x, y + 1, STONE_DARK)
            g.set(x + 1, y, STONE_LIGHT)
    g.rect(2, 26, 21, 27, STONE_DARK)
    g.ellipse(11.5, 19.5, 10, 2.8, STONE_LIGHT)
    g.ellipse(11.5, 19.8, 7.6, 1.8, _c("#1c3a6a"))
    g.rect(8, 19, 11, 19, _c("#3a6aa8"))
    _out(g)


def paint_scarecrow(g: Fig, color: str, anim: str, i: int) -> None:
    """A straw-stuffed scarecrow on a pole: a sack face, a wide straw hat, a patched shirt that flaps."""
    d, b, l = _ramp(color)
    tilt = (0, 1, 0, -1)[i % 4] if anim == "idle" else 0
    g.ellipse(8, 23, 4, 1, GROUND_SHADOW)
    _post(g, 7, 10, 8, 23)
    _beam(g, 1, 11, 14, 12)
    g.rect(4, 10, 11, 17 + max(0, tilt), b)  # shirt, the hem flapping
    g.rect(4, 10, 11, 10, l)
    g.rect(10, 11, 11, 17, d)
    g.rect(5, 14, 7, 16, _c("#e8c25a"))  # a patch
    g.set(5, 14, STRAW_SHADE)
    g.set(4 + (tilt + 1) * 3, 18 + max(0, tilt), STRAW)  # straw poking out
    for x in (0, 1, 14, 15):  # straw hands
        g.set(x, 12 + (x % 2), STRAW_LIGHT)
    g.ellipse(7.5, 6.5, 3.6, 3.4, _c("#e8d0a0"))  # sack head
    g.rect(5, 8, 10, 8, _c("#c8a878"))
    g.set(6, 6, F_OUT)
    g.set(9, 6, F_OUT)
    g.rect(6, 8, 9, 8, F_DARK)  # a stitched grin
    g.set(7, 9, F_DARK)
    g.poly([(1, 4.5), (15, 4.5), (11, 0), (4, 0)], STRAW)  # straw hat with a band
    g.rect(4, 1, 11, 1, STRAW_LIGHT)
    g.rect(0, 4, 15, 4, STRAW_SHADE)
    g.rect(4, 3, 11, 3, _c("#c84a3a"))
    _out(g)


def paint_hay(g: Fig, color: str, anim: str, i: int) -> None:
    """A bale of straw: strands drawn in, two twine bands, a lit top."""
    g.ellipse(8, 14, 8, 1.8, GROUND_SHADOW)
    g.rect(1, 4, 14, 13, STRAW)
    g.rect(1, 4, 14, 6, STRAW_LIGHT)
    g.rect(1, 12, 14, 13, STRAW_SHADE)
    for x, y in ((3, 8), (6, 10), (9, 8), (12, 10), (2, 11), (11, 6), (7, 7)):  # strands
        g.set(x, y, STRAW_SHADE)
        g.set(x + 1, y - 1, STRAW_LIGHT)
    for x in (4, 11):  # twine
        g.rect(x, 4, x, 13, F_DARK)
        g.set(x, 4, F_BASE)
    g.set(0, 6, STRAW_LIGHT)
    g.set(15, 9, STRAW)
    _out(g)


def paint_barrel(g: Fig, color: str, anim: str, i: int) -> None:
    """A barrel: staves lit on the left, two iron hoops, a round lid of boards."""
    g.ellipse(8, 15, 7, 1.6, GROUND_SHADOW)
    g.ellipse(7.5, 9, 6.4, 6, F_BASE)
    g.rect(2, 4, 13, 14, F_BASE)
    for x in (4, 7, 10):
        g.rect(x, 4, x, 14, F_DARK)
    g.rect(2, 4, 3, 14, F_LIGHT)
    g.rect(12, 4, 13, 14, F_DARK)
    for y in (6, 12):  # hoops
        g.rect(1, y, 14, y, METAL_DARK)
        g.rect(2, y, 6, y, METAL)
    g.ellipse(7.5, 3.5, 6, 1.8, F_LIGHT)
    g.ellipse(7.5, 3.6, 4.6, 1.1, F_CAP)
    g.rect(5, 3, 10, 3, F_LIGHT)
    _out(g)


def paint_bin(g: Fig, color: str, anim: str, i: int) -> None:
    """The shipping bin: a wooden chest with dark bands and an iron latch (open on its second frame)."""
    open_ = anim == "idle" and i == 1
    g.ellipse(8, 15, 8, 1.6, GROUND_SHADOW)
    g.rect(1, 7, 14, 14, F_BASE)
    g.rect(1, 9, 14, 9, F_LIGHT)
    g.rect(1, 12, 14, 12, F_DARK)
    g.rect(1, 7, 1, 14, F_LIGHT)
    g.rect(14, 7, 14, 14, F_DARK)
    if open_:
        g.rect(1, 1, 14, 4, F_BASE)
        g.rect(1, 1, 14, 1, F_CAP)
        g.rect(2, 5, 13, 7, F_OUT)
    else:
        g.rect(0, 3, 15, 7, F_BASE)
        g.rect(1, 3, 14, 4, F_CAP)
        g.rect(1, 5, 14, 5, F_LIGHT)
        g.rect(0, 7, 15, 7, F_DARK)
        g.rect(7, 6, 8, 9, METAL)  # the latch
        g.set(7, 6, METAL_LIGHT)
        g.rect(7, 9, 8, 9, METAL_DARK)
    _out(g)


def paint_workbench(g: Fig, color: str, anim: str, i: int) -> None:
    """A carpenter's bench: a thick top, legs and a shelf, a saw and a hammer on top, a can on the shelf."""
    g.ellipse(12, 17, 11, 1.6, GROUND_SHADOW)
    _beam(g, 1, 6, 22, 10)
    g.rect(1, 7, 22, 7, F_CAP)
    for x in (2, 20):
        _post(g, x, 11, x + 1, 17)
    g.rect(2, 14, 21, 14, F_DARK)
    g.rect(3, 3, 10, 5, METAL)  # a saw with its handle
    g.rect(3, 5, 10, 5, METAL_DARK)
    g.set(3, 3, METAL_LIGHT)
    g.rect(11, 3, 13, 5, _c("#c84a3a"))
    g.rect(16, 2, 17, 5, F_LIGHT)  # a hammer
    g.rect(14, 1, 19, 2, METAL_DARK)
    g.set(14, 1, METAL)
    g.rect(5, 12, 8, 13, _c("#4a7ad0"))  # a watering can and a sack on the shelf
    g.set(5, 12, _c("#8ab0ff"))
    g.rect(14, 12, 18, 13, STRAW)
    _out(g)


def paint_shop(g: Fig, color: str, anim: str, i: int) -> None:
    """A market stall: a striped, scalloped awning on two posts, a plank counter with crates of produce."""
    d, b, l = _ramp(color)
    g.ellipse(16, 31, 15, 1.8, GROUND_SHADOW)
    for x in (3, 27):
        _post(g, x, 10, x + 1, 30)
    g.rect(1, 19, 30, 29, F_BASE)  # the counter, boards across
    for y in (22, 25):
        g.rect(1, y, 30, y, F_DARK)
    g.rect(1, 19, 30, 20, F_LIGHT)
    g.rect(1, 19, 30, 19, F_CAP)
    g.rect(1, 29, 30, 29, F_DARK)
    for k, x in enumerate(range(0, 32, 4)):  # a striped awning with a scalloped edge
        g.rect(x, 4, x + 3, 10, b if k % 2 == 0 else WHITE)
        g.ellipse(x + 2, 11, 2, 1.6, b if k % 2 == 0 else WHITE)
        g.rect(x, 4, x + 3, 4, l if k % 2 == 0 else WHITE)
        g.set(x + 3, 9, d if k % 2 == 0 else _c("#d8d0c8"))
    g.rect(0, 3, 31, 3, d)
    g.rect(4, 15, 10, 18, F_LIGHT)  # a crate of carrots
    g.rect(4, 17, 10, 17, F_DARK)
    for x in (5, 7, 9):
        g.set(x, 14, _c("#ff8a2a"))
        g.set(x, 13, CROP_LEAF["L"])
    g.ellipse(14, 17, 2, 1.6, _c("#f8f0e0"))  # eggs
    g.ellipse(17.5, 17, 2, 1.6, _c("#f8f0e0"))
    g.set(13, 16, WHITE)
    g.rect(21, 15, 27, 18, STRAW)  # a basket with a chick
    g.rect(21, 17, 27, 17, STRAW_SHADE)
    g.ellipse(24, 14, 1.8, 1.6, _c("#ffd84a"))
    g.set(25, 14, F_OUT)
    g.rect(10, 22, 21, 26, WALL_LIGHT)  # a price board on the counter
    g.rect(12, 24, 19, 24, F_DARK)
    _out(g)


def paint_sprinkler(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(8, 14, 4, 1.2, GROUND_SHADOW)
    g.rect(7, 7, 8, 13, METAL_DARK)
    g.rect(5, 12, 10, 13, METAL)
    g.rect(5, 12, 10, 12, METAL_LIGHT)
    g.ellipse(7.5, 6, 3, 2, METAL)
    g.ellipse(7, 5.5, 1.4, 0.8, METAL_LIGHT)
    k = i % 4
    for n, (dx, dy) in enumerate(((-5, -2), (5, -2), (-3, -4), (3, -4))):  # little jets of water
        if (n + k) % 2 == 0:
            g.set(7.5 + dx, 5 + dy, _c("#7fd0ff"))
            g.set(7.5 + dx * 0.6, 5.5 + dy * 0.6, _c("#c8f0ff"))
    _out(g)


def paint_sign(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(8, 15, 3, 0.8, GROUND_SHADOW)
    _post(g, 7, 8, 8, 15)
    g.rect(1, 2, 14, 9, F_BASE)
    g.rect(1, 2, 14, 2, F_CAP)
    g.rect(1, 3, 14, 3, F_LIGHT)
    g.rect(1, 9, 14, 9, F_DARK)
    g.rect(4, 5, 11, 5, F_DEEP)  # writing
    g.rect(4, 7, 9, 7, F_DEEP)
    g.set(2, 6, F_LIGHT)
    _out(g)


def paint_flower_bush(g: Fig, color: str, anim: str, i: int) -> None:
    """A leafy bush dotted with flowers in its colour."""
    rnd = _rng("bush", color)
    d, b, l = _ramp(color)
    bush = Fig(g.w, g.h)
    _stamp(bush.px, PLANT_ART["bush"][1][1:], 12, CROP_LEAF)
    for _ in range(4):
        fx, fy = 3 + rnd.random() * 9, 4 + rnd.random() * 5
        for ox, oy, k in _blossom(l if rnd.random() < 0.5 else b, _c("#ffe070")):
            X, Y = int(fx) + ox, int(fy) + oy
            if 0 <= X < g.w and 0 <= Y < g.h and bush.px[Y, X, 3]:
                bush.px[Y, X] = k
    g.ellipse(8, 13, 7, 1.6, GROUND_SHADOW)
    _over(g.px, _outlined(bush.px, CROP_OUT))


# Fences join their neighbours: one painter draws a post with rails toward each side that has fence next to it
# (n, e, s, w), and farmgen picks the piece from the cells around it. Every piece fills its whole cell, so rails
# meet rails at the cell edges and a run of fence reads as one line.
F_OUT, F_DEEP, F_DARK, F_BASE, F_LIGHT, F_CAP = (_c("#1c0a18"), _c("#32131e"), _c("#4a2123"), _c("#8a3625"),
                                                 _c("#ae4924"), _c("#c46120"))
GROUND_SHADOW = (0, 0, 0, 77)
FENCE_DIRS = ("", "n", "e", "s", "w", "ne", "ns", "nw", "es", "ew", "sw", "nes", "new", "nsw", "esw", "nesw")


def fence_kind(dirs: str) -> str:
    """The sprite kind of a fence piece joined toward `dirs` (letters in n, e, s, w order)."""
    return {"ew": "fence_h", "ns": "fence_v", "": "fence_post"}.get(dirs, f"fence_{dirs}")


FENCE_KINDS = {fence_kind(d): d for d in FENCE_DIRS}  # kind -> the sides it joins


def _rail(g: Fig, x0: int, x1: int, y: int) -> None:
    """A horizontal rail four pixels tall: outline, lit top, shaded underside, outline."""
    g.rect(x0, y, x1, y, F_OUT)
    g.rect(x0, y + 1, x1, y + 1, F_LIGHT)
    g.rect(x0, y + 2, x1, y + 2, F_DARK)
    g.rect(x0, y + 3, x1, y + 3, F_OUT)


def paint_fence(g: Fig, dirs: str) -> None:
    """One 16x16 fence piece: a post in the middle, rails to the joined sides, a soft shadow on the grass."""
    n, e, s, w = ("n" in dirs), ("e" in dirs), ("s" in dirs), ("w" in dirs)
    x0, x1 = (0 if w else 6), (15 if e else 9)
    if e or w:
        g.rect(x0, 13, x1, 14, GROUND_SHADOW)  # the rails' shadow
    g.rect(4, 14, 11, 15, GROUND_SHADOW)
    if n:  # a rail running up to the post above (seen from the top: a narrow beam)
        g.rect(6, 0, 9, 2, F_OUT)
        g.rect(7, 0, 8, 2, F_BASE)
        g.set(7, 0, F_LIGHT)
    if s:
        g.rect(6, 13, 9, 15, F_OUT)
        g.rect(7, 13, 8, 15, F_DARK)
    for y in (4, 9):
        if w:
            _rail(g, 0, 5, y)
        if e:
            _rail(g, 10, 15, y)
    # the post: outline, body, shaded right side, a lit cap with the end grain
    g.rect(5, 1, 10, 14, F_OUT)
    g.rect(6, 2, 9, 13, F_BASE)
    g.rect(9, 3, 9, 13, F_DARK)
    g.rect(6, 12, 9, 13, F_DARK)
    g.rect(6, 2, 9, 3, F_CAP)
    g.set(7, 2, F_LIGHT)
    g.set(8, 3, F_LIGHT)
    g.rect(6, 4, 9, 4, F_DEEP)
    g.set(7, 7, F_DARK)  # a knot
    g.set(6, 10, F_LIGHT)


# Trees. A leafy crown is a heap of leaf clumps, each lit from the top left with a shaded underside and a dark rim
# where it overlaps the clump behind it; the crown's edge is ragged with leaf tips, the bottom of the crown opens on
# the dark underside where the branches fork from the trunk, and the trunk flares into roots over a soft shadow.
# In the wind the clumps sway a pixel each way, the top ones most and each a little out of step (six frames).
BARK_OUT, BARK_DEEP, BARK_DARK, BARK, BARK_LIGHT = (_c("#1c0a18"), _c("#4a2123"), _c("#8a3625"), _c("#ae4924"),
                                                   _c("#c46120"))
TREE_FRAMES, TREE_FPS = 6, 3


def _hsv(c: RGBA) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)


def _from_hsv(h: float, s: float, v: float, a: int = 255) -> RGBA:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(1.0, max(0.0, s)), min(1.0, max(0.0, v)))
    return int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5), a


def _toward(h: float, target: float, amount: float) -> float:
    """A hue moved `amount` toward `target` the short way round (shadows go cool, lights go warm)."""
    d = (target - h + 0.5) % 1.0 - 0.5
    return h + math.copysign(min(abs(d), amount), d)


def foliage(color: str) -> dict[str, RGBA]:
    """Six tones of leaves from one colour: light, base, shade, deep, the dark underside and the outline."""
    h, s, v = _hsv(_c(color))
    s = min(s, 0.72)  # a red maple stays a warm red, not a hot one
    return {"light": _from_hsv(_toward(h, 0.15, 0.025), s * 0.9, v * 1.1),
            "base": _from_hsv(_toward(h, 0.72, 0.02), s * 1.2, v * 0.86),
            "shade": _from_hsv(_toward(h, 0.72, 0.06), s * 1.3, v * 0.68),
            "deep": _from_hsv(_toward(h, 0.72, 0.12), s * 1.35, v * 0.5),
            "under": _from_hsv(_toward(h, 0.72, 0.15), s * 1.1, v * 0.34),
            "out": _from_hsv(_toward(h, 0.72, 0.22), s * 1.4, v * 0.19)}


def _ring_of(px: np.ndarray) -> np.ndarray:
    a = px[..., 3] > 0
    p = np.pad(a, 1)
    return (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a


def _over(dst: np.ndarray, src: np.ndarray) -> None:
    """Opaque pixels of `src` over `dst` (soft shadows blend)."""
    solid = src[..., 3] == 255
    dst[solid] = src[solid]
    soft = (src[..., 3] > 0) & ~solid & (dst[..., 3] == 0)
    dst[soft] = src[soft]


def _trunk_layer(w: int, h: int, cx: int, top: int, bottom: int, rnd: random.Random, wide: int = 3) -> np.ndarray:
    """A trunk that flares into three roots at the ground, lit on the left, with a groove or two of bark."""
    t = Fig(w, h)
    flare = 4
    for y in range(top, bottom + 1):
        k = max(0, y - (bottom - flare))  # rows into the flare
        half = wide + (k * k) / 4.0
        t.rect(cx - half, y, cx + half - 1, y, BARK)
        t.rect(cx + half - 2, y, cx + half - 1, y, BARK_DARK)
        t.set(cx - half, y, BARK_LIGHT)
    for x0, x1 in ((cx - 2, cx - 4), (cx + 1, cx + 3)):  # the clefts between the roots
        t.line(x0, bottom - flare + 1, x1, bottom, BARK_OUT)
    t.rect(cx - 1, bottom - 1, cx, bottom, BARK_DARK)
    for x in (cx - 2, cx + 1):  # bark grooves
        y0 = top + rnd.randint(4, 7)
        t.rect(x, y0, x, y0 + rnd.randint(2, 3), BARK_DEEP)
    t.rect(cx - wide, top, cx + wide - 1, top + 3, BARK_DEEP)  # in the crown's shade
    t.px[_ring_of(t.px)] = BARK_OUT
    return t.px


def _sway(i: int, amp: float, phase: float) -> int:
    return int(round(amp * math.sin(2 * math.pi * i / TREE_FRAMES + phase)))


def _fruit(base: str) -> list[tuple[int, int, RGBA]]:
    d, b, l = _ramp(base)
    return [(1, 0, b), (2, 0, b), (0, 1, b), (1, 1, l), (2, 1, b), (3, 1, b), (0, 2, b), (1, 2, b), (2, 2, b),
            (3, 2, d), (1, 3, d), (2, 3, d)]


def _blossom(petal: RGBA, heart: RGBA) -> list[tuple[int, int, RGBA]]:
    return [(1, 0, petal), (0, 1, petal), (1, 1, heart), (2, 1, petal), (1, 2, petal)]


TREE_SIZES = {"big": (15.5, 14.5, 13.5, 4, 41), "small": (19.0, 11.5, 10.5, 3, 41)}  # crown cy, rx, ry; trunk half width, ground
LEAF_MOTIF = ((1, 0, "a"), (2, 0, "a"), (0, 1, "a"), (1, 1, "a"), (2, 1, "a"), (3, 1, "b"), (1, 2, "b"), (2, 2, "c"))


def _crown(w: int, h: int, cx: float, cy: float, rx: float, ry: float, rnd: random.Random, P: dict[str, RGBA]) -> np.ndarray:
    """The still crown: a scalloped oval filled with overlapping leaves lit from the top left, a shaded lower edge
    and ragged leaf tips round the top and sides."""
    ys, xs = np.mgrid[0:h, 0:w]
    X, Y = xs + 0.5, ys + 0.5
    m = ((X - cx) / (rx - 1.5)) ** 2 + ((Y - cy) / (ry - 1.5)) ** 2 <= 1
    n = 9
    for k in range(n):  # bumps round the edge
        a = 2 * math.pi * (k + rnd.uniform(-0.25, 0.25)) / n
        bx, by, r = cx + (rx - 3.4) * math.cos(a), cy + (ry - 3.4) * math.sin(a), rnd.uniform(3.2, 4.3)
        m |= ((X - bx) / r) ** 2 + ((Y - by) / r) ** 2 <= 1
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[m] = P["base"]
    tones = {"light": {"a": P["light"], "b": P["base"], "c": P["shade"]},
             "mid": {"a": P["base"], "b": P["base"], "c": P["shade"]},
             "dark": {"a": P["shade"], "b": P["shade"], "c": P["deep"]}}
    for row, ay in enumerate(range(int(cy - ry), int(cy + ry) + 1, 3)):  # leaves in staggered rows
        for ax in range(int(cx - rx) - 2 + (2 if row % 2 else 0), int(cx + rx) + 1, 4):
            jx, jy = ax + rnd.randint(0, 1), ay + rnd.randint(-1, 0)
            score = -0.55 * (jx - cx) / rx - (jy - cy) / ry + rnd.uniform(-0.4, 0.4)
            tone = tones["light" if score > 0.3 else "mid" if score > -0.5 else "dark"]
            for ox, oy, role in LEAF_MOTIF:
                x, y = jx + ox, jy + oy
                if 0 <= x < w and 0 <= y < h and m[y, x]:
                    img[y, x] = tone[role]
    for y0, steps in ((cy + ry * 0.5, (("light", "base"), ("base", "shade"))),
                      (cy + ry * 0.78, (("shade", "deep"), ("base", "deep")))):
        low = np.zeros((h, w), dtype=bool)
        low[int(y0):] = True
        for a, b in steps:  # the crown's lower edge is in its own shade
            img[low & np.all(img == P[a], axis=-1)] = P[b]
    for x in range(w):  # leaf tips: up along the top, out along the sides
        col = np.nonzero(m[:, x])[0]
        if len(col) and col[0] > 0 and (x * 5 + 1) % 3 == 0 and col[0] < cy:
            img[col[0] - 1, x] = P["light"] if x < cx else P["base"]
    for y in range(h):
        row_ = np.nonzero(m[y])[0]
        if len(row_) and y < cy + ry * 0.55 and (y * 7) % 3 == 0:
            if row_[0] > 0:
                img[y, row_[0] - 1] = P["base"]
            if row_[-1] < w - 1:
                img[y, row_[-1] + 1] = P["shade"]
    return img


def _sheared(img: np.ndarray, bands: list[tuple[int, int, int]]) -> np.ndarray:
    """Rows moved sideways, (first row, end row, dx) per band: the crown bending in the wind."""
    out = img.copy()
    for y0, y1, dx in bands:
        if dx:
            out[y0:y1] = np.roll(img[y0:y1], dx, axis=1)
    return out


def paint_tree(g: Fig, color: str, anim: str, i: int, kind: str = "oak", seed: int = 0, size: str = "big") -> None:
    if kind == "pine":
        paint_pine(g, color, anim, i, seed=seed, size=size)
        return
    rnd = _rng("tree", kind, size, seed)
    P = foliage(color)
    w, h = g.w, g.h
    cx = w / 2
    cy, rx, ry, wide, ground = TREE_SIZES[size]
    crown = _crown(w, h, cx, cy, rx, ry, rnd, P)
    solid = crown[..., 3] > 0

    def stamp(fx: float, fy: float, motif: list[tuple[int, int, RGBA]]) -> None:
        for ox, oy, k in motif:
            X, Y = int(fx) + ox, int(fy) + oy
            if 0 <= X < w and 0 <= Y < h and solid[Y, X]:
                crown[Y, X] = k

    if kind == "fruit":
        fruit = _fruit(FRUIT_COLORS[seed % len(FRUIT_COLORS)])
        for fx, fy in ((cx - 9, cy - 4), (cx + 3, cy - 9), (cx + 7, cy - 1), (cx - 3, cy + 1), (cx - 11, cy + 4),
                       (cx + 5, cy + 5), (cx - 2, cy - 5)):
            stamp(fx + rnd.randint(0, 1), fy, fruit)
        for fx, fy in ((cx - 6, cy - 9), (cx + 8, cy - 6), (cx + 1, cy + 3)):
            stamp(fx, fy, _blossom(WHITE, _c("#ffd84a")))
    elif kind == "blossom":
        for _ in range(18):
            fx, fy = cx + rnd.uniform(-rx + 2, rx - 3), cy + rnd.uniform(-ry + 2, ry * 0.5)
            stamp(fx, fy, _blossom(WHITE if rnd.random() < 0.55 else P["light"],
                                   _c("#ffe070") if rnd.random() < 0.5 else P["shade"]))
    cf = Fig(w, h)
    cf.px = crown
    top = int(cy + ry * 0.45)
    cf.ellipse(cx, cy + ry * 0.86, 5.5, 2.6, P["under"])  # the dark underside where the trunk goes in
    for side in (-1, 1):  # two branches forking out of the trunk into the lower crown
        x0, y0, x1, y1 = cx - 0.5 + side * 2, cy + ry * 0.92, cx + side * 6.5, cy + ry * 0.55
        cf.line(x0, y0, x1, y1, BARK_OUT, 2)
        cf.line(x0 + (0 if side < 0 else 1), y0, x1 + (0 if side < 0 else 1), y1, BARK if side < 0 else BARK_DARK, 1)
    if anim == "idle":  # the top of the crown sways most, the middle follows a little behind
        s_top, s_mid = _sway(i, 1.0, 0.0), _sway(i, 0.6, -1.0)
        crown = _sheared(crown, [(0, int(cy - ry * 0.25), s_top), (int(cy - ry * 0.25), int(cy + ry * 0.3), s_mid)])
    crown[_ring_of(crown)] = P["out"]
    g.ellipse(cx, ground, wide * 2.4, 2.4, GROUND_SHADOW)
    _over(g.px, _trunk_layer(w, h, int(cx), top, ground, rnd, wide))
    _over(g.px, crown)


def paint_pine(g: Fig, color: str, anim: str, i: int, seed: int = 0, size: str = "big", snow: bool = False) -> None:
    """A fir: tiers of boughs with ragged hems, lit on the left; the top tiers sway in the wind."""
    rnd = _rng("pine", size, seed)
    P = foliage(color)
    w, h = g.w, g.h
    cx = w / 2
    ground = h - 3
    tiers = ((3, 4.5), (9, 7.0), (16, 9.5), (24, 11.5)) if size == "big" else ((8, 4.0), (14, 6.5), (21, 9.0))
    g.ellipse(cx, ground, 8, 2.4, GROUND_SHADOW)
    _over(g.px, _trunk_layer(w, h, int(cx), tiers[-1][0] + 6, ground, rnd, 2))
    crown = np.zeros((h, w, 4), dtype=np.uint8)
    ys, xs = np.mgrid[0:h, 0:w]
    for k, (y, half) in enumerate(tiers):
        dx = _sway(i, (1.0, 1.0, 0.6, 0.0)[k], -0.4 * k) if anim == "idle" else 0
        tx = cx + dx
        bottom = y + 8
        hem = np.array([((x * 7 + k * 3) % 4 == 0) * 1.0 for x in range(w)])  # ragged lower edge
        inside = (ys + 0.5 >= y - 4) & (ys + 0.5 <= bottom - hem[xs]) & (np.abs(xs + 0.5 - tx) <= half * (ys + 0.5 - (y - 4)) / 12 + 0.5)
        crown[inside] = P["base"]
        right = inside & (xs + 0.5 - tx > (ys + 0.5 - y) * 0.15 + 0.5)
        crown[right] = P["shade"]
        crown[inside & (ys + 0.5 > bottom - 2 - hem[xs])] = P["deep"]
        for j in range(3):  # lit needles on the left
            lx, ly = int(round(tx - 1 - j * half / 4)), int(round(y - 1 + j * 2.4))
            if 0 <= lx < w and 0 <= ly < h and inside[ly, lx]:
                crown[ly, lx] = P["light"]
                if lx + 1 < w and inside[ly, lx + 1]:
                    crown[ly, lx + 1] = P["light"]
        if snow:  # snow on each tier's top, a little blue in its shade
            cap = inside & (ys + 0.5 < y + 1 + (np.abs(xs + 0.5 - tx) * 0.35)) & (ys + 0.5 > y - 4)
            crown[cap] = SNOW
            crown[cap & (xs + 0.5 > tx + 1)] = SNOW_SHADE
            for x in range(int(tx - half * 0.7), int(tx + half * 0.7)):
                if (x + k) % 3 == 0:
                    yy = int(bottom - 3)
                    if 0 <= x < w and inside[yy, x]:
                        crown[yy, x] = SNOW
    crown[_ring_of(crown)] = P["out"]
    _over(g.px, crown)


FRUIT_COLORS = ["#ff9a2a", "#e83a3a", "#ffd84a"]
SNOW, SNOW_SHADE = _c("#f8fbff"), _c("#c8d8ec")


def paint_snowy_pine(g: Fig, color: str, anim: str, i: int, seed: int = 0) -> None:
    paint_pine(g, color, "still", i, seed=seed, snow=True)


def paint_bare_tree(g: Fig, color: str, anim: str, i: int, seed: int = 0) -> None:
    """A winter tree: forked branches with snow along their tops."""
    rnd = _rng("bare", seed)
    w, h = g.w, g.h
    cx, ground = w // 2, h - 3
    g.ellipse(cx, ground, 9, 2.4, GROUND_SHADOW)
    _over(g.px, _trunk_layer(w, h, cx, 20, ground, rnd, 3))
    b = Fig(w, h)
    limbs = [((cx - 1, 22), (cx - 9, 10), 2), ((cx + 1, 21), (cx + 9, 8), 2), ((cx, 21), (cx + 1, 4), 2),
             ((cx - 6, 14), (cx - 12, 12), 1), ((cx + 6, 13), (cx + 13, 13), 1), ((cx - 8, 11), (cx - 7, 4), 1),
             ((cx + 8, 10), (cx + 6, 3), 1), ((cx + 1, 9), (cx - 3, 2), 1), ((cx + 1, 8), (cx + 5, 1), 1)]
    for (x0, y0), (x1, y1), wd in limbs:
        b.line(x0, y0, x1, y1, BARK if wd > 1 else BARK_DARK, wd)
    tops = []
    for (x0, y0), (x1, y1), wd in limbs:  # snow on the upper side of each limb
        n = max(abs(x1 - x0), abs(y1 - y0))
        for k in range(2, n + 1, 2):
            x, y = int(round(x0 + (x1 - x0) * k / n)), int(round(y0 + (y1 - y0) * k / n)) - 1
            tops.append((x, y))
    b.px[_ring_of(b.px)] = BARK_OUT
    for x, y in tops:
        if 0 <= x < w and 0 <= y < h:
            b.px[y, x] = SNOW
    _over(g.px, b.px)


def paint_palm(g: Fig, color: str, anim: str, i: int, seed: int = 0) -> None:
    """A palm: a curved ringed trunk and drooping fronds that sway, coconuts under the crown."""
    P = foliage(color)
    w, h = g.w, g.h
    cx, ground = w // 2, h - 3
    sway = _sway(i, 1.0, 0.0) if anim == "idle" else 0
    g.ellipse(cx, ground, 8, 2.4, GROUND_SHADOW)
    t = Fig(w, h)
    for k, y in enumerate(range(13, ground + 1)):
        x = cx + 2 - (y - 13) ** 0.5 * 0.9 + (ground - y) * 0.05
        t.rect(x - 2, y, x + 1, y, _c("#c8945a") if (y // 2) % 2 else _c("#a87444"))
        t.set(x + 1, y, _c("#8a5a34"))
    t.px[_ring_of(t.px)] = BARK_OUT
    _over(g.px, t.px)
    top = (cx + 1 + sway, 12)
    f = Fig(w, h)
    for dx, dy, droop in ((-14, 3, 4), (14, 3, 4), (-11, -4, 3), (11, -5, 3), (-3, -10, 1), (5, -9, 1)):
        n = 10
        for k in range(n + 1):  # a frond: an arc that droops toward its tip, thinning out
            u = k / n
            x = top[0] + dx * u + (sway if u > 0.6 else 0)
            y = top[1] + dy * u + droop * u * u * 2
            wd = 3 if u < 0.6 else 2
            f.rect(x - 1, y - 1, x - 2 + wd, y - 2 + wd, P["base"])
            f.set(x, y + 1, P["shade"])
            if k % 2 == 0 and u > 0.2:
                f.set(x, y - 1, P["light"])
    f.px[_ring_of(f.px)] = P["out"]
    for fx in (-2, 1):
        f.ellipse(top[0] + fx, top[1] + 3, 1.7, 1.7, _c("#7a4a2a"))
        f.set(top[0] + fx - 1, top[1] + 2, _c("#a8703a"))
    _over(g.px, f.px)


def paint_cactus(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.ellipse(8, 23, 6, 1.5, _c("#2c5a30", 110))
    g.rect(5, 4, 10, 22, b)
    g.ellipse(7.5, 4, 2.6, 2, b)
    g.rect(9, 5, 10, 22, d)
    g.rect(6, 5, 6, 21, l)
    g.rect(0, 10, 4, 12, b)
    g.rect(0, 6, 2, 11, b)
    g.rect(11, 13, 15, 15, b)
    g.rect(13, 8, 15, 14, d)
    for y in range(7, 22, 4):
        g.set(7, y, _c("#f8f0d0"))
    g.set(8, 2, _c("#ff8fb4"))
    _out(g)


def paint_stump(g: Fig, color: str, anim: str, i: int) -> None:
    """What a felled tree leaves: a sawn top with rings, roots splayed into the grass."""
    t = Fig(g.w, g.h)
    t.rect(4, 6, 11, 12, BARK)
    t.rect(10, 6, 11, 12, BARK_DARK)
    t.rect(4, 7, 4, 11, BARK_LIGHT)
    t.poly([(4, 9), (1, 13.5), (6, 13.5)], BARK)  # roots
    t.poly([(11, 9), (14.5, 13.5), (9, 13.5)], BARK_DARK)
    t.line(7, 10, 6, 13, BARK_OUT)
    t.ellipse(7.5, 6, 4.4, 2.2, _c("#e8b070"))  # the sawn top and its rings
    t.ellipse(7.5, 6, 2.8, 1.3, _c("#c88850"))
    t.ellipse(7.5, 6, 1.2, 0.6, _c("#e8b070"))
    t.rect(4, 7, 11, 7, BARK_DEEP)
    t.px[_ring_of(t.px)] = BARK_OUT
    g.ellipse(8, 13.5, 7, 2, GROUND_SHADOW)
    _over(g.px, t.px)


def paint_boulder(g: Fig, color: str, anim: str, i: int) -> None:
    """A rock: facets lit from the top left, a crack, a little moss on top."""
    d, b, l = _ramp(color)
    g.ellipse(8, 13.5, 7, 2, GROUND_SHADOW)
    g.ellipse(8, 9, 7, 5.4, d)
    g.ellipse(7.5, 8.2, 6.4, 4.6, b)
    g.ellipse(5.8, 6.6, 3.2, 2.2, l)
    g.rect(4, 6, 6, 6, WHITE)
    g.line(9, 7, 11, 10, d)  # a crack
    g.set(12, 10, d)
    g.rect(3, 12, 13, 12, d)
    for x, c in ((7, CROP_LEAF["B"]), (8, CROP_LEAF["L"]), (9, CROP_LEAF["B"]), (10, CROP_LEAF["M"])):  # moss
        g.set(x, 4, c)
    g.set(8, 3, CROP_LEAF["L"])
    _out(g)


# furniture ---------------------------------------------------------------------------------------

def paint_bed(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.rect(1, 1, 14, 6, WOOD)  # headboard
    g.rect(1, 1, 14, 2, WOOD_LIGHT)
    g.rect(2, 5, 13, 29, _c("#f4ece0"))  # sheet
    g.rect(3, 6, 12, 10, WHITE)  # pillow
    g.rect(3, 10, 12, 10, _c("#d8d0c8"))
    g.rect(2, 12, 13, 28, b)  # blanket
    g.rect(2, 12, 13, 13, l)
    g.rect(12, 14, 13, 28, d)
    for y in (17, 22):
        g.rect(2, y, 13, y, d)
    g.rect(1, 28, 14, 31, WOOD_DARK)  # footboard
    _out(g)


def paint_fireplace(g: Fig, color: str, anim: str, i: int) -> None:
    brick, mortar = _c("#c8643a"), _c("#8a3e24")
    g.rect(2, 0, 29, 31, brick)
    for y in range(0, 32, 4):
        g.rect(2, y, 29, y, mortar)
        for x in range(2 + (4 if (y // 4) % 2 else 0), 30, 8):
            g.rect(x, y, x, y + 3, mortar)
    g.rect(0, 12, 31, 14, WOOD)  # mantel
    g.rect(0, 12, 31, 12, WOOD_LIGHT)
    g.rect(7, 17, 24, 31, _c("#2a1e2e"))  # the hearth
    g.rect(8, 28, 23, 31, _c("#5a3a2a"))
    k = i % 4
    flame = (_c("#ffb02e"), _c("#ff6a2a"), _c("#fff0a0"))
    for n, (fx, h) in enumerate(((11, 7), (15, 9), (19, 6))):
        hh = h + (0, 1, 0, -1)[(k + n) % 4]
        g.poly([(fx - 2, 28), (fx + 2, 28), (fx + (n - 1), 28 - hh)], flame[n % 2])
        g.poly([(fx - 1, 28), (fx + 1, 28), (fx, 28 - hh // 2)], flame[2])
    g.rect(9, 27, 22, 28, WOOD_DARK)  # logs
    g.rect(6, 8, 9, 11, _c("#e0c060"))  # a candle and a frame on the mantel
    g.rect(20, 5, 27, 11, WOOD_DARK)
    g.rect(21, 6, 26, 10, _c("#8ab0ff"))
    _out(g)


def paint_table(g: Fig, color: str, anim: str, i: int) -> None:
    g.ellipse(16, 22, 13, 2, _c("#2a1e2e", 70))
    g.rect(1, 4, 30, 13, WOOD)  # top
    g.rect(1, 4, 30, 5, WOOD_LIGHT)
    g.rect(1, 13, 30, 14, WOOD_DARK)
    g.rect(3, 15, 5, 22, WOOD_DARK)  # legs
    g.rect(26, 15, 28, 22, WOOD_DARK)
    g.rect(9, 6, 22, 11, WHITE)  # a cloth, a vase of flowers
    g.rect(14, 2, 17, 7, _c("#8ab0ff"))
    g.set(14, 1, _c("#ff8fb4"))
    g.set(16, 0, _c("#ffd84a"))
    g.set(17, 1, _c("#ff8fb4"))
    _out(g)


def paint_chair(g: Fig, color: str, anim: str, i: int) -> None:
    g.rect(3, 0, 12, 9, WOOD)  # back
    g.rect(4, 1, 11, 2, WOOD_LIGHT)
    g.rect(5, 4, 10, 7, WOOD_DARK)
    g.rect(2, 9, 13, 13, WOOD_LIGHT)  # seat
    g.rect(3, 13, 4, 19, WOOD_DARK)
    g.rect(11, 13, 12, 19, WOOD_DARK)
    _out(g)


def paint_dresser(g: Fig, color: str, anim: str, i: int) -> None:
    g.rect(1, 4, 22, 23, WOOD)
    g.rect(1, 4, 22, 5, WOOD_LIGHT)
    for y in (8, 14, 20):
        g.rect(3, y - 2, 20, y + 1, WOOD_DARK)
        g.rect(4, y - 1, 19, y, WOOD_LIGHT)
        g.rect(10, y - 1, 13, y - 1, _c("#ffd84a"))
    g.rect(5, 0, 9, 4, _c("#c84a3a"))  # a jar and a book on top
    g.rect(13, 1, 19, 4, _c("#4a7ad0"))
    _out(g)


def paint_potted_plant(g: Fig, color: str, anim: str, i: int) -> None:
    d, b, l = _ramp(color)
    g.rect(4, 16, 11, 23, _c("#c8643a"))
    g.rect(3, 15, 12, 17, _c("#e0804a"))
    for (x0, y0, x1, y1) in ((8, 15, 3, 4), (8, 15, 12, 2), (8, 15, 8, 0), (8, 15, 1, 10), (8, 15, 14, 9)):
        g.line(x0, y0, x1, y1, d, 2)
        g.ellipse(x1, y1, 2.4, 1.8, b)
        g.set(x1 - 1, y1 - 1, l)
    _out(g)


# animals ------------------------------------------------------------------------------------------

# Farm animals: soft white coats shaded cool grey-blue, warm patches, a dark plum outline and a soft shadow.
COAT, COAT_SHADE, COAT_DEEP = _c("#fffaf2"), _c("#c7cfde"), _c("#8a9db8")
COMB, COMB_DARK = _c("#eb262e"), _c("#a8121c")
BEAK, BEAK_DARK = _c("#ff9d0e"), _c("#ee6a0e")
ANIMAL_OUT = _c("#1c0a18")


def _coat(color: str) -> tuple[RGBA, RGBA, RGBA, RGBA]:
    """light, base, shade, deep of an animal's coat: near-white coats shade cool, others shade from their colour."""
    if sum(_c(color)[:3]) > 640:
        return WHITE, COAT, COAT_SHADE, COAT_DEEP
    d, b, l = _ramp(color)
    return l, b, d, tuple(int(c * 0.7) for c in d[:3]) + (255,)


def _animal_out(g: Fig) -> None:
    g.px[_ring_of(g.px) & (g.px[..., 3] == 0)] = ANIMAL_OUT


def paint_chicken(g: Fig, color: str, anim: str, i: int) -> None:
    L, B, S, D = _coat(color)
    k = i % 4
    peck = anim == "idle" and i % 2 == 1
    hop = (0, 1, 0, 1)[k] if anim == "run" else 0
    body = Fig(g.w, g.h)
    lift = ((1, 0), (0, 0), (0, 1), (0, 0))[k] if anim == "run" else (0, 0)
    for x, up in ((6, lift[0]), (9, lift[1])):  # legs and toes
        body.rect(x, 12 - hop, x, 13 - up, BEAK)
        body.rect(x - 1, 14 - up, x + 1, 14 - up, BEAK_DARK)
    body.ellipse(3.2, 6.6 - hop, 2.2, 3.2, S)  # tail feathers, up at the back
    body.ellipse(3.6, 6.0 - hop, 1.4, 2.4, B)
    body.set(2, 3 - hop, D)
    body.set(4, 3 - hop, S)
    body.ellipse(7.5, 9.5 - hop, 5.6, 3.7, B)  # body
    body.rect(3, 11 - hop, 12, 12 - hop, S)  # the underside in shade
    body.ellipse(7.5, 12.4 - hop, 4.2, 1.0, S)
    body.rect(5, 7 - hop, 9, 7 - hop, L)  # lit back
    body.ellipse(6.6, 9.6 - hop, 3.0, 1.8, S)  # wing
    body.rect(5, 8 - hop, 8, 8 - hop, B)
    body.set(4, 10 - hop, D)
    hx, hy = (12, 6 - hop) if not peck else (13, 9 - hop)
    body.ellipse(hx, hy, 2.6, 2.6, B)  # head
    body.set(hx - 1, hy - 1, L)
    for dx, dy in ((-1, -3), (0, -3), (1, -3), (0, -4)):  # comb
        body.set(hx + dx, hy + dy, COMB)
    body.set(hx - 1, hy - 2, COMB_DARK)
    body.rect(hx + 2, hy, hx + 3, hy, BEAK)  # beak and wattle
    body.set(hx + 3, hy + 1, BEAK_DARK)
    body.set(hx + 1, hy + 2, COMB)
    body.set(hx + 1, hy - 1, ANIMAL_OUT)  # eye
    _animal_out(body)
    g.ellipse(7.5, 14.6, 5.2, 1.3, GROUND_SHADOW)
    _over(g.px, body.px)


def paint_chick(g: Fig, color: str, anim: str, i: int) -> None:
    hop = (0, 1)[i % 2] if anim == "run" else 0
    yel, yel_l, yel_d = _c("#ffd84a"), _c("#fff08a"), _c("#e0a830")
    body = Fig(g.w, g.h)
    body.rect(4, 9, 4, 10, BEAK)
    body.rect(7, 9 - hop, 7, 10, BEAK)
    body.ellipse(5.5, 7 - hop, 3.6, 2.9, yel)  # body
    body.rect(3, 8 - hop, 8, 9 - hop, yel_d)
    body.ellipse(7.6, 4.4 - hop, 2.5, 2.3, yel)  # head
    body.set(7, 3 - hop, yel_l)
    body.set(5, 6 - hop, yel_l)
    body.ellipse(4.6, 7 - hop, 1.6, 1.1, yel_d)  # wing
    body.set(8, 4 - hop, ANIMAL_OUT)
    body.rect(10, 5 - hop, 10, 5 - hop, BEAK_DARK)
    _animal_out(body)
    g.ellipse(6, 11, 3.8, 0.9, GROUND_SHADOW)
    _over(g.px, body.px)


def paint_cow(g: Fig, color: str, anim: str, i: int) -> None:
    pd, pb, pl = _ramp(color)
    k = i % 4
    step = ((1, -1), (0, 0), (-1, 1), (0, 0))[k] if anim == "run" else (0, 0)
    chew = anim == "idle" and i % 2 == 1
    pink, pink_d = _c("#ffa399"), _c("#ff7073")
    body = Fig(g.w, g.h)
    for x, s, col in ((7, step[0], COAT), (11, step[1], COAT_SHADE), (20, step[1], COAT), (24, step[0], COAT_SHADE)):
        body.rect(x + s, 16, x + 1 + s, 20, col)  # legs and hooves
        body.rect(x + s, 21, x + 1 + s, 22, _c("#3a2a30"))
    body.ellipse(15, 12, 11, 6, COAT)  # body
    body.ellipse(15, 16.6, 9.5, 1.6, COAT_SHADE)  # the belly in shade
    body.rect(8, 7, 20, 7, WHITE)  # the lit back
    for (x, y, rx, ry) in ((10.5, 10, 4, 3), (19.5, 13.5, 3.4, 2.4), (16, 7.6, 2.2, 1.4)):  # patches
        body.ellipse(x, y, rx, ry, pb)
        body.ellipse(x + 0.8, y + 0.9, rx * 0.75, ry * 0.6, pd)
        body.set(x - rx * 0.4, y - ry * 0.4, pl)
    body.ellipse(14, 17, 2.5, 1, pink)  # udder
    body.set(14, 18, pink_d)
    body.line(4, 10, 2, 15, COAT_SHADE)  # tail with a tuft
    body.rect(1, 15, 2, 16, pb)
    hy = 9 + (1 if chew else 0)
    body.ellipse(26, hy, 4.4, 4, COAT)  # head
    body.rect(23, hy + 1, 26, hy + 2, COAT_SHADE)
    body.ellipse(25, hy - 2, 2.2, 1.6, pb)
    body.ellipse(28.5, hy + 2, 2.6, 2, pink)  # muzzle
    body.rect(27, hy + 3, 30, hy + 3, pink_d)
    body.set(28, hy + 2, pink_d)
    body.set(30, hy + 2, pink_d)
    body.set(26, hy - 1, ANIMAL_OUT)  # eye
    body.set(25, hy - 2, WHITE)
    body.rect(22, hy - 4, 23, hy - 3, _c("#f0e6c8"))  # horns
    body.rect(28, hy - 5, 29, hy - 4, _c("#f0e6c8"))
    body.rect(20, hy - 2, 22, hy - 1, pb)  # ear
    body.set(21, hy - 1, pink)
    _animal_out(body)
    g.ellipse(16, 23, 12, 1.4, GROUND_SHADOW)
    _over(g.px, body.px)


# pests, in the same 16 px style (side views, facing right) ---------------------------------------

def paint_crow(g: Fig, color: str, anim: str, i: int) -> None:
    """A crow: glossy black with a blue sheen, orange beak and legs; it hops and flaps when it runs."""
    d, b, l = _ramp(color)
    sheen, deep = _c("#7a78b8"), tuple(int(c * 0.6) for c in d[:3]) + (255,)
    k = i % 4
    hop = (0, 2, 3, 1)[k] if anim == "run" else 0
    flap = anim == "run" and k in (1, 2)
    peck = anim == "idle" and i % 2 == 1
    body = Fig(g.w, g.h)
    for x in (6, 9):  # legs and toes
        body.rect(x, 12 - hop, x, 13 - hop, BEAK)
        body.rect(x, 14 - hop, x + 1, 14 - hop, BEAK_DARK)
    body.poly([(3, 7.5 - hop), (-0.5, 6 - hop), (0, 9 - hop), (3, 10.5 - hop)], deep)  # tail
    body.ellipse(7, 9.2 - hop, 5, 3.5, b)  # body
    body.rect(4, 11 - hop, 10, 12 - hop, d)
    body.rect(5, 6 - hop, 8, 6 - hop, l)
    if flap:  # a wing raised
        body.poly([(4.5, 8 - hop), (2, 0.5 - hop), (6, 2 - hop), (9, 7.5 - hop)], deep)
        body.line(3, 2 - hop, 6, 7 - hop, sheen)
    else:
        body.ellipse(6, 9.6 - hop, 3.4, 2.1, deep)
        body.rect(4, 8 - hop, 8, 8 - hop, sheen)
    hx, hy = (12, 6 - hop) if not peck else (12.5, 8.5)
    body.ellipse(hx, hy, 2.8, 2.6, b)  # head
    body.set(hx - 1, hy - 2, sheen)
    body.rect(hx + 2, hy, hx + 3.5, hy, BEAK)  # beak
    body.set(hx + 3, hy + 1, BEAK_DARK)
    body.set(hx + 1, hy - 1, WHITE)  # eye
    body.set(hx + 1, hy, ANIMAL_OUT)
    _animal_out(body)
    g.ellipse(8, 14.8, 4.4, 1.0, GROUND_SHADOW)
    _over(g.px, body.px)


def paint_fox(g: Fig, color: str, anim: str, i: int) -> None:
    """A fox: orange with a white chest, muzzle and tail tip, dark socks and ears; it trots when it runs."""
    d, b, l = _ramp(color)
    sock = _c("#4a2123")
    k = i % 4
    step = ((1, -1), (0, 0), (-1, 1), (0, 0))[k] if anim == "run" else (0, 0)
    bob = (0, 1, 0, 1)[k] if anim == "run" else 0
    wag = (0, 1)[i % 2] if anim == "idle" else 0
    body = Fig(g.w, g.h)
    for x, s_, col in ((5, step[0], d), (7, step[1], b), (11, step[1], d), (13, step[0], b)):  # legs
        body.rect(x + s_, 11, x + s_ + 1, 12, col)
        body.rect(x + s_, 13, x + s_ + 1, 14, sock)
    body.ellipse(3.2, 7.5 + bob - wag, 3.2, 2.4, b)  # the bushy tail, its white tip
    body.ellipse(3.6, 8.5 + bob - wag, 2.4, 1.2, d)
    body.ellipse(1.0, 6.2 + bob - wag, 1.6, 1.4, WHITE)
    body.ellipse(9.5, 9 + bob, 5.4, 3.0, b)  # body
    body.rect(6, 7 + bob, 12, 7 + bob, l)
    body.ellipse(10.5, 10.8 + bob, 3.2, 1.2, WHITE)  # chest and belly
    body.ellipse(14.2, 6.4 + bob, 3.0, 2.7, b)  # head
    body.set(13, 4 + bob, l)
    body.poly([(13.5, 7 + bob), (18, 7.5 + bob), (17, 9.5 + bob), (13.5, 9 + bob)], WHITE)  # muzzle and cheek
    body.set(17, 7 + bob, ANIMAL_OUT)  # nose
    body.poly([(11.5, 4.5 + bob), (12.5, 0.5 + bob), (14.5, 4 + bob)], d)  # ears
    body.poly([(13.5, 4.5 + bob), (15, 0.5 + bob), (16.5, 4.5 + bob)], b)
    body.set(15, 2 + bob, sock)
    body.set(15, 5.5 + bob, ANIMAL_OUT)  # eye
    body.set(14, 5 + bob, WHITE)
    _animal_out(body)
    g.ellipse(9, 14.8, 6.5, 1.1, GROUND_SHADOW)
    _over(g.px, body.px)


def paint_rabbit(g: Fig, color: str, anim: str, i: int) -> None:
    """A rabbit: long ears pink inside, a white belly and powder-puff tail; it bounds when it runs."""
    d, b, l = _ramp(color)
    pink = _c("#ffa3b8")
    k = i % 4
    hop = (0, 2, 3, 1)[k] if anim == "run" else 0
    twitch = anim == "idle" and i % 2 == 1
    lean = 1 if anim == "run" and k in (1, 2) else 0  # ears swept back mid-leap
    body = Fig(g.w, g.h)
    body.ellipse(6.5, 12.6 - hop, 2.8, 1.5, d)  # hind foot
    body.rect(10, 13 - hop, 11, 13 - hop, d)  # front paw
    body.ellipse(7, 10.4 - hop, 4.6, 3.3, b)  # body
    body.ellipse(7.8, 11.6 - hop, 3, 1.4, WHITE)  # belly
    body.rect(4, 8 - hop, 8, 8 - hop, l)
    body.ellipse(2.6, 9.4 - hop, 1.8, 1.7, WHITE)  # tail
    body.ellipse(11.2, 7 - hop, 3, 2.7, b)  # head
    body.ellipse(12.4, 8.2 - hop, 1.6, 1.0, WHITE)  # cheek
    for x0, col in ((9, b), (11, d)):  # ears
        top = 0 + (1 if twitch and x0 == 11 else 0)
        body.line(x0 - lean, top - hop, x0, 4.5 - hop, col, 2)
    body.line(9 - lean, 1 - hop, 9, 3.5 - hop, pink)
    body.set(12, 6 - hop, ANIMAL_OUT)  # eye
    body.set(12, 5 - hop, WHITE)
    body.set(14, 7.5 - hop, pink)  # nose
    _animal_out(body)
    g.ellipse(8, 14.8, 4.4, 1.0, GROUND_SHADOW)
    _over(g.px, body.px)


def paint_mouse(g: Fig, color: str, anim: str, i: int) -> None:
    """A field mouse: round ears pink inside, a pointed snout, a long pink tail; it scurries when it runs."""
    d, b, l = _ramp(color)
    pink, pink_d = _c("#ffa3b8"), _c("#e07890")
    k = i % 4
    sc = (0, 1, 0, 1)[k] if anim == "run" else 0
    sniff = anim == "idle" and i % 2 == 1
    body = Fig(g.w, g.h)
    body.line(4, 12.5, 1, 11 - sc, pink_d)  # tail
    body.line(1, 11 - sc, 0, 8 + sc, pink_d)
    body.rect(6 + sc, 13, 7 + sc, 13, pink)  # feet
    body.rect(10 - sc, 13, 11 - sc, 13, pink)
    body.ellipse(8, 11.2, 4.6, 2.8, b)  # body
    body.ellipse(8.5, 12.4, 3, 1.0, l)  # belly
    body.rect(6, 9, 9, 9, l)
    body.ellipse(12, 10.6, 2.6, 2.2, b)  # head and snout
    body.poly([(13, 9.5), (15.5 + (0.5 if sniff else 0), 11.2), (13, 12.2)], b)
    body.set(15 + (1 if sniff else 0), 11, pink)  # nose
    body.ellipse(10.6, 8.0, 1.9, 1.9, l)  # ear
    body.ellipse(10.8, 8.2, 1.0, 1.0, pink)
    body.set(12.6, 10, ANIMAL_OUT)  # eye
    body.set(12, 9.5, WHITE)
    _animal_out(body)
    g.ellipse(8, 14.6, 4.6, 1.0, GROUND_SHADOW)
    _over(g.px, body.px)


PEST_KINDS = {"crow": ("crow", "#3a3448"), "raven": ("crow", "#3a3448"), "bird": ("crow", "#8a6a4a"),
              "sparrow": ("crow", "#a87a50"), "pigeon": ("crow", "#9aa0b4"), "magpie": ("crow", "#3a3448"),
              "fox": ("fox", "#e07a2a"), "wolf": ("fox", "#8a8a9a"), "coyote": ("fox", "#c09a6a"),
              "raccoon": ("fox", "#8a8090"), "dog": ("fox", "#b08050"), "rabbit": ("rabbit", "#d8c8b8"),
              "bunny": ("rabbit", "#f4ece0"), "hare": ("rabbit", "#c0a080"), "mouse": ("mouse", "#9a9aa8"),
              "rat": ("mouse", "#7a7484"), "mole": ("mouse", "#5a4a44"), "gopher": ("mouse", "#a07a50")}


def pest_kind(name: str) -> tuple[str, str] | None:
    """(farm sprite kind, colour) for a pest's name, or None when it is not a farm animal."""
    import re
    for w in reversed([w.lower() for w in re.findall(r"[A-Z][a-z]*|[a-z]+", name)]):
        if w in PEST_KINDS:
            return PEST_KINDS[w]
        if w.rstrip("s") in PEST_KINDS:
            return PEST_KINDS[w.rstrip("s")]
    return None


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


# Crops. Each kind of plant has a body drawn by hand in a little pixel grammar (L light, B base, M mid, D deep
# leaf), one body per stage, outlined in dark teal over a soft shadow; ripe plants carry their produce, outlined in
# its own dark. Stages: 0 seeds in a mound, 1 sprout, 2 young, 3 grown, 4 ripe.
CROP_LEAF = {"L": _c("#7bc04e"), "B": _c("#4ba837"), "M": _c("#2f8a3e"), "D": _c("#106d54")}
CROP_OUT = _c("#052a3a")
CROP_SOIL = (_c("#b07848"), _c("#d8a068"), _c("#4a2a18"))  # a mound of earth: base, lit top, outline

PLANT_ART: dict[str, tuple[tuple[str, ...], ...]] = {
    "sprout": (("....LL..LL....",
                "....BLL.LB....",
                ".....BBMB.....",
                ".......D......"),),
    "bush": (("......LL......",
              ".....LLBB.....",
              "..LL..BM..LL..",
              ".LLBB.MD.LBBM.",
              "..BBMMMDMMBM..",
              "....MMDDMM....",
              "......DD......"),
             ("......LLL.......",
              "...LL.LBBB.LL...",
              "..LLBBLBMBLLBB..",
              ".LLBBMBBMMBBBMM.",
              ".LBBMMLLBMMLBBM.",
              "..BMMLLBBBMLLBM.",
              ".LLBMBBBMMDLBBM.",
              ".LBBMMMMDDBBMMD.",
              "..BMMDMMDMBMMD..",
              "...MMDDMDDDMD...",
              ".....DD.DD......")),
    "blades": (("........L.....",
                "...L....B.....",
                "...BL..LB.....",
                "....B.LB..L...",
                "....BMB.MB....",
                ".....MMMM.....",
                "......MM......"),
               ("..........L.....",
                "...L......B.....",
                "...BL....LB.....",
                "....B..L.B..L...",
                "....BL.B.B.LB...",
                ".....B.BLB.B....",
                ".....BMBBMMB....",
                "......BMBMB.....",
                "......MMBMM.....",
                ".......MMM......",
                ".......MDM......")),
    "fronds": (("....L...L.....",
                "...LBL.LBL....",
                "....B.M.B.....",
                "..L..BMB..L...",
                ".LBL.MMM.LBL..",
                "..B.MMMMM.B...",
                ".....MDDM....."),
               ("......L..L......",
                ".....LBLLBL.....",
                "..L...BMMB...L..",
                ".LBL.L.MM.L.LBL.",
                "..B.LBLMMLBL.B..",
                "...B..BMMB..B...",
                ".L..BMMMMMMB..L.",
                "LBL..MMBBMM..LBL",
                ".B.MMMBMMBMMM.B.",
                "..MMMMMMMMMMMM..",
                "....MDDMMDDM....")),
    "corn": (("......L.......",
              "...L..B..L....",
              "...BL.B.LB....",
              "....BLBLB.....",
              ".....BMB......",
              "......M.......",
              "......D......."),
             ("......L.........",
              "......B.........",
              "...L..BL...L....",
              "...BL.BB..LB....",
              "....BLMB.LB.....",
              "......MBLB......",
              "..LL..MB........",
              "..LBB.MB..LL....",
              "....BBMMBLBB....",
              "......MM.BB.....",
              "......MM........",
              "......DM........",
              "......DD........")),
    "wheat": (("..L...L...L...",
               "..B..LB..LB...",
               "..BL.BB.LB....",
               "...B.BM.B.....",
               "...BMBMMB.....",
               "....MMMM......",
               ".....MD......."),
              ("..L...L...L.....",
               "..B..LB..LB..L..",
               ".LB..BB..BB.LB..",
               ".BB..BB..BB.BB..",
               ".BB..BM.LBM.BM..",
               "..BL.BM.BM.LB...",
               "..BB.BM.BM.BM...",
               "...BMBMMBMBM....",
               "...MMBMMMMMM....",
               "....MMMMMMM.....",
               ".....MMDDM......")),
    "vine": (("..............",
              "..LL......LL..",
              ".LLBB....LLBB.",
              "..BMMM..MMMM..",
              "....MMMMDM....",
              "......DD......"),
             ("................",
              "..LLB......LLB..",
              ".LLBBM....LLBBM.",
              ".LBBMM.LL.LBBMM.",
              "..BMMDLLBB.BMMD.",
              "...MDMBBMMMMDD..",
              ".LL.MMMMMDDM.LL.",
              "LLBBMMDDMMDMLLBB",
              ".BMMD..DD...BMMD",
              "..DD........DD..")),
    "cabbage": (("..............",
                 "....L..L......",
                 "...LBLLBL.....",
                 "..LBBMMBBL....",
                 "..BMMDDMMB....",
                 "...MDDDDM.....",
                 ".....DD......."),
                ("................",
                 "......L..L......",
                 "..L..LBLLBL..L..",
                 ".LBL.BBMMBB.LBL.",
                 ".BBBLBMMMMBLBBB.",
                 ".BMBBBMDDMBBBMB.",
                 "..MMBBMDDMBBMM..",
                 ".LMMMBMMMMBMMML.",
                 "LBBMMMMDDMMMMBBL",
                 ".BMMDDMMMMDDMMB.",
                 "..DD..DDDD..DD..")),
}
FAMILY = {"strawberry": "bush", "tomato": "bush", "eggplant": "bush", "blueberry": "bush", "berry": "bush",
          "potato": "bush", "onion": "blades", "carrot": "fronds", "turnip": "fronds", "corn": "corn",
          "wheat": "wheat", "pumpkin": "vine", "cabbage": "cabbage"}


def _stamp(px: np.ndarray, art: tuple[str, ...], bottom: int, colors: dict[str, RGBA]) -> None:
    """Pixel-grammar rows into the frame, centred, the last row on `bottom`."""
    h, w = px.shape[:2]
    top = bottom - len(art) + 1
    for r, row in enumerate(art):
        x0 = (w - len(row)) // 2
        for k, ch in enumerate(row):
            if ch in colors and 0 <= top + r < h and 0 <= x0 + k < w:
                px[top + r, x0 + k] = colors[ch]


def _outlined(px: np.ndarray, col: RGBA) -> np.ndarray:
    px = px.copy()
    px[_ring_of(px)] = col
    return px


def _produce(kind: str, color: str) -> tuple[dict[str, RGBA], list[tuple[str, ...]], list[tuple[int, int]]]:
    """What a ripe plant carries: colours, a little picture (p base, q light, r dark, g leaf), and where it hangs."""
    d, b, l = _ramp(color)
    cols = {"p": b, "q": l, "r": d, "g": CROP_LEAF["L"], "w": WHITE, "s": _c("#ffe0a0")}
    berry = ("pp", "qp")
    if kind == "strawberry":
        return cols, [("gg.", "ppr", "sp.", ".r.")], [(2, 8), (10, 6), (6, 11), (11, 10)]
    if kind == "tomato":
        return cols, [(".g.", "pqp", "ppr", ".r.")], [(3, 7), (10, 5), (7, 10), (11, 10)]
    if kind == "eggplant":
        return cols, [("g.", "pp", "qp", "pr", "r.")], [(3, 8), (10, 7), (7, 10)]
    if kind == "potato":
        return {**cols, "p": _c("#c8986a"), "q": _c("#e0b888"), "r": _c("#8a6040")}, [(".pp.", "qppr", ".rr.")], [(2, 12), (10, 12)]
    if kind == "onion":
        return {**cols, "p": _c("#f4ece0"), "q": WHITE, "r": _c("#d8c8b0")}, [(".pp.", "qppp", "pppr", ".rr.")], [(6, 11)]
    if kind == "carrot":
        return cols, [("pqpp", "pppr", ".pr.")], [(6, 12)]
    if kind == "turnip":
        return {**cols, "q": WHITE}, [(".qq.", "qqpp", "pppr", ".rr.")], [(6, 11)]
    if kind == "corn":
        return cols, [(".g", "qp", "pp", "pr", "gr")], [(9, 4), (3, 7)]
    if kind == "wheat":
        return cols, [("q", "p", "p")], [(2, 5), (5, 4), (8, 5), (11, 4), (3, 9), (9, 9)]
    if kind == "pumpkin":
        return cols, [("...gg...", ".pprppp.", "pqprpppr", "pqprpppr", "pppprppr", ".rrrrrr.")], [(4, 9)]
    if kind == "cabbage":
        return {**cols, "p": _c("#c8f0a0"), "q": _c("#eeffd8"), "r": _c("#8ad860")}, [("..qq..", ".qpqpq", "qppqpr", "pqpprr", ".rrrr.")], [(5, 6)]
    return cols, [berry], [(3, 7), (10, 5), (6, 10), (11, 10), (4, 11)]  # blueberries, berries


def paint_crop(g: Fig, kind: str, color: str, stage: int) -> None:
    """One growth stage (0 seeds .. 4 ripe) of a crop, standing on a 16x16 soil tile."""
    w, h = g.w, g.h
    base_y = 13
    if stage == 0:  # a little mound of earth with the seeds showing
        mound = Fig(w, h)
        _stamp(mound.px, ("...qqq...", ".qqbbbqq.", "qbbbbbbbb", "bbbbbbbbb"), base_y, {"q": CROP_SOIL[1], "b": CROP_SOIL[0]})
        d, b, l = _ramp(color)
        seed = _c("#f0d8a0") if sum(b[:3]) > 600 else b
        for x, y in ((5, 11), (8, 10), (10, 11)):
            mound.px[y, x] = seed
            mound.px[y, x + 1] = d
        g.rect(4, base_y + 1, 12, base_y + 1, GROUND_SHADOW)
        _over(g.px, _outlined(mound.px, CROP_SOIL[2]))
        return
    fam = FAMILY.get(kind, "bush")
    if stage == 1:
        art = PLANT_ART["blades"][0][3:] if fam in ("blades", "wheat", "corn") else PLANT_ART["sprout"][0]
    else:
        art = PLANT_ART[fam][0 if stage == 2 else 1]
    plant = Fig(w, h)
    _stamp(plant.px, art, base_y, CROP_LEAF)
    if stage == 4:
        if kind == "wheat":  # the whole field turns gold
            gold = _ramp(color)
            for a, b in (("L", 2), ("B", 1), ("M", 0)):
                plant.px[np.all(plant.px == CROP_LEAF[a], axis=-1)] = gold[b]
        cols, pics, spots = _produce(kind, color)
        fruit = Fig(w, h)
        for (x, y), pic in zip(spots, pics * len(spots)):
            for r, row in enumerate(pic):
                for k, ch in enumerate(row):
                    if ch in cols and 0 <= y + r < h and 0 <= x + k < w:
                        fruit.px[y + r, x + k] = cols[ch]
        plant.px = _outlined(plant.px, CROP_OUT)
        dark = tuple(int(c * 0.45) for c in _ramp(color)[0][:3]) + (255,)
        _over(plant.px, _outlined(fruit.px, dark if kind not in ("onion", "turnip", "cabbage", "potato") else _c("#3a2a24")))
    else:
        plant.px = _outlined(plant.px, CROP_OUT)
    cols_ = np.nonzero((plant.px[..., 3] > 0).any(axis=0))[0]
    if len(cols_):
        g.rect(cols_[0] + 1, base_y + 1, cols_[-1] - 1, base_y + 2, GROUND_SHADOW)
    _over(g.px, plant.px)


def crop_sheet(name: str, color: str) -> np.ndarray:
    """Five 16x16 growth stages side by side (seeds, sprout, young, grown, ripe), transparent background."""
    kind = crop_kind(name)
    out = np.zeros((CELL, CELL * 5, 4), dtype=np.uint8)
    for stage in range(5):
        g = Fig(CELL, CELL)
        paint_crop(g, kind, color, stage)
        out[:, stage * CELL:(stage + 1) * CELL] = g.px
    return out


def _outline_dark(g: Fig, col: RGBA = _c("#1e3a24")) -> None:
    a = g.px[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    g.px[ring] = col


def soil_tile(wet: bool) -> np.ndarray:
    """A 16x16 tilled patch: ridges and furrows over the whole tile, so plots side by side make one dug patch on the
    garden bed; darker when watered."""
    base, dark, light = (_c("#5a3420"), _c("#3e2414"), _c("#704428")) if wet else (_c("#86522e"), _c("#62381e"), _c("#a26a3e"))
    g = Fig(CELL, CELL)
    g.rect(0, 0, 15, 15, base)
    for y in (2, 6, 10, 14):
        g.rect(0, y, 15, y, dark)          # the furrow
        g.rect(0, y - 1, 15, y - 1, light)  # the lit top of the ridge above it
        for x in range((y * 3) % 5, 16, 5):
            g.set(x, y - 2, light)           # crumbs
    if wet:
        for x, y in ((3, 4), (11, 8), (6, 12)):
            g.set(x, y, _c("#8a6a52"))       # a glint of water
    return g.px


# Produce icons in the same pixel grammar: p base, q light, h shine, r dark, s seeds or eyes, g G d leaves.
CROP_ICONS: dict[str, tuple[str, ...]] = {
    "strawberry": ("......gGg.....", "....GgGGdG....", "..pppGdGpp....", ".ppqqpppppr...", ".pqhpppsppr...",
                   ".pqpspppppr...", "..ppppsppsr...", "..pspppppr....", "...ppppsrr....", "....ppprr.....",
                   ".....prr......"),
    "tomato": (".....gGg......", "...GgGdGGd....", "..ppGdpdGpp...", ".pqqpppppppr..", ".pqhppppppprr.",
               ".pqppppppppr..", ".ppppppppprr..", "..pppppppprr..", "...pppppprr...", ".....rrrr....."),
    "eggplant": ("..gG..........", ".GgGd.........", ".dGdpp........", "..ppqhp.......", "..pqhppp......",
                 "...pqpppp.....", "...ppppppp....", "....ppppppr...", ".....pppppr...", "......ppprr...",
                 ".......rrr...."),
    "blueberry": (".....gG.......", "....GgGd......", "..pp.dd.pp....", ".pqhp..pqhp...", ".pqppr.pqppr..",
                  ".rpprr.rpprr..", "..rr.pp..rr...", ".....qhp......", "....pqppr.....", "....rpprr.....",
                  ".....rrr......"),
    "potato": ("....pppppp....", "..ppqqppppp...", ".pqqhpppsppr..", ".pqppppppppr..", ".ppsppppppprr.",
               ".pppppppsprr..", "..ppppppprr...", "...rrrrrrr...."),
    "onion": (".....gG.......", ".....gGd......", "......Gd......", "....ppppp.....", "..ppqhpppp....",
              ".pqqhpppppr...", ".pqppppppprr..", ".ppppppppprr..", "..ppppppprr...", "...pppppprr...",
              ".....rrrr.....", "......r......."),
    "carrot": ("..........gG..", "........gGgd..", ".......GgGd...", "......pppd....", ".....pqhpr....",
               "....pqpppr....", "....pqppr.....", "...pqpppr.....", "...pppprr.....", "..ppprr.......",
               "..pprr........", ".prr.........."),
    "turnip": (".....gGd......", "....gGdGd.....", "......d.......", "....wwwww.....", "..wwhwwwww....",
               ".wwhwwwwwwp...", ".pwwwwwwwwp...", ".pppppppppr...", "..pppppppr....", "...pppppr.....",
               ".....pr......."),
    "corn": ("......qh......", ".....qpqp.....", ".....pqpp.....", "....GpqppG....", "....gGpqpGd...",
             "...gGdpqpdGd..", "...gGdpppdGd..", "...gGddppdGd..", "....gGdpdGd...", ".....gGdGd....",
             "......GdG....."),
    "wheat": ("..q...q...q...", ".qpq.qpq.qpq..", ".pqp.pqp.pqp..", ".qpq.qpq.qpq..", "..p...p...p...",
              "..r..rr..r....", "...r.rr.r.....", "....rrrr......", "....GddG......", "....rrrr......",
              "...r.rr.r.....", "..r..rr..r...."),
    "pumpkin": ("......dG......", ".....dGd......", "...ppprpppp...", "..pqqprppprp..", ".pqhpprpppprp.",
                ".pqppprppppr..", ".ppppprpppprr.", ".ppppprppprrr.", "..pppprppprr..", "...rrrrrrrr..."),
    "cabbage": ("....GgGGgG....", "..GgwwwwwgG...", ".Ggwhwwwwwgd..", ".gwhwGwwGwwd..", "Ggwwwwdwwwwgd.",
                "Ggwwwwdwwwwgd.", ".gwwGwdwGwwd..", ".dgwwwwwwwgd..", "..ddgwwwgdd...", "....dddddd...."),
}
CROP_ICONS["berry"] = CROP_ICONS["blueberry"]


def crop_icon(name: str, color: str) -> np.ndarray:
    """A 16x16 produce icon (the harvested crop): dark outline, then a white ring, for the hotbar and pop-ups."""
    kind = crop_kind(name)
    d, b, l = _ramp(color)
    cols = {"p": b, "q": l, "r": d, "h": WHITE, "s": _c("#ffe0a0"), "g": CROP_LEAF["L"], "G": CROP_LEAF["B"],
            "d": CROP_LEAF["D"], "w": _c("#f4f0e8")}
    if kind == "potato":
        cols["s"] = d
    if kind == "cabbage":
        cols.update({"w": _c("#9fd868"), "h": _c("#e0ffc0")})
    g = Fig(CELL, CELL)
    art = CROP_ICONS.get(kind, CROP_ICONS["berry"])
    _stamp(g.px, art, 1 + len(art) + (14 - len(art)) // 2, cols)
    g.px[_ring_of(g.px)] = _c("#2a1e2e")
    g.px[_ring_of(g.px)] = WHITE
    return g.px


def item_icon(item: str) -> np.ndarray:
    """16x16 icons for animal products and gathered materials: egg, milk, wood, stone, fish."""
    g = Fig(CELL, CELL)
    if item == "hay":
        g.rect(2, 6, 13, 13, _c("#e8c25a"))
        g.rect(2, 6, 13, 7, _c("#f8de8a"))
        g.rect(7, 6, 8, 13, _c("#9a6a2a"))
        for k in range(5):
            g.set(3 + k * 2, 3 + (k % 2), _c("#e8c25a"))
            g.set(3 + k * 2, 4 + (k % 2), _c("#e8c25a"))
    elif item == "fish":
        g.ellipse(7, 8, 5.4, 3.4, _c("#5aa8e0"))
        g.ellipse(6, 7, 3.4, 1.4, _c("#9ad4f8"))
        g.rect(4, 10, 9, 10, _c("#3a78b0"))
        g.poly([(11, 8), (15, 4), (15, 12)], _c("#3a78b0"))
        g.set(4, 7, BLACK)
        g.rect(7, 5, 9, 5, _c("#3a78b0"))
    elif item == "egg":
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

def _tree(kind: str, size: str = "big"):
    return lambda g, color, anim, i, seed=0: paint_tree(g, color, anim, i, kind="oak" if kind == "maple" else kind,
                                                        seed=seed, size=size)


def _farmer(g: Fig, color: str, anim: str, i: int, seed: int = 0) -> None:
    hair = [_c("#4a2e22"), _c("#2b2230"), _c("#e8c060"), _c("#b84a2a")][seed % 4]
    name, _, facing = anim.partition("_")
    paint_farmer(g, color, name if name in ("idle", "run") else "idle", i, facing=facing or "down", hair=hair)


# kind -> (size, {anim: (frames, fps, loop)}, painter, default colour)
SPRITES: dict[str, tuple[tuple[int, int], dict[str, tuple[int, float, bool]], object, str]] = {
    "farmhouse": ((80, 80), {"idle": (1, 1, False)}, paint_farmhouse, "#b4472e"),
    "coop": ((40, 40), {"idle": (1, 1, False)}, paint_coop, "#c0503a"),
    **{f"tree_{k}{suffix}": ((32, 44), {"idle": (TREE_FRAMES, TREE_FPS, True)}, _tree(k, size), col)
       for k, col in (("oak", "#5cb84a"), ("fruit", "#5cb84a"), ("blossom", "#ffa8c8"), ("maple", "#d8402a"))
       for suffix, size in (("", "big"), ("_small", "small"))},
    "tree_pine": ((24, 44), {"idle": (TREE_FRAMES, TREE_FPS, True)}, _tree("pine"), "#2f8a5a"),
    "tree_pine_small": ((24, 44), {"idle": (TREE_FRAMES, TREE_FPS, True)}, _tree("pine", "small"), "#2f8a5a"),
    "tree_snowy_pine": ((24, 44), {"idle": (1, 1, False)}, paint_snowy_pine, "#2f7a5a"),
    "tree_bare": ((32, 44), {"idle": (1, 1, False)}, paint_bare_tree, "#9a5e36"),
    "tree_palm": ((32, 44), {"idle": (TREE_FRAMES, TREE_FPS, True)}, paint_palm, "#4caf50"),
    "cactus": ((16, 24), {"idle": (1, 1, False)}, paint_cactus, "#5aa048"),
    "well": ((24, 30), {"idle": (1, 1, False)}, paint_well, "#b4472e"),
    "bed": ((16, 32), {"idle": (1, 1, False)}, paint_bed, "#4a7ad0"),
    "fireplace": ((32, 32), {"idle": (4, 6, True)}, paint_fireplace, "#c8643a"),
    "table": ((32, 24), {"idle": (1, 1, False)}, paint_table, "#9a5e36"),
    "chair": ((16, 20), {"idle": (1, 1, False)}, paint_chair, "#9a5e36"),
    "dresser": ((24, 24), {"idle": (1, 1, False)}, paint_dresser, "#9a5e36"),
    "potted_plant": ((16, 24), {"idle": (1, 1, False)}, paint_potted_plant, "#5cb84a"),
    "scarecrow": ((16, 24), {"idle": (4, 2, True)}, paint_scarecrow, "#4a7ad0"),
    "stump": ((16, 16), {"idle": (1, 1, False)}, paint_stump, "#9a5e36"),
    "boulder": ((16, 16), {"idle": (1, 1, False)}, paint_boulder, "#a8a8b8"),
    "bin": ((16, 16), {"idle": (1, 1, False)}, paint_bin, "#9a5e36"),
    "hay": ((16, 16), {"idle": (1, 1, False)}, paint_hay, "#e8c25a"),
    "barrel": ((16, 16), {"idle": (1, 1, False)}, paint_barrel, "#9a5e36"),
    "signpost": ((16, 16), {"idle": (1, 1, False)}, paint_sign, "#9a5e36"),
    "workbench": ((24, 18), {"idle": (1, 1, False)}, paint_workbench, "#9a5e36"),
    "shop": ((32, 32), {"idle": (1, 1, False)}, paint_shop, "#3a8ad0"),
    "sprinkler": ((16, 16), {"idle": (4, 6, True)}, paint_sprinkler, "#a8a8b8"),
    "flower_bush": ((16, 16), {"idle": (1, 1, False)}, paint_flower_bush, "#ff8fb4"),
    **{k: ((16, 16), {"idle": (1, 1, False)}, (lambda g, color, anim, i, d=d: paint_fence(g, d)), "#8a3625")
       for k, d in FENCE_KINDS.items()},
    "chicken": ((16, 16), {"idle": (2, 2, True), "run": (4, 8, True)}, paint_chicken, "#f4ece0"),
    "crow": ((16, 16), {"idle": (2, 2, True), "run": (4, 10, True), "hurt": (1, 1, False)}, paint_crow, "#3a3448"),
    "fox": ((18, 16), {"idle": (2, 2, True), "run": (4, 10, True), "hurt": (1, 1, False)}, paint_fox, "#e07a2a"),
    "rabbit": ((16, 16), {"idle": (2, 2, True), "run": (4, 10, True), "hurt": (1, 1, False)}, paint_rabbit, "#d8c8b8"),
    "mouse": ((16, 16), {"idle": (2, 2, True), "run": (4, 12, True), "hurt": (1, 1, False)}, paint_mouse, "#9a9aa8"),
    "chick": ((12, 12), {"idle": (2, 3, True), "run": (2, 8, True)}, paint_chick, "#ffd84a"),
    "cow": ((32, 24), {"idle": (2, 1, True), "run": (4, 6, True)}, paint_cow, "#a0582e"),
    "farmer": ((FARMER_W, FARMER_H), {"idle": (4, 3, True), "run": (4, 8, True), "idle_up": (4, 3, True),
                                       "run_up": (4, 8, True), "idle_side": (4, 3, True), "run_side": (4, 8, True),
                                       "hurt": (1, 1, False)}, _farmer, "#e8503a"),
}


# Pieces placed by their whole frame rather than by what is drawn on it, so neighbouring pieces line up.
FULL_FRAME = set(FENCE_KINDS)


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
