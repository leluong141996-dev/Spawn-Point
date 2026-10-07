"""Command line: spawnpoint validate | build | run | components | manifest."""

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
    cr.add_argument("--port", type=int, default=8060)
    cr.add_argument("--record", action="store_true", help="save LLM calls as local fine-tuning data")

    tw = sub.add_parser("tweak", help="change a created game with a text request (uses the LLM)")
    tw.add_argument("project", type=Path)
    tw.add_argument("request")
    tw.add_argument("--no-web", action="store_true")
    tw.add_argument("--record", action="store_true", help="save LLM calls as local fine-tuning data")

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

    ds = sub.add_parser("dataset", help="recorded fine-tuning data")
    ds.add_argument("action", choices=["stats", "path"])
    ds.add_argument("--json", action="store_true")

    sv = sub.add_parser("serve", help="serve a project's web build with live reload")
    sv.add_argument("project", type=Path)
    sv.add_argument("--port", type=int, default=8060)
    sv.add_argument("--no-open", action="store_true")

    args = ap.parse_args(argv)
    try:
        from . import studio_cli
        return {"validate": _validate, "build": _build, "run": _run, "components": _components,
                "manifest": _manifest, "create": studio_cli.create, "tweak": studio_cli.tweak,
                "serve": studio_cli.serve, "dataset": studio_cli.dataset,
                "sprites": _sprites}[args.cmd](args)
    except godot.GodotError as e:
        print(f"error: {e}", file=sys.stderr)
        if e.output:
            print(e.output[-3000:], file=sys.stderr)
        return 2


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


def _sprites(args) -> int:
    from .sprites import generate as gen, importer
    from .sprites.spriteset import SpriteError, load

    try:
        if args.sprites_cmd == "kinds":
            for k, spec in gen.KINDS.items():
                print(f"{k:<8} {spec.size[0]}x{spec.size[1]} px  animations: {', '.join(spec.anims)}")
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
