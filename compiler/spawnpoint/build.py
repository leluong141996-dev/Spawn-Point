"""The full pipeline: validate -> write project -> Godot builds scenes -> smoke run."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import godot, manifest as manifest_mod, music, project, sfx
from .analyze import Analysis, analyze
from .diagnostics import Diagnostics
from .manifest import Manifest

BUILD_SCENE = "res://addons/spawn_point/tools/build.tscn"
SMOKE_SCENE = "res://addons/spawn_point/tools/smoke.tscn"


@dataclass
class BuildResult:
    out_dir: Path | None
    diagnostics: Diagnostics
    timings: dict[str, float] = field(default_factory=dict)
    smoke: dict[str, Any] | None = None
    log: str = ""

    @property
    def ok(self) -> bool:
        return self.diagnostics.ok and self.out_dir is not None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "out_dir": str(self.out_dir) if self.out_dir else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "smoke": self.smoke,
        }


def load_graph(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def validate(data: Any, manifest: Manifest | None = None, base_dir: Path | None = None) -> Analysis:
    return analyze(data, manifest or manifest_mod.load(), base_dir)


def build(data: Any, out_dir: Path, *, manifest: Manifest | None = None, smoke: bool = True,
          base_dir: Path | None = None) -> BuildResult:
    """`base_dir` is the graph file's folder (for relative sprite paths)."""
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    if base_dir is not None:
        data = absolutize_sprites(data, base_dir)  # the project's spawnpoint.json must stand alone
    analysis = validate(data, manifest, base_dir)
    timings["validate"] = time.perf_counter() - t0
    if not analysis.ok:
        return BuildResult(None, analysis.diagnostics, timings)
    diags = analysis.diagnostics
    plan = analysis.plan
    assert plan is not None and analysis.rules_source is not None

    t = time.perf_counter()
    feature = _godot_feature()
    project.write(out_dir, data, plan, analysis.rules_source, feature, analysis.sprites, analysis.tiles_image,
                  analysis.scenery_images)
    sfx.write_all(out_dir / "sfx", seed=analysis.graph.settings.seed)
    if analysis.graph.settings.music != "none":
        music.write(out_dir / "sfx", analysis.graph.settings.music, analysis.graph.settings.seed)
    timings["write"] = time.perf_counter() - t

    log: list[str] = []
    t = time.perf_counter()
    imp = godot.import_project(out_dir)
    log.append(imp.output)
    timings["godot_import"] = time.perf_counter() - t

    t = time.perf_counter()
    res = godot.run_scene(out_dir, BUILD_SCENE, check=False)
    log.append(res.output)
    timings["godot_build"] = time.perf_counter() - t
    errors = res.script_errors + [ln for ln in res.output.splitlines() if "SPAWNPOINT_BUILD_ERROR" in ln]
    if res.returncode != 0 or "SPAWNPOINT_BUILD_OK" not in res.output or errors:
        for e in errors or [f"Godot build exited with code {res.returncode}"]:
            diags.error("E_GODOT_BUILD", "(build)", e)
        return BuildResult(out_dir, diags, timings, log="\n".join(log))

    report = None
    if smoke:
        t = time.perf_counter()
        res = godot.run_scene(out_dir, SMOKE_SCENE, fixed_fps=60, check=False, timeout=120)
        log.append(res.output)
        timings["smoke"] = time.perf_counter() - t
        report = _smoke_report(res.output)
        for e in res.script_errors:
            diags.error("E_RUNTIME", "(smoke)", e)
        if report is None:
            diags.error("E_RUNTIME", "(smoke)", "smoke run produced no report (crash?)")
        else:
            _judge_smoke(report, plan, diags)
    timings["total"] = time.perf_counter() - t0
    return BuildResult(out_dir, diags, timings, report, "\n".join(log))


def absolutize_sprites(data: Any, base_dir: Path) -> Any:
    if not isinstance(data, dict) or not isinstance(data.get("entities"), dict):
        return data
    out = json.loads(json.dumps(data))
    for ent in out["entities"].values():
        ref = ent.get("sprite") if isinstance(ent, dict) else None
        if isinstance(ref, str) and not Path(ref).is_absolute():
            ent["sprite"] = str((base_dir / ref).resolve())
    return out


def _godot_feature() -> str:
    try:
        m = re.match(r"(\d+)\.(\d+)", godot.version())
        if m:
            return f"{m.group(1)}.{m.group(2)}"
    except Exception:
        pass
    return "4.6"


def _smoke_report(output: str) -> dict | None:
    for line in output.splitlines():
        if line.startswith("SPAWNPOINT_SMOKE "):
            try:
                return json.loads(line.removeprefix("SPAWNPOINT_SMOKE "))
            except json.JSONDecodeError:
                return None
    return None


def _judge_smoke(report: dict, plan: dict, diags: Diagnostics) -> None:
    if report.get("error"):
        diags.error("E_RUNTIME", "(smoke)", report["error"])
        return
    if not report.get("player_found"):
        diags.error("E_RUNTIME", "(smoke)", "the player entity was not found when the level ran")
        return
    player = next((e for e in plan["entities"] if any(c["name"] == "PlayerInput" for c in e["components"])), None)
    moves = player is None or any(c["name"] in ("PlatformerMovement", "TopDownMovement") for c in player["components"])
    if plan["genre"] == "platformer" and moves and not report.get("on_floor_after_1s"):  # a card hero only stands
        diags.warning("W_SMOKE_FLOOR", "(smoke)", "the player is not standing on a floor after 1 second")
    if moves and report.get("moved_px", 0) < 4:  # a bubble-shooter launcher does not walk
        diags.warning("W_SMOKE_STUCK", "(smoke)", "the player did not move under scripted input (stuck?)")
