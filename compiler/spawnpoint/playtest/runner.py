"""Runs the Godot playtest bots on a built project and returns their telemetry."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .. import godot
from ..manifest import ADDON_DIR

PLAYTEST_SCENE = "res://addons/spawn_point/tools/playtest.tscn"
PROFILES = ("novice", "average", "expert")


def sync_addon(project: Path) -> None:
    """Brings the project's copy of the library up to date (older builds lack telemetry hooks)."""
    shutil.copytree(ADDON_DIR, project / "addons" / "spawn_point", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.import", "*.uid", "__pycache__"))


def time_limit(graph: dict, brief: dict | None = None) -> float:
    """Seconds a run may take: generous for slow players, scaled to the level size and goal."""
    rows = graph["level"]["map"]
    width_px = max(len(r) for r in rows) * graph.get("settings", {}).get("tile_size", 32)
    player = graph["entities"].get("Player", {}).get("components", {})
    speed = (player.get("PlatformerMovement") or player.get("TopDownMovement") or {}).get("max_speed", 230)
    limit = width_px / (float(speed) * 0.25) + 30 if graph["genre"] == "platformer" else 90.0
    if brief and brief.get("goal") == "survive":
        limit = max(limit, brief.get("survive_seconds", 60) + 15)
    return float(min(max(limit, 45.0), 240.0))


def run(project: Path, *, profiles: tuple[str, ...] = PROFILES, runs: int = 3, seed: int = 1,
        limit_s: float = 90.0, sync: bool = True) -> list[dict]:
    if sync:
        sync_addon(project)
        godot.import_project(project)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "playtest.json"
        game_seconds = limit_s * runs * len(profiles)
        # Bots run far faster than real time; a script error makes Godot hang, so keep a cap.
        res = godot.run_scene(project, PLAYTEST_SCENE, [str(out), ",".join(profiles), str(runs), str(seed),
                                                        str(limit_s)],
                              fixed_fps=60, check=False, timeout=60 + game_seconds / 5)
        if not out.exists():
            raise godot.GodotError("playtest produced no report", res.output)
        if res.script_errors:
            raise godot.GodotError("playtest hit script errors: " + "; ".join(res.script_errors[:3]), res.output)
        return json.loads(out.read_text())["runs"]
