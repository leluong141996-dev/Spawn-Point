"""Sub-project 5: bots play the game, telemetry is aggregated, parameters are tuned within bounds."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import manifest as manifest_mod
from ..build import build
from ..manifest import Manifest
from ..studio.creative import apply_patch
from . import report as report_mod, runner, tuner
from .report import Report
from .tuner import Change

OUT_DIR = "playtest"


@dataclass
class PlaytestResult:
    baseline: Report
    final: Report
    changes: list[Change] = field(default_factory=list)
    rounds: list[dict] = field(default_factory=list)
    files: dict[str, Path] = field(default_factory=dict)
    seconds: float = 0.0
    difficulty: int = 2


def goal_entities(graph: dict) -> set[str]:
    return {n for n, e in graph["entities"].items()
            if any(c in e.get("components", {}) for c in ("Collectible", "TriggerZone"))}


def merge_tuning(old: list[dict], changes: list[Change]) -> list[dict]:
    merged = {(t["entity"], t["component"], t["param"]): t for t in old}
    for c in changes:
        merged[(c.entity, c.component, c.param)] = c.to_patch()
    return list(merged.values())


def playtest(project: Path, *, runs: int = 3, profiles: tuple[str, ...] = runner.PROFILES, tune: bool = False,
             rounds: int = 2, seed: int = 1, manifest: Manifest | None = None, original: dict | None = None,
             difficulty: int = 2, brief: dict | None = None,
             on_progress: Callable[[str], None] | None = None) -> PlaytestResult:
    """Plays `project` with bots; with `tune`, proposes bounded changes and keeps them only if the
    score improves. `original` is the untuned graph used for the bounds (default: current graph)."""
    t0 = time.perf_counter()
    manifest = manifest or manifest_mod.load()
    say = on_progress or (lambda _m: None)
    graph = json.loads((project / "spawnpoint.json").read_text())
    original = original or graph
    goals = goal_entities(graph)
    limit = runner.time_limit(graph, brief)

    say(f"playing {len(profiles)} profiles x {runs} runs (≤ {limit:.0f}s each)")
    baseline = report_mod.aggregate(runner.run(project, profiles=profiles, runs=runs, seed=seed, limit_s=limit), goals)
    best_graph, best = graph, baseline
    result = PlaytestResult(baseline, baseline, difficulty=difficulty)
    built_graph = graph
    if tune:
        for i in range(rounds):
            changes = tuner.propose(best, best_graph, original, manifest, difficulty)
            if not changes:
                break
            say(f"round {i + 1}: trying {len(changes)} change(s)")
            candidate = apply_patch(best_graph, {"set_params": [c.to_patch() for c in changes], "add_rules": []})
            built = build(candidate, project, manifest=manifest, smoke=True)
            built_graph = candidate
            if not built.ok:
                result.rounds.append({"round": i + 1, "changes": [str(c) for c in changes], "accepted": False,
                                      "error": [str(d) for d in built.diagnostics.errors]})
                break
            rep = report_mod.aggregate(runner.run(project, profiles=profiles, runs=runs, seed=seed, limit_s=limit,
                                                  sync=False), goals)
            before, after = tuner.score(best, difficulty), tuner.score(rep, difficulty)
            accepted = after < before
            result.rounds.append({"round": i + 1, "changes": [str(c) for c in changes], "score_before": before,
                                  "score_after": after, "accepted": accepted})
            say(f"round {i + 1}: score {before} -> {after} ({'kept' if accepted else 'reverted'})")
            if not accepted:
                break
            best_graph, best = candidate, rep
            result.changes.extend(changes)
        if built_graph is not best_graph:  # the last candidate was rejected: rebuild the best one
            build(best_graph, project, manifest=manifest, smoke=False)
    result.final = best
    out = project / OUT_DIR
    out.mkdir(exist_ok=True)
    payload = {"difficulty": difficulty, "targets": tuner.targets(difficulty),
               "score": {"baseline": tuner.score(baseline, difficulty), "final": tuner.score(best, difficulty)},
               "baseline": baseline.to_dict(), "final": best.to_dict(), "rounds": result.rounds,
               "changes": [c.to_patch() | {"reason": c.reason} for c in result.changes]}
    (out / "report.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(report_mod.markdown(best, best_graph.get("name", project.name),
                                                       [str(c) for c in result.changes]))
    plan = json.loads((project / "build_plan.json").read_text())
    report_mod.heatmap(plan, best.runs, out / "heatmap.png")
    result.files = {"json": out / "report.json", "md": out / "report.md", "heatmap": out / "heatmap.png"}
    result.seconds = time.perf_counter() - t0
    return result
