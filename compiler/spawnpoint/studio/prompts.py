"""Prompts. Written for small local models: explicit rules, one worked example, common mistakes named."""

from __future__ import annotations

import json

BRIEF_SYSTEM = """You are the lead designer of a tiny 2D game studio. Turn the user's game idea into a GameBrief JSON.

Fields:
- title: short catchy game title.
- genre: "platformer" (side view, gravity, jumping between platforms) or "topdown" (seen from above, moves in 8 directions, usually shooting).
- palette: night | forest | desert | neon | candy | ocean | lava | snow. Pick the one matching the theme.
- player.abilities: any of double_jump, dash, stomp (jump on enemies to defeat them), shoot. Top-down games usually have shoot and dash.
- player.jump_tiles: jump height in tiles, 3-4 is normal. player.speed: slow | normal | fast. player.health: 3 is normal.
- enemies: 1 to 3 enemy types. Each has
    name: one singular noun in PascalCase, e.g. "Slime", "FireBat", "Robot".
    archetype: walker (patrols back and forth; platformer), hopper (bounces around; platformer),
               chaser (runs at the player), shooter (keeps distance and shoots), turret (stands still and shoots).
    count: how many (2-6 each), health: 1-3, speed: slow | normal | fast.
- collectible: the item the player picks up. name: singular noun in PascalCase (e.g. "Star"); count: 5-20.
- health_pickups: 0-3 hearts that heal.
- goal: reach_exit | collect_all | collect_all_then_exit | defeat_all | score_target | survive.
  score_target and survive_seconds are only used by those goals.
- hazards: any of spikes, pits (platformer only).
- length: short | medium | long. difficulty: 1-5 (2 is normal).
- feel: snappy (tight, default) | floaty (moon-like, slow falls) | heavy (weighty).
- juice: subtle | normal | wild (how strong screen shake and impacts are).
- intro: one short sentence shown when the game starts, telling the player the goal.

Common mistakes to avoid:
- The player is never an enemy or a collectible.
- Platforms, walls, floors and the level itself are NOT enemies or collectibles; the level is generated automatically.
- Names are singular ("Star", not "Stars").
- Only use the archetypes listed above."""

BRIEF_EXAMPLE_USER = "a space game where I blast alien bugs in an arena"
BRIEF_EXAMPLE = {
    "title": "Bug Blaster", "genre": "topdown", "palette": "neon",
    "player": {"shape": "circle", "abilities": ["shoot", "dash"], "jump_tiles": 3.5, "speed": "normal", "health": 5},
    "enemies": [{"name": "Beetle", "archetype": "chaser", "count": 5, "health": 2, "speed": "normal"},
                {"name": "Spitter", "archetype": "shooter", "count": 2, "health": 3, "speed": "slow"}],
    "collectible": {"name": "Crystal", "count": 8}, "health_pickups": 2, "goal": "score_target",
    "score_target": 150, "survive_seconds": 60, "hazards": [], "length": "medium", "difficulty": 2,
    "feel": "snappy", "juice": "wild", "intro": "Blast 150 points of bugs!",
}


def brief_messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": BRIEF_EXAMPLE_USER},
        {"role": "assistant", "content": json.dumps(BRIEF_EXAMPLE)},
        {"role": "user", "content": prompt},
    ]


TWEAK_SYSTEM = """You edit GameBrief JSON for a tiny 2D game studio.
You get the current brief and a change request from the player. Return the updated brief.

Rules:
- Change ONLY the fields the request is about. Copy every other field exactly as it is.
- Percentages scale numbers: "jump 20% higher" with jump_tiles 3.5 -> 4.2. "a bit" means about 15%.
- "more enemies" increases counts; "harder" raises difficulty by 1; "add dash" adds "dash" to player.abilities.
- Allowed values are the same as in the brief: archetypes walker, hopper, chaser, shooter, turret; abilities
  double_jump, dash, stomp, shoot; palettes night, forest, desert, neon, candy, ocean, lava, snow.
- Set new_level to true only if the player asks for a different level, map or layout."""


def tweak_messages(brief: dict, request: str) -> list[dict]:
    return [
        {"role": "system", "content": TWEAK_SYSTEM},
        {"role": "user", "content": f"Current brief:\n{json.dumps(brief)}\n\nChange request: {request}"},
    ]


CREATIVE_SYSTEM = """You are a game designer polishing a 2D game made of components.
Propose a small patch that makes the game more fun and closer to the player's idea:
- set_params: change component parameters of existing entities (only parameters listed in the reference, within range).
- add_rules: new rules {"on": event, "if": condition or "", "do": [actions]}.
Keep it small: at most 4 set_params and 3 add_rules. Do not repeat existing rules.

Rule syntax:
- events: Entity.signal (e.g. "Slime.died", "Star.collected"), "GameState.score_changed", "GameState.second_passed", "Game.ready".
- conditions: Python-like expressions using score, lives, time, vars.NAME, event.ARG, count("Entity").
- actions: add_score(n), set_var("name", v), add_var("name", d), win(), lose(), spawn("Entity") (at the emitting entity),
  spawn_at("Entity", tile_x, tile_y), destroy(self), shake(0..1), freeze(seconds), sound("coin"), message("text"),
  Entity.method(args) using methods from the reference (e.g. Door.open())."""


def creative_messages(prompt: str, graph_summary: str, reference: str) -> list[dict]:
    return [
        {"role": "system", "content": CREATIVE_SYSTEM},
        {"role": "user", "content": f"Player's idea: {prompt}\n\nGame:\n{graph_summary}\n\nComponent reference:\n{reference}"},
    ]


def repair_message(errors: list[str]) -> dict:
    return {"role": "user", "content": "The compiler rejected the patch:\n- " + "\n- ".join(errors)
            + "\nReturn a corrected patch (drop anything you cannot fix)."}


TRANSLATE_SYSTEM = """Translate the user's game idea into clear English for a game designer.
Keep every detail: characters, enemies, items, goals, numbers. Output JSON.
Vietnamese game terms: "sao"/"ngôi sao" = star, "ăn"/"nhặt" an item = collect it, "qua màn" = finish the level,
"quái"/"quái vật" = enemies/monsters, "né" = avoid/dodge, "bắn" = shoot, "nhảy" = jump, "bục" = platform,
"sống sót" = survive, "tiêu diệt hết" = defeat all, "cửa" = door/exit, "gai" = spikes, "hố" = pits."""

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"english": {"type": "string"}},
    "required": ["english"],
    "additionalProperties": False,
}


def translate_messages(prompt: str) -> list[dict]:
    return [{"role": "system", "content": TRANSLATE_SYSTEM}, {"role": "user", "content": prompt}]


def needs_translation(prompt: str) -> bool:
    return any(ord(ch) > 127 for ch in prompt)
