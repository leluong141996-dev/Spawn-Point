"""The cast page shown while a game builds, and "new look" (other colours and details, same game)."""

import json

from spawnpoint.studio import cast
from spawnpoint.studio.assemble import assemble, look_color
from spawnpoint.studio.brief import GameBrief, normalize
from spawnpoint.studio_cli import LOOK_BACK, LOOK_NEW


def _fox() -> GameBrief:
    return normalize(GameBrief(title="Star Collector", genre="platformer", palette="candy", player={"character": "Fox"},
                               enemies=[{"name": "Slime", "archetype": "walker", "count": 3}],
                               collectible={"name": "Star", "count": 8}, goal="collect_all"))[0]


def test_a_new_look_changes_the_art_and_nothing_else():
    a, b = assemble(_fox(), 2, 4), assemble(_fox(), 2, 4, look=1)
    assert a["level"] == b["level"] and a["rules"] == b["rules"], "same level, same rules"
    pa, pb = a["entities"]["Player"]["sprite"]["generate"], b["entities"]["Player"]["sprite"]["generate"]
    assert pa["kind"] == pb["kind"] and pa["features"] == pb["features"], "still the same fox"
    assert pa["color"] != pb["color"] and pa["seed"] != pb["seed"]
    assert look_color("#29adff", 0) == "#29adff"
    strip = lambda g: {n: {k: v for k, v in e.items() if k != "sprite"} for n, e in g["entities"].items()}  # noqa: E731
    assert strip(a) == strip(b), "components and tuning are untouched"


def test_look_requests_in_english_and_vietnamese():
    for t in ("new look", "give me another look", "đổi hình nhân vật", "reroll"):
        assert LOOK_NEW.search(t), t
    for t in ("old look", "quay lại hình cũ"):
        assert LOOK_BACK.search(t), t
    for t in ("make the jump higher", "look at the boss", "đổi màu ban đêm"):
        assert not LOOK_NEW.search(t) and not LOOK_BACK.search(t), t


def test_cast_roles_put_the_hero_first_then_the_boss():
    g = assemble(normalize(GameBrief(title="Frost Spire", genre="cards", palette="snow", hero_class="mage",
                                     enemies=[{"name": "Yeti", "archetype": "brute"}], boss="IceQueen"))[0], 2, 3)
    assert cast.roles(g) == [("Player", "hero"), ("IceQueen", "boss"), ("Yeti", "foe")]


def test_the_cast_page_waits_for_the_game(tmp_path, manifest):
    out = tmp_path / "game"
    (out / "web").mkdir(parents=True)
    (out / "web" / "version.json").write_text("{}")  # an earlier build of this game
    members = cast.write(out, assemble(_fox(), 2, 4), manifest, hero="Fox")
    web = out / "web"
    assert not (web / "version.json").exists(), "an old build is not shown as ready"
    assert [m[1] for m in members][:2] == ["hero", "foe"]
    assert all((web / "cast" / f"{i}.gif").exists() for i in range(len(members)))
    page = (web / "index.html").read_text()
    assert "Star Collector" in page and ">Fox<" in page and "version.json" in page
    cast.status(out, "Ready!")
    assert json.loads((web / "status.json").read_text()) == {"text": "Ready!"}
