"""The v5 wire format: one small schema per genre."""

import json

import pytest

from spawnpoint.studio import genres
from spawnpoint.studio.assemble import assemble
from spawnpoint.studio.brief import GameBrief, normalize
from spawnpoint.studio.llm import ScriptedModel
from spawnpoint.studio.orchestrator import create, design_brief, load_session, tweak
from spawnpoint.studio.prompts import BRIEF_SYSTEM, BRIEF_SYSTEM_V5, FARM_LINE, brief_format, brief_messages, brief_messages_v5

BRIEFS = {
    "platformer": dict(title="a", genre="platformer", player={"character": "Fox", "abilities": ["stomp", "sword"]},
                       enemies=[{"name": "Slime", "archetype": "walker"}], hazards=["spikes"], feel="floaty"),
    "topdown": dict(title="b", genre="topdown", goal="survive", level_ups=True, art_style="cartoon",
                    enemies=[{"name": "Bat", "archetype": "chaser"}]),
    "bubble": dict(title="c", genre="bubble", player={"character": "Dino"}, collectible={"name": "Egg"}),
    "farm": dict(title="d", genre="farm", player={"character": "Bunny", "abilities": ["sword"]}, crops=["Carrot", "Corn"],
                 enemies=[{"name": "Crow", "archetype": "walker"}, {"name": "Fox", "archetype": "chaser"}], score_target=300,
                 survive_seconds=240),
    "tower_defense": dict(title="e", genre="tower_defense", towers=["Archer", "Mage"],
                          enemies=[{"name": "Goblin", "archetype": "walker"}, {"name": "Ogre", "archetype": "walker", "speed": "slow"}]),
    "shmup": dict(title="f", genre="shmup", player={"character": "Falcon", "health": 4}, boss="Warship",
                  enemies=[{"name": "Drone", "archetype": "drifter"}, {"name": "Saucer", "archetype": "weaver", "count": 5}]),
}


@pytest.fixture
def v5(monkeypatch):
    monkeypatch.setenv("SPAWNPOINT_BRIEF_FORMAT", "v5")


@pytest.mark.parametrize("genre", sorted(BRIEFS))
def test_every_genre_round_trips_and_is_shorter(genre):
    brief, _ = normalize(GameBrief(**BRIEFS[genre]))
    wire = genres.to_wire(brief)
    assert list(wire)[0] == "genre" and wire["genre"] == genre
    again, _ = normalize(genres.parse_wire(wire))
    assert again.model_dump() == brief.model_dump()
    assert len(json.dumps(wire)) < len(json.dumps(brief.model_dump()))
    # only this genre's fields exist
    foreign = {"crops": "farm", "towers": "tower_defense", "boss": "shmup", "level_ups": "topdown", "rescue_target": "platformer"}
    assert not any(k in wire and g != genre for k, g in foreign.items())


def test_wire_ignores_unknown_keys_and_rejects_unknown_genres():
    brief, _ = normalize(GameBrief(**BRIEFS["platformer"]))
    assert genres.parse_wire(brief.model_dump()).genre == "platformer"  # a GameBrief-shaped answer still parses
    with pytest.raises(ValueError):
        genres.parse_wire({"genre": "racing"})
    with pytest.raises(ValueError):
        genres.parse_wire({"title": "x"})


def test_schema_is_a_closed_union_of_the_genres():
    schema = genres.wire_schema()
    assert [r["$ref"].split("/")[-1] for r in schema["oneOf"]] == [f"{g.__name__}" for g in genres.WIRE_BY_GENRE.values()]
    assert "discriminator" not in json.dumps(schema)
    for name, d in schema["$defs"].items():
        if d.get("type") == "object":
            assert d["additionalProperties"] is False, name
        if name.endswith("W"):
            assert list(d["properties"])[0] == "genre", name  # the genre comes first
    assert genres.wire_tweak_schema()["properties"]["brief"]["oneOf"]


def test_the_wire_models_allow_only_what_the_genre_has():
    with pytest.raises(Exception):
        genres.FarmW.model_validate({"genre": "farm", "title": "x", "abilities": ["shoot"]})
    with pytest.raises(Exception):
        genres.TopdownW.model_validate({"genre": "topdown", "title": "x", "enemies": [{"name": "A", "archetype": "walker"}]})
    assert genres.ShmupW.model_validate({"genre": "shmup", "title": "x", "enemies": [{"name": "A", "archetype": "weaver"}]})


def test_v5_prompts_are_much_shorter():
    old = sum(len(m["content"]) for m in brief_messages("a game"))
    new = sum(len(m["content"]) for m in brief_messages_v5("a game"))
    assert new < old * 0.5, (old, new)
    for g in genres.GENRES:
        assert g in BRIEF_SYSTEM_V5
    assert len(BRIEF_SYSTEM_V5) < len(BRIEF_SYSTEM)


def test_the_format_defaults_to_v5_and_v4_stays_available(monkeypatch):
    monkeypatch.delenv("SPAWNPOINT_BRIEF_FORMAT", raising=False)
    assert brief_format() == "v5"
    monkeypatch.setenv("SPAWNPOINT_BRIEF_FORMAT", "v4")
    assert brief_format() == "v4"
    monkeypatch.setenv("SPAWNPOINT_BRIEF_FORMAT", "V5")
    assert brief_format() == "v5"


def test_design_brief_in_v5(v5):
    wire = genres.to_wire(normalize(GameBrief(**BRIEFS["farm"]))[0])
    llm = ScriptedModel([wire])
    brief, notes, english = design_brief("trang trại thỏ", llm)  # Vietnamese goes straight to the designer
    assert english == "trang trại thỏ" and len(llm.seen) == 1
    assert brief.genre == "farm" and brief.crops == ["Carrot", "Corn"] and brief.score_target == 300
    system = llm.seen[0][0]["content"]
    # a system line (plus the farm words, since this is a farm) and the idea: no example turns
    assert system == BRIEF_SYSTEM_V5 + "\n" + FARM_LINE and len(llm.seen[0]) == 2


def test_create_and_tweak_in_v5(v5, tmp_path, manifest):
    wire = genres.to_wire(normalize(GameBrief(**BRIEFS["tower_defense"]))[0])
    out = tmp_path / "td"
    assert create("towers", out, ScriptedModel([wire]), web_export=False, manifest=manifest).ok
    session = load_session(out)
    assert session["brief"]["genre"] == "tower_defense" and session["brief"]["goal"] == "defend"  # sessions keep GameBrief
    llm = ScriptedModel([{"brief": dict(wire, palette="snow"), "new_level": False}])
    assert tweak(out, "snow", llm, web_export=False, manifest=manifest).ok
    sent = json.loads(llm.seen[0][-1]["content"].split("Game: ")[1].split("\nRequest:")[0])
    assert sent["genre"] == "tower_defense" and "player" not in sent  # the model sees the wire shape only
    assert load_session(out)["brief"]["palette"] == "snow"


def test_recorded_targets_use_the_wire_shape(v5, tmp_path, manifest):
    from spawnpoint.studio.dataset import Recorder

    wire = genres.to_wire(normalize(GameBrief(**BRIEFS["bubble"]))[0])
    rec = Recorder(tmp_path / "data")
    assert create("eggs", tmp_path / "g", ScriptedModel([wire]), web_export=False, manifest=manifest, recorder=rec).ok
    records = [json.loads(line) for f in (tmp_path / "data").glob("*.jsonl") for line in f.read_text().splitlines()]
    brief_rec = next(r for r in records if r["task"] == "brief")
    assert brief_rec["target"]["genre"] == "bubble" and "item" in brief_rec["target"] and "player" not in brief_rec["target"]
    assert brief_rec["corrected"] is False


# --- the shmup genre ---------------------------------------------------------------------------

def _shmup(**over):
    d = dict(BRIEFS["shmup"], **over)
    brief, notes = normalize(GameBrief(**d))
    return brief, notes


def test_shmup_normalization():
    b, notes = _shmup(goal="collect_all", player={"character": "Falcon", "abilities": ["dash", "shoot"]}, hazards=["spikes"])
    assert b.goal == "defeat_boss" and b.player.abilities == [] and not b.hazards and b.collectible.count == 0
    assert b.boss == "Warship" or b.boss  # a shooter that is won by a boss has one
    none, notes = normalize(GameBrief(title="s", genre="shmup"))
    assert [e.name for e in none.enemies] == ["Drone", "Saucer"] and none.boss == "Warship"
    assert any("added" in n for n in notes)
    legacy, _ = normalize(GameBrief(title="s", genre="shmup", enemies=[{"name": "Bat", "archetype": "chaser"},
                                                                         {"name": "Gun", "archetype": "turret"}]))
    assert [e.archetype for e in legacy.enemies] == ["diver", "gunship"]
    other, notes = normalize(GameBrief(title="p", genre="platformer", goal="defeat_boss", boss="Big"))
    assert other.goal == "reach_exit" and other.boss == ""
    score, _ = _shmup(goal="score_target", boss="Big")
    assert score.boss == "Big"  # a name is kept, but it is only used with defeat_boss
    clash, _ = _shmup(boss="Drone")
    assert clash.boss != "Drone", "the boss must not share a name with an enemy"


@pytest.mark.parametrize("goal", ["defeat_boss", "score_target", "survive"])
@pytest.mark.parametrize("style", ["pixel", "cartoon"])
def test_shmup_assembles_clean(manifest, goal, style):
    from spawnpoint.analyze import analyze

    brief, _ = _shmup(goal=goal, art_style=style)
    for layer in (0, 1, 2):
        graph = assemble(brief, layer, seed=3)
        a = analyze(graph, manifest)
        warnings = [d for d in a.diagnostics.warnings if not (layer == 0 and d.code == "W_NO_WIN")]
        assert a.ok and not warnings, (goal, layer, [str(d) for d in a.diagnostics])
    ents, rules = graph["entities"], json.dumps(graph["rules"])
    player = ents["Player"]["components"]
    assert {"ShmupShip", "Weapon", "PlayerInput"} <= set(player) and ents["Player"]["sprite"]["generate"]["kind"] == "ship"
    assert {"Drone", "Saucer"} <= set(ents) and "FlightPath" in ents["Saucer"]["components"]
    assert ents["Saucer"]["components"]["FlightPath"]["pattern"] == "wave"
    assert "Player.power_up()" in rules and "spawn('PowerUp')" in rules
    assert graph["settings"]["scenery"] == "space" and "#" not in "".join(graph["level"]["map"])
    spawner = ents["Lair"]["components"]["WaveSpawner"]
    assert spawner["endless"] == (goal != "defeat_boss")
    if goal == "defeat_boss":
        assert "BossGate" in ents and ents["BossGate"]["components"]["WaveSpawner"]["autostart"] is False
        assert "BossGate.start()" in rules and "Warship.died" in rules and ents["Warship"]["sprite"]["generate"]["size"] == 3
    else:
        assert "BossGate" not in ents and "G" not in "".join(graph["level"]["map"])


def test_shmup_waves_introduce_every_type_and_scale_with_difficulty():
    easy, _ = _shmup(difficulty=1, enemies=[{"name": "Drone", "archetype": "drifter"}, {"name": "Saucer", "archetype": "weaver"},
                                            {"name": "Hunter", "archetype": "diver"}, {"name": "Cruiser", "archetype": "gunship"}])
    hard, _ = _shmup(difficulty=5, enemies=[e.model_dump() for e in easy.enemies])
    from spawnpoint.studio.assemble import _Assembler

    def waves(b):
        text = _Assembler(b, 2, 0)._shmup_waves()
        return [(int(p.split(" x ")[0]), p.split(" x ")[1].split(" every")[0]) for p in text.split("; ")]
    e, h = waves(easy), waves(hard)
    assert {name for _, name in e} == {"Drone", "Saucer", "Hunter", "Cruiser"}, e
    assert [n for _, n in e][0] == "Drone", "the easiest type opens"
    assert sum(c for c, _ in h) > sum(c for c, _ in e)


def test_shmup_wire_round_trip_through_a_session(v5, tmp_path, manifest):
    wire = genres.to_wire(_shmup()[0])
    out = tmp_path / "shmup"
    assert create("space shooter", out, ScriptedModel([wire]), web_export=False, manifest=manifest).ok
    session = load_session(out)
    assert session["brief"]["genre"] == "shmup" and session["brief"]["boss"] == "Warship"
    llm = ScriptedModel([{"brief": dict(wire, boss="Dreadnought", difficulty=4), "new_level": False}])
    assert tweak(out, "harder, bigger boss", llm, web_export=False, manifest=manifest).ok
    s2 = load_session(out)["brief"]
    assert s2["boss"] == "Dreadnought" and s2["difficulty"] == 4
