"""The cast page: while `spawnpoint create` builds the layers, the browser shows the game's characters (the hero,
the enemies, the boss, the pickups) moving, with the game's name and goal, and switches to the game when it is
ready. The first thing a new user sees is their game's cast instead of grey placeholder shapes.

    write(out_dir, graph, manifest)   -> the cast page in <out_dir>/web (index.html, cast/*.gif, status.json)
    status(out_dir, text)             -> the progress line on the page
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from PIL import Image

from .web import WEB_DIR

CARD_BG = (36, 31, 66)
CELL = 112  # the largest a character is drawn on the page (whole-number scales only)
SKIP = {"Bullet", "EnemyBullet", "Slash", "Gust", "XpGem"}


def roles(graph: dict) -> list[tuple[str, str]]:
    """(entity, role) for the characters worth showing, hero first, bosses before the other foes, pickups last."""
    ents = graph["entities"]
    bosses = set()
    for e in ents.values():
        battle = e.get("components", {}).get("CardBattle")
        if battle:  # card games list their foes and which one is the boss
            bosses |= {f.split("|")[0] for f in battle.get("foes", "").split(";") if f.count("|") >= 2 and f.split("|")[2] == "boss"}
    out = []
    for name, e in ents.items():
        comps = e.get("components", {})
        if name in SKIP or e.get("decor") or "sprite" not in e:
            continue
        if "PlayerInput" in comps:
            out.append((name, "hero"))
        elif name in bosses or "HealthBar" in comps:
            out.append((name, "boss"))
        elif e.get("team") == "enemy" or {"ChaseAI", "PatrolAI", "PathFollower", "FlightPath", "CropPest"} & set(comps):
            out.append((name, "foe"))
        elif "Collectible" in comps:
            out.append((name, "pickup"))
    order = {"hero": 0, "boss": 1, "foe": 2, "pickup": 3}
    return sorted(out, key=lambda r: order[r[1]])[:8]


def _gif(sprite, path: Path) -> None:
    """The sprite idling, then running when it can, on the card's colour, at a whole-number scale."""
    anims = sprite.animations
    seq = []
    for name in ("idle", "run"):
        a = anims.get(name)
        if a:
            seq += [(name, f) for f in a.frames] * (3 if len(a.frames) < 3 else 1)
    if not seq:
        a = next(iter(anims.values()))
        seq = [("", f) for f in a.frames]
    w, h = sprite.frame_size
    k = max(1, CELL // max(w, h))
    frames = []
    for _anim, (col, row) in seq:
        f = Image.fromarray(sprite.frame(col, row)).convert("RGBA").resize((w * k, h * k), Image.NEAREST)
        card = Image.new("RGBA", f.size, CARD_BG + (255,))
        card.alpha_composite(f)
        frames.append(card.convert("RGB"))
    fps = (anims.get("idle") or next(iter(anims.values()))).fps or 6
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)


def write(out_dir: Path, graph: dict, manifest, hero: str = "") -> list[tuple[str, str]]:
    """Writes the cast page into the game's web folder (the game's own export replaces it when it is ready)."""
    from ..analyze import analyze

    web = out_dir / WEB_DIR
    (web / "cast").mkdir(parents=True, exist_ok=True)
    for old in ("version.json", "index.html"):  # an earlier build of this game must not be shown as "ready"
        (web / old).unlink(missing_ok=True)
    (web / ".gdignore").write_text("")
    analysis = analyze(graph, manifest)
    cast = [(n, r) for n, r in roles(graph) if n in analysis.sprites]
    for i, (name, _role) in enumerate(cast):
        _gif(analysis.sprites[name], web / "cast" / f"{i}.gif")
    title = graph.get("name", "Your game")
    player = next((e for e in graph["entities"].values() if "PlayerInput" in e.get("components", {})), {})
    menu = player.get("components", {}).get("GameMenu", {})
    goal = menu.get("subtitle") or next((r["do"][0][len("message("):-1].strip("'\"") for r in graph.get("rules", [])
                                         if r.get("on") == "Game.ready" and r["do"]), "")
    (web / "index.html").write_text(page(title, goal, [(f"cast/{i}.gif", _label(n, r, hero), r)
                                                     for i, (n, r) in enumerate(cast)]))
    status(out_dir, "Building the level ...")
    return cast


def _label(name: str, role: str, hero: str) -> str:
    """ "IceSpirit" -> "Ice Spirit"; the hero is called what the design calls it."""
    if role == "hero" and name == "Player":
        name = hero or "You"
    return "".join(" " + c if c.isupper() and i and not name[i - 1].isupper() else c for i, c in enumerate(name)).strip()


def status(out_dir: Path, text: str) -> None:
    (out_dir / WEB_DIR).mkdir(parents=True, exist_ok=True)
    (out_dir / WEB_DIR / "status.json").write_text(json.dumps({"text": text}))


ROLE_TEXT = {"hero": "Hero", "boss": "Boss", "foe": "Enemy", "pickup": "Pickup"}
ROLE_COLOR = {"hero": "#29adff", "boss": "#ff004d", "foe": "#ffa300", "pickup": "#ffec27"}


def page(title: str, goal: str, cards: list[tuple[str, str, str]]) -> str:
    items = "\n".join(
        f'<div class="card" style="animation-delay:{0.12 * i:.2f}s"><img src="{src}" alt="{html.escape(label)}">'
        f'<b>{html.escape(label)}</b><i style="color:{ROLE_COLOR[role]}">{ROLE_TEXT[role]}</i></div>'
        for i, (src, label, role) in enumerate(cards))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; min-height: 100vh; background: #14102a; color: #fff1e8; display: flex; flex-direction: column;
  align-items: center; justify-content: center; font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; }}
h1 {{ color: #ffec27; font-size: clamp(28px, 6vw, 56px); margin: 0 16px 6px; text-align: center;
  text-shadow: 4px 4px 0 #1d1a33; letter-spacing: 1px; }}
p.goal {{ margin: 0 16px 28px; text-align: center; color: #d8d0e8; max-width: 720px; }}
.cast {{ display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; max-width: 980px; padding: 0 16px; }}
.card {{ background: rgb{CARD_BG}; border: 4px solid #1d1a33; box-shadow: 0 0 0 2px #4a4070, 6px 6px 0 #0a0818;
  padding: 12px; width: 132px; display: flex; flex-direction: column; align-items: center; gap: 6px;
  animation: pop .5s cubic-bezier(.2, 1.6, .5, 1) both; }}
.card img {{ width: auto; height: 112px; image-rendering: pixelated; object-fit: contain; }}
.card b {{ font-size: 15px; text-align: center; }}
.card i {{ font-style: normal; font-size: 12px; text-transform: uppercase; letter-spacing: 2px; }}
@keyframes pop {{ from {{ transform: scale(.4) translateY(30px); opacity: 0; }} to {{ transform: none; opacity: 1; }} }}
.bar {{ width: min(520px, 80vw); height: 14px; background: #1d1a33; border: 3px solid #4a4070; margin: 34px 0 10px;
  overflow: hidden; }}
.bar span {{ display: block; height: 100%; width: 30%; background: #e8902a; animation: slide 1.2s ease-in-out infinite; }}
@keyframes slide {{ from {{ margin-left: -30%; }} to {{ margin-left: 100%; }} }}
#status {{ color: #9ee8ff; min-height: 1.4em; }}
</style></head>
<body>
<h1>{html.escape(title)}</h1>
<p class="goal">{html.escape(goal)}</p>
<div class="cast">
{items}
</div>
<div class="bar"><span></span></div>
<div id="status">Building the level ...</div>
<script>
// The game replaces this page: when its build lands (version.json appears) the page reloads into it.
setInterval(function () {{
  fetch('status.json?' + Date.now(), {{cache: 'no-store'}}).then(function (r) {{ return r.ok ? r.json() : null; }})
    .then(function (j) {{ if (j) document.getElementById('status').textContent = j.text; }}).catch(function () {{}});
  fetch('version.json?' + Date.now(), {{cache: 'no-store'}}).then(function (r) {{ if (r.ok) location.reload(); }})
    .catch(function () {{}});
}}, 700);
</script>
</body></html>
"""
