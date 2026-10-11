"""Deterministic level generators.

Platformer levels are stitched from hand-designed chunks; top-down levels are bordered arenas whose
obstacles never disconnect the floor. Generators only produce geometry and *slots*; the assembler
decides what goes into each slot.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

Cell = tuple[int, int]

PLATFORMER_HEIGHT = 14
STAND_ROW = 11  # row the player / walkers stand on (ground top is row 12)


@dataclass
class Layout:
    width: int
    height: int
    tiles: dict[Cell, str] = field(default_factory=dict)  # solid | oneway
    player: Cell = (0, 0)
    exit: Cell | None = None
    door: Cell | None = None
    ground_slots: list[Cell] = field(default_factory=list)  # walkers, turrets...
    air_slots: list[Cell] = field(default_factory=list)  # pickups
    hazard_slots: list[Cell] = field(default_factory=list)  # spikes
    portal_slots: list[Cell] = field(default_factory=list)  # spawners (top-down)
    free_cells: list[Cell] = field(default_factory=list)  # walkable, unoccupied (top-down)
    chunks: list[str] = field(default_factory=list)  # platformer chunk names, in order

    def is_free(self, c: Cell) -> bool:
        return c not in self.tiles


# --- platformer chunks ------------------------------------------------------------------------
# Rows are absolute rows 4..13 (the top 4 rows are always empty). Markers:
#   '#' solid  '=' one-way  'g' ground enemy slot  'c' pickup slot  'h' hazard slot  '.' empty


@dataclass(frozen=True)
class Chunk:
    name: str
    rows: tuple[str, ...]
    needs_up: int  # tiles of jump height required
    pit: bool = False
    min_difficulty: int = 1
    needs_across: int = 0  # tiles of horizontal jump distance required


CHUNKS: tuple[Chunk, ...] = (
    Chunk("flat", (
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
        "...c..c...",
        "..........",
        "..g....g..",
        "##########",
        "##########"), 0),
    Chunk("low_platforms", (
        "............",
        "............",
        "............",
        "............",
        "....cc......",
        "............",
        "...====.....",
        ".g.......g..",
        "############",
        "############"), 2),
    Chunk("stairs", (
        "..............",
        "..............",
        "..........cc..",
        "..............",
        ".........====.",
        "..............",
        "..====........",
        "g......g......",
        "##############",
        "##############"), 2),
    Chunk("block_step", (
        "............",
        "............",
        "............",
        "............",
        "....c.......",
        "............",
        "....###.....",
        ".g..###...g.",
        "############",
        "############"), 2),
    Chunk("tower", (
        "............",
        "............",
        "............",
        ".....ccc....",
        "............",
        ".....###....",
        ".....###....",
        ".g...###..g.",
        "############",
        "############"), 3, min_difficulty=2),
    Chunk("high_platform", (
        "............",
        "............",
        "....cccc....",
        "............",
        "...======...",
        "............",
        "............",
        "..g......g..",
        "############",
        "############"), 4, min_difficulty=2),
    Chunk("spike_run", (
        "............",
        "............",
        "............",
        "............",
        "............",
        "....c..c....",
        "............",
        "..hh....hh..",
        "############",
        "############"), 2),
    Chunk("low_ceiling", (
        "............",
        "............",
        "............",
        "............",
        "..########..",
        "............",
        "...c.c.c....",
        "..g.....g...",
        "############",
        "############"), 0),
    Chunk("gap", (
        "..........",
        "..........",
        "..........",
        "..........",
        "..........",
        "....cc....",
        "..........",
        "..g.......",
        "####..####",
        "####..####"), 0, pit=True, needs_across=3),
    Chunk("bridge_gap", (
        "..............",
        "..............",
        "..............",
        "..............",
        "......cc......",
        "..............",
        ".....====.....",
        "..g........g..",
        "####......####",
        "####......####"), 2, pit=True, min_difficulty=2, needs_across=3),
)

START = (
    "......",
    "......",
    "......",
    "......",
    "......",
    "......",
    "......",
    "..P...",
    "######",
    "######",
)

LENGTH_CHUNKS = {"short": 4, "medium": 7, "long": 11}


def _fits(c: Chunk, jump_up: int, jump_across: int, pits: bool) -> bool:
    return c.needs_up <= jump_up and c.needs_across <= jump_across and (pits or not c.pit)


def usable_chunks(jump_up: int, jump_across: int, pits: bool, difficulty: int) -> list[Chunk]:
    return [c for c in CHUNKS if _fits(c, jump_up, jump_across, pits) and c.min_difficulty <= difficulty]


CHUNK_BY_NAME = {c.name: c for c in CHUNKS}


def plan_chunks(seed: int, length: str, jump_up: int, jump_across: int, pits: bool, difficulty: int) -> list[str]:
    rng = random.Random(f"chunks:{seed}")
    pool = usable_chunks(jump_up, jump_across, pits, difficulty)
    picks: list[Chunk] = []
    for _ in range(LENGTH_CHUNKS[length]):
        options = [c for c in pool if not picks or c.name != picks[-1].name] or pool
        # Harder levels lean toward chunks that need more skill.
        weights = [1.0 + (c.needs_up + (2 if c.pit else 0)) * (difficulty - 1) * 0.25 for c in options]
        picks.append(rng.choices(options, weights)[0])
    return [c.name for c in picks]


def chunks_fit(names: list[str], length: str, jump_up: int, jump_across: int, pits: bool) -> bool:
    """Whether a previously planned chunk sequence still works for changed player abilities."""
    if len(names) != LENGTH_CHUNKS[length] or any(n not in CHUNK_BY_NAME for n in names):
        return False
    return all(_fits(CHUNK_BY_NAME[n], jump_up, jump_across, pits) for n in names)


def platformer(seed: int, length: str, jump_up: int, jump_across: int, pits: bool, difficulty: int, door: bool,
               chunks: list[str] | None = None) -> Layout:
    names = chunks if chunks is not None else plan_chunks(seed, length, jump_up, jump_across, pits, difficulty)
    picks = [CHUNK_BY_NAME[n] for n in names]

    lay = Layout(0, PLATFORMER_HEIGHT)
    x0 = _stamp(lay, START, 0)
    for chunk in picks:
        x0 = _stamp(lay, chunk.rows, x0)
    x0 = _end_chunk(lay, x0, door)
    lay.width = x0
    lay.chunks = list(names)
    return lay


def floor_below(lay: Layout, c: Cell) -> int | None:
    """Height in tiles of cell `c` above the floor the player would stand on beneath it."""
    x, y = c
    for yy in range(y + 1, lay.height):
        if (x, yy) in lay.tiles:
            return yy - 1 - y
    return None


def _stamp(lay: Layout, rows: tuple[str, ...], x0: int) -> int:
    top = PLATFORMER_HEIGHT - len(rows)
    for dy, row in enumerate(rows):
        y = top + dy
        for dx, ch in enumerate(row):
            c = (x0 + dx, y)
            if ch == "#":
                lay.tiles[c] = "solid"
            elif ch == "=":
                lay.tiles[c] = "oneway"
            elif ch == "g":
                lay.ground_slots.append(c)
            elif ch == "c":
                lay.air_slots.append(c)
            elif ch == "h":
                lay.hazard_slots.append(c)
            elif ch == "P":
                lay.player = c
    return x0 + len(rows[0])


def _end_chunk(lay: Layout, x0: int, door: bool) -> int:
    width = 9
    for x in range(x0, x0 + width):
        lay.tiles[(x, 12)] = lay.tiles[(x, 13)] = "solid"
    if door:
        # A wall from the ceiling down to the door, so the exit can only be reached through it.
        for y in range(0, 8):
            lay.tiles[(x0 + 2, y)] = "solid"
        lay.door = (x0 + 2, STAND_ROW)
    lay.exit = (x0 + 6, STAND_ROW)
    return x0 + width


def extra_ground_cells(lay: Layout, min_x: int) -> list[Cell]:
    """Standing cells on solid ground that no slot uses (for overflow enemies / pickups)."""
    used = set(lay.ground_slots) | set(lay.air_slots) | set(lay.hazard_slots)
    blocked = {lay.player, lay.exit, lay.door}
    out = []
    for x in range(min_x, lay.width):
        c = (x, STAND_ROW)
        if lay.tiles.get((x, STAND_ROW + 1)) == "solid" and lay.is_free(c) and c not in used and c not in blocked \
                and lay.is_free((x, STAND_ROW - 1)):
            out.append(c)
    if lay.door:
        out = [c for c in out if c[0] < lay.door[0] - 1]
    return out


# --- top-down arena ---------------------------------------------------------------------------

ARENA_SIZE = {"short": (28, 18), "medium": (36, 24), "long": (46, 30)}
OBSTACLES = ((2, 2), (4, 1), (1, 4), (3, 3), (2, 1), (1, 2))


def arena(seed: int, length: str, difficulty: int) -> Layout:
    w, h = ARENA_SIZE[length]
    lay = Layout(w, h)
    for x in range(w):
        lay.tiles[(x, 0)] = lay.tiles[(x, h - 1)] = "solid"
    for y in range(h):
        lay.tiles[(0, y)] = lay.tiles[(w - 1, y)] = "solid"
    lay.player = (w // 2, h // 2)

    rng = random.Random(f"arena:{seed}")
    target = (w * h) // (34 - difficulty * 2)
    placed = attempts = 0
    while placed * 4 < target and attempts < 400:
        attempts += 1
        ow, oh = rng.choice(OBSTACLES)
        x, y = rng.randint(2, w - 3 - ow), rng.randint(2, h - 3 - oh)
        cells = [(x + i, y + j) for i in range(ow) for j in range(oh)]
        if any(abs(cx - lay.player[0]) <= 3 and abs(cy - lay.player[1]) <= 3 for cx, cy in cells):
            continue
        if any(c in lay.tiles for c in cells):
            continue
        for c in cells:
            lay.tiles[c] = "solid"
        if not _connected(lay):
            for c in cells:
                del lay.tiles[c]
            continue
        placed += 1

    dist = _distances(lay, lay.player)
    lay.free_cells = sorted(c for c in dist if c != lay.player)
    lay.exit = max(dist, key=lambda c: (dist[c], c))
    corners = [(2, 2), (w - 3, h - 3), (w - 3, 2), (2, h - 3)]
    lay.portal_slots = [_nearest_free(lay, dist, c) for c in corners]
    return lay


def _neighbors(c: Cell):
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _distances(lay: Layout, start: Cell) -> dict[Cell, int]:
    dist = {start: 0}
    q = deque([start])
    while q:
        c = q.popleft()
        for n in _neighbors(c):
            if n not in dist and lay.is_free(n) and 0 <= n[0] < lay.width and 0 <= n[1] < lay.height:
                dist[n] = dist[c] + 1
                q.append(n)
    return dist


def _connected(lay: Layout) -> bool:
    free = sum(1 for x in range(lay.width) for y in range(lay.height) if lay.is_free((x, y)))
    return len(_distances(lay, lay.player)) == free


def _nearest_free(lay: Layout, dist: dict[Cell, int], c: Cell) -> Cell:
    return min(dist, key=lambda d: (abs(d[0] - c[0]) + abs(d[1] - c[1]), d))


# --- tower defense ----------------------------------------------------------------------------

TD_SIZE = {"short": (26, 15, 2), "medium": (30, 17, 3), "long": (34, 21, 4)}


@dataclass
class RoadLayout:
    width: int
    height: int
    road: list[Cell]  # in walking order, from the lair to the base
    pads: list[Cell]
    commander: Cell


def td_road(seed: int, length: str) -> RoadLayout:
    """A snake road with `lanes` horizontal runs joined at alternating ends, inside a walled field, and
    build pads in the strips between the runs (each pad covers two runs)."""
    w, h, lanes = TD_SIZE[length]
    rng = random.Random(f"td:{seed}")
    step = (h - 6) / max(1, lanes - 1)
    ys = [round(3 + i * step) for i in range(lanes)]
    road: list[Cell] = []
    x = 1
    for j, y in enumerate(ys):
        last = j == lanes - 1
        if j % 2 == 0:
            end = w - 3 if last else w - 4 - rng.randint(0, 1)
        else:
            end = 2 if last else 3 + rng.randint(0, 1)
        dx = 1 if end > x else -1
        for xx in range(x, end + dx, dx):
            if (xx, y) not in road:
                road.append((xx, y))
        x = end
        if not last:
            for yy in range(y + 1, ys[j + 1]):
                road.append((x, yy))
    mirror = rng.random() < 0.5
    if mirror:
        road = [(w - 1 - cx, cy) for cx, cy in road]
    on_road = set(road)
    near = {(cx + i, cy + k) for cx, cy in road for i in (-1, 0, 1) for k in (-1, 0, 1)}
    pads: list[Cell] = []
    rows = [(ys[j] + ys[j + 1]) // 2 for j in range(lanes - 1)] + [ys[0] - 2, ys[-1] + 2]
    for r, y in enumerate(rows):
        if not 1 <= y <= h - 2:
            continue
        for xx in range(3 + (r % 2) * 2, w - 3, 4):
            c = (xx, y)
            if c not in near and c not in on_road:
                pads.append(c)
    cx, cy = w // 2, h // 2  # the camera follows the commander: keep it in the middle
    commander = next(c for c in sorted(((x2, y2) for x2 in range(1, w - 1) for y2 in range(1, h - 1)),
                                       key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))
                     if c not in on_road and c not in pads)
    return RoadLayout(w, h, road, pads, commander)


FARM_SIZE = {"short": (26, 17, 2, 4), "medium": (32, 19, 3, 4), "long": (36, 21, 3, 6)}


@dataclass
class FarmLayout:
    width: int
    height: int
    player: Cell
    market: Cell
    plots: list[Cell]
    nests: list[Cell]
    rocks: list[Cell]


def farm(seed: int, length: str) -> FarmLayout:
    """Rows of plots in the middle, the farmer on one side, the market stall on the other; pests come
    from the corners."""
    w, h, rows, cols = FARM_SIZE[length]
    rng = random.Random(f"farm:{seed}")
    mirror = rng.random() < 0.5
    x0 = 7
    y0 = h // 2 - (rows - 1) * 3 // 2
    plots = [(x0 + i * 3, y0 + j * 3) for j in range(rows) for i in range(cols)]
    player, market = (3, h // 2), (w - 6, h // 2)
    nests = [(2, 1), (w - 3, 1), (2, h - 2), (w - 3, h - 2)]
    taken = set(plots) | {player, market, (market[0] + 1, market[1])}
    rocks: list[Cell] = []
    for _ in range(40):
        if len(rocks) >= 2 + rng.randint(0, 2):
            break
        c = (rng.randint(2, w - 3), rng.randint(2, h - 3))
        if all(abs(c[0] - t[0]) > 2 or abs(c[1] - t[1]) > 2 for t in taken) and c[0] > x0 + cols * 3 - 1:
            rocks.append(c)
            taken.add(c)
    if mirror:
        flip = lambda c: (w - 1 - c[0], c[1])  # noqa: E731
        plots, rocks, nests = [flip(c) for c in plots], [flip(c) for c in rocks], [flip(c) for c in nests]
        player, market = flip(player), (w - 1 - market[0] - 1, market[1])
    return FarmLayout(w, h, player, market, plots, nests, rocks)
