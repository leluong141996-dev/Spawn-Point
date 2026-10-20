"""One contact sheet of every procedural kind plus a cast of named people, for reviewing the art by eye.

`spawnpoint sprites gallery` renders it; tests check the cast still covers every kind, so a new kind
cannot ship without a place on the sheet.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from .generate import KINDS, features_for, generate
from .spriteset import SpriteSet

# (name, kind, colour): one entry per kind at least; people show off the accessories their names pick.
CAST: list[tuple[str, str, str]] = [
    ("Hero", "hero", "#29adff"), ("Knight", "hero", "#29adff"), ("Wizard", "hero", "#7e2553"),
    ("Ranger", "hero", "#3a8a40"), ("Viking", "hero", "#ab5236"), ("King", "hero", "#ffa300"),
    ("Princess", "hero", "#ff77a8"), ("Ninja", "hero", "#5f574f"), ("Skeleton", "hero", "#c2c3c7"),
    ("SkeletonArcher", "hero", "#c2c3c7"), ("Zombie", "hero", "#00e436"), ("Orc", "hero", "#3a8a40"),
    ("Goblin", "hero", "#00e436"),
    ("Slime", "slime", "#00e436"), ("Frog", "hopper", "#3a8a40"), ("Bat", "flyer", "#7e2553"),
    ("Robot", "robot", "#83769c"), ("Turret", "turret", "#83769c"), ("Beetle", "bug", "#ab5236"),
    ("Wolf", "beast", "#8a8a9a"), ("Spider", "spider", "#5f574f"), ("Dragon", "dragon", "#ff004d"),
    ("Ghost", "ghost", "#c2c3c7"), ("Snake", "snake", "#3a8a40"),
    ("Coin", "coin", "#ffcc40"), ("Star", "star", "#ffec27"), ("Gem", "gem", "#29adff"),
    ("Heart", "heart", "#ff004d"), ("Orb", "orb", "#83769c"), ("GoldKey", "key", "#ffcc40"),
    ("HealthPotion", "potion", "#e04858"), ("MagicScroll", "scroll", "#c03040"), ("Bomb", "bomb", "#333344"),
    ("TreasureChest", "chest", "#96603a"), ("Arrow", "arrow", "#e04858"), ("Bullet", "bullet", "#ffec27"),
    ("Slash", "slash", "#fff1e8"),
    ("Door", "door", "#ab5236"), ("Cage", "door", "#8a8f98"), ("Exit", "exit", "#00e436"), ("Portal", "portal", "#83769c"),
    ("Spikes", "spikes", "#c2c3c7"), ("Tree", "tree", "#4aa050"), ("PineTree", "tree", "#2f7a50"),
    ("BerryBush", "bush", "#5ab050"), ("MossyRock", "rock", "#8a8a9a"),
    ("Fighter", "ship", "#29adff"), ("Saucer", "ufo", "#00e436"),
]

CELL, PAD, LABEL, BG, TILE, TEXT = 96, 10, 14, (36, 40, 52, 255), (52, 58, 74, 255), (220, 224, 232, 255)


def render(name: str, kind: str, color: str, style: str, seed: int = 1) -> SpriteSet:
    feats = features_for(name)
    if style == "cartoon":
        from .cartoon import generate_cartoon
        return generate_cartoon(name, kind, color, feats, seed)
    return generate(name, kind, color, feats, seed, fine=style == "fine")


def gallery(style: str = "fine", columns: int = 8, cast: list[tuple[str, str, str]] | None = None) -> Image.Image:
    """The first idle frame of each cast member, scaled by a whole number to fit a cell, name underneath."""
    cast = cast or CAST
    rows = -(-len(cast) // columns)
    out = Image.new("RGBA", (PAD + columns * (CELL + PAD), PAD + rows * (CELL + LABEL + PAD)), BG)
    d = ImageDraw.Draw(out)
    smooth = style == "cartoon"
    for n, (name, kind, color) in enumerate(cast):
        s = render(name, kind, color, style)
        idle = s.animations.get("idle") or next(iter(s.animations.values()))
        w, h = s.frame_size
        frame = Image.fromarray(s.frame(*idle.frames[0]))
        zoom = CELL / max(w, h) if smooth else max(1, CELL // max(w, h))
        size = (max(1, round(w * zoom)), max(1, round(h * zoom)))
        frame = frame.resize(size, Image.LANCZOS if smooth else Image.NEAREST)
        x, y = PAD + (n % columns) * (CELL + PAD), PAD + (n // columns) * (CELL + LABEL + PAD)
        d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=TILE)
        out.alpha_composite(frame, (x + (CELL - size[0]) // 2, y + CELL - size[1] if KINDS[kind].anchor == "bottom"
                                    else y + (CELL - size[1]) // 2))
        d.text((x + 2, y + CELL + 1), name[:15], fill=TEXT)
    return out
