import itertools
import json
import math

import pytest

from spawnpoint import godot
from spawnpoint.analyze import analyze
from spawnpoint.studio import levelgen
from spawnpoint.studio.assemble import PLATFORMER_GRAVITY, TILE, assemble, jump_velocity
from spawnpoint.studio.brief import GameBrief, normalize, pascal_singular
from spawnpoint.studio.creative import apply_patch, creative_pass
from spawnpoint.studio.llm import ScriptedModel, parse_json
from spawnpoint.studio.orchestrator import create, design_brief, diff_briefs, load_session, tweak
from spawnpoint.studio.web import export_preset


def brief(**kw) -> GameBrief:
    data = {"title": "Test", "genre": "platformer",
            "enemies": [{"name": "Slime", "archetype": "walker", "count": 3}]}
    data.update(kw)
    return GameBrief.model_validate(data)


# --- normalization ----------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Stars", "Star"), ("fire bats", "FireBat"), ("Enemies", "Enemy"), ("Berries", "Berry"),
    ("Boss", "Boss"), ("Cactus", "Cactus"), ("mice", "Mouse"), ("123", "Coin"), ("", "Coin"),
])
def test_pascal_singular(raw, expected):
    assert pascal_singular(raw, "Coin") == expected


def test_normalize_repairs_weak_model_output():
    b, notes = normalize(brief(
        genre="topdown",
        enemies=[{"name": "Zombies", "archetype": "walker", "count": 4},
                 {"name": "Health", "archetype": "turret", "count": 1},
                 {"name": "zombie", "archetype": "chaser", "count": 2},
                 {"name": "Ghost", "archetype": "chaser", "count": 0}],
        collectible={"name": "Player", "count": 5},
        player={"abilities": ["double_jump", "shoot", "shoot"]},
        hazards=["pits", "spikes"]))
    assert [e.name for e in b.enemies] == ["Zombie", "HealthFoe"]
    assert b.enemies[0].archetype == "chaser"
    assert b.collectible.name == "PlayerItem"
    assert b.player.abilities == ["shoot"]
    assert b.hazards == ["spikes"]
    assert b.intro
    assert len(notes) >= 5


def test_normalize_fixes_impossible_goals():
    b, _ = normalize(brief(goal="collect_all", collectible={"name": "Gem", "count": 0}))
    assert b.collectible.count > 0
    b, _ = normalize(brief(goal="defeat_all", enemies=[]))
    assert b.goal == "reach_exit"
    b, _ = normalize(brief(goal="defeat_all", player={"abilities": []}))
    assert "stomp" in b.player.abilities
    b, _ = normalize(brief(genre="topdown", goal="defeat_all", enemies=[{"name": "Bot", "archetype": "chaser"}]))
    assert "shoot" in b.player.abilities


# --- assembler --------------------------------------------------------------------------------

def test_jump_velocity_reaches_requested_height():
    for tiles in (2.0, 3.5, 6.0):
        v = jump_velocity(tiles)
        h = v * v / (2 * PLATFORMER_GRAVITY)
        assert h == pytest.approx(tiles * TILE * 0.92, rel=1e-3)


COMBOS = list(itertools.product(
    ["platformer", "topdown"],
    ["reach_exit", "collect_all", "collect_all_then_exit", "defeat_all", "score_target", "survive"],
    ["walker", "hopper", "chaser", "shooter", "turret"],
))


@pytest.mark.parametrize("genre, goal, archetype", COMBOS)
def test_every_combination_compiles_cleanly(manifest, genre, goal, archetype):
    b, _ = normalize(brief(genre=genre, goal=goal, hazards=["spikes", "pits"],
                           enemies=[{"name": "Foe", "archetype": archetype, "count": 4}],
                           player={"abilities": ["double_jump", "dash", "stomp", "shoot"]}))
    for layer in (0, 1, 2):
        a = analyze(assemble(b, layer, seed=11), manifest)
        problems = [str(d) for d in a.diagnostics if not (layer == 0 and d.code == "W_NO_WIN")]
        assert a.ok and not problems, problems


@pytest.mark.parametrize("jump_tiles", [1.5, 2.0, 3.0, 5.0, 8.0])
@pytest.mark.parametrize("length", ["short", "long"])
def test_platformer_levels_reachable_for_any_jump(manifest, jump_tiles, length):
    b, _ = normalize(brief(length=length, difficulty=5, hazards=["pits", "spikes"], goal="collect_all",
                           player={"jump_tiles": jump_tiles}))
    for seed in range(3):
        a = analyze(assemble(b, 2, seed), manifest)
        assert a.ok and not a.diagnostics.warnings, [str(d) for d in a.diagnostics]


def test_layers_add_content(manifest):
    b, _ = normalize(brief(juice="wild", feel="heavy"))
    l0, l1, l2 = (assemble(b, layer, 5) for layer in (0, 1, 2))
    assert set(l0["entities"]) == {"Player"}
    assert {"Slime", b.collectible.name} <= set(l1["entities"])
    assert "juice" not in l1["entities"]["Player"]
    assert l2["entities"]["Player"]["juice"]["shake_on_hurt"] > 0.35
    assert l2["entities"]["Player"]["components"]["PlatformerMovement"]["fall_gravity_multiplier"] == 2.2
    tiles = lambda g: [r.translate(str.maketrans("PC1234^+DEOtpbr", "." * 15)).rstrip(".") for r in g["level"]["map"]]
    assert tiles(l0) == tiles(l2)  # same geometry across layers


def test_deterministic_and_cosmetic_tweaks_keep_the_map():
    b, _ = normalize(brief())
    assert assemble(b, 2, 7) == assemble(b, 2, 7)
    recolored, _ = normalize(b.model_copy(update={"palette": "lava", "juice": "wild"}))
    decor = str.maketrans("tpbr", "****")  # props follow the theme but keep their cells
    same = lambda g: [r.translate(decor) for r in g["level"]["map"]]
    assert same(assemble(b, 2, 7)) == same(assemble(recolored, 2, 7))


def test_arena_floor_is_connected():
    for seed in range(5):
        lay = levelgen.arena(seed, "long", 5)
        free = {(x, y) for x in range(lay.width) for y in range(lay.height) if lay.is_free((x, y))}
        assert len(lay.free_cells) + 1 == len(free)


def test_defeat_all_counts_every_enemy_type():
    b, _ = normalize(brief(goal="defeat_all", enemies=[{"name": "Slime", "archetype": "walker"},
                                                       {"name": "Frog", "archetype": "hopper"}]))
    rules = assemble(b, 1, 1)["rules"]
    wins = [r for r in rules if r["do"] == ["win()"]]
    assert {r["on"] for r in wins} == {"Slime.died", "Frog.died"}
    assert all(r["if"] == "count('Slime') + count('Frog') == 0" for r in wins)


# --- creative pass ----------------------------------------------------------------------------

def test_apply_patch():
    g = {"entities": {"Slime": {"components": {"Health": {}}}}, "rules": []}
    out = apply_patch(g, {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_health", "value": 3}],
                          "add_rules": [{"on": "Slime.died", "if": "", "do": ["shake(0.5)"]}]})
    assert out["entities"]["Slime"]["components"]["Health"] == {"max_health": 3}
    assert out["rules"] == [{"on": "Slime.died", "do": ["shake(0.5)"]}]
    assert g["rules"] == []  # input untouched


def test_creative_pass_repairs_then_applies(manifest):
    b, _ = normalize(brief())
    graph = assemble(b, 2, 3)
    bad = {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_hp", "value": 3}], "add_rules": []}
    good = {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_health", "value": 2}],
            "add_rules": [{"on": "Slime.died", "if": "", "do": ["shake(0.4)"]}]}
    llm = ScriptedModel([bad, good])
    res = creative_pass(graph, "slimes", llm, manifest)
    assert res.applied and res.rounds == 2
    assert "max_hp" in llm.seen[1][-1]["content"]  # diagnostics were fed back
    assert res.graph["entities"]["Slime"]["components"]["Health"]["max_health"] == 2


def test_creative_pass_drops_unfixable_patch(manifest):
    graph = assemble(normalize(brief())[0], 2, 3)
    bad = {"set_params": [], "add_rules": [{"on": "Nope.died", "if": "", "do": ["win()"]}]}
    res = creative_pass(graph, "x", ScriptedModel([bad, bad, bad]), manifest)
    assert not res.applied and res.graph is graph and res.errors


# --- LLM plumbing -----------------------------------------------------------------------------

def test_parse_json_tolerates_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_design_brief_translates_non_english():
    raw = brief().model_dump()
    llm = ScriptedModel([{"english": "a ninja collects stars"}, raw])
    b, notes, english = design_brief("ninja ăn sao", llm)
    assert english == "a ninja collects stars"
    assert llm.seen[1][-1]["content"] == "a ninja collects stars"
    assert b.title == "Test"


def test_diff_briefs():
    a = brief().model_dump()
    b = json.loads(json.dumps(a))
    b["player"]["jump_tiles"] = 4.2
    b["palette"] = "lava"
    assert diff_briefs(a, b) == ['palette: "night" -> "lava"', "player.jump_tiles: 3.5 -> 4.2"]


def test_export_preset_is_single_threaded_with_live_reload():
    cfg = export_preset()
    assert "variant/thread_support=false" in cfg
    assert "version.json" in cfg


# --- end to end with real Godot, scripted LLM -------------------------------------------------

@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_create_and_tweak_with_scripted_llm(tmp_path, manifest):
    raw = brief(goal="collect_all_then_exit").model_dump()
    llm = ScriptedModel([raw])
    out = tmp_path / "game"
    seen_layers = []
    res = create("a slime game", out, llm, web_export=False, manifest=manifest,
                 on_layer=lambda r: seen_layers.append(r.layer))
    assert res.ok, [str(d) for r in res.layers for d in r.build.diagnostics]
    assert seen_layers == [0, 1, 2]
    session = load_session(out)
    assert session["brief"]["title"] == "Test"
    map_before = json.loads((out / "spawnpoint.json").read_text())["level"]["map"]

    updated = json.loads(json.dumps(session["brief"]))
    updated["player"]["jump_tiles"] = 4.2
    llm2 = ScriptedModel([{"brief": updated, "new_level": False}])
    res2 = tweak(out, "jump 20% higher", llm2, web_export=False, manifest=manifest)
    assert res2.ok and res2.changes == ["player.jump_tiles: 3.5 -> 4.2"]
    graph = json.loads((out / "spawnpoint.json").read_text())
    assert graph["level"]["map"] == map_before
    assert math.isclose(graph["entities"]["Player"]["components"]["PlatformerMovement"]["jump_velocity"],
                        jump_velocity(4.2))
    assert load_session(out)["history"][0]["request"] == "jump 20% higher"


# --- dataset recording ------------------------------------------------------------------------

@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_recorder_captures_corrected_targets(tmp_path, manifest):
    from spawnpoint.studio.dataset import Recorder, iter_records, stats

    raw = brief(enemies=[{"name": "Slimes", "archetype": "walker", "count": 3}]).model_dump()
    bad_patch = {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_hp", "value": 2}],
                 "add_rules": []}
    good_patch = {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_health", "value": 2}],
                  "add_rules": []}
    llm = ScriptedModel([{"english": "slime game"}, raw, bad_patch, good_patch])
    rec = Recorder(tmp_path / "ds")
    res = create("game slime ăn xu", tmp_path / "game", llm, web_export=False, creative=True,
                 manifest=manifest, recorder=rec)
    assert res.ok
    records = list(iter_records(tmp_path / "ds"))
    assert [r["task"] for r in records] == ["translate", "brief", "creative", "creative"]
    b = records[1]
    assert b["raw"]["enemies"][0]["name"] == "Slimes"
    assert b["target"]["enemies"][0]["name"] == "Slime"  # normalized answer is the training target
    assert any("Slimes" in n for n in b["notes"])
    assert b["accepted"] is True and b["corrected"] is True and b["meta"]["prompt"] == "game slime ăn xu"
    assert records[0]["corrected"] is False
    bad, good = records[2], records[3]
    assert bad["accepted"] is False and bad["target"] is None and bad["errors"]
    assert good["accepted"] is True and good["target"] == good_patch
    st = stats(tmp_path / "ds")
    assert st["records"] == 4 and st["tasks"]["brief"]["corrected"] == 1


def test_recorder_flushes_even_when_the_llm_fails(tmp_path, manifest):
    from spawnpoint.studio.dataset import Recorder, iter_records
    from spawnpoint.studio.orchestrator import StudioError

    llm = ScriptedModel([{"title": 5}])  # not a valid brief
    rec = Recorder(tmp_path / "ds")
    with pytest.raises(StudioError):
        create("x", tmp_path / "game", llm, web_export=False, manifest=manifest, recorder=rec)
    (r,) = list(iter_records(tmp_path / "ds"))
    assert r["task"] == "brief" and r["accepted"] is False and r["target"] is None


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_tweak_keeps_creative_patch_and_tuning(tmp_path, manifest):
    from spawnpoint.studio.orchestrator import _save_session

    raw = brief().model_dump()
    patch = {"set_params": [{"entity": "Slime", "component": "Health", "param": "max_health", "value": 2}],
             "add_rules": []}
    out = tmp_path / "game"
    assert create("slimes", out, ScriptedModel([raw, patch]), web_export=False, creative=True, manifest=manifest).ok
    session = load_session(out)
    session["tuning"] = [{"entity": "Player", "component": "PlatformerMovement", "param": "coyote_time", "value": 0.18},
                         {"entity": "Ghost", "component": "Health", "param": "max_health", "value": 9}]  # stale entry
    _save_session(out, session)
    updated = json.loads(json.dumps(session["brief"]))
    updated["palette"] = "lava"
    assert tweak(out, "lava colors", ScriptedModel([{"brief": updated, "new_level": False}]), web_export=False,
                 manifest=manifest).ok
    g = json.loads((out / "spawnpoint.json").read_text())
    assert g["entities"]["Slime"]["components"]["Health"]["max_health"] == 2
    assert g["entities"]["Player"]["components"]["PlatformerMovement"]["coyote_time"] == 0.18
    assert "Ghost" not in g["entities"]


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_studio_playtest_uses_brief_difficulty(tmp_path, manifest):
    from spawnpoint.studio.orchestrator import studio_playtest

    out = tmp_path / "game"
    assert create("slimes", out, ScriptedModel([brief(difficulty=4, length="short").model_dump()]),
                  web_export=False, manifest=manifest).ok
    res = studio_playtest(out, runs=1, tune=False, web_export=False, manifest=manifest)
    assert res.difficulty == 4
    assert set(res.final.profiles) == {"novice", "average", "expert"}


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_cockpit_overrides_persist_and_beat_tuning(tmp_path, manifest):
    from spawnpoint.studio.edits import apply_override, set_param_patch
    from spawnpoint.studio.orchestrator import _save_session

    out = tmp_path / "game"
    assert create("slimes", out, ScriptedModel([brief().model_dump()]), web_export=False, manifest=manifest).ok
    session = load_session(out)
    session["tuning"] = [{"entity": "Player", "component": "Health", "param": "max_health", "value": 4}]
    _save_session(out, session)
    res = apply_override(out, set_param_patch("Player", "Health", "max_health", 7), manifest=manifest, web_export=False)
    assert res.ok, res.errors
    assert load_session(out)["overrides"][0]["set_params"][0]["value"] == 7
    bad = apply_override(out, set_param_patch("Player", "Health", "max_hp", 7), manifest=manifest, web_export=False)
    assert not bad.ok and "max_hp" in bad.errors[0] and len(load_session(out)["overrides"]) == 1
    updated = json.loads(json.dumps(load_session(out)["brief"]))
    updated["palette"] = "snow"
    assert tweak(out, "snow", ScriptedModel([{"brief": updated, "new_level": False}]), web_export=False, manifest=manifest).ok
    g = json.loads((out / "spawnpoint.json").read_text())
    assert g["entities"]["Player"]["components"]["Health"]["max_health"] == 7  # the person's edit wins


def test_resolve_model_prefers_fine_tuned_adapter(monkeypatch):
    from spawnpoint.studio.llm import OpenAICompatible

    llm = OpenAICompatible(model=None, base_url="http://x")
    monkeypatch.setattr(llm, "_request", lambda path, payload=None: {"data": [
        {"id": "base", "parent": None}, {"id": "Tuned-7B", "parent": "base"}]})
    assert llm.resolve_model() == "Tuned-7B"
    llm2 = OpenAICompatible(model=None, base_url="http://x")
    monkeypatch.setattr(llm2, "_request", lambda path, payload=None: {"data": [{"id": "only"}]})
    assert llm2.resolve_model() == "only"


def test_pickup_colour_follows_its_name():
    from spawnpoint.studio.assemble import PALETTES, pickup_color

    assert pickup_color("GoldCoin", PALETTES["ocean"]) == "#ffd23f"  # not the ocean palette's white
    assert pickup_color("Rubies", PALETTES["night"]) == "#ff004d"  # plural names work
    assert pickup_color("Marble", PALETTES["ocean"]) == PALETTES["ocean"]["pickup"]  # unknown: palette colour


def test_topdown_score_target_takes_a_real_fight():
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import EnemyBrief, GameBrief, normalize

    b = GameBrief(title="t", genre="topdown", goal="score_target", score_target=100, difficulty=2,
                  enemies=[EnemyBrief(name="LaserTurret", archetype="turret", count=2)])
    b, notes = normalize(b)
    assert b.score_target == 100 and not any("raised" in n for n in notes)  # the brief keeps what was said
    rules = json.dumps(assemble(b, 2, seed=1)["rules"])
    assert "score >= 320" in rules and "Score 320 points!" in rules  # the game makes it a real fight


def test_topdown_score_target_the_player_asked_for_is_kept():
    from spawnpoint.studio.brief import EnemyBrief, GameBrief, normalize

    b = GameBrief(title="t", genre="topdown", goal="score_target", score_target=200, difficulty=2,
                  enemies=[EnemyBrief(name="LaserTurret", archetype="turret", count=2)])
    b, notes = normalize(b)
    assert b.score_target == 200 and not any("raised" in n for n in notes)
    from spawnpoint.studio.assemble import assemble
    assert "score >= 200" in json.dumps(assemble(b, 2, seed=1)["rules"])


@pytest.mark.parametrize("kind", ["bubble", "rescue", "survivor", "farm", "tower_defense", "sword_platformer",
                                  "sword_topdown"])
def test_new_game_kinds_assemble_clean(manifest, kind):
    from spawnpoint.analyze import analyze
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import CollectibleBrief, EnemyBrief, GameBrief, PlayerBrief, normalize

    briefs = {
        "bubble": GameBrief(title="Dino Pop", genre="bubble", player=PlayerBrief(character="Dino"),
                            collectible=CollectibleBrief(name="Egg")),
        "rescue": GameBrief(title="Save Mom", genre="platformer", goal="rescue", rescue_target="Mom",
                            player=PlayerBrief(character="Ninja", abilities=["stomp"]),
                            enemies=[EnemyBrief(name="Slime", archetype="walker", count=3)]),
        "survivor": GameBrief(title="Night", genre="topdown", goal="survive", level_ups=True,
                              enemies=[EnemyBrief(name="Bat", archetype="chaser", count=3)]),
        "farm": GameBrief(title="Valley", genre="farm", art_style="cartoon", crops=["carrots", "Corn"],
                          player=PlayerBrief(character="Farmer", abilities=["sword"]),
                          enemies=[EnemyBrief(name="Crow", archetype="walker", count=3),
                                   EnemyBrief(name="Fox", archetype="chaser", count=2)]),
        "tower_defense": GameBrief(title="Siege", genre="tower_defense", towers=["Archer", "Cannon", "Mage"],
                                   enemies=[EnemyBrief(name="Goblin", archetype="walker"),
                                            EnemyBrief(name="Ogre", archetype="walker", speed="slow")]),
        "sword_platformer": GameBrief(title="Knight", genre="platformer", goal="defeat_all",
                                      player=PlayerBrief(character="Knight", abilities=["sword"]),
                                      enemies=[EnemyBrief(name="Slime", archetype="walker", count=3)]),
        "sword_topdown": GameBrief(title="Blade", genre="topdown", goal="defeat_all",
                                   player=PlayerBrief(character="Samurai", abilities=["sword", "dash"]),
                                   enemies=[EnemyBrief(name="Skeleton", archetype="chaser", count=3)]),
    }
    brief, _ = normalize(briefs[kind])
    for layer in (0, 1, 2):
        graph = assemble(brief, layer, seed=3)
        a = analyze(graph, manifest)
        warnings = [d for d in a.diagnostics.warnings if not (layer == 0 and d.code == "W_NO_WIN")]  # L0 = controls
        assert a.ok and not warnings, (kind, layer, [str(d) for d in a.diagnostics])
    ents, rules = graph["entities"], json.dumps(graph["rules"])
    if kind == "bubble":
        assert "BubbleBoard" in ents["Player"]["components"] and "win()" in rules and "lose()" in rules
    elif kind == "rescue":
        assert {"Cage", "CageKey", "Mom"} <= set(ents) and "Cage.open()" in rules
        assert "hair" in ents["Mom"]["sprite"]["generate"]["features"]
    elif kind == "farm":
        player = ents["Player"]["components"]
        assert player["Farmer"]["crops"].startswith("Carrot|") and "Corn|" in player["Farmer"]["crops"]
        assert ents["Slash"]["sprite"]["generate"]["kind"] == "slash" and "Health" in player  # the fox bites
        assert "CropPest" in ents["Crow"]["components"] and "ChaseAI" in ents["Fox"]["components"]
        assert "art_style" not in graph["settings"]  # a cartoon request still gets pixel art
        assert "score >= 250" in rules and "lose()" in rules
    elif kind == "tower_defense":
        towers = ents["Commander"]["components"]["TowerBuilder"]["towers"]
        assert towers == "ArcherTower|50;CannonTower|110;MageTower|90"
        assert "Lair.WaveSpawner.cleared" in rules and "Ogre" in ents["Lair"]["components"]["WaveSpawner"]["waves"]
        assert ents["CannonTower"]["sprite"]["generate"]["kind"] == "turret" and "PathFollower" in ents["Goblin"]["components"]
    elif kind.startswith("sword"):
        assert ents["Player"]["components"]["Weapon"]["projectile"] == "Slash" and "Bullet" not in ents
    else:
        player = ents["Player"]["components"]
        assert {"Experience", "LevelUpMenu"} <= set(player) and player["Weapon"]["auto_fire"]
        assert "BatNest" in ents and "spawn('XpGem')" in rules and "time_limit" in rules


def test_pick_model_prefers_spawnpoint_then_adapters():
    from spawnpoint.studio.llm import pick_model

    ollama = [{"id": "bge-m3:latest"}, {"id": "qwen3:4b"}, {"id": "hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M"}]
    assert pick_model(ollama) == "hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M"
    vllm = [{"id": "base"}, {"id": "coder-v1", "parent": "base"}]
    assert pick_model(vllm) == "coder-v1"
    assert pick_model([{"id": "gpt-x"}]) == "gpt-x"


def test_default_base_url_falls_back_to_ollama(monkeypatch):
    from spawnpoint.studio import llm

    monkeypatch.delenv("SPAWNPOINT_LLM_BASE_URL", raising=False)
    monkeypatch.setattr(llm, "_answers", lambda url: url == llm.OLLAMA_BASE_URL)
    assert llm.default_base_url() == llm.OLLAMA_BASE_URL
    monkeypatch.setattr(llm, "_answers", lambda url: True)
    assert llm.default_base_url() == llm.DEFAULT_BASE_URL
    monkeypatch.setenv("SPAWNPOINT_LLM_BASE_URL", "http://example:1/v1")
    assert llm.default_base_url() == "http://example:1/v1"


def test_llm_backend_choice(monkeypatch):
    from spawnpoint import llm_server

    tools = {"docker", "nvidia-smi", "ollama"}
    monkeypatch.setattr(llm_server.shutil, "which", lambda t: t if t in tools else None)
    assert llm_server.pick_backend() == "vllm"
    tools.discard("nvidia-smi")
    assert llm_server.pick_backend() == "ollama"
    tools.clear()
    with pytest.raises(RuntimeError, match="Ollama"):
        llm_server.pick_backend()
    assert llm_server.pick_backend("vllm") == "vllm"


def test_normalize_farm_and_tower_defense():
    from spawnpoint.studio.brief import EnemyBrief, GameBrief, PlayerBrief, normalize

    farm, notes = normalize(GameBrief(title="f", genre="farm", goal="survive", hazards=["spikes"],
                                      player=PlayerBrief(abilities=["shoot", "sword", "double_jump"])))
    assert farm.goal == "score_target" and farm.crops == ["Carrot", "Tomato", "Pumpkin"]
    assert farm.player.abilities == ["sword"] and not farm.hazards and notes
    td, _ = normalize(GameBrief(title="t", genre="tower_defense", towers=["archers", "Goblin"],
                                enemies=[EnemyBrief(name="Goblins", archetype="chaser")],
                                player=PlayerBrief(abilities=["shoot"])))
    assert td.goal == "defend" and td.player.abilities == [] and td.towers == ["ArcherTower", "GoblinTower"]
    td2, _ = normalize(GameBrief(title="t", genre="tower_defense"))
    assert td2.enemies and td2.towers == ["ArcherTower", "CannonTower"]
    both, notes = normalize(GameBrief(title="b", genre="topdown", player=PlayerBrief(abilities=["sword", "shoot"])))
    assert both.player.abilities == ["shoot"] and any("one weapon" in n for n in notes)
    other, _ = normalize(GameBrief(title="o", genre="platformer", goal="defend"))
    assert other.goal == "survive"


def test_level_ups_turn_a_platformer_into_a_survivor():
    from spawnpoint.studio.brief import GameBrief, PlayerBrief, normalize

    b, notes = normalize(GameBrief(title="s", genre="platformer", goal="survive", level_ups=True, hazards=["pits"],
                                   player=PlayerBrief(abilities=["stomp", "dash"])))
    assert b.genre == "topdown" and b.level_ups and b.goal == "survive" and not b.hazards
    assert b.player.abilities == ["dash", "shoot"] and any("survivor" in n for n in notes)
    plain, _ = normalize(GameBrief(title="p", genre="platformer", goal="reach_exit"))
    assert plain.genre == "platformer"
