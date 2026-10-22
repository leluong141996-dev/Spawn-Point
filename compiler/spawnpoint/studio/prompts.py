"""Prompts. Written for small local models: explicit rules, one worked example, common mistakes named."""

from __future__ import annotations

import json
import os
import re

# Names choose the art (sprites/generate.py FEATURE_WORDS, studio/assemble.py sprite_kind), so the prompts show
# the model nouns that draw something specific. tests/test_sprites.py checks each one still does.
ART_HEROES = ("Knight", "Wizard", "Ranger", "Viking", "King", "Ninja", "Princess")
ART_MONSTERS = ("Skeleton", "Zombie", "Ghost", "Dragon", "Spider", "Snake", "Wolf", "Orc", "Goblin", "Bat", "PiranhaPlant",
                "Mushroom", "Snail", "Reaper", "FireSpirit", "Alien")
ART_PICKUPS = ("Coin", "Gem", "Star", "Key", "Potion", "Scroll", "Chest")
FARM_LINE = ('Farms: crops are named in English: "dâu tây" = Strawberry, "nho" = Grape, "cà rốt" = Carrot, "bí ngô"/"bí đỏ" = Pumpkin,'
             ' "khoai tây" = Potato, "ngô"/"bắp" = Corn, "lúa" = Wheat, "cà chua" = Tomato, "bắp cải" = Cabbage; pests too:'
             ' "quạ" = Crow, "cáo" = Fox, "thỏ" = Rabbit, "chuột" = Rat. The palette sets the season: an island farm ("trên đảo")'
             ' is ocean, a farm in the woods forest, a winter farm ("mùa đông", snow) snow, a desert farm desert, an autumn farm'
             ' ("mùa thu") lava.')
ART_LINE = (f"Names choose the art, so use concrete nouns: heroes like {', '.join(ART_HEROES)} (a Ranger or Archer has a bow"
            f" and shoots arrows); monsters like {', '.join(ART_MONSTERS)}; pickups like {', '.join(ART_PICKUPS)}."
            " Words combine: SkeletonArcher is a skeleton with a bow, GoldKey a key, HealthPotion a potion.")

BRIEF_SYSTEM = """You are the lead designer of a tiny 2D game studio. Turn the user's game idea into a GameBrief JSON.

Fields:
- title: short catchy game title.
- genre: "platformer" (side view, gravity, jumping between platforms), "topdown" (seen from above, moves in 8 directions, usually shooting)
  or "bubble" (a bubble shooter / egg shooter: aim a launcher and pop 3 of the same colour; no enemies, no abilities)
  or "farm" (farming: plant, water, harvest, sell at the market before sunset; pests eat crops)
  or "tower_defense" (invaders walk a road to your castle; build towers beside the road; no abilities).
- art_style: "pixel" (default, retro pixel art) or "cartoon" (smooth, non-pixel 2D: hand-drawn, cute, cartoon, vector, HD).
- palette: night | forest | desert | neon | candy | ocean | lava | snow. Pick the one matching the theme.
- player.character: what the player is, one word in PascalCase (e.g. "Ninja", "Fox", "Astronaut").
- player.abilities: any of double_jump, dash, stomp (jump on enemies to defeat them), shoot, sword (melee slash up close;
  use it for knights, samurai, swords, blades, axes, melee, beat 'em up). Top-down games usually have shoot and dash. Pick shoot OR sword, not both.
- player.jump_tiles: jump height in tiles, 3-4 is normal. player.speed: slow | normal | fast. player.health: 3 is normal.
- enemies: 1 to 3 enemy types. Each has
    name: one singular noun in PascalCase, e.g. "Slime", "FireBat", "Robot".
    archetype: walker (patrols back and forth; platformer), hopper (bounces around; platformer),
               chaser (runs at the player), shooter (keeps distance and shoots), turret (stands still and shoots).
    count: how many (2-6 each), health: 1-3, speed: slow | normal | fast.
- collectible: the item the player picks up. name: singular noun in PascalCase (e.g. "Star"); count: 5-20.
- health_pickups: 0-3 hearts that heal.
- goal: reach_exit | collect_all | collect_all_then_exit | defeat_all | score_target | survive | rescue | clear_board | defend.
  score_target and survive_seconds are only used by those goals.
  rescue (platformer): find a key, open a cage and save someone; rescue_target is who, one word in PascalCase (e.g. "Mom", "Princess", "Puppy").
  clear_board is the goal of every bubble game; the collectible name is what gets popped (e.g. "Egg", "Bubble").
  farm: goal score_target is the money to earn, survive_seconds is how long the day lasts; crops: 1-3 crop names
  in PascalCase, cheapest first (e.g. ["Carrot", "Tomato", "Pumpkin"]); enemies are pests (walker eats crops, chaser bites the farmer).
  defend is the goal of every tower_defense game: survive every wave. towers: 1-3 tower names in PascalCase (e.g. ["Archer", "Cannon", "Mage"]);
  enemies are the invaders (speed slow = big and tough, fast = swarms; count = wave size, 3 is normal).
- level_ups (top-down only): true for survivor games where the player auto-fires, collects XP gems and picks an upgrade on each level up. Usually with goal survive.
- hazards: any of spikes, pits (platformer only).
- length: short | medium | long. difficulty: 1-5 (2 is normal).
- feel: snappy (tight, default) | floaty (moon-like, slow falls) | heavy (weighty).
- juice: subtle | normal | wild (how strong screen shake and impacts are).
- intro: one short sentence shown when the game starts, telling the player the goal.

Common mistakes to avoid:
- The player is never an enemy or a collectible.
- Platforms, walls, floors and the level itself are NOT enemies or collectibles; the level is generated automatically.
- Names are singular ("Star", not "Stars").
- Only use the archetypes listed above.

""" + ART_LINE

BRIEF_EXAMPLE_USER = "a space game where I blast alien bugs in an arena"
BRIEF_EXAMPLE = {
    "title": "Bug Blaster", "genre": "topdown", "palette": "neon",
    "player": {"character": "Astronaut", "shape": "circle", "abilities": ["shoot", "dash"], "jump_tiles": 3.5, "speed": "normal", "health": 5},
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
- "remove dash" removes "dash" from player.abilities; "no enemies" empties enemies.
- "cartoon style" / "not pixel" sets art_style "cartoon"; "pixel art" sets art_style "pixel".
- Allowed values are the same as in the brief: archetypes walker, hopper, chaser, shooter, turret; abilities
  double_jump, dash, stomp, shoot, sword; palettes night, forest, desert, neon, candy, ocean, lava, snow.
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
"sống sót" = survive, "tiêu diệt hết" = defeat all, "cửa" = door/exit, "gai" = spikes, "hố" = pits,
"hiệp sĩ" = knight, "phù thủy" = wizard (female: witch), "cung thủ"/"xạ thủ" = archer, "thợ săn" = hunter, "vua" = king,
"công chúa" = princess, "bộ xương" = skeleton, "xác sống" = zombie, "ma" = ghost, "rồng" = dragon, "nhện" = spider,
"rắn" = snake, "sói" = wolf, "yêu tinh" = goblin, "dơi" = bat, "chìa khóa" = key, "bình máu"/"bình thuốc" = potion,
"cuộn giấy"/"bí kíp" = scroll, "rương"/"kho báu" = treasure chest, "đồng xu"/"tiền" = coin, "đá quý" = gem,
"cung tên" = bow and arrows, "mũi tên" = arrow, "khiên" = shield, "kiếm" = sword."""

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


# --- the v5 format: one small schema per genre (see genres.py) and prompts to match ---------------------------
# A fine-tuned model has learned the field list, so the prompt only has to say what the genres are and which
# words mean what. About a third of the v4 prompt, and no worked example.

BRIEF_SYSTEM_V5 = """You design tiny 2D games. Answer with one JSON object that starts with "genre":
platformer (side view, jumping), topdown (seen from above, moving and shooting; level_ups for survivor games), bubble (bubble or egg shooter), farm (plant, water, harvest and sell crops; pests eat them), tower_defense (invaders walk a road to your castle, you build towers), shmup (side-scrolling space shooter with a boss).
Names are singular PascalCase ("Slime"). Palette: night, forest, desert, neon, candy, ocean, lava or snow. art_style is pixel, or cartoon when the player asks for smooth, hand-drawn or non-pixel art. Keep numbers the player gives exactly ("score 300 points").
Archetypes: walker patrols, hopper bounces, chaser runs at you, shooter keeps its distance and shoots, turret stands still and shoots. Shmup: drifter flies straight, weaver in a wave, diver dives at you, gunship stops and shoots. Speed is slow, normal or fast (tower defense: slow = big and tough, fast = swarms).
Abilities: double_jump, dash, stomp, shoot, sword (melee); one weapon, shoot or sword. Goals: reach_exit, collect_all, collect_all_then_exit, defeat_all, score_target, survive, rescue (platformer), defeat_boss (shmup).
The level, platforms and the player are never enemies or pickups.
""" + ART_LINE
# Farm words in English and Vietnamese: only a farm prompt gets the farm vocabulary, so every other prompt reads
# exactly as the model was trained on.
FARM_WORDS = re.compile(r"farm|harvest|crop|plant|nông trại|nông trang|trang trại|làm vườn|trồng|thu hoạch|gieo", re.I)


CARD_LINE = ('Card games (deckbuilders like Slay the Spire, "game thẻ bài") are genre cards: hero (who you play),'
             ' hero_class warrior, mage or rogue (the starting deck), cards: up to 6 of {name, kind} with kind strike, heavy,'
             ' multi_hit, sweep (hits every foe), block, heal, draw, poison, weaken or rage (more damage for the fight);'
             ' enemies: {name, archetype} where brute hits hard, guard blocks, caster curses and poisons, swarm comes in packs;'
             ' boss: the last foe.')
# Only prompts that ask for a card game: "upgrade cards" in a survivor or "key cards" in a shooter do not.
CARD_WORDS = re.compile(r"card ?games?|card battler|card roguelike|card-based|deck|slay the spire|thẻ bài|bộ bài|đánh bài|"
                        r"game bài", re.I)


def brief_messages_v5(prompt: str) -> list[dict]:
    system = BRIEF_SYSTEM_V5 + ("\n" + FARM_LINE if FARM_WORDS.search(prompt) else "")
    system += "\n" + CARD_LINE if CARD_WORDS.search(prompt) else ""
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


TWEAK_SYSTEM_V5 = """You edit a game's JSON. Answer {"brief": the updated game, "new_level": true only if the player asks for a different level or map}.
Change only what the request is about; copy everything else exactly. Percentages scale numbers ("jump 20% higher": 3.5 -> 4.2), "a bit" is about 15%, "harder" adds 1 to difficulty, "add X" adds to a list, "remove X" removes it, "no enemies" empties enemies, "cartoon" or "not pixel" sets art_style cartoon, "pixel art" sets pixel."""


def tweak_messages_v5(brief: dict, request: str) -> list[dict]:
    return [{"role": "system", "content": TWEAK_SYSTEM_V5},
            {"role": "user", "content": f"Game: {json.dumps(brief)}\nRequest: {request}"}]


def brief_format() -> str:
    """"v5": the model writes one small schema per genre (the SpawnPoint-Coder v5 models and later);
    "v4": one big GameBrief form, for the v1-v4 models. SPAWNPOINT_BRIEF_FORMAT=v4 switches back."""
    return "v4" if os.environ.get("SPAWNPOINT_BRIEF_FORMAT", "v5").lower() == "v4" else "v5"
