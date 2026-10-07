"""ASCII level parsing, checks, and a platformer reachability estimate."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .diagnostics import Diagnostics, did_you_mean, join_path
from .graph import Level

TILE_KINDS = ("solid", "oneway")
EMPTY = {".", " "}
MAX_W, MAX_H = 512, 256


@dataclass
class Placement:
    entity: str
    x: int
    y: int


@dataclass
class LevelData:
    width: int
    height: int
    tiles: dict[tuple[int, int], str] = field(default_factory=dict)  # (x, y) -> solid | oneway
    placements: list[Placement] = field(default_factory=list)

    def is_solid(self, x: int, y: int) -> bool:
        return self.tiles.get((x, y)) == "solid"

    def is_floor(self, x: int, y: int) -> bool:
        return (x, y) in self.tiles


def parse_level(level: Level, entity_names: set[str], diags: Diagnostics) -> LevelData | None:
    path = "level"
    ok = True
    legend: dict[str, str] = {}
    for ch, value in level.legend.items():
        p = join_path(path, "legend", ch)
        if len(ch) != 1:
            diags.error("E_LEGEND_KEY", p, f"legend keys must be single characters, got '{ch}'")
            ok = False
            continue
        if ch in EMPTY:
            diags.error("E_LEGEND_KEY", p, f"'{ch}' is reserved for empty space")
            ok = False
            continue
        if value not in TILE_KINDS and value not in entity_names:
            diags.error("E_LEGEND_VALUE", p, f"'{value}' is neither a tile kind nor an entity",
                        did_you_mean(value, [*TILE_KINDS, *entity_names]))
            ok = False
            continue
        legend[ch] = value

    rows = level.map
    if not rows or not any(r.strip(". ") for r in rows):
        diags.error("E_MAP_EMPTY", join_path(path, "map"), "the map is empty")
        return None
    width = max(len(r) for r in rows)
    height = len(rows)
    if width > MAX_W or height > MAX_H:
        diags.error("E_MAP_SIZE", join_path(path, "map"), f"map is {width}x{height}; maximum is {MAX_W}x{MAX_H}")
        return None

    data = LevelData(width, height)
    unknown: dict[str, list[tuple[int, int]]] = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in EMPTY:
                continue
            if ch not in legend:
                unknown.setdefault(ch, []).append((x, y))
                continue
            value = legend[ch]
            if value in TILE_KINDS:
                data.tiles[(x, y)] = value
            else:
                data.placements.append(Placement(value, x, y))
    for ch, cells in unknown.items():
        if ch in level.legend:
            continue  # already reported as a bad legend entry
        where = ", ".join(f"({x},{y})" for x, y in cells[:4]) + (" ..." if len(cells) > 4 else "")
        diags.error("E_MAP_CHAR", join_path(path, "map"), f"character '{ch}' at {where} is not in the legend",
                    f'Add "{ch}": "<tile kind or entity>" to level.legend, or use "." for empty')
        ok = False
    return data if ok else None


@dataclass
class JumpModel:
    """How far the player can travel, in tiles (rough estimate for warnings)."""

    up: int
    across: int
    height_tiles: int


def jump_model(jump_velocity: float, gravity: float, fall_mult: float, max_speed: float,
               tile: int, player_h: float, air_jumps: int = 0) -> JumpModel:
    if gravity <= 0:
        return JumpModel(99, 99, 1)
    jumps = 1 + max(0, air_jumps)
    h = jump_velocity**2 / (2 * gravity) * jumps
    t_up = jump_velocity / gravity * jumps
    t_down = math.sqrt(2 * h / (gravity * fall_mult))
    return JumpModel(int(h // tile), max(1, int(max_speed * (t_up + t_down) // tile)),
                     max(1, math.ceil(player_h / tile)))


def unreachable(data: LevelData, start: tuple[int, int], targets: list[Placement], jm: JumpModel) -> list[Placement]:
    """Targets the player probably cannot reach (platformer heuristic: jumps, walks and falls)."""

    def free(x: int, y: int) -> bool:
        return 0 <= x < data.width and y < data.height and not data.is_solid(x, y)

    def standable(x: int, y: int) -> bool:
        if not (0 <= x < data.width and 0 <= y < data.height - 1):
            return False
        if not data.is_floor(x, y + 1):
            return False
        return all(free(x, y - k) for k in range(jm.height_tiles))

    # Drop the player onto the floor below its start cell.
    sx, sy = start
    while sy < data.height - 1 and not standable(sx, sy):
        sy += 1
    if not standable(sx, sy):
        return []  # Reported separately as W_NO_GROUND.
    stands = [(x, y) for x in range(data.width) for y in range(data.height) if standable(x, y)]
    if len(stands) > 4000:
        return []  # Too big for this quadratic heuristic; skip the warning.
    seen = {(sx, sy)}
    queue = deque([(sx, sy)])
    while queue:
        x, y = queue.popleft()
        for nx, ny in stands:
            if (nx, ny) in seen:
                continue
            dy = ny - y  # positive = lower
            reach = jm.across + max(0, dy)
            if abs(nx - x) <= reach and dy >= -jm.up:
                seen.add((nx, ny))
                queue.append((nx, ny))
    missing = []
    for t in targets:
        ok = any(abs(t.x - x) <= jm.across and y - jm.up - jm.height_tiles < t.y <= y + 1 for x, y in seen)
        if not ok:
            missing.append(t)
    return missing


def has_ground_below(data: LevelData, x: int, y: int) -> bool:
    return any(data.is_floor(x, yy) for yy in range(y + 1, data.height))
