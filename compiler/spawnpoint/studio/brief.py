"""GameBrief: the small, enumerated design an LLM fills in, plus normalization of weak-model output."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Genre = Literal["platformer", "topdown", "bubble", "farm", "tower_defense", "shmup"]
Palette = Literal["night", "forest", "desert", "neon", "candy", "ocean", "lava", "snow"]
Ability = Literal["double_jump", "dash", "stomp", "shoot", "sword"]
Archetype = Literal["walker", "hopper", "chaser", "shooter", "turret", "drifter", "weaver", "diver", "gunship"]
Speed = Literal["slow", "normal", "fast"]
DEFAULT_SCORE_TARGET = 100

# Points per defeated enemy, by archetype (the assembler writes them as rules).
ENEMY_POINTS = {"walker": 5, "hopper": 10, "chaser": 10, "shooter": 25, "turret": 20,
                "drifter": 5, "weaver": 10, "diver": 15, "gunship": 25}

Goal = Literal["reach_exit", "collect_all", "collect_all_then_exit", "defeat_all", "score_target", "survive",
               "rescue", "clear_board", "defend", "defeat_boss"]
Hazard = Literal["spikes", "pits"]

ARCHETYPES_BY_GENRE: dict[str, tuple[str, ...]] = {
    "platformer": ("walker", "hopper", "chaser", "shooter", "turret"),
    "topdown": ("chaser", "shooter", "turret"),
    "bubble": (),
    # Farm pests and tower-defense invaders have their own behaviour; the archetype only flavours them.
    "farm": ("walker", "hopper", "chaser", "shooter", "turret"),
    "tower_defense": ("walker", "hopper", "chaser", "shooter", "turret"),
    # Side-scrolling space shooter: how an enemy flies (straight / sine wave / dives at you / stops and shoots).
    "shmup": ("drifter", "weaver", "diver", "gunship"),
}
# What an archetype becomes when it does not exist in the genre.
ARCHETYPE_FALLBACK = {"topdown": {"walker": "chaser", "hopper": "chaser"},
                      "shmup": {"walker": "drifter", "hopper": "weaver", "chaser": "diver", "shooter": "gunship",
                                "turret": "gunship"}}


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
    rescue_target: str = Field(default="Mom", max_length=24, description="who the player saves (goal rescue)")
    level_ups: bool = Field(default=False, description="XP gems and an upgrade pick each level (top-down survivor)")
    boss: str = Field(default="", max_length=24, description="the end boss's name (shmup; empty = no boss)")
    crops: list[str] = Field(default_factory=list, max_length=3, description="what the farm grows (farm)")
    towers: list[str] = Field(default_factory=list, max_length=3, description="towers the player builds (tower_defense)")
    art_style: Literal["pixel", "cartoon"] = "pixel"
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
    "Entities", "Rules", "HUD", "Camera", "Cage", "CageKey", "XpGem", "Slash", "Plot", "Stall", "Gust",
    "Road", "Pad", "Commander", "Lair", "Castle", "BossGate", "PowerUp", "Starfield",
}
COMPONENT_NAMES = {
    "Health", "Hitbox", "Hurtbox", "Weapon", "Projectile", "Collectible", "TriggerZone", "Spawner",
    "Gate", "PlayerInput", "PatrolAI", "ChaseAI", "PlatformerMovement", "TopDownMovement", "Aim",
    "Juice", "Stomp", "BubbleBoard", "Experience", "XpOrb", "LevelUpMenu", "FarmPlot", "Farmer", "Market",
    "CropPest", "Base", "GroundPatch", "PathFollower", "TowerBrain", "TowerBuilder", "TowerSlot", "WaveSpawner",
    "Animator", "FlightPath", "ShmupShip", "HealthBar",
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
            fixed = fixed + {"enemy": "Foe", "boss": "Boss"}.get(what, "Item")
        base, i = fixed, 2
        while fixed in taken:
            fixed, i = f"{base}{i}", i + 1
        if fixed != name:
            notes.append(f"renamed {what} '{name}' -> '{fixed}'")
        taken.add(fixed)
        return fixed

    b.collectible.name = unique(b.collectible.name, "Coin", "collectible")
    b.player.character = pascal_singular(b.player.character, "Hero")

    # Genre-specific goals and features.
    if b.genre == "bubble":
        if b.goal != "clear_board":
            notes.append(f"bubble shooters are won by clearing the board; goal '{b.goal}' -> 'clear_board'")
            b.goal = "clear_board"
        if b.enemies or b.hazards or b.player.abilities or b.level_ups:
            notes.append("a bubble shooter has no enemies, hazards, abilities or level-ups; dropped them")
        b.enemies, b.hazards, b.player.abilities, b.level_ups = [], [], [], False
        b.health_pickups = 0
        if b.collectible.name == "Coin":  # the default pickup makes no sense as a bubble
            b.collectible.name = "Egg"
    elif b.genre == "shmup":
        if b.goal not in ("defeat_boss", "score_target", "survive"):
            notes.append(f"shooters are won by beating the boss, scoring or surviving; goal '{b.goal}' -> 'defeat_boss'")
            b.goal = "defeat_boss"
        if b.hazards or b.level_ups or b.player.abilities:
            notes.append("a shooter has no hazards, level-ups or abilities; dropped them")
        b.hazards, b.level_ups, b.player.abilities = [], False, []
        b.health_pickups, b.collectible.count = 0, 0
        if not b.enemies:
            b.enemies = [EnemyBrief(name="Drone", archetype="drifter", count=6), EnemyBrief(name="Saucer", archetype="weaver", count=4)]
            notes.append("a shooter needs enemies; added Drones and Saucers")
        if b.goal == "defeat_boss":
            b.boss = b.boss or "Warship"
    elif b.genre == "farm":
        if b.goal != "score_target":
            notes.append(f"farms are won by earning money before sunset; goal '{b.goal}' -> 'score_target'")
            b.goal = "score_target"
        if b.hazards or b.level_ups:
            notes.append("a farm has no hazards or level-ups; dropped them")
        b.hazards, b.level_ups = [], False
        b.player.abilities = [a for a in b.player.abilities if a in ("dash", "sword")]
        b.crops = [pascal_singular(c, "Carrot") for c in b.crops] or ["Carrot", "Tomato", "Pumpkin"]
        b.crops = list(dict.fromkeys(b.crops))
    elif b.genre == "tower_defense":
        if b.goal != "defend":
            notes.append(f"tower defense is won by surviving every wave; goal '{b.goal}' -> 'defend'")
            b.goal = "defend"
        if b.hazards or b.level_ups or b.player.abilities:
            notes.append("in tower defense the towers fight; dropped hazards, level-ups and abilities")
        b.hazards, b.level_ups, b.player.abilities = [], False, []
        b.health_pickups = 0
        b.towers = [pascal_singular(t, "Archer") for t in b.towers] or ["Archer", "Cannon"]
        b.towers = [t if t.endswith("Tower") else t + "Tower" for t in dict.fromkeys(b.towers)]
        b.collectible.count = 0
        if not b.enemies:
            b.enemies = [EnemyBrief(name="Goblin", archetype="walker", count=8)]
            notes.append("tower defense needs invaders; added Goblins")
    elif b.goal == "defend":
        b.goal = "survive"
        notes.append("goal 'defend' is for tower defense; using 'survive'")
    if b.goal == "clear_board" and b.genre != "bubble":
        b.goal = "reach_exit" if b.genre == "platformer" else "score_target"
        notes.append(f"goal 'clear_board' is for bubble shooters; using '{b.goal}'")
    if b.goal == "defeat_boss" and b.genre != "shmup":
        b.goal = "reach_exit" if b.genre == "platformer" else "score_target"
        notes.append(f"goal 'defeat_boss' is for shooters; using '{b.goal}'")
    if b.goal == "rescue" and b.genre != "platformer":
        b.goal = "reach_exit"
        notes.append("rescue missions are platformers here; using 'reach_exit'")
    if b.goal == "rescue":
        b.rescue_target = unique(b.rescue_target, "Mom", "rescue target")
    if b.level_ups and b.genre == "platformer":
        # Level-ups mean a survivor game, and those are top-down: the level-ups are the stronger signal.
        b.genre = "topdown"
        b.player.abilities = [a for a in b.player.abilities if a not in ("double_jump", "stomp")]
        b.hazards = [h for h in b.hazards if h != "pits"]
        if b.goal in ("reach_exit", "collect_all_then_exit", "rescue"):
            b.goal = "survive"
        notes.append("level-ups are a top-down survivor feature; switched the genre to 'topdown'")
    if b.level_ups and b.genre != "topdown":
        b.level_ups = False
        notes.append("level-ups are for top-down games; ignored")
    if b.level_ups and "shoot" not in b.player.abilities:
        b.player.abilities.append("shoot")
        notes.append("level-up games fire on their own; gave the player 'shoot'")

    if b.boss and b.genre != "shmup":
        b.boss = ""
        notes.append("only shooters have a boss; ignored")
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
    if b.genre == "shmup" and b.boss:
        b.boss = unique(b.boss, "Warship", "boss")  # after the enemies, so a clash renames the boss
    if b.genre == "tower_defense":
        b.towers = [unique(t, "ArcherTower", "tower") for t in b.towers]

    b.player.abilities = list(dict.fromkeys(b.player.abilities))
    if "sword" in b.player.abilities and "shoot" in b.player.abilities:
        b.player.abilities.remove("sword")
        notes.append("one weapon per hero: kept 'shoot', dropped 'sword'")
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
        elif b.genre == "topdown" and not {"shoot", "sword"} & set(b.player.abilities):
            b.player.abilities.append("shoot")
            notes.append("defeating enemies in top-down needs shooting; gave the player 'shoot'")
        elif b.genre == "platformer" and not {"stomp", "shoot", "sword"} & set(b.player.abilities):
            b.player.abilities.append("stomp")
            notes.append("defeating enemies needs an attack; gave the player 'stomp'")
    if b.goal == "collect_all" and b.genre == "topdown" and b.collectible.count == 0:
        b.collectible.count = 10
    if not b.intro:
        b.intro = _default_intro(b)
    return b, notes


def _default_intro(b: GameBrief) -> str:
    c = b.collectible.name
    if b.genre == "farm":
        return f"Earn ${b.score_target} before sunset!"
    return {
        "reach_exit": "Reach the exit!",
        "collect_all": f"Collect every {c}!",
        "collect_all_then_exit": f"Collect every {c} to open the door!",
        "defeat_all": "Defeat every enemy!",
        "score_target": f"Score {b.score_target} points!",
        "survive": f"Survive {b.survive_seconds} seconds!",
        "rescue": f"Find the key and save {b.rescue_target}!",
        "clear_board": f"Pop every {c}!",
        "defend": "Build towers and hold the castle!",
        "defeat_boss": f"Destroy the {b.boss or 'boss'}!",
    }[b.goal]
