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


def _load_brief(data: dict) -> GameBrief:
    """A GameBrief, or the per-genre shape the v5 model writes."""
    try:
        return GameBrief.model_validate(data)
    except Exception:
        from .studio import genres
        return genres.parse_wire(data)


def _brief_summary(brief: GameBrief, notes: list[str]) -> None:
    b = brief
    enemies = ", ".join(f"{e.count}x {e.name} ({e.archetype})" for e in b.enemies) or "none"
    _say(f"  “{b.title}” — {b.genre}, palette {b.palette}, goal {b.goal}, {b.length}, difficulty {b.difficulty}")
    if b.genre == "cards":
        own = ", ".join(f"{c.name} ({c.kind})" for c in b.cards) or "the class's own"
        _say(f"  hero: {b.player.character} ({b.hero_class}); cards: {own}")
        _say(f"  foes: {', '.join(f'{e.name} ({e.archetype})' for e in b.enemies) or 'none'}; boss: {b.boss}")
        for n in notes:
            _say(f"  note: {n}")
        return
    _say(f"  player: {b.player.character} ({', '.join(b.player.abilities) or 'no abilities'}); jump {b.player.jump_tiles} tiles; "
         f"speed {b.player.speed}; feel {b.feel}; juice {b.juice}")
    _say(f"  enemies: {enemies}; pickups: {b.collectible.count}x {b.collectible.name}; hazards: {', '.join(b.hazards) or 'none'}")
    for n in notes:
        _say(f"  note: {n}")


def create(args) -> int:
    if getattr(args, "ai_art", False):
        import os
        os.environ["SPAWNPOINT_AI_ART"] = "1"  # read by create(); stored in studio.json for later tweaks
    from .installer import web_templates_ready
    if not args.no_web and not web_templates_ready():
        _say("note: the Godot web export templates are missing, so the game will not open in the browser."
             " Run `spawnpoint setup` once to fetch them; until then play with `spawnpoint run`.")
        args.no_web = True
    llm = OpenAICompatible()
    brief = _load_brief(json.loads(args.brief.read_text())) if args.brief else None
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
                           recorder=recorder, playtest=args.playtest,
                           on_progress=lambda m: _say(f"  [playtest] {m}"))
    except (LLMError, StudioError) as e:
        _say(f"error: {e}")
        return 2
    if result.creative is not None:
        c = result.creative
        _say(f"Creative pass: {'applied' if c.applied else 'dropped'} after {c.rounds} round(s)"
             + (f": {json.dumps(c.patch)}" if c.applied else (f" — {c.errors[:2]}" if c.errors else "")))
    if result.playtest is not None:
        _print_playtest(result.playtest)
    _say(f"Done in {result.timings.get('total', 0):.1f}s (design {result.timings.get('design', 0):.1f}s; LLM {result.usage}).")
    out = out_holder["out"]
    if not result.ok:
        _say(f"Native:     spawnpoint run {_rel(out)}")
        return 1
    if not getattr(args, "no_chat", False) and sys.stdin.isatty():
        _chat(out, llm, web_export=not args.no_web)
    _say(f"Change it:  spawnpoint tweak {_rel(out)} \"make the jump 20% higher\"")
    _say(f"Share it:   spawnpoint share {_rel(out)}   (a zip for itch.io or your friends)")
    _say(f"Native:     spawnpoint run {_rel(out)}")
    if server is not None and not args.no_serve:
        _say("Serving — press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.stop()
    return 0


CHAT_EXAMPLES = ('"make the jump higher"', '"add more enemies"', '"make it harder"', '"cho nhảy cao hơn"',
                 '"thêm quái"', '"night colors"')


# What words can change, per genre (what the design controls), for when a request maps to nothing.
CAN_CHANGE = {
    "platformer": "the hero (and its jump, speed, health, dash, double jump, sword or gun), enemies, pickups, spikes and pits",
    "topdown": "the hero (speed, health, dash, sword or gun), enemies, pickups, level-ups and how long to survive",
    "farm": "the crops, the pests, the season and the money to earn",
    "tower_defense": "the towers and the invaders",
    "shmup": "the ship, the enemies and the boss",
    "bubble": "the shooter and what is popped",
    "cards": "the hero and its class, the cards, the foes and the boss",
}


def _cannot(genre: str) -> str:
    return (f"I can't change that yet. Words can change {CAN_CHANGE.get(genre, 'the hero and the enemies')}, "
            "plus the theme, the difficulty, the level length and the title.")


def _chat(project: Path, llm, web_export: bool) -> None:
    """Change the game with words, one request after another, until an empty line."""
    _say("")
    _say(f"Change it with words, e.g. {', '.join(CHAT_EXAMPLES[:4])}. Press Enter on an empty line when done.")
    while True:
        try:
            request = input("change> ").strip()
        except (EOFError, KeyboardInterrupt):
            _say("")
            return
        if not request:
            return
        try:
            result = do_tweak(project, request, llm, web_export=web_export, on_layer=_report_layer)
        except (LLMError, StudioError) as e:
            _say(f"  error: {e}")
            continue
        for c in result.changes or [_cannot(result.brief.genre)]:
            _say(f"  {c}")
        if result.ok and web_export:
            _say("  the browser tab reloads with the new version")


def share(args) -> int:
    project = args.project.resolve()
    if not (project / "project.godot").exists():
        _say(f"error: {project} is not a built game")
        return 2
    _say(f"Packing {_rel(project)} for the web ...")
    zip_path = web.share_zip(project, args.out.resolve() if args.out else None)
    size = zip_path.stat().st_size / 1e6
    _say(f"Wrote {_rel(zip_path)} ({size:.1f} MB)")
    if getattr(args, "itch", None):
        return _push_itch(project, args.itch)
    _say("  itch.io: create a new project, kind of project HTML, upload the zip and tick")
    _say('  "This file will be played in the browser"; viewport 960 x 540, and turn on the fullscreen button.')
    _say("  Or in one step next time: spawnpoint share <game> --itch your-name/your-game")
    _say("  Anywhere else: unzip it on any static web host (GitHub Pages, Netlify...) and open index.html.")
    return 0


def _push_itch(project: Path, target: str) -> int:
    """Uploads the shared web build to an itch.io page with butler (logging in through the browser if needed)."""
    import os
    import re
    import subprocess

    from . import installer

    if not re.fullmatch(r"[\w.-]+/[\w.-]+", target):
        _say("error: --itch wants your-name/your-game, as in https://your-name.itch.io/your-game")
        return 2
    butler = installer.ensure_butler(_say)
    if not os.environ.get("BUTLER_API_KEY") and not installer.butler_logged_in():
        _say("  log in to itch.io in the browser window that opens ...")
        if subprocess.run([butler, "login"]).returncode != 0:
            _say("error: itch.io login failed")
            return 2
    _say(f"Uploading to itch.io ({target}:html5) ...")
    pushed = subprocess.run([butler, "push", str(project / web.SHARE_DIR), f"{target}:html5"])
    if pushed.returncode != 0:
        _say("error: the upload failed. The page must exist first: create it on itch.io (kind of project: HTML).")
        return 2
    user, game = target.split("/", 1)
    _say(f"Uploaded: https://{user}.itch.io/{game}")
    _say('  first upload only: on the page\'s edit screen tick "This file will be played in the browser" for it,')
    _say("  set the viewport to 960 x 540 and turn on the fullscreen button.")
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
        _say(_cannot(result.brief.genre))
    for n in result.notes:
        _say(f"  note: {n}")
    _say(f"Done in {result.timings.get('total', 0):.1f}s (LLM {result.usage}). "
         "An open browser tab reloads automatically; otherwise run `spawnpoint serve`.")
    return 0 if result.ok else 1


def _print_playtest(res) -> None:
    from .playtest import tuner

    def table(rep, label):
        _say(f"  {label}:")
        for p in rep.profiles.values():
            causes = ", ".join(f"{k} {v}" for k, v in list(p.causes.items())[:3]) or "no deaths"
            _say(f"    {p.profile:<8} won {p.wins}/{p.runs}  deaths {p.deaths:<3} ({causes})  "
                 f"missed jumps {p.jumps_missed}/{p.jumps_intended}  pickups {p.pickup_rate:.0%}  stuck {p.stuck}")

    table(res.baseline, "before" if res.changes else "results")
    for r in res.rounds:
        verdict = "kept" if r.get("accepted") else "reverted"
        _say(f"  round {r['round']} ({verdict}, score {r.get('score_before')} -> {r.get('score_after')}):")
        for c in r["changes"]:
            _say(f"    {c}")
    if res.changes:
        table(res.final, "after")
    for issue in res.final.level_issues:
        _say(f"  level issue: {issue}")
    _say(f"  targets (difficulty {res.difficulty}): {tuner.targets(res.difficulty)}")
    _say(f"  report: {_rel(res.files['md'])}  heatmap: {_rel(res.files['heatmap'])}  ({res.seconds:.1f}s)")


def playtest(args) -> int:
    from . import playtest as pt
    from .studio.orchestrator import studio_playtest

    project = args.project.resolve()
    profiles = tuple(p.strip() for p in args.profiles.split(",") if p.strip())
    progress = lambda m: _say(f"  {m}")
    _say(f"Playtesting {_rel(project)} ...")
    if (project / "studio.json").exists() and args.difficulty is None:
        res = studio_playtest(project, runs=args.runs, tune=args.tune, rounds=args.rounds, on_progress=progress)
    else:
        res = pt.playtest(project, runs=args.runs, profiles=profiles, tune=args.tune, rounds=args.rounds,
                          seed=args.seed, difficulty=args.difficulty or 2, on_progress=progress)
    if args.json:
        print(res.files["json"].read_text())
    else:
        _print_playtest(res)
    return 0


def studio(args) -> int:
    from .cockpit.server import Cockpit, CockpitServer

    server = CockpitServer(Cockpit(args.workspace), args.port).start()
    _say(f"Spawn Point Studio at {server.url} (games in {_rel(args.workspace.resolve())}) — Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(server.url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


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
