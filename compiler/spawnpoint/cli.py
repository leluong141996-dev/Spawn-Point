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

    tw = sub.add_parser("tweak", help="change a created game with a text request (uses the LLM)")
    tw.add_argument("project", type=Path)
    tw.add_argument("request")
    tw.add_argument("--no-web", action="store_true")

    sv = sub.add_parser("serve", help="serve a project's web build with live reload")
    sv.add_argument("project", type=Path)
    sv.add_argument("--port", type=int, default=8060)
    sv.add_argument("--no-open", action="store_true")

    args = ap.parse_args(argv)
    try:
        from . import studio_cli
        return {"validate": _validate, "build": _build, "run": _run, "components": _components,
                "manifest": _manifest, "create": studio_cli.create, "tweak": studio_cli.tweak,
                "serve": studio_cli.serve}[args.cmd](args)
    except godot.GodotError as e:
        print(f"error: {e}", file=sys.stderr)
        if e.output:
            print(e.output[-3000:], file=sys.stderr)
        return 2


def _print_diags(diags) -> None:
    for d in diags:
        print(("  ✗ " if d.severity == "error" else "  ! ") + str(d))


def _validate(args) -> int:
    analysis = validate(load_graph(args.graph))
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
    result = build(data, out.resolve(), smoke=not args.no_smoke)
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


def _manifest(args) -> int:
    data = manifest_mod.generate()
    print(f"Wrote {manifest_mod.MANIFEST_PATH} ({len(data['components'])} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
