"""GameBrief: the small, enumerated design an LLM fills in, plus normalization of weak-model output."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Genre = Literal["platformer", "topdown"]
Palette = Literal["night", "forest", "desert", "neon", "candy", "ocean", "lava", "snow"]
Ability = Literal["double_jump", "dash", "stomp", "shoot"]
Archetype = Literal["walker", "hopper", "chaser", "shooter", "turret"]
Speed = Literal["slow", "normal", "fast"]
DEFAULT_SCORE_TARGET = 100

# Points per defeated enemy, by archetype (the assembler writes them as rules).
ENEMY_POINTS = {"walker": 5, "hopper": 10, "chaser": 10, "shooter": 25, "turret": 20}

Goal = Literal["reach_exit", "collect_all", "collect_all_then_exit", "defeat_all", "score_target", "survive"]
Hazard = Literal["spikes", "pits"]

ARCHETYPES_BY_GENRE: dict[str, tuple[str, ...]] = {
    "platformer": ("walker", "hopper", "chaser", "shooter", "turret"),
    "topdown": ("chaser", "shooter", "turret"),
}
# What an archetype becomes when it does not exist in the genre.
ARCHETYPE_FALLBACK = {"topdown": {"walker": "chaser", "hopper": "chaser"}}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlayerBrief(_Model):
    character: str = Field(default="Hero", max_length=24, description="what the player is, e.g. Ninja, Fox, Robot")
    shape: Literal["capsule", "circle", "rect"] = "capsule"
    abilities: list[Ability] = Field(default_factory=list, max_length=4)
    jump_tiles: float = Field(default=3.5, ge=1.5, le=8.0, description="jump height in tiles (platformer)")
    speed: Speed = "normal"
    health: int = Field(default=3, ge=1, le=10)


class EnemyBrief(_Model):
    name: str = Field(max_length=24)
    archetype: Archetype
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class CollectibleBrief(_Model):
    name: str = Field(default="Coin", max_length=24)
    count: int = Field(default=10, ge=0, le=60)


class GameBrief(_Model):
    title: str = Field(max_length=40)
    genre: Genre
    palette: Palette = "night"
    player: PlayerBrief = Field(default_factory=PlayerBrief)
    enemies: list[EnemyBrief] = Field(default_factory=list, max_length=4)
    collectible: CollectibleBrief = Field(default_factory=CollectibleBrief)
    health_pickups: int = Field(default=1, ge=0, le=10)
    goal: Goal = "collect_all_then_exit"
    score_target: int = Field(default=DEFAULT_SCORE_TARGET, ge=10, le=10000)
    survive_seconds: int = Field(default=60, ge=10, le=600)
    hazards: list[Hazard] = Field(default_factory=list, max_length=2)
    length: Literal["short", "medium", "long"] = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)
    feel: Literal["snappy", "floaty", "heavy"] = "snappy"
    juice: Literal["subtle", "normal", "wild"] = "normal"
    intro: str = Field(default="", max_length=80)


def json_schema() -> dict:
    """JSON schema for guided decoding (vLLM / OpenAI structured outputs)."""
    return GameBrief.model_json_schema()


# --- normalization ----------------------------------------------------------------------------

RESERVED_NAMES = {
    "Player", "Bullet", "EnemyBullet", "Exit", "Door", "HealthPack", "Spikes", "Portal",
    "GameState", "Game", "World", "FX", "Sfx", "SP", "Entity", "Visual", "Shape", "Main", "Tiles",
    "Entities", "Rules", "HUD", "Camera",
}
COMPONENT_NAMES = {
    "Health", "Hitbox", "Hurtbox", "Weapon", "Projectile", "Collectible", "TriggerZone", "Spawner",
    "Gate", "PlayerInput", "PatrolAI", "ChaseAI", "PlatformerMovement", "TopDownMovement", "Aim",
    "Juice", "Stomp",
}
_IRREGULAR = {"enemies": "enemy", "bodies": "body", "ponies": "pony", "berries": "berry", "cherries": "cherry",
              "flies": "fly", "mice": "mouse", "geese": "goose", "children": "child", "leaves": "leaf",
              "knives": "knife", "wolves": "wolf", "elves": "elf", "zombies": "zombie", "lives": "life"}
_KEEP_S = ("ss", "us", "is", "os")


def pascal_singular(raw: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", raw or "")
    if not words:
        return fallback
    last = words[-1].lower()
    if last in _IRREGULAR:
        words[-1] = _IRREGULAR[last]
    elif last.endswith("ies") and len(last) > 4:
        words[-1] = words[-1][:-3] + "y"
    elif last.endswith("s") and not last.endswith(_KEEP_S) and len(last) > 3:
        words[-1] = words[-1][:-1]
    name = "".join(w[:1].upper() + w[1:] for w in words)[:24]
    return name if name[:1].isalpha() else fallback


def normalize(brief: GameBrief) -> tuple[GameBrief, list[str]]:
    """Repair typical weak-model mistakes. Returns a new brief and human-readable notes."""
    b = brief.model_copy(deep=True)
    notes: list[str] = []
    taken = set(RESERVED_NAMES) | set(COMPONENT_NAMES)

    def unique(name: str, fallback: str, what: str) -> str:
        fixed = pascal_singular(name, fallback)
        if fixed in taken:
            fixed = fixed + ("Foe" if what == "enemy" else "Item")
        base, i = fixed, 2
        while fixed in taken:
            fixed, i = f"{base}{i}", i + 1
        if fixed != name:
            notes.append(f"renamed {what} '{name}' -> '{fixed}'")
        taken.add(fixed)
        return fixed

    b.collectible.name = unique(b.collectible.name, "Coin", "collectible")
    b.player.character = pascal_singular(b.player.character, "Hero")

    allowed = ARCHETYPES_BY_GENRE[b.genre]
    enemies = []
    seen_names: set[str] = set()
    for e in b.enemies:
        if e.count == 0:
            notes.append(f"dropped enemy '{e.name}' with count 0")
            continue
        if e.archetype not in allowed:
            new = ARCHETYPE_FALLBACK.get(b.genre, {}).get(e.archetype, allowed[0])
            notes.append(f"{e.name}: archetype '{e.archetype}' does not exist in {b.genre}; using '{new}'")
            e.archetype = new
        if pascal_singular(e.name, "Enemy").lower() in seen_names:
            notes.append(f"merged duplicate enemy '{e.name}'")
            continue
        seen_names.add(pascal_singular(e.name, "Enemy").lower())
        e.name = unique(e.name, "Enemy", "enemy")
        enemies.append(e)
    b.enemies = enemies

    b.player.abilities = list(dict.fromkeys(b.player.abilities))
    if b.genre == "topdown":
        dropped = [a for a in b.player.abilities if a in ("double_jump", "stomp")]
        if dropped:
            notes.append(f"top-down has no jumping; ignored {', '.join(dropped)}")
            b.player.abilities = [a for a in b.player.abilities if a not in dropped]
        if "pits" in b.hazards:
            b.hazards = [h for h in b.hazards if h != "pits"]
            notes.append("top-down has no pits; ignored")
        if not b.enemies and "shoot" not in b.player.abilities and b.goal in ("defeat_all",):
            pass
    b.hazards = list(dict.fromkeys(b.hazards))

    total_enemies = sum(e.count for e in b.enemies)
    if b.goal in ("collect_all", "collect_all_then_exit") and b.collectible.count == 0:
        b.collectible.count = 8
        notes.append(f"goal '{b.goal}' needs pickups; added 8 {b.collectible.name}s")
    if b.goal == "defeat_all":
        if total_enemies == 0:
            b.goal = "reach_exit" if b.genre == "platformer" else "collect_all"
            notes.append(f"goal 'defeat_all' without enemies; using '{b.goal}'")
        elif b.genre == "topdown" and "shoot" not in b.player.abilities:
            b.player.abilities.append("shoot")
            notes.append("defeating enemies in top-down needs shooting; gave the player 'shoot'")
        elif b.genre == "platformer" and not {"stomp", "shoot"} & set(b.player.abilities):
            b.player.abilities.append("stomp")
            notes.append("defeating enemies needs an attack; gave the player 'stomp'")
    if b.goal == "collect_all" and b.genre == "topdown" and b.collectible.count == 0:
        b.collectible.count = 10
    if b.goal == "score_target":
        reachable = b.collectible.count + total_enemies * 10
        if reachable < b.score_target and b.genre == "platformer":
            b.score_target = max(10, reachable - reachable % 5)
            notes.append(f"score_target lowered to {b.score_target} (the level holds only that many points)")
        elif b.genre == "topdown" and b.enemies and b.score_target == DEFAULT_SCORE_TARGET:
            # Enemies keep spawning in top-down arenas: an unspecified target should take a real fight, not
            # five shots. A target the player asked for is kept as it is.
            per_kill = max(ENEMY_POINTS.get(e.archetype, 10) for e in b.enemies)
            floor = per_kill * (8 + 4 * b.difficulty)
            if b.score_target < floor:
                if b.intro == f"Score {b.score_target} points!":
                    b.intro = ""  # the default intro names the old target
                b.score_target = floor
                notes.append(f"score_target raised to {floor} ({8 + 4 * b.difficulty} kills at difficulty {b.difficulty})")
    if not b.intro:
        b.intro = _default_intro(b)
    return b, notes


def _default_intro(b: GameBrief) -> str:
    c = b.collectible.name
    return {
        "reach_exit": "Reach the exit!",
        "collect_all": f"Collect every {c}!",
        "collect_all_then_exit": f"Collect every {c} to open the door!",
        "defeat_all": "Defeat every enemy!",
        "score_target": f"Score {b.score_target} points!",
        "survive": f"Survive {b.survive_seconds} seconds!",
    }[b.goal]
