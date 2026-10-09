"""Semantic analysis: graph + manifest -> diagnostics + build plan (the IR consumed by build.gd)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import level as lvl
from .diagnostics import Diagnostics, did_you_mean, join_path
from .graph import Entity, Graph, parse
from .manifest import BODY_CLASSES, Component, Manifest, Param
from .rules import compile_rules
from .sprites import resolve as sprite_resolve
from .sprites.spriteset import SpriteError, SpriteSet

PLAN_FORMAT = 1
ENTITY_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RESERVED = {"GameState", "Game", "World", "FX", "Sfx", "SP", "Entity", "Visual", "Shape", "Main", "Tiles",
            "Entities", "Rules", "HUD", "Camera"}

# PICO-8 inspired placeholder palette.
COLORS = {
    "player": "#29adff", "enemy": "#ff004d", "collectible": "#ffec27", "bullet_player": "#fff1e8",
    "bullet_enemy": "#ff77a8", "gate": "#ab5236", "trigger": "#00e436", "other": "#c2c3c7",
}
GENRE_DEFAULTS = {
    "platformer": {"gravity": 1600.0, "background": "#1d2b53", "solid": "#5f574f", "solid_top": "#00e436",
                   "oneway": "#ab5236", "walls": ["left", "right", "top"]},
    "topdown": {"gravity": 0.0, "background": "#1a1c2c", "solid": "#5f574f", "solid_top": "#83769c",
                "oneway": "#ab5236", "walls": ["left", "right", "top", "bottom"]},
}
MOVEMENT = {"PlatformerMovement", "TopDownMovement"}
RULES_SCRIPT = "res://rules/main_rules.gd"

# Layer bits — keep in sync with runtime/sp.gd.
L_WORLD, L_PLAYER, L_ENEMY, L_PICKUP = 1, 2, 4, 32


@dataclass
class Analysis:
    graph: Graph | None
    diagnostics: Diagnostics
    plan: dict | None = None
    rules_source: str | None = None
    sprites: dict[str, SpriteSet] = field(default_factory=dict)  # entity -> resolved sprite sheet
    tiles_image: Any = None  # pixel-art tile atlas (PIL image), written to res://sprites/tiles.png

    @property
    def ok(self) -> bool:
        return self.diagnostics.ok and self.plan is not None


def analyze(data: Any, manifest: Manifest, base_dir: Path | None = None) -> Analysis:
    """`base_dir` resolves relative sprite paths (the graph file's folder)."""
    graph, diags = parse(data)
    if graph is None:
        return Analysis(None, diags)
    return _Analyzer(graph, manifest, diags, base_dir).run()


class _Analyzer:
    def __init__(self, graph: Graph, manifest: Manifest, diags: Diagnostics, base_dir: Path | None = None):
        self.g = graph
        self.m = manifest
        self.d = diags
        self.base_dir = base_dir
        self.genre = GENRE_DEFAULTS[graph.genre]
        self.sprites: dict[str, SpriteSet] = {}
        self.tiles_image = None

    # -- entry -----------------------------------------------------------------------------
    def run(self) -> Analysis:
        g = self.g
        comps_by_entity = {name: list(e.components) for name, e in g.entities.items()}
        teams = {name: self._team(e) for name, e in g.entities.items()}
        self._resolve_sprites(teams)
        params_by_entity: dict[str, dict[str, dict]] = {}
        for name, ent in g.entities.items():
            params_by_entity[name] = self._check_entity(name, ent)

        players = [n for n, e in g.entities.items() if "PlayerInput" in e.components]
        if not players:
            self.d.error("E_NO_PLAYER", "entities", "no entity has a PlayerInput component",
                         'Add "PlayerInput": {} to the player entity')
        elif len(players) > 1:
            self.d.error("E_MULTIPLE_PLAYERS", "entities", f"several entities have PlayerInput: {', '.join(players)}")

        data = lvl.parse_level(g.level, set(g.entities), self.d)
        if data is not None and len(players) == 1:
            self._check_level(data, players[0], params_by_entity[players[0]])

        rules = compile_rules(g.rules, comps_by_entity, self.m, self.d)
        if not rules.calls_win and self.d.ok:
            self.d.warning("W_NO_WIN", "rules", "no rule calls win(); the game cannot be won",
                           'e.g. {"on": "Exit.triggered", "do": ["win()"]}')

        if not self.d.ok or data is None:
            return Analysis(g, self.d)
        plan = self._plan(data, teams, params_by_entity, players[0])
        return Analysis(g, self.d, plan, rules.source, self.sprites, self.tiles_image)

    # -- sprites ---------------------------------------------------------------------------
    def _resolve_sprites(self, teams: dict[str, str]) -> None:
        for name, ent in self.g.entities.items():
            if ent.sprite is None:
                continue
            color = ent.shape.color or self._color(ent, teams[name])
            try:
                sprite = sprite_resolve.resolve(name, ent, self.base_dir, color)
            except SpriteError as e:
                self.d.error("E_SPRITE", join_path("entities", name, "sprite"), str(e),
                             "Generator kinds: " + ", ".join(sorted(sprite_resolve.KINDS)) if "kind" in str(e) else None)
                continue
            self.sprites[name] = sprite
            if "shape" not in ent.model_fields_set:
                # No explicit shape: the body collision comes from the drawing.
                ent.shape = sprite_resolve.derived_shape(ent, sprite, self.g.genre)

    # -- entities --------------------------------------------------------------------------
    def _team(self, e: Entity) -> str:
        if e.team:
            return e.team
        c = e.components
        if "PlayerInput" in c:
            return "player"
        if any(k in c for k in ("Hitbox", "PatrolAI", "ChaseAI")):
            return "enemy"
        return "neutral"

    def _check_entity(self, name: str, ent: Entity) -> dict[str, dict]:
        path = join_path("entities", name)
        if not ENTITY_NAME.match(name):
            self.d.error("E_ENTITY_NAME", path, f"entity name '{name}' must be PascalCase (e.g. 'BlueSlime')")
        if name in RESERVED or name in self.m.components:
            self.d.error("E_ENTITY_NAME", path, f"'{name}' is reserved", f"Rename it, e.g. '{name}Entity'")
        body_class = BODY_CLASSES[ent.body]
        resolved: dict[str, dict] = {}
        movement = [c for c in ent.components if c in MOVEMENT]
        if len(movement) > 1:
            self.d.error("E_MOVEMENT", join_path(path, "components"), "an entity can have only one movement component")
        if self.g.genre == "platformer" and "TopDownMovement" in ent.components:
            self.d.warning("W_GENRE", join_path(path, "components"), "TopDownMovement in a platformer ignores gravity")
        if self.g.genre == "topdown" and "PlatformerMovement" in ent.components:
            self.d.warning("W_GENRE", join_path(path, "components"), "PlatformerMovement in a top-down game falls forever")

        for cname, params in ent.components.items():
            cpath = join_path(path, "components", cname)
            comp = self.m.get(cname)
            if comp is None:
                self.d.error("E_UNKNOWN_COMPONENT", cpath, f"unknown component '{cname}'",
                             did_you_mean(cname, self.m.components))
                continue
            if comp.hosts and body_class not in comp.hosts:
                want = " or ".join(k for k, v in BODY_CLASSES.items() if v in comp.hosts)
                self.d.error("E_HOST", cpath, f"{cname} needs body '{want}', but {name} is '{ent.body}'",
                             f'Set "body": "{want}" on {name}')
            for req in comp.requires:
                if req not in ent.components:
                    self.d.error("E_REQUIRES", cpath, f"{cname} requires the {req} component", f'Add "{req}": {{}}')
            if comp.is_area and ent.shape.type == "none":
                self.d.error("E_SHAPE", cpath, f"{cname} needs a collision shape but {name} has shape 'none'")
            resolved[cname] = self._check_params(comp, params or {}, cpath)

        if "Projectile" in ent.components and "Hitbox" not in ent.components:
            self.d.warning("W_PROJECTILE_HITBOX", path, f"{name} is a projectile without a Hitbox; it deals no damage",
                           'Add "Hitbox": {"damage": 1}')

        if isinstance(ent.juice, dict):
            juice = self.m.get("Juice")
            if juice:
                resolved["Juice"] = self._check_params(juice, ent.juice, join_path(path, "juice"))
        return resolved

    def _check_params(self, comp: Component, params: dict[str, Any], path: str) -> dict:
        out: dict[str, Any] = {}
        for key, value in params.items():
            ppath = join_path(path, key)
            p = comp.params.get(key)
            if p is None:
                self.d.error("E_UNKNOWN_PARAM", ppath, f"{comp.name} has no parameter '{key}'",
                             did_you_mean(key, comp.params))
                continue
            converted = self._convert(p, value, ppath)
            if converted is None:
                continue
            if key in comp.entity_params and converted not in self.g.entities:
                self.d.error("E_ENTITY_REF", ppath, f"'{converted}' is not an entity", did_you_mean(converted, self.g.entities))
                continue
            if key in comp.entity_params and comp.name == "Weapon":
                target = self.g.entities[converted]
                if "Projectile" not in target.components:
                    self.d.error("E_NOT_PROJECTILE", ppath, f"Weapon fires '{converted}', which has no Projectile component")
            out[key] = converted
        for key in comp.entity_params:
            if key not in params:
                default = comp.params[key].default
                if default not in self.g.entities:
                    self.d.error("E_ENTITY_REF", join_path(path, key),
                                 f"{comp.name}.{key} must name an entity (default '{default}' does not exist)")
        return out

    def _convert(self, p: Param, v: Any, path: str) -> Any:
        def bad(expected: str) -> None:
            self.d.error("E_PARAM_TYPE", path, f"{p.name} must be {expected}, got {v!r}")

        t = p.type
        if t == "bool":
            if not isinstance(v, bool):
                return bad("true or false")
            return v
        if t in ("int", "float"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return bad("a number")
            if t == "int":
                if float(v) != int(v):
                    return bad("a whole number")
                v = int(v)
            else:
                v = float(v)
            if p.min is not None and not (p.min <= v <= p.max):
                self.d.error("E_PARAM_RANGE", path, f"{p.name} = {v:g} is outside {p.min:g}..{p.max:g}")
                return None
            return v
        if t in ("String", "StringName"):
            if not isinstance(v, str):
                return bad("a string")
            if p.choices and v not in p.choices:
                self.d.error("E_PARAM_CHOICE", path, f"{p.name} must be one of {', '.join(p.choices)}",
                             did_you_mean(v, p.choices))
                return None
            return v
        if t == "Vector2":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
                return bad("[x, y]")
            return [float(v[0]), float(v[1])]
        if t == "Color":
            if not (isinstance(v, str) and re.match(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$", v)):
                return bad("a hex color like '#ff004d'")
            return v
        self.d.error("E_PARAM_TYPE", path, f"{p.name} has unsupported type {t}")
        return None

    # -- level -----------------------------------------------------------------------------
    def _check_level(self, data: lvl.LevelData, player: str, player_params: dict[str, dict]) -> None:
        mp = join_path("level", "map")
        spots = [p for p in data.placements if p.entity == player]
        if len(spots) != 1:
            self.d.error("E_PLAYER_PLACEMENT", mp, f"the player '{player}' must appear exactly once on the map (found {len(spots)})",
                         "Put its legend character once in level.map")
            return
        start = spots[0]
        if self.g.genre != "platformer":
            return
        if not lvl.has_ground_below(data, start.x, start.y):
            self.d.warning("W_NO_GROUND", mp, f"no floor below the player at ({start.x},{start.y}); they will fall out")
            return
        ent = self.g.entities[player]
        mv = self.m.get("PlatformerMovement")
        if "PlatformerMovement" not in ent.components or mv is None:
            return
        mv_params = player_params.get("PlatformerMovement", {})  # validated values only

        def param(name: str) -> float:
            return float(mv_params.get(name, mv.params[name].default))

        gravity = (self.g.settings.gravity if self.g.settings.gravity is not None else self.genre["gravity"]) * param("gravity_scale")
        jm = lvl.jump_model(param("jump_velocity"), gravity, param("fall_gravity_multiplier"), param("max_speed"),
                            self.g.settings.tile_size, ent.shape.size[1], int(param("air_jumps")))
        targets = [p for p in data.placements
                   if any(c in self.g.entities[p.entity].components for c in ("Collectible", "TriggerZone"))]
        for t in lvl.unreachable(data, (start.x, start.y), targets, jm):
            self.d.warning("W_UNREACHABLE", mp, f"{t.entity} at ({t.x},{t.y}) looks unreachable "
                           f"(jump ≈ {jm.up} tiles up, {jm.across} across)", "Lower it, add a platform, or raise jump_velocity")

    # -- plan ------------------------------------------------------------------------------
    def _plan(self, data: lvl.LevelData, teams: dict[str, str], params: dict[str, dict], player: str) -> dict:
        g, s = self.g, self.g.settings
        ts = s.tile_size
        juice_on = s.juice == "default"
        entities = []
        for name, ent in g.entities.items():
            team = teams[name]
            comps = []
            for cname in ent.components:
                comp = self.m.get(cname)
                p = params[name].get(cname, {})
                area_scale = None
                if comp.is_area:
                    area_scale = float(p.get("size_scale", comp.params["size_scale"].default)) if "size_scale" in comp.params else 1.0
                comps.append({"name": cname, "script": comp.script, "params": p, "area_scale": area_scale})
            if juice_on and ent.juice != "none":
                comps.append({"name": "Juice", "script": self.m.get("Juice").script,
                              "params": params[name].get("Juice", {}), "area_scale": None})
            sprite = self.sprites.get(name)
            if sprite is not None and self.m.get("Animator"):
                comps.append({"name": "Animator", "script": self.m.get("Animator").script, "params": {},
                              "area_scale": None})
            entities.append({
                "name": name,
                "body": ent.body,
                "team": team,
                "is_player": name == player,
                "layer": self._layer(ent, team),
                "mask": self._mask(ent),
                "shape": {"type": ent.shape.type, "size": list(ent.shape.size),
                          "color": ent.shape.color or self._color(ent, team)},
                "eye": ent.body == "character" and sprite is None,
                "pivot": "bottom" if g.genre == "platformer" and ent.body == "character" else "center",
                "sprite": sprite_resolve.plan_entry(name, sprite) if sprite is not None else None,
            })
            entities[-1]["components"] = comps

        placements = []
        for p in data.placements:
            ent = g.entities[p.entity]
            x = (p.x + 0.5) * ts
            floating = any(c in ent.components for c in ("Collectible", "Projectile", "Spawner"))
            if g.genre == "platformer" and not floating:
                y = (p.y + 1) * ts - ent.shape.size[1] / 2
            else:
                y = (p.y + 0.5) * ts
            placements.append({"entity": p.entity, "x": x, "y": y})

        solid, oneway = s.tiles.get("solid"), s.tiles.get("oneway")
        tiles_style = {
            "solid": {"color": (solid and solid.color) or self.genre["solid"],
                      "top": (solid and solid.top) or self.genre["solid_top"]},
            "oneway": {"color": (oneway and oneway.color) or self.genre["oneway"]},
        }
        if s.tile_style == "pixel":
            from .sprites.tiles import tileset
            self.tiles_image = tileset(g.genre, tiles_style["solid"]["color"], tiles_style["solid"]["top"],
                                       tiles_style["oneway"]["color"], ts, s.seed)
            tiles_style["texture"] = "res://sprites/tiles.png"
        return {
            "format": PLAN_FORMAT,
            "name": g.name,
            "genre": g.genre,
            "tile_size": ts,
            "lives": s.lives,
            "viewport": list(s.viewport),
            "zoom": s.zoom,
            "background": s.background or self.genre["background"],
            "gravity": s.gravity if s.gravity is not None else self.genre["gravity"],
            "tiles": tiles_style,
            "map": {"width": data.width, "height": data.height,
                    "cells": [[x, y, k] for (x, y), k in sorted(data.tiles.items(), key=lambda kv: (kv[0][1], kv[0][0]))]},
            "bounds": [0, 0, data.width * ts, data.height * ts],
            "walls": self.genre["walls"],
            "entities": entities,
            "placements": placements,
            "rules_script": RULES_SCRIPT,
        }

    def _layer(self, ent: Entity, team: str) -> int:
        if ent.body == "character":
            return {"player": L_PLAYER, "enemy": L_ENEMY}.get(team, 0)
        if ent.body == "static":
            return L_WORLD
        return 0 if "Projectile" in ent.components else L_PICKUP

    def _mask(self, ent: Entity) -> int:
        if ent.body == "character":
            return L_WORLD
        if ent.body == "static":
            return 0
        return L_WORLD if "Projectile" in ent.components else (L_PLAYER | L_ENEMY)

    def _color(self, ent: Entity, team: str) -> str:
        c = ent.components
        if "PlayerInput" in c:
            return COLORS["player"]
        if "Projectile" in c:
            return COLORS["bullet_enemy"] if team == "enemy" else COLORS["bullet_player"]
        if "Collectible" in c:
            return COLORS["collectible"]
        if "Gate" in c:
            return COLORS["gate"]
        if "TriggerZone" in c:
            return COLORS["trigger"]
        if team == "enemy":
            return COLORS["enemy"]
        return COLORS["other"]
