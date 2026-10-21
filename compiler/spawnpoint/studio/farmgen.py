"""The cozy farm map: a farmhouse with a dirt path to its door, a fenced crop field, an animal pen with a coop,
a pond, a shipping bin, and trees, rocks and bushes around the edges; on an island (water all round, cliffs to
the south) or in a meadow ringed by woods.

Everything is laid out on the level grid (one cell = one 32 px tile = one 16 px art tile). The map comes back as
terrain characters (see sprites/farm.py), solid cells (water and the edge), plots, and objects to place
(an object stands on the bottom of its cell).
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

Cell = tuple[int, int]

FARM_MAPS = {"short": (30, 20), "medium": (34, 22), "long": (40, 26)}
HOUSE_W, HOUSE_H = 5, 4  # cells the farmhouse covers (its roof reaches half a cell higher)


@dataclass
class CozyFarm:
    width: int
    height: int
    island: bool
    terrain: list[str]
    solid: set[Cell]
    player: Cell
    door: Cell
    bin: Cell
    plots: list[Cell]
    pen: tuple[int, int, int, int]  # x0, y0, x1, y1 inside the fence
    animals: list[Cell]
    objects: list[tuple[str, Cell]] = field(default_factory=list)  # (kind, cell): see OBJECT_KINDS
    nests: list[Cell] = field(default_factory=list)
    fishing: list[tuple[Cell, Cell]] = field(default_factory=list)  # (shore cell, direction of the water)
    # Inside the farmhouse: a room below the map (past a strip of sea and darkness, so the camera never shows both).
    room: tuple[int, int, int, int] | None = None  # x0, y0, x1, y1 of the floor
    door_mat: Cell | None = None  # stand here inside and press interact to go out
    outdoor_height: int = 0  # rows of the farm itself (the room comes after)

    def blocked(self) -> set[Cell]:
        """Cells nobody can walk through: water, the edge, and solid objects' cells."""
        out = set(self.solid)
        for kind, c in self.objects:
            if kind == "farmhouse":
                out |= {(c[0] + dx, c[1] + dy) for dx in range(-2, 3) for dy in range(-1, 1)}
            elif kind == "coop":
                out |= {(c[0] + dx, c[1]) for dx in (-1, 0, 1)}
            elif kind not in ("flower_bush",):
                out.add(c)
        return out


# Objects the assembler turns into entities.
OBJECT_KINDS = ("farmhouse", "coop", "fence_h", "fence_v", "fence_post", "tree_oak", "tree_pine", "tree_blossom",
                "tree_fruit", "tree_maple", "tree_snowy_pine", "tree_bare", "tree_palm", "cactus", "boulder", "stump",
                "flower_bush", "hay", "barrel", "well", "scarecrow", "signpost",
                "bed", "fireplace", "table", "chair", "dresser", "potted_plant")
# What grows around the farm in each season: (tree kinds, weights), and the small things scattered between them.
SEASON_TREES = {
    "spring": (["tree_oak", "tree_pine", "tree_fruit", "tree_blossom"], [4, 3, 2, 2]),
    "autumn": (["tree_oak", "tree_maple", "tree_pine", "tree_fruit"], [4, 3, 2, 1]),
    "winter": (["tree_snowy_pine", "tree_bare"], [5, 3]),
    "desert": (["tree_palm", "cactus"], [3, 4]),
}
SEASON_SMALL = {"spring": ["boulder", "boulder", "stump", "flower_bush", "flower_bush"],
                "autumn": ["boulder", "boulder", "stump", "stump", "flower_bush"],
                "winter": ["boulder", "boulder", "stump"],
                "desert": ["boulder", "boulder", "boulder", "cactus"]}


def cozy_farm(seed: int, length: str = "medium", plot_target: int = 12, island: bool | None = None,
              season: str = "spring") -> CozyFarm:
    """`island` forces water all round (True) or a meadow (False); None lets the seed choose. `season` picks the
    trees (see SEASON_TREES); the ground's colours are the terrain painter's business."""
    trees_of, weights = SEASON_TREES.get(season, SEASON_TREES["spring"])
    w, h = FARM_MAPS.get(length, FARM_MAPS["medium"])
    rng = random.Random(f"cozyfarm:{seed}")
    pick = rng.random() < 0.6
    island = pick if island is None else island
    m = 2  # the margin: water around an island, woods around a meadow
    grid = [["." for _ in range(w)] for _ in range(h)]
    taken: set[Cell] = set()
    objects: list[tuple[str, Cell]] = []

    def put(kind: str, c: Cell) -> None:
        objects.append((kind, c))
        taken.add(c)

    def path(c: Cell) -> None:
        if 0 <= c[0] < w and 0 <= c[1] < h:
            grid[c[1]][c[0]] = ":"
            taken.add(c)

    # the frame: water (island) with a bumpy coast, or open land (the woods are planted later)
    if island:
        for y in range(h):
            for x in range(w):
                if x < m or y < m or x >= w - m or y >= h - m:
                    grid[y][x] = "~"
        for _ in range(rng.randint(5, 8)):  # bays bitten out of the coast
            side = rng.choice("nswe")
            bw, bh = rng.randint(2, 5), rng.randint(1, 2)
            if side in "ns":
                x0 = rng.randint(m + 1, w - m - bw - 1)
                y0 = m if side == "n" else h - m - bh
                cells = [(x, y) for x in range(x0, x0 + bw) for y in range(y0, y0 + bh)]
            else:
                y0 = rng.randint(m + 1, h - m - bw - 1)
                x0 = m if side == "w" else w - m - bh
                cells = [(x, y) for x in range(x0, x0 + bh) for y in range(y0, y0 + bw)]
            for x, y in cells:
                grid[y][x] = "~"

    # the farmhouse, top left, with the door facing the main road below it
    hx, hy = m + 4, m + 3  # the house's door cell column is hx, its bottom row hy + 1
    house = (hx, hy + 1)
    door = (hx, hy + 2)
    for dx in range(-3, 4):
        for dy in range(-3, 3):
            taken.add((hx + dx, hy + dy))
            if grid[hy + dy][hx + dx] == "~":
                grid[hy + dy][hx + dx] = "."
    objects.append(("farmhouse", house))
    road = hy + 5
    for y in range(door[1], road + 1):
        path((hx, y))
    for x in range(m + 1, w - m - 1):
        path((x, road))
    bin_cell = (hx + 3, hy + 2)
    taken.add(bin_cell)
    put("signpost", (hx - 1, road - 1))
    put("well", (hx - 4, hy + 2)) if hx - 4 > m else None
    put("barrel", (hx + 4, hy + 2))

    # the crop field: 2x2 groups of plots inside a fence, gate in the bottom side onto the road
    n_groups = max(2, min(8, round(plot_target / 4)))
    groups_y = 1 if n_groups <= 3 else 2
    groups_x = -(-n_groups // groups_y)
    fw, fh = groups_x * 3 + 1, groups_y * 3 + 1
    fx0 = hx + 6
    fy0 = road - 1 - fh
    if fy0 < m + 1:
        fy0 = m + 1
    fx0 = min(fx0, w - m - fw - 2)
    plots: list[Cell] = []
    for gy in range(groups_y):
        for gx in range(groups_x):
            for dy in (0, 1):
                for dx in (0, 1):
                    plots.append((fx0 + 1 + gx * 3 + dx, fy0 + 1 + gy * 3 + dy))
    for x in range(fx0 - 1, fx0 + fw + 1):
        for y in range(fy0 - 1, fy0 + fh + 1):
            if grid[y][x] == "~":
                grid[y][x] = "."
            if fx0 <= x < fx0 + fw and fy0 <= y < fy0 + fh:
                grid[y][x] = ","
            taken.add((x, y))
    gate_x = fx0 + fw // 2
    _fence(objects, fx0 - 1, fy0 - 1, fx0 + fw, fy0 + fh, gate=(gate_x, fy0 + fh))
    for y in range(fy0 + fh, road):
        path((gate_x, y))
    put("scarecrow", (fx0 + 3 if groups_x > 1 else fx0 + fw - 1, fy0 + fh - 1)) if (fx0 + 3, fy0 + fh - 1) not in plots else None

    # the animal pen below the road, gate at the top; a coop inside
    pw, ph = 8, 5
    px0 = m + 2
    py0 = road + 2
    if py0 + ph + 1 > h - m - 1:
        py0 = h - m - ph - 2
    for x in range(px0 - 1, px0 + pw + 1):
        for y in range(py0 - 1, py0 + ph + 1):
            if grid[y][x] == "~":
                grid[y][x] = "."
            taken.add((x, y))
    pen_gate = (px0 + pw // 2, py0 - 1)
    _fence(objects, px0 - 1, py0 - 1, px0 + pw, py0 + ph, gate=pen_gate)
    for y in range(road + 1, py0):
        path((pen_gate[0], y))
    objects.append(("coop", (px0 + 1, py0 + 1)))
    put("hay", (px0 + pw - 1, py0))
    animals = [(px0 + 2 + 2 * (i % 3), py0 + 2 + 2 * (i // 3)) for i in range(6)]  # apart, so none start stuck

    # the pond: below the road on the right
    lw, lh = rng.randint(4, 6), rng.randint(2, 3)
    lx0 = max(px0 + pw + 3, w - m - lw - 4 - rng.randint(0, 3))
    ly0 = min(road + 3, h - m - lh - 2)
    for x in range(lx0, lx0 + lw):
        for y in range(ly0, ly0 + lh):
            if (x in (lx0, lx0 + lw - 1) and y in (ly0, ly0 + lh - 1)) and rng.random() < 0.6:
                continue  # rounder corners
            grid[y][x] = "~"
            taken.add((x, y))
    for x in range(lx0 - 1, lx0 + lw + 1):
        for y in range(ly0 - 1, ly0 + lh + 1):
            taken.add((x, y))

    # fishing spots: shore cells on the pond's north and west sides (the bobber lands on the water)
    pond = {(x, y) for x in range(lx0, lx0 + lw) for y in range(ly0, ly0 + lh) if grid[y][x] == "~"}
    fishing: list[tuple[Cell, Cell]] = []
    for c, d in (((lx0 + lw // 2, ly0 - 1), (0, 1)), ((lx0 - 1, ly0 + lh // 2), (1, 0))):
        if (c[0] + d[0], c[1] + d[1]) in pond and grid[c[1]][c[0]] != "~":
            fishing.append((c, d))

    # trees, rocks, bushes and stumps on the free land, thicker toward the edges
    solid = {(x, y) for y in range(h) for x in range(w) if grid[y][x] == "~" or x in (0, w - 1) or y in (0, h - 1)}
    near_path = {(x + dx, y + dy) for y in range(h) for x in range(w) if grid[y][x] == ":" for dx in (-1, 0, 1)
                 for dy in (-1, 0, 1)}
    trees: list[Cell] = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            c = (x, y)
            if c in taken or c in solid or c in near_path or grid[y][x] != ".":
                continue
            edge = min(x - m, y - m, w - m - 1 - x, h - m - 1 - y)
            if not island and edge < 0:
                edge = 0
            chance = 0.55 if edge <= 0 else 0.3 if edge <= 2 else 0.05
            if any(abs(x - t[0]) < 2 and abs(y - t[1]) < 2 for t in trees):
                continue
            if rng.random() < chance:
                kind = rng.choices(trees_of, weights)[0]
                trees.append(c)
                put(kind, c)
            elif rng.random() < 0.05:
                put(rng.choice(SEASON_SMALL.get(season, SEASON_SMALL["spring"])), c)
    if not island:  # woods all round a meadow: the outer ring is solid
        for y in range(h):
            for x in range(w):
                if x < 1 or y < 1 or x >= w - 1 or y >= h - 1:
                    solid.add((x, y))

    player = (door[0], door[1] + 1)
    nests = [c for c in ((m + 1, m + 1), (w - m - 2, m + 1), (m + 1, h - m - 2), (w - m - 2, h - m - 2))]
    terrain = ["".join(r) for r in grid]
    farm = CozyFarm(w, h, island, terrain, solid, player, door, bin_cell, plots, (px0, py0, px0 + pw - 1, py0 + ph - 1),
                    animals, objects, nests, fishing)
    _clear_paths(farm)
    _add_interior(farm)
    return farm


SEA_GAP, DARK_GAP = 6, 6  # rows of sea, then darkness, between the farm and the room
ROOM_W, ROOM_H = 11, 9


def _add_interior(farm: CozyFarm) -> None:
    """The farmhouse's inside: back wall with windows, floorboards, a rug, bed, dresser, fireplace, table and
    chairs, a door mat. Laid out below the map; the house's door and the mat are linked by warps."""
    w = farm.width
    x0, y0 = (w - ROOM_W) // 2, farm.height + SEA_GAP + DARK_GAP
    rows = [list("~" * w) for _ in range(SEA_GAP)] + [list(" " * w) for _ in range(DARK_GAP + ROOM_H + 1)]
    for dy in range(ROOM_H):
        for dx in range(ROOM_W):
            edge = dy < 2 or dy == ROOM_H - 1 or dx in (0, ROOM_W - 1)
            rows[SEA_GAP + DARK_GAP + dy][x0 + dx] = "W" if edge else "F"
    cx = x0 + ROOM_W // 2
    for dy in (4, 5):
        for dx in (-1, 0, 1):
            rows[SEA_GAP + DARK_GAP + dy][cx + dx] = "R"
    mat = (cx, y0 + ROOM_H - 2)
    rows[SEA_GAP + DARK_GAP + ROOM_H - 2][cx] = "M"
    farm.terrain = farm.terrain + ["".join(r) for r in rows]
    for dy, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in "~ W":
                farm.solid.add((x, farm.height + dy))
    farm.objects += [("bed", (x0 + 1, y0 + 3)), ("potted_plant", (x0 + 2, y0 + 2)), ("dresser", (x0 + 4, y0 + 2)),
                     ("fireplace", (x0 + ROOM_W - 3, y0 + 2)), ("table", (cx, y0 + 5)), ("chair", (cx - 2, y0 + 5)),
                     ("chair", (cx + 2, y0 + 5)), ("potted_plant", (x0 + ROOM_W - 2, y0 + ROOM_H - 2))]
    farm.room = (x0 + 1, y0 + 2, x0 + ROOM_W - 2, y0 + ROOM_H - 2)
    farm.outdoor_height = farm.height
    farm.door_mat = mat
    farm.height += SEA_GAP + DARK_GAP + ROOM_H + 1


def _fence(objects: list[tuple[str, Cell]], x0: int, y0: int, x1: int, y1: int, gate: Cell) -> None:
    """A rectangle of fence with one gap; corners are posts."""
    for x in range(x0, x1 + 1):
        for y in (y0, y1):
            if (x, y) == gate:
                continue
            corner = x in (x0, x1)
            objects.append(("fence_post" if corner else "fence_h", (x, y)))
    for y in range(y0 + 1, y1):
        for x in (x0, x1):
            if (x, y) != gate:
                objects.append(("fence_v", (x, y)))


def _clear_paths(farm: CozyFarm) -> None:
    """Nothing stands on a path or on the cells everyone needs to reach."""
    keep = {(x, y) for y, row in enumerate(farm.terrain) for x, ch in enumerate(row) if ch == ":"}
    keep |= {farm.player, farm.bin, farm.door} | {c for c, _ in farm.fishing}
    farm.objects = [(k, c) for k, c in farm.objects if c not in keep or k == "farmhouse"]


def reachable(farm: CozyFarm, start: Cell | None = None) -> set[Cell]:
    """Cells the farmer can walk to (4-neighbour flood fill over unblocked cells)."""
    blocked = farm.blocked()
    start = start or farm.player
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= n[0] < farm.width and 0 <= n[1] < farm.height and n not in seen and n not in blocked:
                seen.add(n)
                q.append(n)
    return seen
