import json

import pytest
from PIL import Image

from spawnpoint import godot
from spawnpoint.build import build
from spawnpoint.playtest import goal_entities, merge_tuning, playtest
from spawnpoint.playtest.report import aggregate, heatmap, markdown
from spawnpoint.playtest.runner import time_limit
from spawnpoint.playtest.tuner import Change, propose, score, targets

from conftest import load_example


def run(profile, outcome="won", deaths=(), missed=0, intended=10, collected=5, total=5, unreachable=(), hits=0):
    return {"profile": profile, "run": 0, "outcome": outcome, "time": 20.0, "score": 0, "lives_left": 1,
            "deaths": [{"x": x, "y": 5, "cause": c, "t": 1.0, "after_jump": aj} for c, x, aj in deaths],
            "damage": [{"x": 0, "y": 0, "cause": "Slime", "t": 1.0}] * hits, "stuck": [], "unreachable": list(unreachable),
            "jumps": {"intended": intended, "performed": intended - missed, "missed": [{"x": 0, "y": 0}] * missed},
            "pickups": {"total": total, "collected": collected}}


def graph():
    g = load_example("pixel_hopper.json")
    return json.loads(json.dumps(g))


def test_aggregate_and_markdown():
    rep = aggregate([run("novice", "lost", [("Spikes", 3, False), ("Spikes", 4, False), ("fall", 9, True)], missed=4),
                     run("novice"), run("expert")])
    n = rep.get("novice")
    assert n.win_rate == 0.5 and n.deaths == 3 and n.causes == {"Spikes": 2, "fall": 1}
    assert n.falls_after_jump == 1 and n.missed_rate == 0.2
    md = markdown(rep, "Test", ["Player.Health.max_health = 4 — reason"])
    assert "| novice | 1/2 |" in md and "Tuning applied" in md


def test_level_issues_only_for_goal_entities():
    u = [{"entity": "Coin", "x": 3, "y": 2, "reason": "no_path"}, {"entity": "Slime", "x": 9, "y": 2, "reason": "no_path"}]
    rep = aggregate([run("expert", "timeout", unreachable=u)], {"Coin"})
    assert rep.level_issues == ["Coin at (3,2) has no path from the player",
                                "even the expert bot never won — the goal may be impossible or the time too short"]


def test_targets_and_score():
    assert targets(1)["novice"] == 0.8 and targets(5)["novice"] == 0.3
    good = aggregate([run("novice", deaths=[("Slime", 3, False)]), run("average"), run("expert")])
    bad = aggregate([run("novice", "lost"), run("average", "lost"), run("expert")])
    flawless = aggregate([run("novice"), run("average"), run("expert")])
    assert score(good, 2) == 0 and score(bad, 2) > 1
    assert score(flawless, 2) == 0.3 and score(flawless, 1) == 0  # nobody ever dies: no challenge
    grazed = aggregate([run("novice", hits=2), run("average"), run("expert")])
    assert 0 < score(grazed, 2) < score(flawless, 2)  # getting hit at all is progress


def test_rule_missed_jumps_raise_coyote_and_buffer(manifest):
    g = graph()
    rep = aggregate([run("novice", missed=5, intended=10), run("average")])
    changes = {(c.entity, c.param): c.value for c in propose(rep, g, g, manifest)}
    assert changes[("Player", "coyote_time")] == pytest.approx(0.14)
    assert changes[("Player", "jump_buffer")] == pytest.approx(0.16)


def test_rule_dominant_enemy_slows_down(manifest):
    g = graph()
    rep = aggregate([run("novice", "lost", [("Slime", 3, False)] * 3), run("average", "lost", [("Slime", 4, False)])])
    changes = {(c.entity, c.component, c.param): c.value for c in propose(rep, g, g, manifest)}
    assert changes[("Slime", "PlatformerMovement", "max_speed")] == pytest.approx(51.0)
    assert changes[("Player", "Health", "max_health")] == 4


def test_rule_spikes_shrink_hurtbox_and_bounds(manifest):
    g = graph()
    g["entities"]["Player"]["components"]["Hurtbox"] = {"size_scale": 0.6}
    rep = aggregate([run("novice", "lost", [("Spikes", 3, False)] * 3), run("average", "lost", [("Spikes", 3, False)])])
    keys = {(c.entity, c.component, c.param) for c in propose(rep, g, g, manifest)}
    assert ("Player", "Hurtbox", "size_scale") not in keys  # already at the floor


def test_rule_bullets_lower_fire_rate(manifest):
    g = load_example("pixel_arena.json")
    rep = aggregate([run("novice", "lost", [("EnemyBullet", 3, False)] * 3), run("average", "lost", [("EnemyBullet", 3, False)])])
    changes = {(c.entity, c.param): c.value for c in propose(rep, g, g, manifest)}
    assert changes[("Shooter", "fire_rate")] == pytest.approx(1.3 * 0.85, abs=0.01)


def test_rule_too_easy_steps_up_every_threat(manifest):
    g = graph()
    rep = aggregate([run("novice"), run("novice"), run("average"), run("expert")])
    assert propose(rep, g, g, manifest, difficulty=1) == []  # easy games may be easy
    hard = {(c.entity, c.param) for c in propose(rep, g, g, manifest, difficulty=2)}
    assert {("Slime", "max_speed"), ("Frog", "max_speed")} <= hard
    died = aggregate([run("novice", deaths=[("Slime", 3, False)]), run("average")])
    assert propose(died, g, g, manifest, difficulty=2) == []  # someone died: there is a challenge


def test_rule_too_easy_top_down_shooters_and_spawners(manifest):
    g = json.loads(json.dumps(load_example("pixel_arena.json")))
    rep = aggregate([run("novice"), run("average"), run("expert")])
    changes = {(c.entity, c.component, c.param): c.value for c in propose(rep, g, g, manifest, difficulty=2)}
    assert ("Shooter", "Weapon", "fire_rate") in changes
    assert not any(e == "Player" for e, _, _ in changes)
    spawners = [n for n, e in g["entities"].items() if "Spawner" in e.get("components", {})]
    for n in spawners:
        assert (n, "Spawner", "interval") in changes and (n, "Spawner", "max_alive") in changes


def test_bounds_are_relative_to_the_original(manifest):
    original = graph()
    tuned = graph()
    tuned["entities"]["Slime"]["components"]["PlatformerMovement"]["max_speed"] = 31
    rep = aggregate([run("novice", "lost", [("Slime", 3, False)] * 3), run("average", "lost", [("Slime", 3, False)])])
    c = next(c for c in propose(rep, tuned, original, manifest) if c.entity == "Slime")
    assert c.value == 30  # floor: 50% of the original 60


def test_merge_tuning_latest_wins():
    old = [{"entity": "Player", "component": "Health", "param": "max_health", "value": 4}]
    new = merge_tuning(old, [Change("Player", "Health", "max_health", 5, "r"), Change("Slime", "PatrolAI", "speed_scale", 0.8, "r")])
    assert {(t["entity"], t["value"]) for t in new} == {("Player", 5), ("Slime", 0.8)}


def test_time_limit_and_goal_entities():
    g = graph()
    assert 45 <= time_limit(g) <= 240
    assert time_limit(load_example("pixel_arena.json"), {"goal": "survive", "survive_seconds": 120}) == 135
    assert goal_entities(g) == {"Coin", "Heart", "Exit"}


def test_heatmap_renders(tmp_path, manifest):
    from spawnpoint.analyze import analyze
    plan = analyze(graph(), manifest).plan
    out = heatmap(plan, [run("novice", "lost", [("Spikes", 3, False), ("fall", 20, True)])], tmp_path / "h.png")
    img = Image.open(out)
    assert img.width == plan["map"]["width"] * 12


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
def test_playtest_end_to_end(tmp_path):
    out = tmp_path / "game"
    assert build(load_example("pixel_hopper.json"), out).ok
    res = playtest(out, runs=1, profiles=("expert",))
    exp = res.final.get("expert")
    assert exp.runs == 1 and exp.wins == 1, res.final.to_dict()["profiles"]
    assert (out / "playtest" / "heatmap.png").exists() and (out / "playtest" / "report.md").exists()
