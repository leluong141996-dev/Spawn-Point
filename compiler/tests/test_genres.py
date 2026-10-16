"""The v5 wire format: one small schema per genre."""

import json

import pytest

from spawnpoint.studio import genres
from spawnpoint.studio.assemble import assemble
from spawnpoint.studio.brief import GameBrief, normalize
from spawnpoint.studio.llm import ScriptedModel
from spawnpoint.studio.orchestrator import create, design_brief, load_session, tweak
from spawnpoint.studio.prompts import BRIEF_SYSTEM, BRIEF_SYSTEM_V5, brief_format, brief_messages, brief_messages_v5

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


def test_the_format_defaults_to_v4_until_the_v5_model_ships(monkeypatch):
    monkeypatch.delenv("SPAWNPOINT_BRIEF_FORMAT", raising=False)
    assert brief_format() == "v4"
    monkeypatch.setenv("SPAWNPOINT_BRIEF_FORMAT", "v5")
    assert brief_format() == "v5"


def test_design_brief_in_v5(v5):
    wire = genres.to_wire(normalize(GameBrief(**BRIEFS["farm"]))[0])
    llm = ScriptedModel([{"english": "a bunny farm"}, wire])
    brief, notes, english = design_brief("trang trại thỏ", llm)
    assert brief.genre == "farm" and brief.crops == ["Carrot", "Corn"] and brief.score_target == 300
    system = llm.seen[1][0]["content"]
    assert system == BRIEF_SYSTEM_V5 and len(llm.seen[1]) == 2  # a system line and the idea: no example turns


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
