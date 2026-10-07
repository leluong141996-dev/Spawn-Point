"""CLI handlers for the studio commands: create, tweak, serve."""

from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path

from .project import slugify
from .studio import dataset as dataset_mod, web
from .studio.brief import GameBrief
from .studio.llm import LLMError, OpenAICompatible
from .studio.orchestrator import LayerReport, StudioError, create as do_create, tweak as do_tweak

LAYER_NAMES = {0: "L0 core loop", 1: "L1 goals & enemies", 2: "L2 feel & polish"}


def _say(msg: str) -> None:
    print(msg, flush=True)


def _report_layer(r: LayerReport) -> None:
    b = r.build
    status = "ok" if b.ok else "FAILED"
    secs = b.timings.get("total", 0) + (r.web_seconds or 0)
    _say(f"  [{LAYER_NAMES[r.layer]}] {status} in {secs:.1f}s"
         + (f" (build {b.timings.get('total', 0):.1f}s, web {r.web_seconds:.1f}s)" if r.web_seconds else ""))
    for d in b.diagnostics:
        if d.severity == "error" or r.layer > 0:
            _say(f"      {d}")


def _brief_summary(brief: GameBrief, notes: list[str]) -> None:
    b = brief
    enemies = ", ".join(f"{e.count}x {e.name} ({e.archetype})" for e in b.enemies) or "none"
    _say(f"  “{b.title}” — {b.genre}, palette {b.palette}, goal {b.goal}, {b.length}, difficulty {b.difficulty}")
    _say(f"  player: {', '.join(b.player.abilities) or 'no abilities'}; jump {b.player.jump_tiles} tiles; "
         f"speed {b.player.speed}; feel {b.feel}; juice {b.juice}")
    _say(f"  enemies: {enemies}; pickups: {b.collectible.count}x {b.collectible.name}; hazards: {', '.join(b.hazards) or 'none'}")
    for n in notes:
        _say(f"  note: {n}")


def create(args) -> int:
    llm = OpenAICompatible()
    brief = GameBrief.model_validate(json.loads(args.brief.read_text())) if args.brief else None
    server: web.Server | None = None
    out_holder: dict[str, Path] = {}

    def out_dir_for(b: GameBrief) -> Path:
        out_holder["out"] = (args.out or Path("out") / slugify(b.title)).resolve()
        _say(f"Building into {_rel(out_holder['out'])}")
        return out_holder["out"]

    def on_brief(b: GameBrief, notes: list[str]) -> None:
        _say("Design:")
        _brief_summary(b, notes)

    def on_layer(r: LayerReport) -> None:
        nonlocal server
        _report_layer(r)
        if r.build.ok and not args.no_web and not args.no_serve and server is None:
            server = web.Server(out_holder["out"], args.port).start()
            _say(f"  ▶ playing at {server.url}  (the page reloads as layers land)")
            if not args.no_open:
                webbrowser.open(server.url)

    recorder = _recorder(args)
    _say(f"Designing with {llm.base_url} ..." if brief is None else "Using the given brief ...")
    try:
        result = do_create(args.prompt, out_dir_for, llm, seed=args.seed, creative=args.creative,
                           brief=brief, web_export=not args.no_web, on_layer=on_layer, on_brief=on_brief,
                           recorder=recorder)
    except (LLMError, StudioError) as e:
        _say(f"error: {e}")
        return 2
    if result.creative is not None:
        c = result.creative
        _say(f"Creative pass: {'applied' if c.applied else 'dropped'} after {c.rounds} round(s)"
             + (f": {json.dumps(c.patch)}" if c.applied else (f" — {c.errors[:2]}" if c.errors else "")))
    _say(f"Done in {result.timings.get('total', 0):.1f}s (design {result.timings.get('design', 0):.1f}s; LLM {result.usage}).")
    out = out_holder["out"]
    _say(f"Change it:  spawnpoint tweak {_rel(out)} \"make the jump 20% higher\"")
    _say(f"Native:     spawnpoint run {_rel(out)}")
    if not result.ok:
        return 1
    if server is not None and not args.no_serve:
        _say("Serving — press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.stop()
    return 0


def tweak(args) -> int:
    llm = OpenAICompatible()
    project = args.project.resolve()
    _say(f"Tweaking {project} ...")
    try:
        result = do_tweak(project, args.request, llm, web_export=not args.no_web, on_layer=_report_layer,
                          recorder=_recorder(args))
    except (LLMError, StudioError) as e:
        _say(f"error: {e}")
        return 2
    if result.changes:
        _say("Changes:")
        for c in result.changes:
            _say(f"  {c}")
    else:
        _say("No changes (the request did not map to anything the brief controls).")
    for n in result.notes:
        _say(f"  note: {n}")
    _say(f"Done in {result.timings.get('total', 0):.1f}s (LLM {result.usage}). "
         "An open browser tab reloads automatically; otherwise run `spawnpoint serve`.")
    return 0 if result.ok else 1


def _recorder(args) -> dataset_mod.Recorder | None:
    if not (getattr(args, "record", False) or dataset_mod.enabled_by_env()):
        return None
    rec = dataset_mod.Recorder()
    _say(f"Recording LLM calls as training data in {rec.directory} (local only)")
    return rec


def dataset(args) -> int:
    if args.action == "path":
        _say(str(dataset_mod.default_dir()))
        return 0
    st = dataset_mod.stats()
    if args.json:
        print(json.dumps(st, indent=2))
        return 0
    _say(f"{st['records']} record(s) in {dataset_mod.default_dir()}")
    for task, t in st["tasks"].items():
        _say(f"  {task:<9} {t['count']:>5}  accepted {t['accepted']:>5}  corrected by the pipeline {t['corrected']:>5}")
    if st["models"]:
        _say("  models: " + ", ".join(f"{m} ({n})" for m, n in st["models"].items()))
    return 0


def serve(args) -> int:
    project = args.project.resolve()
    if not (project / web.WEB_DIR / "index.html").exists():
        _say(f"error: {project} has no web build (run `spawnpoint create` or `tweak` first)")
        return 2
    server = web.Server(project, args.port).start()
    _say(f"Playing at {server.url} — press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(server.url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)
