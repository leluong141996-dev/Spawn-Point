"""The v5 wire format: what the model reads and writes, one small schema per genre.

`GameBrief` stays the canonical design (the assembler, sessions and tests use it). The model, though, no longer fills
one big form with 20 fields of which most make no sense for the genre at hand: it writes `{"genre": ..., ...}` and
only that genre's fields exist (a discriminated union, so guided decoding cannot invent `crops` for a platformer).
That makes the prompts and the answers much shorter and removes a whole class of cross-genre mistakes.

    parse_wire(raw)  -> GameBrief   (lenient: unknown keys are ignored, so GameBrief-shaped answers parse too)
    to_wire(brief)   -> dict        (the genre's fields only, every field written out: the training target)
    wire_schema()    -> JSON schema for guided decoding
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .brief import GameBrief, Palette, Speed

Length = Literal["short", "medium", "long"]
ArtStyle = Literal["pixel", "cartoon"]


class _W(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- shared pieces ----------------------------------------------------------------------------

class _Look(_W):
    genre: str  # declared here so it comes first in every genre (subclasses narrow it to one value)
    title: str = Field(max_length=40)
    palette: Palette = "night"
    art_style: ArtStyle = "pixel"


class _Pickup(_W):
    name: str = Field(default="Coin", max_length=24)
    count: int = Field(default=10, ge=0, le=60)


# Enemies: the same fields as EnemyBrief, only the archetypes a genre has.
class PlatformerEnemy(_W):
    name: str = Field(max_length=24)
    archetype: Literal["walker", "hopper", "chaser", "shooter", "turret"]
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class TopdownEnemy(_W):
    name: str = Field(max_length=24)
    archetype: Literal["chaser", "shooter", "turret"]
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class FarmPest(_W):  # a walker eats crops, a chaser bites the farmer
    name: str = Field(max_length=24)
    archetype: Literal["walker", "chaser"]
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class Invader(_W):  # tower defense: slow ones are big and tough, fast ones come in swarms
    name: str = Field(max_length=24)
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class ShmupEnemy(_W):  # drifter: straight, weaver: sine wave, diver: dives at you, gunship: stops and shoots
    name: str = Field(max_length=24)
    archetype: Literal["drifter", "weaver", "diver", "gunship"]
    count: int = Field(default=3, ge=0, le=20)
    health: int = Field(default=1, ge=1, le=20)
    speed: Speed = "normal"


class PlatformerPlayer(_W):
    character: str = Field(default="Hero", max_length=24)
    abilities: list[Literal["double_jump", "dash", "stomp", "shoot", "sword"]] = Field(default_factory=list, max_length=4)
    jump_tiles: float = Field(default=3.5, ge=1.5, le=8.0)
    speed: Speed = "normal"
    health: int = Field(default=3, ge=1, le=10)


class TopdownPlayer(_W):
    character: str = Field(default="Hero", max_length=24)
    abilities: list[Literal["dash", "shoot", "sword"]] = Field(default_factory=list, max_length=3)
    speed: Speed = "normal"
    health: int = Field(default=3, ge=1, le=10)


# --- the genres -------------------------------------------------------------------------------

class PlatformerW(_Look):
    genre: Literal["platformer"]
    player: PlatformerPlayer = Field(default_factory=PlatformerPlayer)
    enemies: list[PlatformerEnemy] = Field(default_factory=list, max_length=4)
    collectible: _Pickup = Field(default_factory=_Pickup)
    health_pickups: int = Field(default=1, ge=0, le=10)
    goal: Literal["reach_exit", "collect_all", "collect_all_then_exit", "defeat_all", "score_target", "survive",
                  "rescue"] = "collect_all_then_exit"
    score_target: int = Field(default=100, ge=10, le=10000)
    survive_seconds: int = Field(default=60, ge=10, le=600)
    rescue_target: str = Field(default="Mom", max_length=24)
    hazards: list[Literal["spikes", "pits"]] = Field(default_factory=list, max_length=2)
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)
    feel: Literal["snappy", "floaty", "heavy"] = "snappy"
    juice: Literal["subtle", "normal", "wild"] = "normal"


class TopdownW(_Look):
    genre: Literal["topdown"]
    player: TopdownPlayer = Field(default_factory=TopdownPlayer)
    enemies: list[TopdownEnemy] = Field(default_factory=list, max_length=4)
    collectible: _Pickup = Field(default_factory=_Pickup)
    health_pickups: int = Field(default=1, ge=0, le=10)
    goal: Literal["collect_all", "collect_all_then_exit", "defeat_all", "score_target", "survive"] = "collect_all"
    score_target: int = Field(default=100, ge=10, le=10000)
    survive_seconds: int = Field(default=60, ge=10, le=600)
    hazards: list[Literal["spikes"]] = Field(default_factory=list, max_length=1)
    level_ups: bool = False
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)
    feel: Literal["snappy", "floaty", "heavy"] = "snappy"
    juice: Literal["subtle", "normal", "wild"] = "normal"


class BubbleW(_Look):
    genre: Literal["bubble"]
    character: str = Field(default="Hero", max_length=24)
    item: str = Field(default="Egg", max_length=24)
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)


class FarmW(_Look):
    genre: Literal["farm"]
    character: str = Field(default="Farmer", max_length=24)
    abilities: list[Literal["dash", "sword"]] = Field(default_factory=list, max_length=2)
    crops: list[str] = Field(default_factory=list, max_length=3)
    enemies: list[FarmPest] = Field(default_factory=list, max_length=4)
    score_target: int = Field(default=100, ge=10, le=10000)
    survive_seconds: int = Field(default=60, ge=10, le=600)
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)


class TowerDefenseW(_Look):
    genre: Literal["tower_defense"]
    enemies: list[Invader] = Field(default_factory=list, max_length=4)
    towers: list[str] = Field(default_factory=list, max_length=3)
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)


class ShmupW(_Look):
    genre: Literal["shmup"]
    ship: str = Field(default="Ship", max_length=24)
    enemies: list[ShmupEnemy] = Field(default_factory=list, max_length=4)
    boss: str = Field(default="", max_length=24)
    goal: Literal["defeat_boss", "score_target", "survive"] = "defeat_boss"
    score_target: int = Field(default=100, ge=10, le=10000)
    survive_seconds: int = Field(default=60, ge=10, le=600)
    health: int = Field(default=3, ge=1, le=10)
    speed: Speed = "normal"
    length: Length = "medium"
    difficulty: int = Field(default=2, ge=1, le=5)
    juice: Literal["subtle", "normal", "wild"] = "normal"


WIRE_BY_GENRE: dict[str, type[_Look]] = {"platformer": PlatformerW, "topdown": TopdownW, "bubble": BubbleW, "farm": FarmW,
                                         "tower_defense": TowerDefenseW, "shmup": ShmupW}
GENRES = tuple(WIRE_BY_GENRE)
_UNION = TypeAdapter(Annotated[Union[tuple(WIRE_BY_GENRE.values())], Field(discriminator="genre")])  # type: ignore[valid-type]


# --- conversion -------------------------------------------------------------------------------

def to_wire(brief: GameBrief) -> dict:
    """The genre's fields only, every one written out (the shape of a training target)."""
    d = brief.model_dump()
    g = brief.genre
    if g == "bubble":
        d.update(character=brief.player.character, item=brief.collectible.name)
    elif g == "farm":
        d.update(character=brief.player.character, abilities=list(brief.player.abilities))
    elif g == "shmup":
        d.update(ship=brief.player.character, health=brief.player.health, speed=brief.player.speed)
    return WIRE_BY_GENRE[g].model_validate(d).model_dump()


def from_wire(wire: _Look) -> GameBrief:
    d = wire.model_dump()
    g = d["genre"]
    if g == "bubble":
        d = {**{k: d[k] for k in ("title", "genre", "palette", "art_style", "length", "difficulty")},
             "player": {"character": d["character"]}, "collectible": {"name": d["item"]}}
    elif g == "farm":
        d["player"] = {"character": d.pop("character"), "abilities": d.pop("abilities")}
    elif g == "tower_defense":
        d["goal"] = "defend"
        d["enemies"] = [{**e, "archetype": "walker"} for e in d["enemies"]]  # invaders all walk the road
    elif g == "shmup":
        d["player"] = {"character": d.pop("ship"), "health": d.pop("health"), "speed": d.pop("speed")}
    return GameBrief.model_validate(d)


def parse_wire(raw: dict) -> GameBrief:
    """A model answer (or a GameBrief-shaped dict) -> GameBrief. Unknown keys are ignored."""
    if not isinstance(raw, dict) or raw.get("genre") not in WIRE_BY_GENRE:
        raise ValueError(f"expected an object whose genre is one of {', '.join(GENRES)}")
    return from_wire(WIRE_BY_GENRE[raw["genre"]].model_validate(raw))


# --- schemas ----------------------------------------------------------------------------------

def _closed(node):
    """additionalProperties: false on every object, and no OpenAPI-only `discriminator` keyword."""
    if isinstance(node, dict):
        node.pop("discriminator", None)
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
        for v in node.values():
            _closed(v)
    elif isinstance(node, list):
        for v in node:
            _closed(v)
    return node


def wire_schema() -> dict:
    """JSON schema for the model's answer: one of the genre schemas, picked by `genre`."""
    schema = _closed(_UNION.json_schema())
    return {"type": "object", **schema}  # some servers want an object at the root


def wire_tweak_schema() -> dict:
    schema = wire_schema()
    defs = schema.pop("$defs", {})
    return {"type": "object", "$defs": defs, "properties": {"brief": schema, "new_level": {"type": "boolean"}},
            "required": ["brief", "new_level"], "additionalProperties": False}
