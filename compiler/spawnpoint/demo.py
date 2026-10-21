"""Static demo site: every example game built for the web, playable from one gallery page.

    spawnpoint demo --out site

The games are the SHOWCASE examples below. Each one is built, exported as a single-threaded web build
(works on GitHub Pages, no special headers), checked in headless Chrome (no console errors, a real
screenshot for the card) and linked from index.html.
"""

from __future__ import annotations

import html
import io
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import manifest as manifest_mod
from .build import build, load_graph
from .studio import web, webcheck

REPO = "https://github.com/leluong141996-dev/Spawn-Point"
MODEL = "https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ"
# (example graph, genre tag, one-line pitch, controls). Controls are ASCII: they travel through Godot's
# export_presets.cfg into the game page.
SHOWCASE = [
    ("pixel_hopper.json", "platformer",
     "A Mario-style romp: stomp slimes, double-jump, dash, and collect every coin to open the door.",
     "Move: arrows / WASD | Jump: Space (twice to double-jump) | Dash: Shift | Restart: R",
     {"pad": "lr", "buttons": [["JUMP", "Space"], ["DASH", "ShiftLeft"]]}),
    ("ninja_rescue.json", "platformer",
     "Mom has been caged! Throw shurikens, dodge the masked throwers, grab the key up high and set her free.",
     "Move: arrows / WASD | Jump: Space | Shuriken: X / J | Dash: Shift | Restart: R",
     {"pad": "lr", "buttons": [["JUMP", "Space"], ["STAR", "KeyX"], ["DASH", "ShiftLeft"]]}),
    ("knight_quest.json", "sword platformer",
     "A cartoon knight's run: slash slimes, bats and goblins with your sword, double-jump the spikes and reach the gate.",
     "Move: arrows / WASD | Jump: Space (twice to double-jump) | Sword: X / J | Restart: R",
     {"pad": "lr", "buttons": [["JUMP", "Space"], ["SWORD", "KeyX"]]}),
    ("castle_defense.json", "tower defense",
     "Goblins, orcs and wolves march on the castle: build archer and cannon towers beside the road and hold all seven waves.",
     "Build: click a pad | Tower: 1 archer / 2 cannon | Restart: R",
     {"pad": None, "buttons": [["2", "Digit2"], ["1", "Digit1"]], "tap": "Tap a pad to build; 1 / 2 picks the tower"}),
    ("star_run.json", "side-scrolling shooter",
     "Fly the Falcon through drones, saucers and hunters, grab power-ups for more guns, and bring down the Warship.",
     "Move: arrows / WASD | Fire: automatic | Restart: R",
     {"pad": "dpad", "buttons": [], "tap": "Move with the stick - the ship fires on its own"}),
    ("dino_eggs.json", "bubble shooter",
     "The classic egg shooter: bank shots off the walls, pop three dinosaur eggs of a colour, drop whole clusters.",
     "Aim: mouse or Left / Right | Shoot: click / Space / X | Restart: R",
     {"pad": None, "buttons": [], "tap": "Tap where you want the egg to go"}),
    ("night_survivor.json", "survivor",
     "Survive three minutes of the night: auto-fire, collect gems, level up and pick a new power each time.",
     "Move: arrows / WASD | Dash: Shift | Pick an upgrade: 1 / 2 / 3 or click | Restart: R",
     {"pad": "dpad", "buttons": [["DASH", "ShiftLeft"]], "tap": "Move with the stick - you shoot on your own"}),
    ("sunny_farm.json", "farming",
     "A cozy island farm over three days: buy seeds, till and grow strawberries, carrots and pumpkins, feed the hens and the cow, fish in the pond, chop wood, sleep in the farmhouse, upgrade your tools, and sell it all at the shipping bin. Your farm is saved as you play.",
     "Move: arrows / WASD | Till, plant, water, harvest, feed, fish, chop, go in, sleep: Space / E | Seed: 1 / 2 / 3 or click it | Shoo crows: X | Restart: R",
     {"pad": "dpad", "buttons": [["ACT", "Space"], ["SHOO", "KeyX"]],
      "tap": "ACT works the field, feeds, fishes and opens doors; tap a seed in the bar to choose it"}),
    ("pixel_arena.json", "arena shooter",
     "A top-down arena: blast through robots and turrets, then reach the portal.",
     "Move: WASD | Aim: mouse | Shoot: click / X | Dash: Shift | Restart: R",
     {"pad": "dpad", "buttons": [["DASH", "ShiftLeft"]], "tap": "Move with the stick, tap to shoot"}),
]
TOUCH_JS = Path(__file__).with_name("demo_touch.js")


def game_overlay(controls: str, touch: dict | None = None) -> str:
    """Injected into every game page: a way back to the gallery and the controls (bottom-left, clear of
    the HUD), plus the touch controls on phones (../touch.js). Hidden for screenshots (?shot)."""
    return (
        "<script>window.SP_TOUCH=" + json.dumps(touch or {}) + ";</script><script src=\"../touch.js\"></script>"
        "<style>#sp-bar{position:fixed;bottom:30px;left:8px;z-index:10;display:flex;gap:10px;align-items:center;"
        "font:12px/1.4 ui-monospace,Menlo,monospace;color:#fff;background:rgba(0,0,0,.55);padding:5px 10px;"
        "border-radius:6px;pointer-events:none}#sp-bar a{color:#ffec27;text-decoration:none;pointer-events:auto}"
        "@media (max-width:700px){#sp-bar span{display:none}}</style>"
        "<script>addEventListener('DOMContentLoaded',function(){if(location.search.indexOf('shot')>=0)return;"
        "var b=document.createElement('div');b.id='sp-bar';"
        "b.innerHTML='<a href=\\\"../\\\">&lt;- all games</a><span>" + controls + "</span>';"
        "document.body.appendChild(b);});</script>"
    )


@dataclass
class Game:
    slug: str
    graph: Path
    title: str = ""
    tag: str = ""
    blurb: str = ""
    controls: str = ""
    touch: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def discover(examples: Path | None = None) -> list[Game]:
    examples = examples or manifest_mod.EXAMPLES_DIR
    games: list[Game] = []
    for name, tag, blurb, controls, touch in SHOWCASE:
        path = examples / name
        if path.exists():
            data = load_graph(path)
            games.append(Game(path.stem.replace("_", "-"), path, data.get("name", path.stem), tag, blurb, controls,
                              touch))
    return games


def build_site(out: Path, games: list[Game] | None = None, screenshots: bool = True, log=print) -> list[Game]:
    """Builds every game into out/<slug>/ and writes out/index.html. Returns the games (with any errors)."""
    games = discover() if games is None else games
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for g in games:
            project = Path(tmp) / g.slug
            result = build(load_graph(g.graph), project, base_dir=g.graph.parent)
            if not result.ok:
                g.errors = [str(d) for d in result.diagnostics.errors] or ["build failed"]
                log(f"  {g.slug}: build failed: {g.errors[0]}")
                continue
            seconds = web.export(project, head_include=game_overlay(g.controls, g.touch))
            target = out / g.slug
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(project / web.WEB_DIR, target,
                            ignore=shutil.ignore_patterns(".gdignore", web.VERSION_FILE))
            share_engine(out, target)
            log(f"  {g.slug}: built (web export {seconds:.1f}s)")
    shutil.copy2(TOUCH_JS, out / "touch.js")  # every game page loads it (before the browser check)
    built = [g for g in games if (out / g.slug / "index.html").exists()]
    if screenshots:
        if webcheck.find_chrome() is None:
            log("Chrome not found: skipping the browser check and screenshots")
        else:
            check_in_browser(out, built, log)
    (out / "index.html").write_text(index_html(built))
    (out / ".nojekyll").write_text("")  # serve files as they are
    return games


ENGINE_DIR = "engine"
ENGINE_FILES = ("index.wasm", "index.js", "index.audio.worklet.js", "index.audio.position.worklet.js")


def share_engine(out: Path, game: Path) -> None:
    """Every game ships the same Godot engine (~37 MB of wasm). Keep one copy in out/engine/ and point each
    game at it, so the site is small and the engine is cached after the first game."""
    engine = out / ENGINE_DIR
    engine.mkdir(exist_ok=True)
    for name in ENGINE_FILES:
        src = game / name
        if not src.exists():
            continue
        dst = engine / name
        if not dst.exists():
            shutil.copy2(src, dst)
        elif dst.read_bytes() != src.read_bytes():
            raise RuntimeError(f"{game.name}/{name} differs from the shared engine (mixed Godot versions?)")
        src.unlink()
    page = game / "index.html"
    text = page.read_text()
    patched = (text.replace('src="index.js"', f'src="../{ENGINE_DIR}/index.js"')
                   .replace('"executable":"index"', f'"executable":"../{ENGINE_DIR}/index","mainPack":"index.pck"')
                   .replace('"index.wasm":', f'"../{ENGINE_DIR}/index.wasm":'))
    if patched.count(f"../{ENGINE_DIR}/") != 3:
        raise RuntimeError(f"{page}: unexpected Godot web shell, cannot point it at the shared engine")
    page.write_text(patched)


def check_in_browser(out: Path, games: list[Game], log=print) -> None:
    """Loads every game from the finished site in headless Chrome: no console errors, plus a thumbnail."""
    import functools
    import threading
    from http.server import ThreadingHTTPServer

    port = web.free_port(8150)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(web._Handler, directory=str(out)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for g in games:
            check = webcheck.check(f"http://localhost:{port}/{g.slug}/?shot", seconds=8)
            g.errors = list(check.errors)
            if not any("Godot Engine" in line for line in check.console):
                g.errors.append("the engine did not start")
            if check.screenshot:
                _thumbnail(check.screenshot, out / g.slug / "thumb.png")
            log(f"  {g.slug}: " + ("plays in Chrome" if not g.errors else "; ".join(g.errors[:2])))
    finally:
        httpd.shutdown()


def _thumbnail(png: bytes, path: Path, width: int = 480) -> None:
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB")
    img.thumbnail((width, width))
    img.save(path, optimize=True)


def index_html(games: list[Game]) -> str:
    cards = "\n".join(_card(g) for g in games)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spawn Point demos</title>
<meta name="description" content="Nine Godot 4 games built with Spawn Point: platformers, a sword fighter, tower defense, a space shooter, a bubble shooter, a survivor, a farm. Play in your browser.">
<meta property="og:title" content="Spawn Point demos: play Godot games in your browser">
<meta property="og:description" content="A Mario-style platformer, a ninja rescue, a dinosaur-egg shooter, a survivor and an arena, all built from Spawn Point components.">
<style>
:root {{ --bg:#14121c; --panel:#1f1c2b; --ink:#f4f1ff; --muted:#a59fbf; --accent:#ffec27; --ai:#29adff; --line:#332f45; }}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{ --bg:#f6f4fb; --panel:#ffffff; --ink:#1b1828; --muted:#5d5875; --accent:#b8860b; --ai:#0b6fb8; --line:#e3dff0; }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif }}
a {{ color:inherit }}
header, main, footer {{ max-width:1100px; margin:0 auto; padding:0 16px }}
header {{ padding-top:40px; padding-bottom:8px }}
h1 {{ font:700 clamp(28px,5vw,44px)/1.1 ui-monospace,Menlo,monospace; margin:0 0 10px; letter-spacing:-.02em }}
h1 span {{ color:var(--accent) }}
.lede {{ color:var(--muted); max-width:720px; margin:0 0 18px }}
.links {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px }}
.links a {{ text-decoration:none; border:1px solid var(--line); background:var(--panel); padding:7px 12px; border-radius:8px; font-size:14px }}
.links a:hover {{ border-color:var(--accent) }}
code {{ font:13px ui-monospace,Menlo,monospace; background:var(--panel); border:1px solid var(--line); padding:2px 6px; border-radius:5px }}
.note {{ color:var(--muted); font-size:13px; margin:4px 0 26px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; padding-bottom:40px }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; display:flex; flex-direction:column; text-decoration:none; transition:transform .12s, border-color .12s }}
.card:hover {{ transform:translateY(-2px); border-color:var(--accent) }}
.thumb {{ aspect-ratio:16/9; background:#000 center/cover no-repeat; image-rendering:pixelated; position:relative }}
.play {{ position:absolute; right:10px; bottom:10px; background:var(--accent); color:#000; font:700 13px ui-monospace,monospace; padding:5px 10px; border-radius:6px }}
.body {{ padding:12px 14px 16px; display:flex; flex-direction:column; gap:6px }}
.title {{ font-weight:700; font-size:17px }}
.tags {{ display:flex; gap:6px; flex-wrap:wrap }}
.tag {{ font:600 11px ui-monospace,monospace; text-transform:uppercase; letter-spacing:.04em; padding:2px 7px; border-radius:4px; border:1px solid var(--line); color:var(--muted) }}
.tag.ai {{ color:var(--ai); border-color:var(--ai) }}
.blurb {{ margin:2px 0 0; color:var(--ink) }}
.controls {{ margin:0; color:var(--muted); font:12px/1.5 ui-monospace,Menlo,monospace }}
footer {{ color:var(--muted); font-size:13px; padding-bottom:40px }}
</style>
</head>
<body>
<header>
  <h1>Spawn<span>Point</span> demos</h1>
  <p class="lede">Nine games, nine ways to play, all built by Spawn Point from small JSON game graphs and a
  library of tested Godot 4 components: game feel, cartoon or pixel art and collisions come for free. Click a card to play in
  your browser, no install needed.</p>
  <div class="links">
    <a href="{REPO}">⭐ GitHub repo</a>
    <a href="{MODEL}">🤗 SpawnPoint-Coder-7B</a>
    <a href="https://pypi.org/project/spawnpoint-studio/">📦 pip install spawnpoint-studio</a>
  </div>
  <p class="note">Desktop + keyboard. Make your own from a sentence:
  <code>spawnpoint create "a ninja platformer where you collect stars"</code></p>
</header>
<main class="grid">
{cards}
</main>
<footer>Built by the <a href="{REPO}/blob/main/.github/workflows/pages.yml">pages workflow</a> from the graphs in
<a href="{REPO}/tree/main/examples">examples/</a>. MIT licensed.</footer>
</body>
</html>
"""


def _card(g: Game) -> str:
    esc = html.escape
    thumb = f' style="background-image:url({g.slug}/thumb.png)"'
    tags = f'<span class="tag ai">{esc(g.tag)}</span>' if g.tag else ""
    return (f'<a class="card" href="{g.slug}/"><div class="thumb"{thumb}><span class="play">▶ PLAY</span></div>'
            f'<div class="body"><div class="title">{esc(g.title)}</div><div class="tags">{tags}</div>'
            f'<p class="blurb">{esc(g.blurb)}</p><p class="controls">{esc(g.controls)}</p></div></a>')
