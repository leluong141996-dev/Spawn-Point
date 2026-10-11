"""Game graph schema (v1). Structural validation only; semantics live in analyze.py."""

from __future__ import annotations

import re
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .diagnostics import Diagnostics, did_you_mean, join_path

HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _check_color(v: str | None) -> str | None:
    if v is not None and not HEX_COLOR.match(v):
        raise ValueError(f"'{v}' is not a hex color like '#29adff'")
    return v


class Shape(_Model):
    type: Literal["rect", "circle", "capsule", "triangle", "spikes", "none"] = "rect"
    size: tuple[float, float] = (28.0, 28.0)
    color: str | None = None

    _color = field_validator("color")(_check_color)

    @field_validator("size")
    @classmethod
    def _positive(cls, v: tuple[float, float]) -> tuple[float, float]:
        if v[0] <= 0 or v[1] <= 0 or v[0] > 1024 or v[1] > 1024:
            raise ValueError("size must be within 1..1024 px")
        return v


class SpriteGenerate(_Model):
    kind: str
    color: str | None = None
    features: list[str] | None = None
    seed: int = 0

    _color = field_validator("color")(_check_color)


class SpriteAI(_Model):
    prompt: str = Field(min_length=1, max_length=200)
    kind: str  # also the pixel size, animations and the fallback when no image provider is available
    color: str | None = None
    seed: int = 0

    _color = field_validator("color")(_check_color)


class SpriteRef(_Model):
    generate: SpriteGenerate | None = None
    ai: SpriteAI | None = None

    @model_validator(mode="after")
    def _one(self) -> "SpriteRef":
        if (self.generate is None) == (self.ai is None):
            raise ValueError('use exactly one of "generate" or "ai"')
        return self


class Entity(_Model):
    body: Literal["character", "static", "area"] = "character"
    team: Literal["player", "enemy", "neutral"] | None = None
    shape: Shape = Field(default_factory=Shape)
    # Path to a .sprite.json (relative to the graph file) or {"generate": {...}}.
    sprite: Union[str, SpriteRef, None] = None
    components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    juice: Union[Literal["none"], dict[str, Any], None] = None


class Level(_Model):
    map: list[str]
    legend: dict[str, str]


class Rule(_Model):
    on: str
    if_: str | None = Field(default=None, alias="if")
    do: list[str] | str

    @property
    def actions(self) -> list[str]:
        return [self.do] if isinstance(self.do, str) else list(self.do)


class TileStyle(_Model):
    color: str | None = None
    top: str | None = None
    _color = field_validator("color", "top")(_check_color)


class Settings(_Model):
    tile_size: int = Field(default=32, ge=8, le=128)
    viewport: tuple[int, int] = (960, 540)
    lives: int = Field(default=3, ge=1, le=99)
    juice: Literal["default", "none"] = "default"
    background: str | None = None
    gravity: float | None = Field(default=None, ge=0, le=10000)
    seed: int = 0
    tiles: dict[Literal["solid", "oneway"], TileStyle] = Field(default_factory=dict)
    tile_style: Literal["pixel", "flat"] = "pixel"
    art_style: Literal["pixel", "cartoon"] = "pixel"  # generated sprites and tiles: pixel art or smooth cartoon
    zoom: float = Field(default=1.0, ge=0.5, le=4.0)

    _bg = field_validator("background")(_check_color)


class Graph(_Model):
    spawnpoint: Literal[1] = 1
    name: str = Field(min_length=1, max_length=80)
    genre: Literal["platformer", "topdown"]
    settings: Settings = Field(default_factory=Settings)
    entities: dict[str, Entity]
    level: Level
    rules: list[Rule] = Field(default_factory=list)


def parse(data: Any) -> tuple[Graph | None, Diagnostics]:
    """Parse raw JSON data into a Graph, converting pydantic errors into diagnostics."""
    diags = Diagnostics()
    try:
        return Graph.model_validate(data), diags
    except ValidationError as e:
        found = []
        for err in e.errors():
            # Drop pydantic's union-branch tags ("str", "SpriteRef", "literal['none']", ...).
            loc = [p for p in err["loc"] if not (isinstance(p, str) and ("[" in p or "-" in p or p in _TYPE_TAGS))]
            path = join_path(*loc) if loc else "(root)"
            msg = err["msg"]
            hint = None
            if err["type"] == "extra_forbidden":
                field = str(loc[-1])
                hint = did_you_mean(field, _allowed_fields(loc[:-1]))
                msg = f"unknown field '{field}'"
            elif err["type"] == "missing":
                msg = f"missing required field '{loc[-1]}'"
            found.append((path, msg, hint))
        # A union reports one error per branch; keep only the most specific ones.
        paths = {p for p, _, _ in found}
        for path, msg, hint in dict.fromkeys(found):
            if not any(o != path and o.startswith(path + ".") for o in paths):
                diags.error("E_SCHEMA", path, msg, hint)
        return None, diags


_TYPE_TAGS = {"str", "int", "float", "bool", "SpriteRef", "SpriteGenerate", "SpriteAI", "Shape", "Entity"}


# Which model lives under a field name (dict/list containers skip their key/index).
_CHILD = {"settings": (Settings, 1), "shape": (Shape, 1), "level": (Level, 1), "generate": (SpriteGenerate, 1),
          "ai": (SpriteAI, 1),
          "sprite": (SpriteRef, 1),
          "entities": (Entity, 2), "rules": (Rule, 2)}


def _allowed_fields(parent_loc: list) -> list[str]:
    """Valid field names at a location (for typo hints)."""
    model: type[BaseModel] | None = Graph
    i = 0
    while model is not None and i < len(parent_loc):
        child = _CHILD.get(str(parent_loc[i]))
        if child is None:
            return []
        model, step = child
        i += step
    if model is None:
        return []
    return [f.alias or name for name, f in model.model_fields.items()]
