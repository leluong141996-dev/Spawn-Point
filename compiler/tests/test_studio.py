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
    tiles = lambda g: [r.translate(str.maketrans("PC1234^+DEO", "." * 11)).rstrip(".") for r in g["level"]["map"]]
    assert tiles(l0) == tiles(l2)  # same geometry across layers


def test_deterministic_and_cosmetic_tweaks_keep_the_map():
    b, _ = normalize(brief())
    assert assemble(b, 2, 7) == assemble(b, 2, 7)
    recolored, _ = normalize(b.model_copy(update={"palette": "lava", "juice": "wild"}))
    assert assemble(b, 2, 7)["level"]["map"] == assemble(recolored, 2, 7)["level"]["map"]


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
