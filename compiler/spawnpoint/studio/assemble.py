"""Brief -> game graph, layer by layer. Fully deterministic for a given (brief, seed)."""

from __future__ import annotations

import math
import os
import random
import re
from typing import Any

from ..level import jump_model
from ..sprites.generate import features_for
from . import levelgen
from .brief import EnemyBrief, GameBrief

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

SPEED = {"slow": 0.75, "normal": 1.0, "fast": 1.3}
ENEMY_POINTS = {"walker": 5, "hopper": 10, "chaser": 10, "shooter": 25, "turret": 20}
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

    # -- top level ---------------------------------------------------------------------------
    def graph(self) -> dict:
        b = self.b
        lay = self._layout()
        grid: dict[tuple[int, int], str] = {}
        self._player(grid, lay)
        if self.layer >= 1:
            self._goal(grid, lay)
            self._enemies(grid, lay)
            self._pickups(grid, lay)
            self._hazards(grid, lay)
        intro = b.intro if self.layer >= 1 else "Layer 0: try the controls!"
        self.rules.insert(0, {"on": "Game.ready", "do": [f"message({_q(intro)})"]})
        if self.layer >= 2:
            self._polish()
        return {
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
        }

    def _layout(self) -> levelgen.Layout:
        b = self.b
        if self.platformer:
            length, up, across, pits = _level_args(b)
            return levelgen.platformer(self.seed, length, up, across, pits, b.difficulty,
                                       door=b.goal == "collect_all_then_exit", chunks=self.chunks)
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
            self.rules.append({"on": "GameState.score_changed", "if": f"score >= {b.score_target}", "do": ["win()"]})
        elif b.goal == "survive":
            n = b.survive_seconds
            self.rules.append({"on": "GameState.second_passed", "if": f"event.seconds == {max(n - 10, 1)}",
                               "do": ["message('10 seconds left!')"]})
            self.rules.append({"on": "GameState.second_passed", "if": f"event.seconds >= {n}", "do": ["win()"]})
        if not self.platformer and b.goal in ("score_target", "survive"):
            self._portals(grid, lay)

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
            self.rules.append({"on": f"{e.name}.died", "do": [f"add_score({ENEMY_POINTS[e.archetype]})"]})

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
                                   "shape": {"type": "circle", "size": [14, 14], "color": self.pal["pickup"]},
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
            ent["juice"] = dict(params)


    def _sprites(self) -> None:
        """Layer 2 art pass: placeholders become generated pixel-art sprites (collision follows)."""
        archetypes = {e.name: e.archetype for e in self.b.enemies}
        ai_art = self.ai_art
        for name, ent in self.entities.items():
            kind = sprite_kind(name, ent, archetypes.get(name), self.b, self.platformer)
            color = ent["shape"]["color"]
            if ai_art:
                subject = self.b.player.character if name == "Player" else name
                words = " ".join(re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", subject)).lower()
                ent["sprite"] = {"ai": {"prompt": f"{words}, {self.b.palette} color palette, game: {self.b.title}",
                                        "kind": kind, "color": color, "seed": self.seed}}
            else:
                gen: dict[str, Any] = {"kind": kind, "color": color, "seed": self.seed}
                if name == "Player":
                    gen["features"] = features_for(self.b.player.character)
                ent["sprite"] = {"generate": gen}
            del ent["shape"]


HUMANOID_WORDS = {"goblin", "zombie", "knight", "skeleton", "orc", "ninja", "soldier", "pirate", "bandit",
                  "wizard", "witch", "mage", "guard", "thief", "samurai", "elf", "troll", "vampire", "mummy"}
FLYER_WORDS = {"bat", "bird", "crow", "ghost", "spirit", "wasp", "bee", "fly", "dragon", "owl", "eagle"}
ROBOT_WORDS = {"robot", "bot", "droid", "mech", "drone", "android", "cyborg", "machine"}
BUG_WORDS = {"bug", "beetle", "ant", "spider", "scorpion", "roach", "crab", "insect"}
HOPPER_WORDS = {"frog", "toad", "bunny", "rabbit", "kangaroo"}
PICKUP_KINDS = (({"coin", "gold", "money", "cash", "token"}, "coin"), ({"star", "starlight"}, "star"),
                ({"gem", "crystal", "diamond", "jewel", "ruby", "emerald", "shard", "sapphire"}, "gem"),
                ({"heart", "life", "health"}, "heart"))


def _words(name: str) -> set[str]:
    import re
    return {w.lower() for w in re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)}


def sprite_kind(name: str, ent: dict, archetype: str | None, brief: GameBrief, platformer: bool) -> str:
    words = _words(name)
    comps = ent.get("components", {})
    if name == "Player":
        return "hero"
    if name in ("Bullet", "EnemyBullet"):
        return "bullet"
    if name == "Door":
        return "door"
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
