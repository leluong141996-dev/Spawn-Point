"""Command line: spawnpoint setup | create | tweak | share | build | run | ... (see `spawnpoint --help`)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__, godot, manifest as manifest_mod
from .build import build, load_graph, validate
from .project import slugify


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="spawnpoint", description="Compile JSON game graphs into Godot 4 projects.")
    ap.add_argument("--version", action="version", version=f"spawnpoint {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a game graph without building")
    v.add_argument("graph", type=Path)
    v.add_argument("--json", action="store_true", help="print diagnostics as JSON")

    b = sub.add_parser("build", help="build a playable Godot project")
    b.add_argument("graph", type=Path)
    b.add_argument("-o", "--out", type=Path, help="output directory (default: out/<game-name>)")
    b.add_argument("--no-smoke", action="store_true", help="skip the headless smoke run")
    b.add_argument("--json", action="store_true", help="print the result as JSON")
    b.add_argument("--run", action="store_true", help="open the game window after a successful build")

    r = sub.add_parser("run", help="play a built project")
    r.add_argument("project", type=Path)

    c = sub.add_parser("components", help="list available components")
    c.add_argument("--json", action="store_true")

    sub.add_parser("manifest", help="regenerate the component manifest from the Godot library")

    cr = sub.add_parser("create", help="design and build a game from a text prompt (uses the LLM)")
    cr.add_argument("prompt")
    cr.add_argument("-o", "--out", type=Path, help="output directory (default: out/<title>)")
    cr.add_argument("--seed", type=int, help="level seed (default: derived from the prompt)")
    cr.add_argument("--brief", type=Path, help="skip the LLM and use this GameBrief JSON")
    cr.add_argument("--creative", action="store_true", help="let the LLM add a validated creative patch")
    cr.add_argument("--no-web", action="store_true", help="skip the web export (play with `spawnpoint run`)")
    cr.add_argument("--no-open", action="store_true", help="do not open the browser")
    cr.add_argument("--no-serve", action="store_true", help="exit after building instead of serving")
    cr.add_argument("--no-chat", action="store_true", help="do not ask for changes after building")
    cr.add_argument("--port", type=int, default=8060)
    cr.add_argument("--record", action="store_true", help="save LLM calls as local fine-tuning data")
    cr.add_argument("--playtest", action="store_true", help="after layer 2, let bots play and tune the game")
    cr.add_argument("--ai-art", action="store_true",
                    help="layer 2 sprites from an image model (SPAWNPOINT_IMAGE_PROVIDER), generated ones as fallback")

    st = sub.add_parser("studio", help="open the web cockpit (create, tweak, click-to-edit, playtest)")
    st.add_argument("--workspace", type=Path, default=Path("out"), help="folder holding the games (default: out)")
    st.add_argument("--port", type=int, default=8070)
    st.add_argument("--no-open", action="store_true")

    pt = sub.add_parser("playtest", help="bots play a built game: report, death heatmap, optional tuning")
    pt.add_argument("project", type=Path)
    pt.add_argument("--runs", type=int, default=3, help="runs per profile")
    pt.add_argument("--profiles", default="novice,average,expert")
    pt.add_argument("--tune", action="store_true", help="adjust parameters within bounds and re-test")
    pt.add_argument("--rounds", type=int, default=2)
    pt.add_argument("--seed", type=int, default=1)
    pt.add_argument("--difficulty", type=int, help="target difficulty 1-5 (default: the brief's, else 2)")
    pt.add_argument("--json", action="store_true")

    tw = sub.add_parser("tweak", help="change a created game with a text request (uses the LLM)")
    tw.add_argument("project", type=Path)
    tw.add_argument("request")
    tw.add_argument("--no-web", action="store_true")
    tw.add_argument("--record", action="store_true", help="save LLM calls as local fine-tuning data")

    lm = sub.add_parser("llm", help="run SpawnPoint-Coder-7B locally (vLLM on NVIDIA, or Ollama anywhere)")
    lm.add_argument("action", choices=["up", "down", "status"])
    lm.add_argument("--port", type=int, default=8000)
    lm.add_argument("--backend", choices=["auto", "vllm", "ollama"], default="auto",
                    help="auto: vLLM with Docker + an NVIDIA GPU, otherwise Ollama")

    ex = sub.add_parser("examples", help="list the example graphs, or copy one here")
    ex.add_argument("action", nargs="?", choices=["list", "copy"], default="list")
    ex.add_argument("name", nargs="?")

    dm = sub.add_parser("demo", help="build every example as a web game plus a gallery page (static site)")
    dm.add_argument("-o", "--out", type=Path, default=Path("site"))
    dm.add_argument("--no-screenshots", action="store_true", help="skip the headless-Chrome check and thumbnails")

    gf = sub.add_parser("gif", help="record a gameplay GIF of a built project (autopilot; needs a display)")
    gf.add_argument("project", type=Path)
    gf.add_argument("-o", "--out", type=Path, help="output file (default: <project>/demo.gif)")
    gf.add_argument("--seconds", type=float, default=8.0)
    gf.add_argument("--fps", type=int, default=20)
    gf.add_argument("--width", type=int, default=640)
    gf.add_argument("--skip", type=float, default=0.0, help="seconds of play before the clip starts")
    gf.add_argument("--focus", default="", choices=["", "field", "animals", "fish", "house"],
                    help="farms: show one activity")
    gf.add_argument("--clean", action="store_true", help="hide the HUD (for covers and banners)")

    lg = sub.add_parser("logo", help="write the Spawn Point pixel-art logo (icons, wordmark, favicon)")
    lg.add_argument("-o", "--out", type=Path, default=Path("logo"))

    ov = sub.add_parser("overview", help="save one picture of a built project's whole map (needs a display)")
    ov.add_argument("project", type=Path)
    ov.add_argument("-o", "--out", type=Path, help="output file (default: <project>/overview.png)")
    ov.add_argument("--seconds", type=float, default=20.0, help="seconds of autopilot play first")

    sp = sub.add_parser("sprites", help="import, generate or preview sprites")
    sps = sp.add_subparsers(dest="sprites_cmd", required=True)
    si = sps.add_parser("import", help="turn a sprite sheet or a folder of frames into a SpriteSet")
    si.add_argument("source", type=Path, help="PNG sheet or folder of PNG frames")
    si.add_argument("--name", help="sprite name (default: from the file name)")
    si.add_argument("--grid", help="cell size WxH, e.g. 32x32 (default: auto-detect from transparent gutters)")
    si.add_argument("--spacing", type=int, default=0)
    si.add_argument("--margin", type=int, default=0)
    si.add_argument("--anim", action="append", default=[], metavar="NAME=FRAMES",
                    help="e.g. idle=0-3 (repeatable; frame indices in reading order)")
    si.add_argument("--rows", help="comma-separated animation names, one per row, e.g. idle,run,jump")
    si.add_argument("--fps", action="append", default=[], metavar="NAME=FPS")
    si.add_argument("--scale", type=int, default=2)
    si.add_argument("--anchor", choices=["bottom", "center"], default="bottom")
    si.add_argument("-o", "--out", type=Path, default=Path("assets/sprites"))
    sg = sps.add_parser("generate", help="draw a procedural pixel-art SpriteSet")
    sg.add_argument("kind")
    sg.add_argument("--name", required=True)
    sg.add_argument("--color", default="#29adff")
    sg.add_argument("--features", help="comma-separated, e.g. mask,tail (default: from the name)")
    sg.add_argument("--seed", type=int, default=0)
    sg.add_argument("-o", "--out", type=Path, default=Path("assets/sprites"))
    sv2 = sps.add_parser("preview", help="render a contact sheet PNG of a SpriteSet with its collision outline")
    sv2.add_argument("sprite", type=Path)
    sv2.add_argument("-o", "--out", type=Path)
    sps.add_parser("kinds", help="list the procedural sprite kinds")
    sga = sps.add_parser("gallery", help="render one contact sheet of every procedural kind, for review")
    sga.add_argument("--style", choices=["pixel", "fine", "cartoon"], default="fine")
    sga.add_argument("-o", "--out", type=Path, default=Path("sprite-gallery.png"))
    spa = sps.add_parser("parade", help="render an animated sheet (GIF) of characters, monsters or items")
    spa.add_argument("--set", dest="which", choices=["heroes", "monsters", "items"], default="heroes")
    spa.add_argument("-o", "--out", type=Path, default=Path("sprite-parade.gif"))

    ds = sub.add_parser("dataset", help="recorded fine-tuning data")
    ds.add_argument("action", choices=["stats", "path"])
    ds.add_argument("--json", action="store_true")

    su = sub.add_parser("setup", help="install Godot and the web templates if missing, and check how the model can run")
    su.add_argument("--check", action="store_true", help="only report what is missing; install nothing")
    su.add_argument("--no-web", action="store_true", help="skip the web export templates")
    su.add_argument("--no-model", action="store_true", help="do not check how the model can run (e.g. on CI)")

    sh = sub.add_parser("share", help="zip a game's web build to upload to itch.io or send to friends")
    sh.add_argument("project", type=Path)
    sh.add_argument("-o", "--out", type=Path, help="zip file (default: <project>-web.zip next to the project)")

    sv = sub.add_parser("serve", help="serve a project's web build with live reload")
    sv.add_argument("project", type=Path)
    sv.add_argument("--port", type=int, default=8060)
    sv.add_argument("--no-open", action="store_true")

    args = ap.parse_args(argv)
    try:
        from . import studio_cli
        return {"validate": _validate, "build": _build, "run": _run, "components": _components,
                "manifest": _manifest, "create": studio_cli.create, "tweak": studio_cli.tweak,
                "serve": studio_cli.serve, "dataset": studio_cli.dataset, "playtest": studio_cli.playtest, "studio": studio_cli.studio,
                "sprites": _sprites, "gif": _gif, "overview": _overview, "logo": _logo, "llm": _llm, "examples": _examples,
                "demo": _demo, "setup": _setup, "share": studio_cli.share}[args.cmd](args)
    except godot.GodotError as e:
        print(f"error: {e}", file=sys.stderr)
        if e.output:
            print(e.output[-3000:], file=sys.stderr)
        return 2


def _setup(args) -> int:
    from . import installer
    return installer.run(args)


def _print_diags(diags) -> None:
    for d in diags:
        print(("  ✗ " if d.severity == "error" else "  ! ") + str(d))


def _validate(args) -> int:
    analysis = validate(load_graph(args.graph), base_dir=args.graph.resolve().parent)
    if args.json:
        print(json.dumps([d.to_dict() for d in analysis.diagnostics], indent=2))
    else:
        _print_diags(analysis.diagnostics)
        n_err, n_warn = len(analysis.diagnostics.errors), len(analysis.diagnostics.warnings)
        print(f"{'OK' if analysis.ok else 'INVALID'}: {n_err} error(s), {n_warn} warning(s)")
    return 0 if analysis.ok else 1


def _build(args) -> int:
    data = load_graph(args.graph)
    name = data.get("name", args.graph.stem) if isinstance(data, dict) else args.graph.stem
    out = args.out or Path("out") / slugify(str(name))
    result = build(data, out.resolve(), smoke=not args.no_smoke, base_dir=args.graph.resolve().parent)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_diags(result.diagnostics)
        if result.ok:
            t = result.timings
            print(f"Built {out} in {t.get('total', sum(t.values())):.1f}s "
                  f"(validate {t.get('validate', 0) * 1000:.0f}ms, godot {t.get('godot_import', 0) + t.get('godot_build', 0):.1f}s"
                  + (f", smoke {t['smoke']:.1f}s" if "smoke" in t else "") + ")")
            if result.smoke:
                print("Smoke:", json.dumps(result.smoke))
            print(f"Play it: spawnpoint run {out}   (or open {out}/project.godot in Godot)")
        else:
            print("BUILD FAILED")
            if result.log:
                tail = "\n".join(result.log.splitlines()[-30:])
                print(tail, file=sys.stderr)
    if result.ok and args.run:
        return _run(argparse.Namespace(project=out))
    return 0 if result.ok else 1


def _run(args) -> int:
    return subprocess.call([godot.find_binary(), "--path", str(args.project)])


def _components(args) -> int:
    m = manifest_mod.load()
    if args.json:
        print(manifest_mod.MANIFEST_PATH.read_text())
        return 0
    for c in sorted(m.components.values(), key=lambda c: (c.category, c.name)):
        hosts = f" (body: {', '.join(c.hosts)})" if c.hosts else ""
        print(f"\n{c.name} [{c.category}]{hosts}")
        print("  " + c.doc.split("\n")[0])
        for p in c.params.values():
            print(f"    {p.describe()}")
        for s in c.signals.values():
            print(f"    signal {s.name}({', '.join(a.name for a in s.args)})")
        for mt in c.methods.values():
            print(f"    {mt.name}({', '.join(a.name for a in mt.args)})")
    return 0


def _llm(args) -> int:
    from . import llm_server

    try:
        return {"up": lambda: llm_server.up(args.port, backend=args.backend),
                "down": lambda: llm_server.down(backend=args.backend),
                "status": lambda: llm_server.status(args.port, backend=args.backend)}[args.action]()
    except (RuntimeError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _examples(args) -> int:
    import shutil

    files = sorted(manifest_mod.EXAMPLES_DIR.glob("*.json"))
    if args.action == "list" or not args.name:
        for f in files:
            data = json.loads(f.read_text())
            print(f"{f.stem:<14} {data.get('genre', ''):<11} {data.get('name', '')}")
        print("Copy one: spawnpoint examples copy pixel_hopper   then: spawnpoint build pixel_hopper.json --run")
        return 0
    src = manifest_mod.EXAMPLES_DIR / f"{args.name.removesuffix('.json')}.json"
    if not src.exists():
        print(f"error: no example '{args.name}'", file=sys.stderr)
        return 1
    shutil.copy2(src, Path.cwd() / src.name)
    print(f"Wrote {src.name}")
    return 0


def _gif(args) -> int:
    from .gif import record_gif

    out = args.out or args.project / "demo.gif"
    path = record_gif(args.project.resolve(), out.resolve(), args.seconds, args.fps, args.width, args.skip, args.focus,
                      args.clean)
    print(f"Wrote {out} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


def _logo(args) -> int:
    from .logo import write

    for path in write(args.out):
        print(f"Wrote {path}")
    return 0


def _overview(args) -> int:
    from .gif import overview

    out = args.out or args.project / "overview.png"
    overview(args.project.resolve(), out.resolve(), args.seconds)
    print(f"Wrote {out}")
    return 0


def _demo(args) -> int:
    from .demo import build_site

    print(f"Building the demo site in {args.out}/")
    games = build_site(args.out, screenshots=not args.no_screenshots)
    failed = [g for g in games if g.errors]
    for g in failed:
        print(f"error: {g.slug}: " + "; ".join(g.errors[:3]), file=sys.stderr)
    print(f"{len(games) - len(failed)}/{len(games)} games ok. Preview: python -m http.server -d {args.out}")
    return 1 if failed else 0


def _sprites(args) -> int:
    from .sprites import generate as gen, importer
    from .sprites.spriteset import SpriteError, load

    try:
        if args.sprites_cmd == "kinds":
            for k, spec in gen.KINDS.items():
                print(f"{k:<8} {spec.size[0]}x{spec.size[1]} px  animations: {', '.join(spec.anims)}")
            return 0
        if args.sprites_cmd == "parade":
            from .sprites.gallery import parade
            frames = parade(args.which)
            frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=True)
            print(f"Wrote {args.out}")
            return 0
        if args.sprites_cmd == "gallery":
            from .sprites.gallery import gallery
            gallery(args.style).save(args.out)
            print(f"Wrote {args.out}")
            return 0
        if args.sprites_cmd == "preview":
            s = load(args.sprite)
            out = args.out or args.sprite.with_suffix("").with_suffix(".preview.png")
            importer.preview(s).save(out)
            print(f"Wrote {out}")
            return 0
        if args.sprites_cmd == "generate":
            feats = [f.strip() for f in args.features.split(",")] if args.features else None
            s = gen.generate(args.name, args.kind, args.color, feats, args.seed)
        else:
            fps = {k: float(v) for k, v in (x.split("=", 1) for x in args.fps)}
            if args.source.is_dir():
                s = importer.import_folder(args.source, args.name, fps=fps, scale=args.scale, anchor=args.anchor)
            else:
                grid = tuple(int(v) for v in args.grid.lower().split("x")) if args.grid else None
                anims = {k: importer.parse_ranges(v) for k, v in (x.split("=", 1) for x in args.anim)} or None
                rows = [r.strip() for r in args.rows.split(",")] if args.rows else None
                s = importer.import_sheet(args.source, args.name, grid=grid, spacing=args.spacing, margin=args.margin,
                                          anims=anims, row_names=rows, fps=fps, scale=args.scale, anchor=args.anchor)
    except (SpriteError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    path = s.save(args.out)
    anims = ", ".join(f"{k} ({len(a.frames)})" for k, a in s.animations.items())
    print(f"Wrote {path}: {s.frame_size[0]}x{s.frame_size[1]} frames, {anims}; outline {len(s.polygon)} points")
    print(f'Use it in a graph: "sprite": "{path}"')
    return 0


def _manifest(args) -> int:
    data = manifest_mod.generate()
    print(f"Wrote {manifest_mod.MANIFEST_PATH} ({len(data['components'])} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
