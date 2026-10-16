"""Brief -> game graph, layer by layer. Fully deterministic for a given (brief, seed)."""

from __future__ import annotations

import math
import os
import random
import re
from typing import Any

from ..level import jump_model
from ..sprites import palettes
from ..sprites.generate import features_for
from . import levelgen
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
             ai_art: bool = False) -> dict:
    """`chunks` pins the platformer level layout (to keep the map across tweaks); `ai_art` asks for
    image-model sprites in layer 2 (generated ones are the fallback)."""
    return _Assembler(brief, layer, seed, chunks, ai_art).graph()


class _Assembler:
    def __init__(self, brief: GameBrief, layer: int, seed: int, chunks: list[str] | None = None,
                 ai_art: bool = False):
        self.ai_art = ai_art
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
            if self.b.art_style != "pixel":
                g["settings"]["art_style"] = self.b.art_style
            else:  # pixel art gets the classic palette that suits the theme
                g["settings"]["pixel_palette"] = palettes.THEME_PALETTE[self.b.palette]
                g["settings"]["scenery"] = self.b.palette
            if self.b.genre == "shmup":
                g["settings"]["scenery"] = "space"  # scrolling stars, whatever the art style
        return g

    # -- farm --------------------------------------------------------------------------------
    def _farm_graph(self) -> dict:
        b, pal = self.b, self.pal
        d = b.difficulty
        lay = levelgen.farm(self.seed, b.length)
        target, minutes = self._farm_target(), self._farm_seconds()
        crops = ";".join(f"{c}|{pickup_color(c, FARM_CROP_PAL)}|{grow}|{price}"
                         for c, (grow, price) in zip(b.crops, FARM_CROPS))
        comps: dict[str, dict] = {"TopDownMovement": {"max_speed": round(210 * SPEED[b.player.speed]),
                                                       "acceleration": 2200}, "PlayerInput": {},
                                  "Farmer": {"crops": crops, "reach": 44, "basket_size": 12}}
        if "dash" in b.player.abilities:
            comps["TopDownMovement"]["dash_speed"] = 640.0
        self.entities["Player"] = {"shape": {"type": "circle", "size": [24, 24], "color": pal["player"]},
                                   "components": comps}
        chasers = [e for e in b.enemies if e.archetype in ("chaser", "shooter")]
        if chasers:  # something hunts the farmer, so the farmer can get hurt
            comps["Health"] = {"max_health": b.player.health, "invincibility_time": 1.0}
            comps["Hurtbox"] = {}
        if b.enemies:
            self._melee_or_gust(comps)
        self.entities["Plot"] = {"body": "area", "juice": "none", "shape": {"type": "none", "size": [30, 30]},
                                 "components": {"FarmPlot": {"water_seconds": round(7.0 - 0.5 * d, 1), "size": 30}}}
        self.entities["Stall"] = {"body": "area", "juice": "none",
                                  "shape": {"type": "rect", "size": [64, 48], "color": "#00000000"},
                                  "components": {"Market": {"width": 64, "color": pal["enemies"][0]}}}
        legend = {"#": "solid", "P": "Player", "f": "Plot", "M": "Stall"}
        cells: dict[tuple[int, int], str] = {lay.player: "P", lay.market: "M"}
        for c in lay.plots:
            cells[c] = "f"
        for c in lay.rocks:
            cells[c] = "#"
        for i, e in enumerate(b.enemies[:3]):
            self._pest(e, i)
            nest = f"{e.name}Nest"
            k = SPEED[e.speed]
            self.entities[nest] = {
                "body": "static", "juice": "none", "shape": {"type": "none", "size": [4, 4]},
                "components": {"Spawner": {"entity": e.name, "interval": round(14.0 / (0.6 + 0.2 * d) / k, 1),
                                           "interval_ramp": 0.95, "min_interval": 5.0,
                                           "start_delay": 20.0 + 15 * i, "max_alive": max(1, min(e.count, 6))}}}
            legend["nqr"[i]] = nest
            cells[lay.nests[i % len(lay.nests)]] = "nqr"[i]
        rows = []
        for y in range(lay.height):
            rows.append("".join("#" if x in (0, lay.width - 1) or y in (0, lay.height - 1)
                                else cells.get((x, y), ".") for x in range(lay.width)).rstrip("."))
        intro = b.intro or f"Earn ${target} before sunset!"
        if intro in (f"Score {b.score_target} points!", f"Earn ${b.score_target} before sunset!"):
            intro = f"Earn ${target} before sunset!"  # the default intro follows the real target
        rules = [
            {"on": "Game.ready", "do": [f"set_var('time_limit', {minutes})", "set_var('score_label', 'MONEY')",
                                        f"message({_q(intro + ' Space: plant, water, harvest')})"]},
            {"on": "GameState.score_changed", "if": f"score >= {target}", "do": ["message('What a harvest!')", "win()"]},
            {"on": "GameState.second_passed", "if": f"event.seconds >= {minutes}",
             "do": ["message('The sun has set')", "lose()"]},
        ]
        if b.enemies:
            pest = b.enemies[0].name
            rules.append({"on": "GameState.second_passed", "if": "event.seconds == 20",
                          "do": [f"message({_q(pest + 's are coming! Chase them off with X')})"]})
            for e in b.enemies[:3]:
                rules.append({"on": f"{e.name}.died", "do": ["add_score(2)"]})
        self.rules = rules
        if self.layer >= 2:
            self._polish()
        bg = FARM_GROUND.get(b.palette, FARM_GROUND["forest"])
        return {"spawnpoint": 1, "name": b.title or "Untitled", "genre": "topdown",
                "settings": {"tile_size": TILE, "lives": 1, "seed": self.seed, "zoom": 1.25, "background": bg,
                             "tiles": {"solid": {"color": "#8a5a3b", "top": "#c2a476"}}},
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
            if ent["shape"].get("type") == "none" or "Market" in ent.get("components", {}):
                continue  # invisible helpers (survivor nests, plots, roads) and self-drawn stalls
            kind = sprite_kind(name, ent, archetypes.get(name), self.b, self.platformer)
            color = ent["shape"]["color"]
            if ai_art:
                subject = self.b.player.character if name == "Player" else name
                words = " ".join(re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", subject)).lower()
                ent["sprite"] = {"ai": {"prompt": f"{words}, {self.b.palette} color palette, game: {self.b.title}",
                                        "kind": kind, "color": color, "seed": self.seed}}
            else:
                gen: dict[str, Any] = {"kind": kind, "color": color, "seed": self.seed}
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
                  "wizard", "witch", "mage", "guard", "thief", "samurai", "elf", "troll", "vampire", "mummy"}
FLYER_WORDS = {"bat", "bird", "crow", "ghost", "spirit", "wasp", "bee", "fly", "dragon", "owl", "eagle"}
ROBOT_WORDS = {"robot", "bot", "droid", "mech", "drone", "android", "cyborg", "machine"}
BUG_WORDS = {"bug", "beetle", "ant", "spider", "scorpion", "roach", "crab", "insect"}
HOPPER_WORDS = {"frog", "toad", "bunny", "rabbit", "kangaroo"}
SHIP_WORDS = {"ship", "fighter", "jet", "plane", "bomber", "gunship", "warship", "cruiser", "destroyer", "battleship",
              "raider", "falcon", "viper", "interceptor", "starfighter", "rocket", "dreadnought", "carrier"}
UFO_WORDS = {"ufo", "saucer", "alien", "drone", "probe", "pod", "orb", "mine", "scout", "invader"}
PICKUP_KINDS = (({"coin", "gold", "money", "cash", "token"}, "coin"), ({"star", "starlight"}, "star"),
                ({"gem", "crystal", "diamond", "jewel", "ruby", "emerald", "shard", "sapphire"}, "gem"),
                ({"heart", "life", "health"}, "heart"))


def _ordered_words(name: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)]


def _words(name: str) -> set[str]:
    return set(_ordered_words(name))


def sprite_kind(name: str, ent: dict, archetype: str | None, brief: GameBrief, platformer: bool) -> str:
    words = _words(name)
    comps = ent.get("components", {})
    if brief.genre == "shmup":
        if name == "Player" or name == brief.boss or archetype == "gunship" or words & SHIP_WORDS:
            return "ship" if not words & UFO_WORDS else "ufo"
        if words & UFO_WORDS or archetype in ("drifter", "weaver", "diver"):
            return "ufo"
    if name == "Player":
        return "hero"
    if name in ("Bullet", "EnemyBullet", "Gust"):
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
        return "bullet"
    if name in ("Door", "Cage"):
        return "door"
    if name in ("CageKey", "XpGem"):
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
    for keys, kind in ((ROBOT_WORDS, "robot"), (FLYER_WORDS, "flyer"), (HUMANOID_WORDS, "hero"),
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
