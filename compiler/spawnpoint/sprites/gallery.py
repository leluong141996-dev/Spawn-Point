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
    ("BitingPlant", "plant", "#ff004d"), ("Mushroom", "mushroom", "#e8403a"), ("Reaper", "reaper", "#7e2553"),
    ("Flame", "flame", "#ff6a1a"), ("Snail", "snail", "#b06ad8"), ("Alien", "alien", "#6fd24a"),
    ("Coin", "coin", "#ffcc40"), ("Star", "star", "#ffec27"), ("Gem", "gem", "#29adff"),
    ("Heart", "heart", "#ff004d"), ("Orb", "orb", "#83769c"), ("GoldKey", "key", "#ffcc40"),
    ("HealthPotion", "potion", "#e04858"), ("MagicScroll", "scroll", "#c03040"), ("Bomb", "bomb", "#333344"),
    ("TreasureChest", "chest", "#96603a"), ("Arrow", "arrow", "#e04858"), ("Bullet", "bullet", "#ffec27"),
    ("Slash", "slash", "#fff1e8"),
    ("Door", "door", "#ab5236"), ("Cage", "door", "#8a8f98"), ("Exit", "exit", "#00e436"), ("Portal", "portal", "#83769c"),
    ("Spikes", "spikes", "#c2c3c7"), ("Tree", "tree", "#4aa050"), ("PineTree", "tree", "#2f7a50"),
    ("BerryBush", "bush", "#5ab050"), ("MossyRock", "rock", "#8a8a9a"),
    ("Fighter", "ship", "#29adff"), ("Saucer", "ufo", "#00e436"),
    ("Farmhouse", "farmhouse", "#b4472e"), ("Coop", "coop", "#c0503a"), ("Oak", "tree_oak", "#5cb84a"),
    ("AppleTree", "tree_fruit", "#5cb84a"), ("CherryTree", "tree_blossom", "#ffa8c8"), ("Pine", "tree_pine", "#2f8a5a"),
    ("Well", "well", "#b4472e"), ("Scarecrow", "scarecrow", "#4a7ad0"), ("Stump", "stump", "#9a5e36"),
    ("Boulder", "boulder", "#a8a8b8"), ("ShippingBin", "bin", "#9a5e36"), ("Hay", "hay", "#e8c25a"),
    ("Barrel", "barrel", "#9a5e36"), ("Signpost", "signpost", "#9a5e36"), ("FlowerBush", "flower_bush", "#ff8fb4"),
    ("FenceH", "fence_h", "#9a5e36"), ("FenceV", "fence_v", "#9a5e36"), ("FencePost", "fence_post", "#9a5e36"),
    ("Chicken", "chicken", "#f4ece0"), ("Chick", "chick", "#ffd84a"), ("Cow", "cow", "#a0582e"),
    ("Farmer", "farmer", "#e8503a"), ("Maple", "tree_maple", "#d8402a"), ("SnowyPine", "tree_snowy_pine", "#2f7a5a"),
    ("BareTree", "tree_bare", "#9a5e36"), ("Palm", "tree_palm", "#4caf50"), ("Cactus", "cactus", "#5aa048"),
    ("Bed", "bed", "#4a7ad0"), ("Fireplace", "fireplace", "#c8643a"), ("Table", "table", "#9a5e36"),
    ("Workbench", "workbench", "#9a5e36"), ("ShopStall", "shop", "#3a8ad0"), ("Sprinkler", "sprinkler", "#a8a8b8"), ("Crow", "crow", "#3a3448"), ("Fox", "fox", "#e07a2a"), ("Rabbit", "rabbit", "#d8c8b8"), ("Mouse", "mouse", "#9a9aa8"),
    ("Chair", "chair", "#9a5e36"), ("Dresser", "dresser", "#9a5e36"), ("PottedPlant", "potted_plant", "#5cb84a"),
    # card battle fighters (sprites/fighters.py)
    ("Knight", "fighter_hero", "#3a78c8"), ("Jelly", "fighter_slime", "#5cd84a"), ("Wolf", "fighter_beast", "#8a8a9a"),
    ("Bat", "fighter_flyer", "#5a4a7a"), ("Treant", "fighter_treant", "#4a9a4a"), ("Spook", "fighter_ghost", "#b8e8f0"),
    ("Spider", "fighter_spider", "#4a3a5a"), ("Toadstool", "fighter_mushroom", "#d8402a"),
    ("Dragon", "fighter_dragon", "#c83a3a"),
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


PARADES: dict[str, list[str]] = {
    "heroes": ["Knight", "Wizard", "Ranger", "Viking", "King", "Princess", "Ninja", "Hero", "Skeleton", "SkeletonArcher",
               "Zombie", "Orc", "Goblin", "Alien", "Reaper"],
    "monsters": ["Slime", "Frog", "BitingPlant", "Wolf", "Mushroom", "Snail", "Flame", "Ghost", "Snake", "Spider", "Bat",
                 "Dragon", "Robot", "Beetle", "Turret"],
    "items": ["Coin", "Star", "Gem", "Heart", "GoldKey", "HealthPotion", "MagicScroll", "Bomb", "TreasureChest", "Arrow",
              "Orb", "BerryBush", "Tree", "PineTree", "MossyRock"],
}


def parade(which: str = "heroes", columns: int = 5, cell: int = 128, fps: int = 10, seconds: float = 3.0,
           style: str = "fine") -> list[Image.Image]:
    """An animated sheet: every cast member idles for half the time and runs for the other half (where it can),
    each at the largest whole-number scale that fits its cell. Returns the GIF frames."""
    by_name = {c[0]: c for c in CAST}
    cast = [by_name[n] for n in PARADES[which]]
    sprites = [render(name, kind, color, style) for name, kind, color in cast]
    rows = -(-len(cast) // columns)
    steps = round(fps * seconds)
    out = []
    for step in range(steps):
        t = step / fps
        img = Image.new("RGBA", (PAD + columns * (cell + PAD), PAD + rows * (cell + PAD)), BG)
        d = ImageDraw.Draw(img)
        for n, ((name, kind, _color), s) in enumerate(zip(cast, sprites)):
            anim = "run" if "run" in s.animations and t >= seconds / 2 else "idle"
            a = s.animations.get(anim) or next(iter(s.animations.values()))
            w, h = s.frame_size
            zoom = max(1, cell // max(w, h))
            idx = int(t * a.fps) % len(a.frames)
            frame = Image.fromarray(s.frame(*a.frames[idx])).resize((w * zoom, h * zoom), Image.NEAREST)
            x, y = PAD + (n % columns) * (cell + PAD), PAD + (n // columns) * (cell + PAD)
            d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=TILE)
            bottom = KINDS[kind].anchor == "bottom"
            img.alpha_composite(frame, (x + (cell - w * zoom) // 2, y + cell - h * zoom - 6 if bottom else y + (cell - h * zoom) // 2))
        out.append(img.convert("RGB"))
    return out
