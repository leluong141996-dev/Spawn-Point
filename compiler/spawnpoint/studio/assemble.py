"""Brief -> game graph, layer by layer. Fully deterministic for a given (brief, seed)."""

from __future__ import annotations

import math
import os
import random
import re
from typing import Any

from ..level import jump_model
from ..sprites import cards as card_art
from ..sprites import fx as fx_art
from ..sprites import farm as farm_art
from ..sprites import palettes
from ..sprites.generate import features_for
from . import farmgen, levelgen
from .brief import DEFAULT_SCORE_TARGET, ENEMY_POINTS, EnemyBrief, GameBrief

TILE = 32
PLATFORMER_GRAVITY = 1600.0
LAYERS = (0, 1, 2)

PALETTES: dict[str, dict[str, Any]] = {
    "night": {"bg": "#1d2b53", "solid": "#5f574f", "top": "#00e436", "oneway": "#ab5236", "player": "#29adff",
              "enemies": ["#ff004d", "#ff77a8", "#ffa300", "#7e2553"], "pickup": "#ffec27", "exit": "#00e436",
              "door": "#ab5236", "hazard": "#c2c3c7", "bullet": "#fff1e8", "enemy_bullet": "#ff77a8", "heart": "#ff77a8"},
    "forest": {"bg": "#12261e", "solid": "#4a3728", "top": "#5fb83d", "oneway": "#8a5a3b", "player": "#f4d35e",
               "enemies": ["#d1495b", "#9b5de5", "#ee964b", "#7e2553"], "pickup": "#ffe66d", "exit": "#a7f070",
               "door": "#8a5a3b", "hazard": "#b8b8b8", "bullet": "#fffbe6", "enemy_bullet": "#ee964b", "heart": "#ff8fab"},
    "desert": {"bg": "#e9a46a", "solid": "#a0522d", "top": "#e6c07b", "oneway": "#8b5a2b", "player": "#2a9d8f",
               "enemies": ["#9b2226", "#005f73", "#ae2012", "#6a040f"], "pickup": "#ffd166", "exit": "#2a9d8f",
               "door": "#6f4518", "hazard": "#5c4033", "bullet": "#fffbe6", "enemy_bullet": "#9b2226", "heart": "#e63946"},
    "neon": {"bg": "#0d0221", "solid": "#241734", "top": "#2de2e6", "oneway": "#ff3864", "player": "#2de2e6",
             "enemies": ["#ff3864", "#f6019d", "#ff6c11", "#9d4edd"], "pickup": "#f9c80e", "exit": "#2de2e6",
             "door": "#ff3864", "hazard": "#f6019d", "bullet": "#ffffff", "enemy_bullet": "#ff6c11", "heart": "#f6019d"},
    "candy": {"bg": "#ffd6e8", "solid": "#c77dff", "top": "#ff9ebb", "oneway": "#f15bb5", "player": "#00bbf9",
              "enemies": ["#f15bb5", "#9b5de5", "#ff595e", "#00f5d4"], "pickup": "#fee440", "exit": "#00f5d4",
              "door": "#9b5de5", "hazard": "#8338ec", "bullet": "#ffffff", "enemy_bullet": "#ff595e", "heart": "#ff595e"},
    "ocean": {"bg": "#03256c", "solid": "#1768ac", "top": "#06bee1", "oneway": "#b1d0e0", "player": "#ffd23f",
              "enemies": ["#ee4266", "#ff9f1c", "#3bceac", "#540d6e"], "pickup": "#f5f5f5", "exit": "#3bceac",
              "door": "#06bee1", "hazard": "#b1d0e0", "bullet": "#ffffff", "enemy_bullet": "#ee4266", "heart": "#ee4266"},
    "lava": {"bg": "#1a0a0a", "solid": "#3d1f1f", "top": "#ff6b35", "oneway": "#8c2f39", "player": "#4cc9f0",
             "enemies": ["#ff4d00", "#ffb703", "#e63946", "#9d0208"], "pickup": "#ffd60a", "exit": "#4cc9f0",
             "door": "#8c2f39", "hazard": "#ffb703", "bullet": "#ffffff", "enemy_bullet": "#ff4d00", "heart": "#ff4d6d"},
    "snow": {"bg": "#a9d6e5", "solid": "#5c7c8a", "top": "#ffffff", "oneway": "#98c1d9", "player": "#ee6c4d",
             "enemies": ["#3d5a80", "#9d4edd", "#c1121f", "#293241"], "pickup": "#ffb703", "exit": "#ee6c4d",
             "door": "#3d5a80", "hazard": "#293241", "bullet": "#ffffff", "enemy_bullet": "#c1121f", "heart": "#c1121f"},
}

# What a pickup is called says what colour it should be: a "GoldCoin" is gold whatever the palette.
NAME_COLORS = {
    "gold": "#ffd23f", "golden": "#ffd23f", "coin": "#ffd23f", "doubloon": "#ffd23f", "treasure": "#ffd23f",
    "star": "#ffec27", "banana": "#ffe66d", "lemon": "#ffe66d", "honey": "#ffb703", "corn": "#ffd166",
    "silver": "#c2c3c7", "pearl": "#fff1e8", "egg": "#fff1e8", "bone": "#fff1e8", "snowflake": "#e0fbfc",
    "ruby": "#ff004d", "apple": "#ff004d", "cherry": "#e63946", "strawberry": "#ff4d6d", "heart": "#ff77a8",
    "emerald": "#00e436", "leaf": "#5fb83d", "clover": "#5fb83d", "lime": "#a7f070",
    "sapphire": "#29adff", "diamond": "#a2f3ff", "crystal": "#2de2e6", "gem": "#2de2e6", "ice": "#a2f3ff",
    "amethyst": "#9b5de5", "grape": "#9b5de5", "plum": "#7e2553",
    "carrot": "#ff9f1c", "orange": "#ffa300", "pumpkin": "#ff6c11", "fire": "#ff6c11", "ember": "#ff4d00",
    "energy": "#3bceac", "battery": "#3bceac", "cell": "#3bceac", "orb": "#2de2e6", "mushroom": "#e63946",
}


def _lum(c: str) -> float:
    def ch(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def farm_slug(title: str) -> str:
    """A save-file name for a farm game's title ("Sunny Farm" -> "sunny-farm")."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "farm"


def pickup_color(name: str, pal: dict[str, Any]) -> str:
    """Colour named by the pickup (first matching word), unless it blends into the background more than the
    palette's own pickup colour does (sprites keep a dark outline, so light palettes stay readable)."""
    need = min(2.0, contrast(pal["pickup"], pal["bg"]))
    for word in _ordered_words(name):
        singular = word[:-3] + "y" if word.endswith("ies") else word
        for w in (word, singular, word.removesuffix("s"), word.removesuffix("es")):
            color = NAME_COLORS.get(w)
            if color and contrast(color, pal["bg"]) >= need:
                return color
    return pal["pickup"]


LEVEL_UP_UPGRADES = ";".join([
    "Rapid Fire|Shoot 25% faster|Weapon.fire_rate*1.25",
    "Multishot|One more shot|Weapon.projectile_count+1,Weapon.spread_deg+12",
    "Power|Shots hit harder|Bullet:Hitbox.damage+1",
    "Piercing|Shots pass through one more enemy|Bullet:Projectile.pierce+1",
    "Long Shot|Shots fly 30% further|Bullet:Projectile.lifetime*1.3,Aim.max_range*1.2",
    "Swift|Move 12% faster|TopDownMovement.max_speed*1.12",
    "Vitality|+1 max health, fully healed|Health.max_health+1,Health.current+99",
    "Magnet|Pull gems from further away|Experience.magnet_radius*1.6",
])

SPEED = {"slow": 0.75, "normal": 1.0, "fast": 1.3}

# Farm: (grow seconds, price) for the first, second and third crop: cheap and quick to slow and valuable.
FARM_CROPS = ((8, 4), (14, 9), (24, 20))
FARM_CROP_PAL = {"pickup": "#ff9f1c", "bg": "#4f8a3a"}
# The cozy farm (farmgen.py, sprites/farm.py): crop colours by kind, what else sells, objects and animals.
FARM_CROP_COLORS = {"strawberry": "#e83a4a", "potato": "#c8986a", "carrot": "#ff8a2a", "tomato": "#e83a3a",
                    "pumpkin": "#ff9a2a", "corn": "#ffd84a", "cabbage": "#8ad860", "wheat": "#e8c25a",
                    "onion": "#f4ece0", "eggplant": "#8a4ac8", "blueberry": "#4a6ae8", "turnip": "#c84a9a"}
FARM_DAYS = {"short": 2, "medium": 3, "long": 4}  # days in a farming season
FARM_RAIN = {"spring": 0.35, "autumn": 0.4, "winter": 0.35, "desert": 0.05}  # chance of a rainy (or snowy) day
FARM_START_MONEY = 15  # enough for the first seeds
# For sale at the shop stall (key, name, price; see ShopComponent), and the rare crop it sells
# (name, colour, grow seconds, price).
FARM_SHOP = (("chicken", "Chicken", 40), ("cow", "Cow", 90), ("seeds", "Golden melon seeds", 60),
             ("sprinkler", "Sprinkler", 55))
FARM_RARE_CROP = ("GoldenMelon", "#ffd84a", 30, 45)
# Tool upgrades at the workbench: (key, name, price); see ToolBenchComponent.
FARM_UPGRADES = (("basket", "Big basket", 30), ("can", "Watering can", 45), ("hoe", "Hoe", 35), ("axe", "Axe", 40),
                 ("rod", "Fishing rod", 30))
FARM_GOODS = (("Egg", 6), ("Milk", 14), ("Fish", 10), ("Wood", 3), ("Stone", 4))
FARM_ISLAND = {"ocean": True, "forest": False, "desert": False}  # an ocean farm is an island, a forest farm a meadow
FARM_SEASON = {"snow": "winter", "desert": "desert", "lava": "autumn"}  # the theme sets the season (spring otherwise)
FARM_TREE_COLORS = {"autumn": {"tree_oak": "#e8922a"}}  # the same tree in another season's colours
# How the season changes the farming: crops grow slower in winter, the soil dries faster in the desert.
FARM_SEASON_PLAY = {"spring": (1.0, 1.0), "autumn": (0.9, 1.0), "winter": (0.65, 1.3), "desert": (0.9, 0.6)}
# object kind -> (entity name, {"base": footprint px, "gather": (item, hits, amount, chip colour)})
FARM_OBJECTS: dict[str, tuple[str, dict]] = {
    "farmhouse": ("Farmhouse", {"base": (150, 56)}), "coop": ("Coop", {"base": (72, 30)}),
    "fence_h": ("FenceH", {"base": (32, 12)}), "fence_v": ("FenceV", {"base": (10, 30)}),
    "fence_post": ("FencePost", {"base": (12, 12)}),
    "tree_oak": ("Oak", {"base": (22, 14), "gather": ("Wood", 3, 2, "#5cb84a")}),
    "tree_pine": ("Pine", {"base": (20, 14), "gather": ("Wood", 3, 2, "#2f8a5a")}),
    "tree_fruit": ("AppleTree", {"base": (22, 14), "gather": ("Wood", 3, 2, "#5cb84a")}),
    "tree_blossom": ("CherryTree", {"base": (22, 14), "gather": ("Wood", 3, 2, "#ffa8c8")}),
    "tree_maple": ("Maple", {"base": (22, 14), "gather": ("Wood", 3, 2, "#d8402a")}),
    "tree_snowy_pine": ("SnowyPine", {"base": (20, 14), "gather": ("Wood", 3, 2, "#f8fbff")}),
    "tree_bare": ("BareTree", {"base": (20, 14), "gather": ("Wood", 2, 2, "#9a5e36")}),
    "tree_palm": ("Palm", {"base": (16, 12), "gather": ("Wood", 3, 2, "#4caf50")}),
    "cactus": ("Cactus", {"base": (16, 12)}),
    "boulder": ("Boulder", {"base": (26, 16), "gather": ("Stone", 2, 2, "#a8a8b8")}),
    "stump": ("Stump", {"base": (22, 12)}), "flower_bush": ("FlowerBush", {"base": (24, 12)}),
    "hay": ("Hay", {"base": (28, 14)}), "barrel": ("Barrel", {"base": (24, 14)}), "well": ("Well", {"base": (44, 28)}),
    "scarecrow": ("Scarecrow", {"base": (12, 10)}), "signpost": ("Signpost", {"base": (12, 8)}),
    "workbench": ("Workbench", {"base": (40, 14)}),
    "shop": ("ShopStall", {"base": (56, 18)}), "sprinkler": ("WaterSprinkler", {"base": (12, 8)}),
    "bed": ("Bed", {"base": (28, 56)}), "fireplace": ("Fireplace", {"base": (60, 20)}), "table": ("Table", {"base": (56, 20)}),
    "chair": ("Chair", {"base": (20, 12)}), "dresser": ("Dresser", {"base": (44, 16)}),
    "potted_plant": ("PottedPlant", {"base": (16, 12)}),
}
# (entity, sprite kind, product, seconds between products, footprint) in the pen, by length
FARM_ANIMALS = {
    "short": [("Chicken", "chicken", "Egg", 18, (16, 10)), ("Chicken", "chicken", "Egg", 18, (16, 10)),
              ("Cow", "cow", "Milk", 30, (24, 12)), ("Chick", "chick", "", 0, (12, 8))],
    "medium": [("Chicken", "chicken", "Egg", 18, (16, 10)), ("Chicken", "chicken", "Egg", 18, (16, 10)),
               ("Chicken", "chicken", "Egg", 18, (16, 10)), ("Chick", "chick", "", 0, (12, 8)),
               ("Cow", "cow", "Milk", 30, (24, 12))],
    "long": [("Chicken", "chicken", "Egg", 18, (16, 10)), ("Chicken", "chicken", "Egg", 18, (16, 10)),
             ("Chicken", "chicken", "Egg", 18, (16, 10)), ("Chick", "chick", "", 0, (12, 8)),
             ("Cow", "cow", "Milk", 30, (24, 12)), ("Cow", "cow", "Milk", 30, (24, 12))],
}
FARM_GROUND = {"forest": "#4f8a3a", "night": "#2f5a3a", "desert": "#c9a66b", "snow": "#dfe9ee",
               "candy": "#9ad08a", "ocean": "#5a9a5a", "lava": "#6b4a3a", "neon": "#24453a"}
ROAD_COLORS = {"snow": "#9fb4c2", "lava": "#4a3030", "neon": "#3a2a5a", "night": "#a08a62"}

# Tower defense. A tower's role comes from its name (cannon, mage...) or else its place in the list.
TOWER_PROFILES: dict[str, dict[str, Any]] = {
    "fast": {"fire_rate": 1.8, "range": 140, "damage": 1, "speed": 520, "cost": 50, "color": "#a0663c",
             "shot": "#fff1e8"},
    "heavy": {"fire_rate": 0.7, "range": 170, "damage": 5, "speed": 360, "pierce": 1, "cost": 110,
              "color": "#5f574f", "shot": "#29243a"},
    "long": {"fire_rate": 1.0, "range": 210, "damage": 3, "speed": 460, "cost": 90, "color": "#7e2553",
             "shot": "#ff77a8"},
}
TOWER_WORDS = {"heavy": {"cannon", "bomb", "catapult", "mortar", "rock", "boulder", "artillery", "dwarf"},
               "long": {"mage", "wizard", "magic", "sniper", "laser", "lightning", "tesla", "crystal", "ice",
                        "frost", "fire", "flame", "storm"},
               "fast": {"archer", "arrow", "bow", "crossbow", "elf", "ninja", "gun", "machine", "dart"}}
WAVE_PATTERN = (0, 0, 1, 2, 1, 0, 2, 1, 0)
INVADER_SPEED = {"slow": 38, "normal": 62, "fast": 105}
INVADER_HP = {"slow": 18, "normal": 6, "fast": 4}
INVADER_GOLD = {"slow": 14, "normal": 5, "fast": 4}


# --- card games ----------------------------------------------------------------------------------
# A card: (cost, type, effects, rarity, icon). Effects use CardBattle's language (dmg:6,vuln:2 ...).
CARD_KINDS: dict[str, tuple[int, str, str, str, str]] = {
    "strike": (1, "attack", "dmg:6", "common", "sword"), "heavy": (2, "attack", "dmg:13", "common", "axe"),
    "multi_hit": (1, "attack", "dmg:3,hits:3", "uncommon", "dagger"), "sweep": (1, "attack", "all:5", "common", "wind"),
    "block": (1, "skill", "blk:6", "common", "shield"), "heal": (1, "skill", "heal:6,exhaust", "uncommon", "heart"),
    "draw": (1, "skill", "draw:2", "common", "book"), "poison": (1, "skill", "poison:5", "common", "drop"),
    "weaken": (1, "skill", "weak:2,blk:4", "uncommon", "skull"), "rage": (1, "power", "str:2", "rare", "flex"),
}
# Each class: the basic attack and block (5 and 4 copies), a signature card, and the cards rewards draw from.
CARD_CLASSES: dict[str, dict[str, Any]] = {
    "warrior": {"strike": ("Strike", "sword"), "block": ("Defend", "shield"),
                "signature": ("Bash", 2, "attack", "dmg:8,vuln:2", "axe"),
                "pool": [("Cleave", 1, "attack", "all:7", "common", "axe"), ("Iron Wave", 1, "attack", "dmg:5,blk:5", "common", "sword"),
                         ("Heavy Blow", 2, "attack", "dmg:14", "common", "axe"), ("Twin Strike", 1, "attack", "dmg:5,hits:2", "common", "sword"),
                         ("Shrug It Off", 1, "skill", "blk:8,draw:1", "common", "shield"), ("Shield Wall", 2, "skill", "blk:15", "uncommon", "shield"),
                         ("Bandage", 1, "skill", "heal:7,exhaust", "uncommon", "heart"), ("Battle Cry", 1, "power", "str:2", "rare", "flex"),
                         ("Uppercut", 2, "attack", "dmg:13,weak:1,vuln:1", "uncommon", "flex")]},
    "mage": {"strike": ("Zap", "bolt"), "block": ("Ward", "shield"),
             "signature": ("Fireball", 2, "attack", "dmg:11,all:3", "fire"),
             "pool": [("Frost Bolt", 1, "attack", "dmg:6,weak:1", "common", "ice"), ("Chain Lightning", 2, "attack", "all:9", "common", "bolt"),
                      ("Arcane Shield", 1, "skill", "blk:8", "common", "staff"), ("Insight", 0, "skill", "draw:2,exhaust", "common", "book"),
                      ("Mana Surge", 0, "skill", "nrg:2,exhaust", "uncommon", "star"), ("Meteor", 3, "attack", "dmg:26", "rare", "fire"),
                      ("Curse", 1, "skill", "weak:2,vuln:2", "uncommon", "skull"), ("Focus", 1, "power", "str:2", "rare", "staff"),
                      ("Ice Wall", 2, "skill", "blk:12,draw:1", "uncommon", "ice")]},
    "rogue": {"strike": ("Stab", "dagger"), "block": ("Dodge", "wind"),
              "signature": ("Poison Dart", 1, "attack", "dmg:3,poison:4", "drop"),
              "pool": [("Flurry", 1, "attack", "dmg:3,hits:3", "common", "dagger"), ("Deadly Poison", 1, "skill", "poison:7", "common", "drop"),
                       ("Backstab", 0, "attack", "dmg:10,exhaust", "uncommon", "dagger"), ("Smoke Bomb", 1, "skill", "blk:7,weak:1", "common", "wind"),
                       ("Quick Draw", 1, "skill", "draw:3", "common", "book"), ("Fan of Knives", 1, "attack", "all:5", "common", "dagger"),
                       ("Adrenaline", 0, "skill", "nrg:1,draw:2,exhaust", "rare", "bolt"), ("Envenom", 1, "power", "str:1", "rare", "drop"),
                       ("Arrow Rain", 2, "attack", "all:8", "uncommon", "bow")]},
}
# A word in a card's name picks its icon ("Fire Ball" burns, "Frost Nova" freezes).
CARD_ICON_WORDS = (({"fire", "flame", "burn", "blaze", "inferno", "meteor", "ember"}, "fire"),
                   ({"ice", "frost", "freeze", "snow", "blizzard", "cold"}, "ice"),
                   ({"lightning", "thunder", "bolt", "shock", "spark", "zap", "storm"}, "bolt"),
                   ({"poison", "venom", "toxic", "acid", "plague"}, "drop"), ({"arrow", "shot", "bow", "volley"}, "bow"),
                   ({"heal", "cure", "mend", "potion", "life", "bandage", "prayer"}, "heart"),
                   ({"shield", "guard", "block", "wall", "armor", "armour", "parry", "barrier", "defend"}, "shield"),
                   ({"dagger", "knife", "stab", "backstab", "shiv", "blade"}, "dagger"), ({"axe", "cleave", "chop"}, "axe"),
                   ({"magic", "spell", "arcane", "staff", "mana", "missile", "hex"}, "staff"),
                   ({"wind", "gust", "whirlwind", "tornado", "dodge", "smoke"}, "wind"), ({"book", "study", "insight", "learn"}, "book"),
                   ({"curse", "doom", "death", "fear", "skull", "weaken"}, "skull"),
                   ({"rage", "fury", "strength", "power", "roar", "might", "berserk"}, "flex"),
                   ({"star", "light", "holy", "smite", "divine"}, "star"))
CARD_FLOORS = {"short": 5, "medium": 7, "long": 9}
CARD_STARTER_RELIC = {"warrior": "burning_blood", "mage": "lantern", "rogue": "snake_ring"}  # see card_content.gd
# Foe archetype -> (base HP, intents with {n} placeholders scaled by difficulty).
CARD_FOES = {"brute": (22, "atk:{8},atk:{12},str:2+atk:{5}"), "guard": (26, "blk:{8}+atk:{5},atk:{8},blk:{12}"),
             "caster": (18, "weak:1+atk:{4},poison:3,atk:{9},vuln:1+atk:{4}"), "swarm": (11, "atk:{5},atk:{3}x2")}
CARD_BOSS_INTENTS = "atk:{11},blk:{12}+str:2,atk:{5}x3,weak:1+atk:{8}"
# What the title screen says about the keys, by genre.
GAME_CONTROLS = {"platformer": "Arrows or WASD to move, Space to jump.", "topdown": "WASD to move, the mouse to aim and shoot.",
                 "bubble": "Aim with the mouse, click to shoot.", "tower_defense": "Click a pad to build a tower.",
                 "shmup": "Arrows or WASD to fly; the ship fires on its own."}
# A theme's tune (music.py has four moods).
GAME_MUSIC = {"snow": "winter", "desert": "desert", "lava": "autumn", "night": "autumn", "neon": "autumn"}
CARD_MUSIC = {"snow": "winter", "desert": "desert", "lava": "autumn", "night": "autumn", "neon": "autumn"}


# Animals and plants look like themselves whatever the theme's colours (slimes, ghosts and dragons take the theme's).
NATURAL_COLORS = {"wolf": "#8a8a9a", "fox": "#e8803a", "bear": "#8a5a3a", "boar": "#7a5a4a", "hog": "#7a5a4a",
                  "pig": "#e8a0a0", "rat": "#8a7a7a", "mouse": "#9a8a8a", "cat": "#e8a050", "tiger": "#e8902a",
                  "lion": "#d8a050", "dog": "#a87a4a", "bat": "#5a4a7a", "crow": "#3a3a4a", "raven": "#3a3a4a",
                  "owl": "#a07a50", "spider": "#4a3a5a", "treant": "#4a9a4a", "ent": "#4a9a4a", "tree": "#4a9a4a",
                  "golem": "#8a8a96", "rock": "#8a8a96", "stone": "#8a8a96", "statue": "#a8a8b0", "frog": "#5ab84a",
                  "snake": "#5a9a4a", "beetle": "#3a5a8a", "rabbit": "#e8e0d8", "bunny": "#e8e0d8"}


def natural_color(name: str, fallback: str) -> str:
    return next((NATURAL_COLORS[w] for w in _ordered_words(name)[::-1] if w in NATURAL_COLORS), fallback)


def card_icon(name: str, fallback: str) -> str:
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", name)}
    return next((icon for keys, icon in CARD_ICON_WORDS if words & keys), fallback)


def _space_bg(bg: str) -> str:
    """Space is dark whatever the theme: light backgrounds are darkened (the theme still tints it)."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    if (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.3:
        return bg
    return "#%02x%02x%02x" % tuple(round(c * 0.22) for c in (r, g, b))


def _default_goal_intro(b: GameBrief) -> str:
    from .brief import _default_intro
    return _default_intro(b)


def tower_profile(name: str, index: int) -> str:
    words = _words(name)
    for prof, keys in TOWER_WORDS.items():
        if words & keys:
            return prof
    return ("fast", "heavy", "long")[index % 3]
ENEMY_SYMBOLS = "1234"
# Decorative props per theme: (entity name, map symbol, colour). Names pick features (PineTree, BerryBush...).
THEME_DECOR: dict[str, list[tuple[str, str, str]]] = {
    "forest": [("Tree", "t", "#4aa050"), ("PineTree", "p", "#2f7a50"), ("BerryBush", "b", "#5ab050"), ("MossyRock", "r", "#8a8a9a")],
    "night": [("PineTree", "p", "#2a5a5a"), ("Bush", "b", "#3a6a5a"), ("Rock", "r", "#6a6a80")],
    "snow": [("PineTree", "p", "#3a7a6a"), ("Rock", "r", "#c0c8d8")],
    "desert": [("Rock", "r", "#c8a070"), ("Bush", "b", "#9aa050")],
    "lava": [("Rock", "r", "#5a4a4a")],
    "candy": [("Tree", "t", "#f08ac0"), ("BerryBush", "b", "#f0a0d0")],
    "ocean": [("MossyRock", "r", "#7a9ab0"), ("Bush", "b", "#4aa090")],
    "neon": [],
}
DECOR_KINDS = {"tree": "tree", "pine": "tree", "bush": "bush", "rock": "rock"}

FEEL_PLATFORMER = {
    "snappy": {},
    "floaty": {"gravity_scale": 0.8, "fall_gravity_multiplier": 1.25, "apex_gravity_multiplier": 0.45,
               "air_acceleration": 900.0, "air_deceleration": 400.0},
    "heavy": {"gravity_scale": 1.25, "fall_gravity_multiplier": 2.2, "acceleration": 1500.0,
              "deceleration": 1800.0, "apex_gravity_multiplier": 0.85},
}
FEEL_TOPDOWN = {
    "snappy": {},
    "floaty": {"acceleration": 900.0, "friction": 700.0},
    "heavy": {"acceleration": 1400.0, "friction": 3200.0},
}
JUICE_SCALE = {"subtle": 0.5, "normal": 1.0, "wild": 1.7}
JUICE_DEFAULTS = {"squash_amount": (0.28, 0.8), "shake_on_hurt": (0.35, 1.0), "shake_on_death": (0.45, 1.0),
                  "shake_on_fire": (0.06, 1.0), "hitstop_on_hurt": (0.06, 0.3), "hitstop_on_death": (0.04, 0.3)}


def jump_velocity(jump_tiles: float, gravity_scale: float = 1.0) -> float:
    # Apex hang adds ~8% height, so aim slightly lower than the requested height.
    h = jump_tiles * TILE * 0.92
    return round(math.sqrt(2 * PLATFORMER_GRAVITY * gravity_scale * h), 1)


def jump_reach_tiles(brief: GameBrief) -> int:
    """Whole tiles the player can climb. Same model as the compiler's reachability check
    (ballistic height of jump_velocity, times the number of jumps, without apex hang)."""
    jumps = 2 if "double_jump" in brief.player.abilities else 1
    h = jump_velocity(brief.player.jump_tiles) ** 2 / (2 * PLATFORMER_GRAVITY) * jumps
    return int(h // TILE)


def jump_across_tiles(brief: GameBrief) -> int:
    """Horizontal tiles one jump covers, using the compiler's model; the most conservative of the
    default feel (layers 0-1) and the brief's feel (layer 2)."""
    speed = 230 * SPEED[brief.player.speed]
    jumps = 2 if "double_jump" in brief.player.abilities else 1
    out = []
    for feel in {"snappy", brief.feel}:
        f = FEEL_PLATFORMER[feel]
        gs = f.get("gravity_scale", 1.0)
        jm = jump_model(jump_velocity(brief.player.jump_tiles, gs), PLATFORMER_GRAVITY * gs,
                        f.get("fall_gravity_multiplier", 1.7), speed, TILE, 34, jumps - 1)
        out.append(jm.across)
    return min(out)


def _level_args(brief: GameBrief) -> tuple:
    return brief.length, jump_reach_tiles(brief), jump_across_tiles(brief), "pits" in brief.hazards


def plan_chunks(brief: GameBrief, seed: int) -> list[str] | None:
    if brief.genre != "platformer":
        return None
    return levelgen.plan_chunks(seed, *_level_args(brief), brief.difficulty)


def chunks_fit(brief: GameBrief, chunks: list[str] | None) -> bool:
    if brief.genre != "platformer" or chunks is None:
        return False
    return levelgen.chunks_fit(chunks, *_level_args(brief))


def ai_art_from_env() -> bool:
    return os.environ.get("SPAWNPOINT_AI_ART", "").lower() in ("1", "true", "yes", "on")


def assemble(brief: GameBrief, layer: int = 2, seed: int = 0, chunks: list[str] | None = None,
             ai_art: bool = False, look: int = 0) -> dict:
    """`chunks` pins the platformer level layout (to keep the map across tweaks); `ai_art` asks for
    image-model sprites in layer 2 (generated ones are the fallback); `look` picks another look for the same game
    (other colours and details for every character, nothing else changes)."""
    return _Assembler(brief, layer, seed, chunks, ai_art, look).graph()


def look_color(color: str, look: int) -> str:
    """The colour a character wears in look number `look` (0: the theme's own)."""
    if not look:
        return color
    import colorsys
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, sat, v = colorsys.rgb_to_hsv(r, g, b)
    r, g, b = colorsys.hsv_to_rgb((h + 0.17 * look) % 1.0, max(sat, 0.35), max(v, 0.45))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


class _Assembler:
    def __init__(self, brief: GameBrief, layer: int, seed: int, chunks: list[str] | None = None,
                 ai_art: bool = False, look: int = 0):
        self.ai_art = ai_art
        self.look = look
        self.art_seed = seed + 1009 * look  # sprites' own randomness (hair, spots, features) for this look
        self.b = brief
        self.layer = layer
        self.seed = seed
        self.chunks = chunks
        self.pal = PALETTES[brief.palette]
        self.platformer = brief.genre == "platformer"
        self.entities: dict[str, dict] = {}
        self.legend: dict[str, str] = {"#": "solid", "=": "oneway"}
        self.rules: list[dict] = []
        self._nest_cells: list[str] = []

    # -- top level ---------------------------------------------------------------------------
    def graph(self) -> dict:
        b = self.b
        if b.genre == "bubble":
            return self._styled(self._bubble_graph())
        if b.genre == "farm":
            return self._styled(self._farm_graph())
        if b.genre == "tower_defense":
            return self._styled(self._td_graph())
        if b.genre == "shmup":
            return self._styled(self._shmup_graph())
        if b.genre == "cards":
            return self._styled(self._cards_graph())
        lay = self._layout()
        grid: dict[tuple[int, int], str] = {}
        self._player(grid, lay)
        if self.layer >= 1:
            self._goal(grid, lay)
            for sym, c in zip(self._nest_cells, [c for c in lay.free_cells if c not in grid]):
                grid[c] = sym
            self._enemies(grid, lay)
            self._pickups(grid, lay)
            self._hazards(grid, lay)
        if self.layer >= 2:
            self._decor(grid, lay)
        intro = b.intro if self.layer >= 1 else "Layer 0: try the controls!"
        if b.goal == "score_target" and intro == f"Score {b.score_target} points!":
            intro = f"Score {self._score_target()} points!"  # the default intro follows the real target
        self.rules.insert(0, {"on": "Game.ready", "do": [f"message({_q(intro)})"]})
        if self.layer >= 2:
            self._polish()
        return self._styled({
            "spawnpoint": 1,
            "name": b.title or "Untitled",
            "genre": b.genre,
            "settings": {
                "tile_size": TILE,
                "lives": 3,
                "seed": self.seed,
                "background": self.pal["bg"],
                "zoom": 1.5,  # pixel-art sprites read better closer up
                "tiles": {"solid": {"color": self.pal["solid"], "top": self.pal["top"]},
                          "oneway": {"color": self.pal["oneway"]}},
            },
            "entities": self.entities,
            "level": {"map": _render(lay, grid), "legend": self.legend},
            "rules": self.rules,
        })

    def _styled(self, g: dict) -> dict:
        if self.layer >= 2:
            if self.b.genre in ("farm", "cards"):  # farms and card battles keep their own colours and backdrops
                return g
            # Spawn Point makes pixel art games: a brief that asks for cartoon art still gets pixel art, with the
            # classic palette that suits the theme.
            g["settings"]["pixel_palette"] = palettes.THEME_PALETTE[self.b.palette]
            g["settings"]["scenery"] = self.b.palette
            g["settings"]["pixel_size"] = 1  # the fine style: detailed chibi people, fine tiles
            if self.b.genre == "shmup":
                g["settings"]["scenery"] = "space"  # scrolling stars, whatever the art style
            self._finished(g)
        return g

    def _finished(self, g: dict) -> None:
        """Every game a prompt makes opens on a title screen, can be paused and has music, like a finished game."""
        player = next((e for e in g["entities"].values() if "PlayerInput" in e.get("components", {})), None)
        if player is None or "GameMenu" in player.get("components", {}):
            return
        intro = next((r["do"][0][len("message("):-1].strip("'\"") for r in g.get("rules", [])
                      if r.get("on") == "Game.ready" and r["do"] and r["do"][0].startswith("message(")), "")
        controls = GAME_CONTROLS.get(self.b.genre, GAME_CONTROLS["platformer"])
        player["components"]["GameMenu"] = {"title": self.b.title or "My Game",
                                            "subtitle": f"{intro} {controls}".strip()}
        g["settings"].setdefault("music", GAME_MUSIC.get(self.b.palette, "spring"))

    # -- cards -------------------------------------------------------------------------------
    def _cards_graph(self) -> dict:
        """A deckbuilder: the hero on the left of a side-view stage, foes spawned on the right for each fight."""
        b, pal, d = self.b, self.pal, self.b.difficulty
        cls = CARD_CLASSES[b.hero_class]
        k_hp, k_dmg = 0.92 + 0.1 * d, 0.97 + 0.05 * d  # harder foes: tougher first, then hitting harder
        cards: dict[str, tuple] = {}
        strike, block = cls["strike"], cls["block"]
        own = list(b.cards)
        first = {kind: next((c for c in own if c.kind == kind), None) for kind in ("strike", "block")}
        if first["strike"]:  # the game's own basic attack and block become the starting cards
            strike = (first["strike"].name, card_icon(first["strike"].name, "sword"))
            own.remove(first["strike"])
        if first["block"]:
            block = (first["block"].name, card_icon(first["block"].name, "shield"))
            own.remove(first["block"])
        cards[strike[0]] = (1, "attack", "dmg:6", "starter", strike[1])
        cards[block[0]] = (1, "skill", "blk:5", "starter", block[1])
        sig = cls["signature"]
        cards[sig[0]] = (sig[1], sig[2], sig[3], "starter", sig[4])
        for c in own:
            cost, kind, fx, rarity, icon = CARD_KINDS[c.kind]
            cards.setdefault(c.name, (cost, kind, fx, rarity, card_icon(c.name, icon)))
        for name, cost, kind, fx, rarity, icon in cls["pool"]:
            cards.setdefault(name, (cost, kind, fx, rarity, icon))
        library = ";".join(f"{n}|{c[0]}|{c[1]}|{c[2]}|{c[3]}|{c[4]}" for n, c in cards.items())

        def scaled(template: str) -> str:
            return re.sub(r"\{(\d+)\}", lambda m: str(max(1, round(int(m.group(1)) * k_dmg))), template)

        foes = []
        for i, e in enumerate(b.enemies):
            hp, intents = CARD_FOES.get(e.archetype, CARD_FOES["brute"])
            foes.append(f"{e.name}|{round(hp * k_hp)}|normal|{scaled(intents)}")
            self._card_foe(e.name, pal["enemies"][i % len(pal["enemies"])])
        foes.append(f"{b.boss}|{round(100 + 14 * (d - 2))}|boss|{scaled(CARD_BOSS_INTENTS)}")
        self._card_foe(b.boss, pal["enemies"][-1], boss=True)
        floors = CARD_FLOORS[b.length]
        battle = {"cards": library, "hero_name": b.player.character, "theme": b.palette, "foe_offset": [300, 0], "foe_gap": 160, "starter": f"{strike[0]}*5,{block[0]}*4,{sig[0]}", "foes": ";".join(foes),
                  "floors": floors, "run_seed": self.seed, "gold_per_fight": 15,
                  "starter_relic": CARD_STARTER_RELIC[b.hero_class]}
        hero_hp = 70 - 3 * (d - 2)
        comps = {"PlayerInput": {}, "Health": {"max_health": hero_hp, "invincibility_time": 0.0}, "CardBattle": battle}
        if self.layer >= 2:
            comps["GameMenu"] = {"title": b.title or "Card Quest",
                                 "subtitle": f"Climb {floors} floors and defeat the {b.boss}."}
        self.entities["Player"] = {"shape": {"type": "capsule", "size": [24, 40], "color": pal["player"]},
                                   "components": comps, "base": [24, 12], "juice": {"shake_on_hurt": 0.0}}
        width, height, ground = 30, 17, 10
        rows = ["." * width for _ in range(height)]
        r = list(rows[ground - 1])
        r[6] = "P"
        rows[ground - 1] = "".join(r)
        if self.layer >= 2:  # the chibi pixel sprites, drawn big: these are portraits, not tiny map sprites
            for name, ent in self.entities.items():
                if name != "Player":
                    ent["shape"]["color"] = natural_color(name, ent["shape"]["color"])
            self._sprites()
            for name, ent in self.entities.items():
                gen = ent.get("sprite", {}).get("generate")
                if gen is not None:
                    gen["size"] = 4 if name == b.boss else 3
                    if gen["kind"] == "hero" and name != "Player":
                        gen["features"] = features_for(name)  # a Skeleton has a skull, a Witch her hat and staff
                        if name == b.boss and "cape" not in gen["features"]:
                            gen["features"].append("cape")  # the boss stands out from its minions
                    if name == "Player":
                        gen["features"] = features_for(b.player.character) or features_for(
                            {"warrior": "Knight", "mage": "Wizard", "rogue": "Rogue"}[b.hero_class])
        settings: dict[str, Any] = {"tile_size": TILE, "lives": 1, "seed": self.seed, "background": pal["bg"],
                                    "zoom": 1.0, "pixel_size": 1, "backdrop": b.palette,
                                    "pixel_palette": palettes.THEME_PALETTE[b.palette],
                                    "art": {**{f"frame_{t}": {"kind": "card_frame", "of": t} for t in ("attack", "skill", "power")},
                                            **{f"ci_{n}": {"kind": "card_icon", "of": n} for n in card_art.ICONS},
                                            **{f"fx_{n}": {"kind": "fx", "of": n} for n in fx_art.EFFECTS},
                                            "card_back": {"kind": "card_back"}}}
        if self.layer >= 2:
            settings["music"] = CARD_MUSIC.get(b.palette, "spring")
        self.rules = [
            {"on": "Game.ready", "do": ["set_var('score_label', 'GOLD')", f"message({_q(b.intro)})"]},
            {"on": "Player.CardBattle.fight_started", "if": "event.kind == 'elite'", "do": ["message('An elite foe!')"]},
            {"on": "Player.CardBattle.won", "do": [f"message({_q('The ' + b.boss + ' is defeated!')})", "win()"]},
        ]
        return {"spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown", "settings": settings,
                "entities": self.entities, "level": {"map": rows, "legend": {"#": "solid", "P": "Player"}},
                "rules": self.rules}

    def _card_foe(self, name: str, color: str, boss: bool = False) -> None:
        """A foe that only stands there: CardBattle spawns it, sets its HP and plays its moves."""
        self.entities[name] = {"team": "enemy", "shape": {"type": "capsule", "size": [30, 36], "color": color},
                               "components": {"Health": {"max_health": 10, "invincibility_time": 0.0}},
                               "base": [40 if boss else 26, 12]}

    # -- farm --------------------------------------------------------------------------------
    def _farm_graph(self) -> dict:
        """A cozy farm: farmhouse, fenced field, animal pen, pond and woods on a drawn map (see farmgen.py)."""
        b, pal = self.b, self.pal
        d = b.difficulty
        season = FARM_SEASON.get(b.palette, "spring")
        fm = farmgen.cozy_farm(self.seed, b.length, plot_target={"short": 8, "medium": 12, "long": 16}.get(b.length, 12),
                               island=FARM_ISLAND.get(b.palette), season=season)
        target, minutes = self._farm_target(), self._farm_seconds()
        days = FARM_DAYS.get(b.length, 3)
        day_seconds = round(max(55.0, minutes * 1.25 / days))
        if b.score_target == DEFAULT_SCORE_TARGET:  # a season of several days, and seeds to buy: a bigger goal
            target = round(target * 1.4 / 10) * 10
        art: dict[str, dict] = {"soil": {"kind": "soil"}, "soil_wet": {"kind": "soil_wet"}}
        crop_entries = []
        for c, (grow, price) in zip(b.crops, FARM_CROPS):
            color = FARM_CROP_COLORS.get(farm_art.crop_kind(c)) or pickup_color(c, FARM_CROP_PAL)
            art[f"crop_{c}"] = {"kind": "crop", "of": c, "color": color}
            art[f"icon_{c}"] = {"kind": "crop_icon", "of": c, "color": color}
            crop_entries.append(f"{c}|{color}|{grow}|{price}|res://sprites/art_crop_{c}.png|res://sprites/art_icon_{c}.png")
        art["icon_hay"] = {"kind": "item_icon", "of": "hay"}
        rare = FARM_RARE_CROP  # sold at the shop stall
        art[f"crop_{rare[0]}"] = {"kind": "crop", "of": rare[0], "color": rare[1]}
        art[f"icon_{rare[0]}"] = {"kind": "crop_icon", "of": rare[0], "color": rare[1]}
        rare_entry = (f"{rare[0]}|{rare[1]}|{rare[2]}|{rare[3]}|res://sprites/art_crop_{rare[0]}.png"
                      f"|res://sprites/art_icon_{rare[0]}.png")
        goods = []
        for item, price in FARM_GOODS:
            art[f"icon_{item.lower()}"] = {"kind": "item_icon", "of": item.lower()}
            goods.append(f"{item}|{price}|res://sprites/art_icon_{item.lower()}.png")
        comps: dict[str, dict] = {"TopDownMovement": {"max_speed": round(190 * SPEED[b.player.speed]),
                                                       "acceleration": 2200}, "PlayerInput": {},
                                  "Farmer": {"crops": ";".join(crop_entries), "goods": ";".join(goods), "reach": 46,
                                             "basket_size": 16, "buy_seeds": True},
                                  "FarmDays": {"days": days, "day_seconds": day_seconds, "weather_seed": self.seed,
                                               "rain_chance": FARM_RAIN[season], "snow": season == "winter"},
                                  "FarmSave": {"slot": f"{farm_slug(b.title or 'farm')}-{self.seed}"},
                                  "GameMenu": {"title": b.title or "My Farm",
                                               "subtitle": f"Earn ${target} in {days} days. Space works the farm, P pauses."}}
        if "dash" in b.player.abilities:
            comps["TopDownMovement"]["dash_speed"] = 600.0
        self.entities["Player"] = {"shape": {"type": "circle", "size": [18, 18], "color": pal["player"]},
                                   "components": comps, "base": [18, 18], "farm_kind": "farmer"}
        chasers = [e for e in b.enemies if e.archetype in ("chaser", "shooter")]
        if chasers:  # something hunts the farmer, so the farmer can get hurt
            comps["Health"] = {"max_health": b.player.health, "invincibility_time": 1.0}
            comps["Hurtbox"] = {}
        if b.enemies:
            self._melee_or_gust(comps)
            comps["Aim"] = {"mode": "movement"}  # the farmer faces where it walks, sword or not
        self.entities["Plot"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [30, 30]},
                                 "components": {"FarmPlot": {"water_seconds": round((7.0 - 0.5 * d) * FARM_SEASON_PLAY[season][1], 1),
                                                             "size": 30, "growth_rate": FARM_SEASON_PLAY[season][0],
                                                             "tilled": False,  # the hoe comes first
                                                             "soil_texture": "res://sprites/art_soil.png",
                                                             "wet_texture": "res://sprites/art_soil_wet.png"}}}
        self.entities["ShippingBin"] = {"body": "area", "juice": "none", "base": [30, 20], "farm_kind": "bin",
                                        "shape": {"type": "rect", "size": [30, 20], "color": "#9a5e36"},
                                        "components": {"Market": {"width": 32, "stall": False}}}
        legend = {"#": "solid", "P": "Player", "f": "Plot", "M": "ShippingBin"}
        cells: dict[tuple[int, int], str] = {fm.player: "P", fm.bin: "M"}
        for c in fm.plots:
            cells[c] = "f"
        symbols = iter("abcdeghijklmopstuvwxyzABCDEFGHIJKLNOQRSTUVWXYZ0123456789")
        sym_of: dict[str, str] = {}

        def place(entity: str, c: tuple[int, int]) -> None:
            if entity not in sym_of:
                sym_of[entity] = next(symbols)
                legend[sym_of[entity]] = entity
            cells[c] = sym_of[entity]

        for kind, c in fm.objects:
            name, spec = FARM_OBJECTS[kind]
            if name not in self.entities:
                ent = {"body": "static", "juice": "none", "base": list(spec["base"]), "farm_kind": kind,
                       "farm_color": FARM_TREE_COLORS.get(season, {}).get(kind),
                       "shape": {"type": "rect", "size": list(spec["base"]), "color": spec.get("color", "#9a5e36")},
                       "components": {}}
                if kind == "bed":
                    ent["components"]["SleepSpot"] = {}
                if kind == "sprinkler":  # waits hidden in the field until bought
                    ent["body"] = "area"
                    ent["components"]["Sprinkler"] = {"radius": 52}
                if kind == "shop":
                    ent["components"]["Shop"] = {"offers": ";".join(f"{k}|{n}|{p}" for k, n, p in FARM_SHOP),
                                                 "rare_crop": rare_entry}
                if kind == "workbench":
                    ent["components"]["ToolBench"] = {"offers": ";".join(f"{k}|{n}|{p}" for k, n, p in FARM_UPGRADES)}
                if "gather" in spec:
                    item, hits, amount, chips = spec["gather"]
                    ent["components"]["Gatherable"] = {"item": item, "hits": hits, "amount": amount, "chip_color": chips,
                                                       **({"leaves": "Stump"} if kind.startswith("tree") else {})}
                self.entities[name] = ent
            place(name, c)
        if fm.door_mat is not None:  # the farmhouse door and the mat inside are linked
            def px(c: tuple[int, int]) -> list[float]:
                return [(c[0] + 0.5) * TILE, (c[1] + 0.5) * TILE]
            self.entities["HouseDoor"] = {"body": "area", "juice": "none", "shape": {"type": "rect", "size": [28, 28], "color": "#00000000"},
                                          "components": {"Warp": {"to": px((fm.door_mat[0], fm.door_mat[1] - 1)), "hint": "Enter"}}}
            self.entities["DoorMat"] = {"body": "area", "juice": "none", "shape": {"type": "rect", "size": [28, 28], "color": "#00000000"},
                                        "components": {"Warp": {"to": px((fm.door[0], fm.door[1] + 1)), "hint": "Go out"}}}
            place("HouseDoor", fm.door)
            place("DoorMat", fm.door_mat)
        for c, wd in fm.fishing:  # shore spots to fish from (wd: which way the water is)
            name = "Shore" if wd == (0, 1) else "ShoreEast"
            if name not in self.entities:
                self.entities[name] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [24, 24]},
                                       "components": {"FishingSpot": {"water_dir": list(wd), "min_wait": 1.5,
                                                                      "max_wait": 4.5,
                                                                      "bite_time": round(1.1 - 0.05 * d, 2)}}}
            place(name, c)
        if "Stump" not in self.entities and any(k.startswith("tree") for k, _ in fm.objects):
            self.entities["Stump"] = {"body": "static", "juice": "none", "base": [22, 12], "farm_kind": "stump",
                                      "shape": {"type": "rect", "size": [22, 12], "color": "#9a5e36"}, "components": {}}
        for i, (animal, c) in enumerate(zip(FARM_ANIMALS[b.length if b.length in FARM_ANIMALS else "medium"], fm.animals)):
            name, kind, product, seconds, base = animal
            if name not in self.entities:
                self.entities[name] = {
                    "team": "neutral", "juice": "none", "base": list(base), "farm_kind": kind,
                    "shape": {"type": "circle", "size": list(base), "color": "#f4ece0"},
                    "components": {"FarmAnimal": {"product": product, "product_seconds": round(seconds * (0.8 + 0.1 * d)) if product else 600,
                                                  "icon": f"res://sprites/art_icon_{product.lower()}.png" if product else "",
                                                  "needs_food": bool(product), "food_icon": "res://sprites/art_icon_hay.png",
                                                  **({"grows_into": "Chicken", "grow_seconds": 75} if kind == "chick" else {}),
                                                  "wander_radius": 56.0, "speed": 26.0 if kind != "chick" else 34.0}}}
            place(name, c)
        for i, e in enumerate(b.enemies[:3]):
            self._pest(e, i)
            pk = farm_art.pest_kind(e.name)
            if pk:  # crows, foxes, rabbits and mice in the farm's own style
                self.entities[e.name].update({"farm_kind": pk[0], "farm_color": pk[1], "base": [16, 12]})
            nest = f"{e.name}Nest"
            k = SPEED[e.speed]
            self.entities[nest] = {
                "body": "static", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                "components": {"Spawner": {"entity": e.name, "interval": round(14.0 / (0.6 + 0.2 * d) / k, 1),
                                           "interval_ramp": 0.95, "min_interval": 5.0,
                                           "start_delay": 25.0 + 15 * i, "max_alive": max(1, min(e.count, 6))}}}
            legend["nqr"[i]] = nest
            cells[fm.nests[i % len(fm.nests)]] = "nqr"[i]
        rows = []
        for y in range(fm.height):
            rows.append("".join(cells.get((x, y), "#" if (x, y) in fm.solid else ".") for x in range(fm.width)).rstrip("."))
        intro = b.intro or f"Earn ${target} in {days} days!"
        if intro in (f"Score {b.score_target} points!", f"Earn ${b.score_target} before sunset!"):
            intro = f"Earn ${target} in {days} days!"  # the default intro follows the real target
        rules = [
            {"on": "Game.ready", "do": ["set_var('score_label', 'MONEY')", f"add_score({FARM_START_MONEY})",
                                        f"message({_q(intro)})"]},
            {"on": "GameState.second_passed", "if": "event.seconds == 4",
             "do": ["message('Space: till, plant, water, fish, chop')"]},
            {"on": "GameState.score_changed", "if": f"score >= {target}", "do": ["message('What a harvest!')", "win()"]},
            {"on": "Player.FarmDays.season_ended", "if": f"score < {target}",
             "do": ["message('The season is over')", "lose()"]},
            {"on": "GameState.second_passed", "if": "event.seconds == 12",
             "do": ["message('Sell crops, eggs, milk and wood at the shipping bin')"]},
        ]
        if b.enemies:
            pest = b.enemies[0].name
            rules.append({"on": "GameState.second_passed", "if": "event.seconds == 25",
                          "do": [f"message({_q(pest + 's are coming! Chase them off with X')})"]})
            for e in b.enemies[:3]:
                rules.append({"on": f"{e.name}.died", "do": ["add_score(2)"]})
        self.rules = rules
        if self.layer >= 2:
            self._polish()
        for ent in self.entities.values():
            ent.pop("farm_kind", None)
            ent.pop("farm_color", None)
        return {"spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown",
                "settings": {"tile_size": TILE, "lives": 1, "seed": self.seed, "zoom": 1.6,
                             "background": "#3aa0e8" if fm.island else "#4f8a3a",
                             "tile_style": "flat", "tiles": {"solid": {"color": "#00000000", "top": "#00000000"}},
                             "terrain": fm.terrain, "season": season, "music": season, "y_sort": True, "art": art},
                "entities": self.entities, "level": {"map": rows, "legend": legend}, "rules": self.rules}

    def _farm_target(self) -> int:
        b = self.b
        if b.score_target != DEFAULT_SCORE_TARGET:
            return b.score_target
        return 150 + 50 * b.difficulty  # an unspecified target: a full day's work

    def _farm_seconds(self) -> int:
        return self.b.survive_seconds if self.b.survive_seconds != 60 else 180

    def _pest(self, e: EnemyBrief, index: int) -> None:
        k = SPEED[e.speed]
        color = self.pal["enemies"][index % len(self.pal["enemies"])]
        comps: dict[str, dict] = {"TopDownMovement": {"max_speed": round(75 * k), "acceleration": 600}}
        if e.archetype in ("chaser", "shooter"):
            comps["ChaseAI"] = {"detect_radius": 260.0}
            comps["Hitbox"] = {"damage": 1, "knockback": 260.0}
        else:
            comps["CropPest"] = {"eat_seconds": round(3.5 - 0.3 * self.b.difficulty, 1), "appetite": 2}
        comps["Health"] = {"max_health": e.health, "invincibility_time": 0.05}
        comps["Hurtbox"] = {"size_scale": 1.2}
        self.entities[e.name] = {"team": "enemy", "shape": {"type": "circle", "size": [22, 22], "color": color},
                                 "components": comps}

    def _melee_or_gust(self, comps: dict) -> None:
        """The farmer's way to chase pests off: a sword swing, or a puff of air."""
        if "sword" in self.b.player.abilities:
            self._sword(comps)
            return
        comps["Aim"] = {"mode": "movement"}
        comps["Weapon"] = {"projectile": "Gust", "fire_rate": 3.0, "spread_deg": 0, "muzzle_distance": 14}
        self.entities["Gust"] = {"body": "area", "juice": "none",
                                 "shape": {"type": "circle", "size": [10, 10], "color": "#fff1e8"},
                                 "components": {"Projectile": {"speed": 380, "lifetime": 0.2, "pierce": 2},
                                                "Hitbox": {"damage": 1, "knockback": 300}}}

    def _sword(self, comps: dict) -> None:
        """Melee: the Weapon spawns a short-lived, slow, piercing swipe right in front of the hero."""
        if not self.platformer and "Aim" not in comps:
            comps["Aim"] = {"mode": "mouse" if self.b.genre == "topdown" else "movement"}
        comps["Weapon"] = {"projectile": "Slash", "fire_rate": 3.2, "spread_deg": 0, "muzzle_distance": 24}
        self.entities["Slash"] = {"body": "area", "team": "player", "juice": "none",
                                  "shape": {"type": "circle", "size": [30, 40], "color": "#e8f1ff"},
                                  "components": {"Projectile": {"speed": 140.0, "lifetime": 0.16, "pierce": 99},
                                                 "Hitbox": {"damage": 2, "knockback": 340.0}}}

    # -- shmup: a side-scrolling shooter -----------------------------------------------------
    def _shmup_graph(self) -> dict:
        b, pal = self.b, self.pal
        d = b.difficulty
        w, h = 24, 14  # a small field, zoomed in: the ships stay big on screen
        k = SPEED[b.player.speed]
        # No wall tiles: the level's invisible bounds keep everything inside, and space has no brick borders.
        cells = {(2, h // 2): "P", (w - 2, h // 2): "L"}
        if b.goal == "defeat_boss":
            cells[(w - 3, h // 2)] = "G"  # where the boss comes in
        rows = ["".join(cells.get((x, y), ".") for x in range(w)) for y in range(h)]
        self.entities["Player"] = {
            "shape": {"type": "circle", "size": [22, 22], "color": pal["player"]},
            "components": {"TopDownMovement": {"max_speed": round(270 * k), "acceleration": 3200.0, "friction": 3600.0},
                           "PlayerInput": {}, "Health": {"max_health": b.player.health, "invincibility_time": 1.3},
                           "Hurtbox": {},
                           "Weapon": {"projectile": "Laser", "fire_rate": 6.0, "spread_deg": 2.0, "muzzle_distance": 20.0},
                           "ShmupShip": {}}}
        self.entities["Laser"] = {"body": "area", "team": "player", "juice": "none",
                                  "shape": {"type": "circle", "size": [8, 8], "color": pal["bullet"]},
                                  "components": {"Projectile": {"speed": 640.0, "lifetime": 1.2},
                                                 "Hitbox": {"damage": 1, "knockback": 0.0}}}
        self._enemy_bullet()
        legend = {"P": "Player", "L": "Lair"}
        rules: list[dict] = []
        for i, e in enumerate(b.enemies[:4]):
            self._shmup_enemy(e, i)
            drop = {"drifter": 0.1, "weaver": 0.14, "diver": 0.16, "gunship": 0.3}[e.archetype]
            rules.append({"on": f"{e.name}.died", "do": [f"add_score({ENEMY_POINTS[e.archetype]})"]})
            rules.append({"on": f"{e.name}.died", "if": f"randf() < {drop}", "do": ["spawn('PowerUp')"]})
        self.entities["PowerUp"] = {"body": "area", "juice": "none",
                                    "shape": {"type": "circle", "size": [18, 18], "color": pal["pickup"]},
                                    "components": {"Collectible": {"kind": "power", "score": 0},
                                                   "FlightPath": {"pattern": "straight", "speed": 70.0}}}
        rules.append({"on": "PowerUp.collected", "do": ["Player.power_up()", "sound('powerup')"]})
        endless = b.goal != "defeat_boss"
        self.entities["Lair"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                                 "components": {"WaveSpawner": {"waves": self._shmup_waves(), "pause": 3.0,
                                                                "spread_y": float((h - 4) * TILE), "endless": endless}}}
        intro = b.intro or _default_goal_intro(b)
        rules.insert(0, {"on": "Game.ready", "do": [f"message({_q(intro)})"]})
        if b.goal == "defeat_boss":
            self._shmup_boss()
            legend["G"] = "BossGate"
            rules.append({"on": "Lair.WaveSpawner.cleared",
                          "do": [f"message({_q('WARNING! The ' + b.boss + ' is coming!')})", "shake(0.5)", "BossGate.start()"]})
            rules.append({"on": f"{b.boss}.died", "do": ["add_score(250)", f"message({_q('The ' + b.boss + ' is destroyed!')})", "win()"]})
        elif b.goal == "score_target":
            rules.append({"on": "GameState.score_changed", "if": f"score >= {self._score_target()}", "do": ["win()"]})
        else:  # survive
            n = b.survive_seconds
            rules.append({"on": "Game.ready", "do": [f"set_var('time_limit', {n})"]})
            rules.append({"on": "GameState.second_passed", "if": f"event.seconds >= {n}", "do": ["win()"]})
        self.rules = rules
        if self.layer >= 2:
            self._polish()
        bg = _space_bg(pal["bg"])
        return {"spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown",
                "settings": {"tile_size": TILE, "lives": 2, "seed": self.seed,
                             "zoom": round(min(960 / (w * TILE), 540 / (h * TILE)), 2), "background": bg,
                             "tiles": {"solid": {"color": pal["solid"], "top": pal["top"]}}},
                "entities": self.entities, "level": {"map": rows, "legend": legend}, "rules": self.rules}

    def _shmup_enemy(self, e: EnemyBrief, index: int) -> None:
        k, d = SPEED[e.speed], self.b.difficulty
        color = self.pal["enemies"][index % len(self.pal["enemies"])]
        comps: dict[str, dict] = {}
        speed = {"drifter": 90, "weaver": 100, "diver": 125, "gunship": 75}[e.archetype] * k
        comps["TopDownMovement"] = {"max_speed": round(speed), "acceleration": 4000.0, "friction": 2000.0}
        path = {"drifter": {"pattern": "straight"},
                "weaver": {"pattern": "wave", "amplitude": 70.0, "frequency": round(0.8 + 0.1 * index, 2)},
                "diver": {"pattern": "dive"},
                "gunship": {"pattern": "hover", "hover_at": 0.74, "amplitude": 90.0, "frequency": 0.4,
                            "aim_at_player": True}}[e.archetype]
        comps["FlightPath"] = path
        if e.archetype == "gunship":
            comps["Weapon"] = {"projectile": "EnemyBullet", "fire_rate": round(0.6 + 0.2 * d * k, 2), "spread_deg": 4.0,
                               "muzzle_distance": 22.0, "auto_fire": True}
        comps.update({"Health": {"max_health": e.health, "invincibility_time": 0.05}, "Hurtbox": {"size_scale": 1.0},
                      "Hitbox": {"damage": 1, "knockback": 160.0}})
        self.entities[e.name] = {"team": "enemy", "shape": {"type": "rect", "size": [28, 20], "color": color},
                                 "components": comps}

    def _shmup_boss(self) -> None:
        b, d = self.b, self.b.difficulty
        self.entities[b.boss] = {
            "team": "enemy", "shape": {"type": "rect", "size": [90, 56], "color": self.pal["enemies"][-1]},
            "components": {"TopDownMovement": {"max_speed": 80, "acceleration": 1500.0, "friction": 1500.0},
                           "FlightPath": {"pattern": "hover", "hover_at": 0.78, "amplitude": 150.0, "frequency": 0.3,
                                          "aim_at_player": True},
                           "Weapon": {"projectile": "EnemyBullet", "fire_rate": round(1.0 + 0.2 * d, 2), "projectile_count": 3,
                                      "spread_deg": 34.0, "muzzle_distance": 50.0, "auto_fire": True},
                           "Health": {"max_health": 40 + 14 * d, "invincibility_time": 0.03}, "Hurtbox": {"size_scale": 1.0},
                           "Hitbox": {"damage": 1, "knockback": 200.0}, "HealthBar": {"always": True, "width": 90.0}}}
        self.entities["BossGate"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                                     "components": {"WaveSpawner": {"waves": f"1 x {b.boss} every 1", "pause": 3.0,
                                                                    "autostart": False}}}

    def _shmup_waves(self) -> str:
        """Easy enemies first, new types joining as the waves go on; gunships come in ones and twos."""
        b = self.b
        n = {"short": 5, "medium": 7, "long": 9}[b.length]
        k = 0.75 + 0.15 * b.difficulty
        order = sorted(b.enemies[:4], key=lambda e: ("drifter", "weaver", "diver", "gunship").index(e.archetype))
        out = []
        for i in range(n):
            pool = order[: min(len(order), 1 + i // 2)]
            # even waves bring in the newest type, odd ones go back to older ones
            e = pool[-1] if i % 2 == 0 else pool[(i // 2 - 1) % len(pool)]
            size = (4 + 1.0 * i) * k * max(0.5, e.count / 3)
            if e.archetype == "gunship":
                size = (2 + i // 2) * max(0.7, e.count / 3)
            every = {"drifter": 0.85, "weaver": 0.75, "diver": 1.0, "gunship": 2.2}[e.archetype] * max(0.6, 1 - 0.05 * i)
            out.append(f"{max(2, round(size))} x {e.name} every {round(every, 2)}")
        return "; ".join(out)

    # -- tower defense -----------------------------------------------------------------------
    def _td_graph(self) -> dict:
        b, pal = self.b, self.pal
        d = b.difficulty
        lay = levelgen.td_road(self.seed, b.length)
        towers = []
        for i, name in enumerate(b.towers[:3]):
            prof = tower_profile(name, i)
            stats = TOWER_PROFILES[prof]
            shot = name.removesuffix("Tower") + "Shot"
            self.entities[name] = {"body": "area", "team": "player",
                                   "shape": {"type": "rect", "size": [26, 26], "color": stats["color"]},
                                   "components": {"Weapon": {"projectile": shot, "fire_rate": stats["fire_rate"],
                                                             "spread_deg": 2, "muzzle_distance": 14},
                                                  "TowerBrain": {"fire_range": stats["range"]}}}
            proj: dict[str, Any] = {"speed": stats["speed"], "lifetime": round(stats["range"] / stats["speed"] + 0.15, 2)}
            if stats.get("pierce"):
                proj["pierce"] = stats["pierce"]
            self.entities[shot] = {"body": "area", "juice": "none",
                                   "shape": {"type": "circle", "size": [8, 8] if prof == "fast" else [12, 12],
                                             "color": stats["shot"]},
                                   "components": {"Projectile": proj,
                                                  "Hitbox": {"damage": stats["damage"], "knockback": 40}}}
            towers.append(f"{name}|{stats['cost']}")
        self.entities["Commander"] = {"body": "character", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                                      "components": {"PlayerInput": {},
                                                     "TowerBuilder": {"towers": ";".join(towers), "start_gold": 150}}}
        self.entities["Road"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                                 "components": {"GroundPatch": {"color": ROAD_COLORS.get(b.palette, "#c9ad7a"),
                                                                "size": 32, "round_corners": 0.4}}}
        self.entities["Pad"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [30, 30]},
                                "components": {"TowerSlot": {"size": 30}}}
        self.entities["Lair"] = {"body": "area", "juice": "none",
                                 "shape": {"type": "circle", "size": [36, 36], "color": pal["enemies"][-1]},
                                 "components": {"WaveSpawner": {"waves": self._waves(), "pause": 7.0}}}
        self.entities["Castle"] = {"body": "area", "juice": "none",
                                   "shape": {"type": "rect", "size": [40, 40], "color": pal["exit"]},
                                   "components": {"Base": {}}}
        rules = [{"on": "Game.ready", "do": ["set_var('score_label', 'GOLD')",
                                             f"message({_q((b.intro or 'Hold the castle!') + ' Click a pad to build')})"]}]
        for i, e in enumerate(b.enemies[:3]):
            self._invader(e, i)
            rules.append({"on": f"{e.name}.died", "do": [f"add_score({INVADER_GOLD[e.speed] * e.health})"]})
        rules.append({"on": "Lair.WaveSpawner.cleared", "do": ["message('The castle stands!')", "win()"]})
        self.rules = rules
        cells = {c: "~" for c in lay.road}
        cells.update({c: "o" for c in lay.pads})
        cells[lay.road[0]], cells[lay.road[-1]], cells[lay.commander] = "S", "B", "P"
        rows = ["".join("#" if x in (0, lay.width - 1) or y in (0, lay.height - 1) else cells.get((x, y), ".")
                        for x in range(lay.width)) for y in range(lay.height)]
        if self.layer >= 2:
            self._polish()
        return {"spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown",
                "settings": {"tile_size": TILE, "lives": max(5, 12 - d), "seed": self.seed,
                             "zoom": round(min(1.0, 960 / (lay.width * TILE), 560 / (lay.height * TILE)), 2),
                             "background": FARM_GROUND.get(b.palette, FARM_GROUND["forest"]),
                             "tiles": {"solid": {"color": "#7a6f62", "top": "#a39a8c"}}},
                "entities": self.entities,
                "level": {"map": rows, "legend": {"#": "solid", "~": "Road", "S": "Lair", "B": "Castle",
                                                  "o": "Pad", "P": "Commander"}},
                "rules": self.rules}

    def _invader(self, e: EnemyBrief, index: int) -> None:
        color = self.pal["enemies"][index % len(self.pal["enemies"])]
        self.entities[e.name] = {
            "team": "enemy", "shape": {"type": "circle", "size": [22, 22], "color": color},
            "components": {"TopDownMovement": {"max_speed": INVADER_SPEED[e.speed], "acceleration": 900},
                           "PathFollower": {"road": "Road"},
                           "Health": {"max_health": round(INVADER_HP[e.speed] * e.health * (0.8 + 0.1 * self.b.difficulty)),
                                      "invincibility_time": 0.02},
                           "Hurtbox": {"size_scale": 1.0}}}

    def _waves(self) -> str:
        """Waves cycle through the invader types and grow; slow ones come in small groups, fast ones in swarms."""
        b = self.b
        n = {"short": 5, "medium": 7, "long": 9}[b.length]
        k = 0.7 + 0.15 * b.difficulty
        out = []
        # Easy invaders open; the toughest type first shows up once a few towers can stand.
        order = sorted(b.enemies[:3], key=lambda e: {"normal": 0, "slow": 1, "fast": 2}[e.speed])
        for i in range(n):
            e = order[WAVE_PATTERN[i] % len(order)]
            size = (6 + 2.5 * i) * k * max(0.5, e.count / 3) * {"slow": 0.4, "normal": 1.0, "fast": 0.85}[e.speed]
            every = {"slow": max(0.9, 2.2 - 0.15 * i), "normal": max(0.45, 1.4 - 0.12 * i),
                     "fast": max(0.4, 0.8 - 0.05 * i)}[e.speed]
            out.append(f"{max(3, round(size))} x {e.name} every {round(every, 2)}")
        return "; ".join(out)

    def _bubble_graph(self) -> dict:
        b, pal = self.b, self.pal
        d = b.difficulty
        width, height = 30, 17
        rows = ["#" * width] + ["#" + "." * (width - 2) + "#" for _ in range(height - 2)] + ["#" * width]
        r = list(rows[14])
        r[12] = "P"
        rows[14] = "".join(r)
        colors = ",".join(dict.fromkeys([*pal["enemies"], pal["pickup"], pal["player"], "#29adff", "#00e436"]))
        board = {"columns": 9 if b.length == "long" else 8, "rows": min(3 + d, 8), "height_rows": 12,
                 "colors": min(3 + (d >= 2) + (d >= 4), 6), "shots_per_drop": max(4, 10 - d),
                 "palette": colors, "launcher_offset": [60, 0]}
        player: dict[str, Any] = {"juice": "none", "components": {"PlayerInput": {}, "BubbleBoard": board}}
        if self.layer >= 2:
            player["sprite"] = {"generate": {"kind": "hero", "color": pal["player"],
                                             "features": features_for(b.player.character)}}
        else:
            player["shape"] = {"type": "capsule", "size": [22, 34], "color": pal["player"]}
        c = b.collectible.name
        return {
            "spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown",
            "settings": {"tile_size": TILE, "lives": 1, "seed": self.seed, "background": pal["bg"], "zoom": 1.0,
                         "tiles": {"solid": {"color": pal["solid"], "top": pal["top"]}}},
            "entities": {"Player": player},
            "level": {"map": rows, "legend": {"#": "solid", "P": "Player"}},
            "rules": [
                {"on": "Game.ready", "do": [f"message({_q(b.intro or 'Pop every ' + c + '!')})"]},
                {"on": "Player.BubbleBoard.ceiling_dropped", "do": ["message('The ceiling is coming down!')"]},
                {"on": "Player.BubbleBoard.cleared", "do": [f"message({_q('Every ' + c + ' popped!')})", "win()"]},
                {"on": "Player.BubbleBoard.overflowed", "do": ["lose()"]},
            ],
        }

    def _layout(self) -> levelgen.Layout:
        b = self.b
        if self.platformer:
            length, up, across, pits = _level_args(b)
            return levelgen.platformer(self.seed, length, up, across, pits, b.difficulty,
                                       door=b.goal in ("collect_all_then_exit", "rescue"), chunks=self.chunks)
        return levelgen.arena(self.seed, b.length, b.difficulty)

    # -- player ------------------------------------------------------------------------------
    def _player(self, grid, lay) -> None:
        p = self.b.player
        abilities = set(p.abilities)
        comps: dict[str, dict] = {}
        if self.platformer:
            feel = FEEL_PLATFORMER[self.b.feel] if self.layer >= 2 else {}
            mv = {"max_speed": round(230 * SPEED[p.speed]),
                  "jump_velocity": jump_velocity(p.jump_tiles, feel.get("gravity_scale", 1.0))}
            if "double_jump" in abilities:
                mv["air_jumps"] = 1
            if "dash" in abilities:
                mv["dash_speed"] = 620.0
            mv.update(feel)
            comps["PlatformerMovement"] = mv
        else:
            feel = FEEL_TOPDOWN[self.b.feel] if self.layer >= 2 else {}
            mv = {"max_speed": round(250 * SPEED[p.speed])}
            if "dash" in abilities:
                mv["dash_speed"] = 720.0
            mv.update(feel)
            comps["TopDownMovement"] = mv
        comps["PlayerInput"] = {}
        comps["Health"] = {"max_health": p.health, "invincibility_time": 0.8}
        comps["Hurtbox"] = {}
        if self.platformer and "stomp" in abilities:
            comps["Stomp"] = {}
        if "sword" in abilities and "shoot" not in abilities:
            self._sword(comps)
        if "shoot" in abilities:
            if not self.platformer:
                comps["Aim"] = {"mode": "mouse"}
            comps["Weapon"] = {"projectile": "Bullet", "fire_rate": 8.0 if not self.platformer else 5.0,
                               "spread_deg": 5.0}
            self.entities["Bullet"] = {
                "body": "area", "team": "player",
                "shape": {"type": "circle", "size": [8, 8], "color": self.pal["bullet"]},
                "components": {"Projectile": {"speed": 720.0, "lifetime": 0.9},
                               "Hitbox": {"damage": 1, "knockback": 160.0}},
            }
        if self.b.level_ups and not self.platformer and self.layer >= 1 and "Bullet" in self.entities:
            # Survivor style: the player only moves; shots aim themselves and get better with each level.
            comps["Aim"] = {"mode": "nearest_enemy", "max_range": 380.0}
            comps["Weapon"] = {"projectile": "Bullet", "fire_rate": 2.6, "projectile_count": 2, "spread_deg": 14.0,
                               "auto_fire": True, "muzzle_distance": 16.0}
            self.entities["Bullet"]["components"]["Projectile"] = {"speed": 560.0, "lifetime": 0.75, "pierce": 1}
            comps["Health"] = {"max_health": max(p.health, 5), "invincibility_time": 1.2}
            comps["Experience"] = {"first_level_xp": 3, "growth": 1.25, "magnet_radius": 110.0}
            comps["LevelUpMenu"] = {"upgrades": LEVEL_UP_UPGRADES}
            self.entities["XpGem"] = {"body": "area", "shape": {"type": "circle", "size": [10, 10], "color": "#29adff"},
                                      "components": {"XpOrb": {"value": 1, "lifetime": 40.0}}}
        shape = {"type": p.shape, "size": [22, 34] if self.platformer else [24, 24], "color": self.pal["player"]}
        if p.shape == "circle":
            shape["size"] = [26, 26] if self.platformer else [24, 24]
        elif p.shape == "rect":
            shape["size"] = [24, 30] if self.platformer else [24, 24]
        elif not self.platformer:
            shape["type"] = "circle"
        self.entities["Player"] = {"shape": shape, "components": comps}
        self.legend["P"] = "Player"
        grid[lay.player] = "P"

    # -- goal --------------------------------------------------------------------------------
    def _goal(self, grid, lay) -> None:
        b, pal = self.b, self.pal
        c = b.collectible.name
        needs_exit = b.goal in ("reach_exit", "collect_all_then_exit")
        if needs_exit:
            self.entities["Exit"] = {
                "body": "area",
                "shape": {"type": "rect", "size": [28, 48]} if self.platformer else {"type": "circle", "size": [40, 40]},
                "components": {"TriggerZone": {"once": not (b.goal == "collect_all_then_exit" and not self.platformer)}},
            }
            self.entities["Exit"]["shape"]["color"] = pal["exit"]
            self.legend["E"] = "Exit"
            grid[lay.exit] = "E"
        if b.goal == "reach_exit":
            self.rules.append({"on": "Exit.triggered", "do": ["win()"]})
        elif b.goal == "collect_all":
            self.rules.append({"on": f"{c}.collected", "if": f"count({_q(c)}) == 0", "do": ["win()"]})
        elif b.goal == "collect_all_then_exit":
            if self.platformer and lay.door:
                self.entities["Door"] = {"body": "static",
                                         "shape": {"type": "rect", "size": [18, 126], "color": pal["door"]},
                                         "components": {"Gate": {}}}
                self.legend["D"] = "Door"
                grid[lay.door] = "D"
                self.rules.append({"on": f"{c}.collected", "if": f"count({_q(c)}) == 0",
                                   "do": ["Door.open()", "message('The door is open!')"]})
                self.rules.append({"on": "Exit.triggered", "do": ["win()"]})
            else:
                self.rules.append({"on": "Exit.triggered", "if": f"count({_q(c)}) == 0", "do": ["win()"]})
                self.rules.append({"on": "Exit.triggered", "if": f"count({_q(c)}) > 0",
                                   "do": [f"message({_q('Collect every ' + c + ' first!')})"]})
        elif b.goal == "defeat_all":
            names = [e.name for e in b.enemies]
            total = " + ".join(f"count({_q(n)})" for n in names)
            for n in names:
                self.rules.append({"on": f"{n}.died", "if": f"{total} == 0", "do": ["win()"]})
        elif b.goal == "score_target":
            self.rules.append({"on": "GameState.score_changed", "if": f"score >= {self._score_target()}", "do": ["win()"]})
        elif b.goal == "rescue":
            self._rescue(grid, lay)
        elif b.goal == "survive":
            n = b.survive_seconds
            self.rules.append({"on": "Game.ready", "do": [f"set_var('time_limit', {n})"]})
            self.rules.append({"on": "GameState.second_passed", "if": f"event.seconds == {max(n - 10, 1)}",
                               "do": ["message('10 seconds left!')"]})
            self.rules.append({"on": "GameState.second_passed", "if": f"event.seconds >= {n}", "do": ["win()"]})
        if not self.platformer and b.goal in ("score_target", "survive"):
            if b.level_ups:
                self._nests()
            else:
                self._portals(grid, lay)

    def _score_target(self) -> int:
        """The brief keeps what the player said; the game makes it playable. A platformer level holds a fixed
        number of points, so the target is capped at what it holds. Top-down arenas keep spawning enemies,
        so an unspecified (default) target becomes a real fight instead of five shots: 8 + 4 x difficulty kills."""
        b = self.b
        if b.genre == "platformer":  # a platformer level holds a fixed number of points
            reachable = b.collectible.count + sum(e.count * ENEMY_POINTS.get(e.archetype, 10) for e in b.enemies)
            return min(b.score_target, max(10, reachable - reachable % 5))
        if not b.enemies or b.score_target != DEFAULT_SCORE_TARGET:
            return b.score_target
        per_kill = max(ENEMY_POINTS.get(e.archetype, 10) for e in b.enemies)
        return max(b.score_target, per_kill * (8 + 4 * b.difficulty))

    def _rescue(self, grid, lay) -> None:
        """Key somewhere high up -> the cage opens -> touch the one you came to save."""
        b, pal = self.b, self.pal
        who = b.rescue_target
        self.entities["Cage"] = {"body": "static", "shape": {"type": "rect", "size": [18, 126], "color": "#8a8f98"},
                                 "components": {"Gate": {}}}
        self.legend["D"] = "Cage"
        grid[lay.door] = "D"
        self.entities[who] = {"body": "area", "shape": {"type": "capsule", "size": [22, 34], "color": pal["heart"]},
                              "components": {"TriggerZone": {}}}
        self.legend["M"] = who
        grid[lay.exit] = "M"
        self.entities["CageKey"] = {"body": "area", "shape": {"type": "circle", "size": [14, 14], "color": "#ffec27"},
                                    "components": {"Collectible": {"kind": "key", "score": 10}}}
        self.legend["K"] = "CageKey"
        # The key is required, so it must be easy to reach for sure: on a platform one single jump above the
        # ground, at most a single jump above that platform. Among those, the highest spot in the back half.
        single = int(jump_velocity(b.player.jump_tiles) ** 2 / (2 * PLATFORMER_GRAVITY) // TILE)

        def safe(c: tuple[int, int]) -> int | None:
            h = levelgen.floor_below(lay, c)
            if h is None or h > single:
                return None
            platform_rise = levelgen.STAND_ROW - (c[1] + h)
            return h + platform_rise if 0 <= platform_rise <= single else None

        before_cage = [(c, height) for c in lay.air_slots
                       if c[0] < lay.door[0] - 1 and c not in grid and (height := safe(c)) is not None]
        back = [x for x in before_cage if x[0][0] > lay.width // 2] or before_cage
        if back:
            spot = max(back, key=lambda x: (x[1], x[0][0]))[0]
        else:  # no suitable air slot: on the ground just before the cage
            spot = (lay.door[0] - 2, levelgen.STAND_ROW)
        grid[spot] = "K"
        self.rules.append({"on": "CageKey.collected", "do": ["Cage.open()", f"message({_q('The cage is open - go to ' + who + '!')})"]})
        self.rules.append({"on": f"{who}.triggered", "do": [f"message({_q('You saved ' + who + '!')})", "win()"]})

    def _nests(self) -> None:
        """Survivor waves: one invisible nest per enemy type, spawning on a ring around the player, denser
        over time; later types arrive later."""
        d = self.b.difficulty
        enemies = self.b.enemies or [EnemyBrief(name=self._default_chaser(), archetype="chaser", count=0)]
        for i, e in enumerate(enemies[:3]):
            self.entities[f"{e.name}Nest"] = {
                "body": "static", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                "components": {"Spawner": {"entity": e.name, "interval": round([1.1, 3.5, 7.0][i] - 0.1 * d, 2),
                                           "interval_ramp": 0.985 if i == 0 else 0.97,
                                           "min_interval": [0.2, 0.9, 2.5][i], "start_delay": [1.0, 20.0, 60.0][i],
                                           "max_alive": [40 + 5 * d, 12 + 2 * d, 4 + d][i], "around_player": 470}}}
            self.legend["n" if i == 0 else ("o" if i == 1 else "q")] = f"{e.name}Nest"
            self._nest_cells.append(("n" if i == 0 else ("o" if i == 1 else "q")))

    def _portals(self, grid, lay) -> None:
        spawn = self.b.enemies[0].name if self.b.enemies else self._default_chaser()
        d = self.b.difficulty
        self.entities["Portal"] = {
            "body": "area", "juice": "none",
            "shape": {"type": "circle", "size": [40, 40], "color": self.pal["enemies"][-1]},
            "components": {"Spawner": {"entity": spawn, "interval": max(1.0, 5.0 - d * 0.7),
                                       "start_delay": 3.0, "max_alive": 2 + d}},
        }
        self.legend["O"] = "Portal"
        for c in lay.portal_slots[: 2 + (1 if d >= 3 else 0)]:
            if c not in grid:
                grid[c] = "O"

    def _default_chaser(self) -> str:
        e = EnemyBrief(name="Chaser", archetype="chaser", count=0)
        self._enemy_entity(e, 0)
        return "Chaser"

    # -- enemies -----------------------------------------------------------------------------
    def _enemies(self, grid, lay) -> None:
        rng = random.Random(f"enemies:{self.seed}")
        if self.platformer:
            slots = [c for c in lay.ground_slots if c[0] > lay.player[0] + 6 and c not in grid]
            overflow = levelgen.extra_ground_cells(lay, lay.player[0] + 8)
        else:
            far = [c for c in lay.free_cells
                   if abs(c[0] - lay.player[0]) + abs(c[1] - lay.player[1]) >= 10 and c not in grid]
            slots, overflow = far, []
        rng.shuffle(slots)
        rng.shuffle(overflow)
        for i, e in enumerate(self.b.enemies):
            sym = ENEMY_SYMBOLS[i]
            self._enemy_entity(e, i)
            self.legend[sym] = e.name
            for _ in range(e.count):
                pool = slots if slots else overflow
                while pool and pool[-1] in grid:
                    pool.pop()
                if not pool:
                    break
                grid[pool.pop()] = sym
            self.rules.append({"on": f"{e.name}.died", "do": [f"add_score({ENEMY_POINTS[e.archetype]})"]
                               + (["spawn('XpGem')"] if self.b.level_ups and "XpGem" in self.entities else [])})

    def _enemy_entity(self, e: EnemyBrief, index: int) -> None:
        k = SPEED[e.speed]
        d = self.b.difficulty
        color = self.pal["enemies"][index % len(self.pal["enemies"])]
        health = {"max_health": e.health, "invincibility_time": 0.1}
        contact = {"damage": 1, "knockback": 280.0}
        comps: dict[str, dict] = {}
        shape: dict[str, Any] = {"type": "rect", "size": [28, 20]}
        mv_name = "PlatformerMovement" if self.platformer else "TopDownMovement"
        if e.archetype == "walker":
            comps = {mv_name: {"max_speed": round(65 * k)}, "PatrolAI": {}}
        elif e.archetype == "hopper":
            shape = {"type": "circle", "size": [26, 22]}
            comps = {mv_name: {"max_speed": round(90 * k), "jump_velocity": 480.0},
                     "PatrolAI": {"jump_interval": round(1.6 / k, 2)}}
        elif e.archetype == "chaser":
            shape = {"type": "circle", "size": [24, 24]} if not self.platformer else {"type": "rect", "size": [24, 24]}
            comps = {mv_name: {"max_speed": round((110 if self.platformer else 130) * k)},
                     "ChaseAI": {"detect_radius": 300.0 + d * 30}}
        elif e.archetype == "shooter":
            shape = {"type": "rect", "size": [26, 26]}
            comps = {mv_name: {"max_speed": round(80 * k)},
                     "ChaseAI": {"detect_radius": 420.0, "keep_distance": 200.0, "fire_range": 380.0},
                     "Weapon": {"projectile": "EnemyBullet", "fire_rate": round(0.6 + 0.25 * d * k, 2),
                                "spread_deg": 8.0, "muzzle_distance": 22.0}}
            self._enemy_bullet()
        elif e.archetype == "turret":
            shape = {"type": "triangle", "size": [28, 28]}
            comps = {"ChaseAI": {"wander": False, "detect_radius": 400.0, "fire_range": 400.0},
                     "Weapon": {"projectile": "EnemyBullet", "fire_rate": round(0.5 + 0.2 * d * k, 2),
                                "spread_deg": 4.0, "muzzle_distance": 22.0}}
            self._enemy_bullet()
        comps.update({"Health": health, "Hurtbox": {"size_scale": 1.0}, "Hitbox": contact})
        shape["color"] = color
        self.entities[e.name] = {"team": "enemy", "shape": shape, "components": comps}
        if self.b.level_ups and not self.platformer:
            if "ChaseAI" in comps:  # swarms always know where the player is
                comps["ChaseAI"].update({"detect_radius": 5000.0, "lose_radius": 5000.0, "wander": False,
                                         "needs_line_of_sight": False})
            # Hundreds of kills: no hit-stop or big shakes per enemy (it would freeze the game).
            self.entities[e.name]["juice"] = {"hitstop_on_death": 0.0, "hitstop_on_hurt": 0.0,
                                              "shake_on_death": 0.04, "shake_on_hurt": 0.0}

    def _enemy_bullet(self) -> None:
        if "EnemyBullet" in self.entities:
            return
        self.entities["EnemyBullet"] = {
            "body": "area", "team": "enemy",
            "shape": {"type": "circle", "size": [10, 10], "color": self.pal["enemy_bullet"]},
            "components": {"Projectile": {"speed": 240.0 + self.b.difficulty * 30, "lifetime": 3.0},
                           "Hitbox": {"damage": 1, "knockback": 220.0}},
        }

    # -- pickups & hazards -------------------------------------------------------------------
    def _pickups(self, grid, lay) -> None:
        b = self.b
        rng = random.Random(f"pickups:{self.seed}")
        if self.platformer:
            reach = jump_reach_tiles(b)
            # Only pickups the player can actually jump to.
            slots = [c for c in lay.air_slots
                     if c not in grid and (h := levelgen.floor_below(lay, c)) is not None and h <= reach]
            extra = levelgen.extra_ground_cells(lay, lay.player[0] + 3)
        else:
            slots = [c for c in lay.free_cells
                     if abs(c[0] - lay.player[0]) + abs(c[1] - lay.player[1]) >= 3 and c not in grid]
            extra = []
        rng.shuffle(slots)
        rng.shuffle(extra)

        def take() -> tuple[int, int] | None:
            for pool in (slots, extra):
                while pool:
                    c = pool.pop()
                    if c not in grid:
                        return c
            return None

        name = b.collectible.name
        if b.collectible.count > 0:
            self.entities[name] = {"body": "area",
                                   "shape": {"type": "circle", "size": [14, 14], "color": pickup_color(name, self.pal)},
                                   "components": {"Collectible": {"kind": name.lower(), "score": 1}}}
            self.legend["C"] = name
            for _ in range(b.collectible.count):
                c = take()
                if c is None:
                    break
                grid[c] = "C"
        if b.health_pickups > 0:
            self.entities["HealthPack"] = {"body": "area",
                                           "shape": {"type": "rect", "size": [16, 14], "color": self.pal["heart"]},
                                           "components": {"Collectible": {"kind": "heart", "score": 0, "heal": 1}}}
            self.legend["+"] = "HealthPack"
            for _ in range(b.health_pickups):
                c = take()
                if c is None:
                    break
                grid[c] = "+"

    def _hazards(self, grid, lay) -> None:
        if "spikes" not in self.b.hazards or not self.platformer:
            return
        rng = random.Random(f"hazards:{self.seed}")
        share = 0.4 + 0.15 * self.b.difficulty
        cells = [c for c in lay.hazard_slots if c not in grid and rng.random() < share]
        if not cells:
            return
        # Enemy team: spikes hurt the player only (enemies walking into them must not give free points).
        self.entities["Spikes"] = {"body": "area", "team": "enemy", "juice": "none",
                                   "shape": {"type": "spikes", "size": [30, 14], "color": self.pal["hazard"]},
                                   "components": {"Hitbox": {"damage": 1, "knockback": 420.0}}}
        self.legend["^"] = "Spikes"
        for c in cells:
            grid[c] = "^"

    # -- polish (layer 2) --------------------------------------------------------------------
    def _decor(self, grid: dict, lay: levelgen.Layout) -> None:
        """Layer 2: a few trees, bushes and rocks on free ground (behind everything, no collision)."""
        props = [d for d in THEME_DECOR.get(self.b.palette, []) if d[0] not in self.entities]
        if not props:
            return
        # Separate streams: where props go depends on the level only, so a re-theme swaps them in place.
        rng, pick = random.Random(self.seed * 7919 + 13), random.Random(self.seed * 7919 + 14)
        keep_clear = [c for c in (lay.player, lay.exit, lay.door) if c is not None]
        if self.platformer:
            spots = sorted(((x, y) for x in range(lay.width) for y in range(lay.height - 1)
                            if lay.is_free((x, y)) and lay.tiles.get((x, y + 1)) == "solid"), key=lambda c: c[0])
            chance, spacing = 0.28, 3
        else:
            spots = list(lay.free_cells)
            chance, spacing = 0.06, 2
        placed: list[tuple[int, int]] = []
        for c in spots:
            if c in grid or any(abs(c[0] - k[0]) <= 2 and abs(c[1] - k[1]) <= 2 for k in keep_clear):
                continue
            if any(abs(c[0] - q[0]) < spacing and abs(c[1] - q[1]) < spacing for q in placed) or rng.random() > chance:
                continue
            name, sym, color = pick.choice(props)
            grid[c] = sym
            placed.append(c)
            if name not in self.entities:
                self.entities[name] = {"body": "area", "decor": True, "juice": "none", "components": {},
                                       "shape": {"type": "rect", "size": [24, 24], "color": color}}
                self.legend[sym] = name

    def _polish(self) -> None:
        self._sprites()
        k = JUICE_SCALE[self.b.juice]
        if k == 1.0:
            return
        params = {name: round(min(default * k, cap), 3) for name, (default, cap) in JUICE_DEFAULTS.items()}
        for name, ent in self.entities.items():
            if ent.get("juice") == "none":
                continue
            ent["juice"] = {**params, **(ent["juice"] if isinstance(ent.get("juice"), dict) else {})}


    def _sprites(self) -> None:
        """Layer 2 art pass: placeholders become generated pixel-art sprites (collision follows)."""
        archetypes = {e.name: e.archetype for e in self.b.enemies}
        ai_art = self.ai_art
        for name, ent in self.entities.items():
            farm_kind = ent.pop("farm_kind", None)
            comps = ent.get("components", {})
            if farm_kind is None and (ent["shape"].get("type") == "none" or "Market" in comps or "Warp" in comps):
                continue  # invisible helpers (survivor nests, plots, roads, doorways) and self-drawn stalls
            if farm_kind is not None:  # the cozy farm's own art (sprites/farm.py)
                gen_farm: dict[str, Any] = {"kind": farm_kind, "seed": self.art_seed,
                                            "color": look_color(ent["shape"]["color"], self.look) if farm_kind == "farmer"
                                            else ent.pop("farm_color", None) or farm_art.SPRITES[farm_kind][3]}
                ent["sprite"] = {"generate": gen_farm}
                del ent["shape"]
                continue
            kind = sprite_kind(name, ent, archetypes.get(name), self.b, self.platformer)
            color = look_color(ent["shape"]["color"], self.look)
            if ai_art:
                subject = self.b.player.character if name == "Player" else name
                words = " ".join(re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", subject)).lower()
                ent["sprite"] = {"ai": {"prompt": f"{words}, {self.b.palette} color palette, game: {self.b.title}",
                                        "kind": kind, "color": color, "seed": self.art_seed}}
            else:
                gen: dict[str, Any] = {"kind": kind, "color": color, "seed": self.art_seed}
                if self.b.genre == "shmup" and name == self.b.boss:
                    gen["size"] = 3  # the same art, three times bigger
                if name == "Player":
                    gen["features"] = features_for(self.b.player.character) + (
                        ["sword"] if "sword" in self.b.player.abilities else [])
                elif "TriggerZone" in ent.get("components", {}) and kind == "hero":
                    gen["features"] = features_for(name)  # "Mom" gets long hair, "Princess" too
                ent["sprite"] = {"generate": gen}
            del ent["shape"]


HUMANOID_WORDS = {"goblin", "zombie", "knight", "skeleton", "orc", "ninja", "soldier", "pirate", "bandit",
                  "wizard", "witch", "mage", "guard", "thief", "samurai", "elf", "troll", "vampire", "mummy",
                  "archer", "hunter", "ranger", "ogre", "giant", "brute", "paladin", "templar", "spearman", "sorcerer",
                  "warlock", "necromancer", "druid", "shaman", "priest", "cleric", "healer", "monk", "rogue",
                  "assassin", "viking", "barbarian", "berserker", "dwarf", "king", "queen", "prince", "princess",
                  "lord", "dracula", "lich", "ghoul", "skelly", "warrior", "fighter", "villager", "peasant"}
FLYER_WORDS = {"bat", "bird", "crow", "wasp", "bee", "fly", "owl", "eagle"}
DRAGON_WORDS = {"dragon", "drake", "wyvern", "wyrm"}
GHOST_WORDS = {"ghost", "spirit", "phantom", "specter", "spectre", "wraith", "spook", "banshee", "poltergeist"}
SPIDER_WORDS = {"spider", "tarantula", "arachnid", "widow"}
SNAKE_WORDS = {"snake", "serpent", "cobra", "python", "viper", "worm", "eel", "naga"}
BEAST_WORDS = {"wolf", "fox", "dog", "puppy", "hound", "cat", "kitty", "tiger", "lion", "bear", "boar", "pig", "hog",
               "panther", "jackal", "hyena", "werewolf", "coyote", "leopard", "cougar"}
PLANT_WORDS = {"plant", "flower", "piranha", "venus", "vine", "sprout", "thorn", "treant", "ent"}
MUSHROOM_WORDS = {"mushroom", "shroom", "toadstool", "fungus", "funguy", "spore"}
REAPER_WORDS = {"reaper", "grim", "scythe"}
FLAME_WORDS = {"flame", "fire", "ember", "blaze", "inferno", "pyro", "lava"}
SNAIL_WORDS = {"snail", "slug"}
ALIEN_WORDS = {"alien", "martian", "extraterrestrial"}
ROBOT_WORDS = {"robot", "bot", "droid", "mech", "drone", "android", "cyborg", "machine"}
BUG_WORDS = {"bug", "beetle", "ant", "scorpion", "roach", "crab", "insect"}
HOPPER_WORDS = {"frog", "toad", "bunny", "rabbit", "kangaroo"}
SHIP_WORDS = {"ship", "fighter", "jet", "plane", "bomber", "gunship", "warship", "cruiser", "destroyer", "battleship",
              "raider", "falcon", "viper", "interceptor", "starfighter", "rocket", "dreadnought", "carrier"}
UFO_WORDS = {"ufo", "saucer", "alien", "drone", "probe", "pod", "orb", "mine", "scout", "invader"}
# Objects come before materials and uses, so a GoldKey is a key and a HealthPotion a potion.
PICKUP_KINDS = (({"key"}, "key"), ({"potion", "elixir", "flask", "tonic", "brew"}, "potion"),
                ({"scroll", "map", "letter", "page", "rune", "spellbook"}, "scroll"),
                ({"bomb", "dynamite", "tnt"}, "bomb"), ({"chest", "treasure", "loot"}, "chest"),
                ({"coin", "gold", "money", "cash", "token"}, "coin"), ({"star", "starlight"}, "star"),
                ({"gem", "crystal", "diamond", "jewel", "ruby", "emerald", "shard", "sapphire"}, "gem"),
                ({"heart", "life", "health"}, "heart"))
ARROW_WORDS = {"arrow", "dart"}
SHOOTER_ARCHETYPES = ("shooter", "turret", "gunship")


def _archers(names: list[str]) -> bool:
    """True when every name draws a bow (their shots are arrows)."""
    return bool(names) and all("bow" in features_for(n) for n in names)


def _ordered_words(name: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)]


def _words(name: str) -> set[str]:
    return set(_ordered_words(name))


def sprite_kind(name: str, ent: dict, archetype: str | None, brief: GameBrief, platformer: bool) -> str:
    words = _words(name)
    comps = ent.get("components", {})
    if ent.get("decor"):
        return next((DECOR_KINDS[w] for w in _ordered_words(name)[::-1] if w in DECOR_KINDS), "rock")
    if brief.genre == "shmup":
        if name == "Player" or name == brief.boss or archetype == "gunship" or words & SHIP_WORDS:
            return "ship" if not words & UFO_WORDS else "ufo"
        if words & UFO_WORDS or archetype in ("drifter", "weaver", "diver"):
            return "ufo"
    if name == "Player":
        return "hero"
    if name in ("Bullet", "EnemyBullet", "Gust"):
        if name == "Bullet" and _archers([brief.player.character]):
            return "arrow"
        if name == "EnemyBullet" and _archers([e.name for e in brief.enemies if e.archetype in SHOOTER_ARCHETYPES]):
            return "arrow"
        return "bullet"
    if name == "Slash":
        return "slash"
    if name == "Lair":
        return "portal"
    if "Base" in comps:
        return "exit"
    if "TowerBrain" in comps:
        return "turret"
    if "Projectile" in comps:
        return "arrow" if words & ARROW_WORDS else "bullet"
    if name in ("Door", "Cage"):
        return "door"
    if name == "CageKey":
        return "key"
    if name == "XpGem":
        return "gem"
    if "TriggerZone" in comps and name not in ("Exit",):
        return "hero"  # someone to rescue
    if name == "Exit":
        return "exit" if platformer else "portal"
    if name == "Portal":
        return "portal"
    if name == "Spikes":
        return "spikes"
    if name == "HealthPack":
        return "heart"
    if "Collectible" in comps:
        for keys, kind in PICKUP_KINDS:
            if words & keys:
                return kind
        return "orb"
    if archetype == "turret":
        return "turret"
    for keys, kind in ((ROBOT_WORDS, "robot"), (DRAGON_WORDS, "dragon"), (FLYER_WORDS, "flyer"), (FLAME_WORDS, "flame"),
                       (GHOST_WORDS, "ghost"), (SPIDER_WORDS, "spider"),
                       (SNAKE_WORDS, "snake"), (BEAST_WORDS, "beast"),
                       (PLANT_WORDS, "plant"), (MUSHROOM_WORDS, "mushroom"), (REAPER_WORDS, "reaper"), (SNAIL_WORDS, "snail"),
                       (ALIEN_WORDS, "alien"), (HUMANOID_WORDS, "hero"),
                       (HOPPER_WORDS, "hopper"), (BUG_WORDS, "bug" if not platformer else "slime")):
        if words & keys:
            return kind
    return {"walker": "slime", "hopper": "hopper", "chaser": "slime" if platformer else "bug",
            "shooter": "robot"}.get(archetype or "", "slime")


def _render(lay: levelgen.Layout, grid: dict[tuple[int, int], str]) -> list[str]:
    rows = []
    for y in range(lay.height):
        row = []
        for x in range(lay.width):
            c = (x, y)
            if c in grid:
                row.append(grid[c])
            elif lay.tiles.get(c) == "solid":
                row.append("#")
            elif lay.tiles.get(c) == "oneway":
                row.append("=")
            else:
                row.append(".")
        rows.append("".join(row).rstrip(".") or ".")
    return rows


def _q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"
