"""The card game (deckbuilder): the brief and wire format, the assembler's battle data and the card art."""

import re

import numpy as np
import pytest

from spawnpoint.analyze import analyze
from spawnpoint.sprites import battle, fx, pixelfont
from spawnpoint.sprites import cards as C
from spawnpoint.studio import genres, prompts
from spawnpoint.studio.assemble import CARD_CLASSES, assemble, card_icon, natural_color
from spawnpoint.studio.brief import CardBrief, EnemyBrief, GameBrief, normalize


def _brief(**kw) -> GameBrief:
    base = dict(title="Spire", genre="cards", palette="night",
                enemies=[EnemyBrief(name="Skeleton", archetype="brute"), EnemyBrief(name="Bat", archetype="swarm")],
                cards=[CardBrief(name="flame slash", kind="heavy"), CardBrief(name="Holy Shield", kind="block")])
    base.update(kw)
    return normalize(GameBrief(**base))[0]


def _battle(g: dict) -> dict:
    return g["entities"]["Player"]["components"]["CardBattle"]


def test_normalize_sets_the_goal_boss_and_card_names():
    b, notes = normalize(GameBrief(title="T", genre="cards", goal="collect_all", palette="snow",
                                   player={"abilities": ["dash"]},
                                   cards=[CardBrief(name="fire ball", kind="heavy"), CardBrief(name="Fire|Ball;", kind="strike")]))
    assert b.goal == "defeat_boss" and b.boss == "Yeti"  # the theme picks a boss when none is named
    assert b.player.abilities == []
    assert [c.name for c in b.cards] == ["Fire Ball"], "separators removed, duplicates merged"
    assert [e.archetype for e in b.enemies] == ["swarm", "brute"], "a card game always has foes"
    assert any("goal" in n for n in notes)


def test_other_genres_drop_cards_and_card_archetypes_fall_back():
    b, _ = normalize(GameBrief(title="T", genre="platformer", cards=[CardBrief(name="Zap")],
                               enemies=[EnemyBrief(name="Ogre", archetype="brute")]))
    assert b.cards == [] and b.enemies[0].archetype == "walker"
    c, _ = normalize(GameBrief(title="T", genre="cards", enemies=[EnemyBrief(name="Imp", archetype="shooter")]))
    assert c.enemies[0].archetype == "caster"


def test_wire_round_trip():
    b = _brief(player={"character": "Witch"}, hero_class="mage", boss="Lich")
    wire = genres.to_wire(b)
    assert wire["genre"] == "cards" and wire["hero"] == "Witch" and wire["hero_class"] == "mage"
    assert wire["enemies"] == [{"name": "Skeleton", "archetype": "brute"}, {"name": "Bat", "archetype": "swarm"}]
    back = normalize(genres.parse_wire(wire))[0]
    assert genres.to_wire(back) == wire
    assert "CardsW" in str(genres.wire_schema())


def test_only_card_prompts_get_the_card_line():
    assert prompts.CARD_LINE in prompts.brief_messages_v5("a deckbuilder card game with skeletons")[0]["content"]
    assert prompts.CARD_LINE in prompts.brief_messages_v5("game thẻ bài đánh rồng")[0]["content"]
    plain = prompts.brief_messages_v5("a ninja platformer")[0]["content"]
    assert plain == prompts.BRIEF_SYSTEM_V5, "other prompts stay exactly as the released model was trained"


@pytest.mark.parametrize("hero_class", list(CARD_CLASSES))
def test_assembled_battle_data_parses_and_validates(hero_class, manifest):
    b = _brief(hero_class=hero_class)
    g = assemble(b, seed=4)
    battle = _battle(g)
    lib = {}
    for entry in battle["cards"].split(";"):
        name, cost, kind, fx, rarity, icon = entry.split("|")
        assert kind in ("attack", "skill", "power") and rarity in ("starter", "common", "uncommon", "rare")
        assert icon in C.ICONS and 0 <= int(cost) <= 3
        assert all(re.fullmatch(r"(dmg|hits|all|blk|draw|nrg|heal|poison|weak|vuln|str):\d+|exhaust", e) for e in fx.split(","))
        lib[name] = rarity
    for part in battle["starter"].split(","):
        assert lib[part.split("*")[0]] == "starter"
    assert "Holy Shield*4" in battle["starter"], "the game's own block card is the starting block"
    assert lib["Flame Slash"] == "common" and card_icon("Flame Slash", "axe") == "fire"
    foes = [f.split("|") for f in battle["foes"].split(";")]
    assert [f[0] for f in foes] == ["Skeleton", "Bat", b.boss] and foes[-1][2] == "boss"
    for f in foes:
        assert f[0] in g["entities"] and g["entities"][f[0]]["team"] == "enemy"
        for step in f[3].split(","):
            for move in step.split("+"):
                assert re.fullmatch(r"(atk:\d+(x\d+)?|blk:\d+|str:\d+|weak:\d+|vuln:\d+|poison:\d+|heal:\d+)", move), move
    a = analyze(g, manifest)
    assert a.ok, [str(x) for x in a.diagnostics]
    assert {"art_frame_attack", "art_ci_sword", "art_ci_crown", "art_fx_slash", "art_card_back", "scenery_ground"} \
        <= set(a.scenery_images)
    assert a.plan["pixel_font"] and a.plan["scenery"]["ground"].endswith("scenery_ground.png")
    sizes = {n: e["sprite"]["generate"]["size"] for n, e in g["entities"].items()}
    assert sizes[b.boss] == 4 and sizes["Player"] == 3, "big pixel portraits, the boss bigger"


def test_difficulty_makes_foes_tougher_and_length_adds_floors():
    easy, hard = (_battle(assemble(_brief(difficulty=d), seed=1)) for d in (1, 5))
    hp = lambda bt: [int(f.split("|")[1]) for f in bt["foes"].split(";")]  # noqa: E731
    assert all(h > e for e, h in zip(hp(easy), hp(hard)))
    assert [_battle(assemble(_brief(length=n), seed=1))["floors"] for n in ("short", "medium", "long")] == [5, 7, 9]


def test_card_art():
    for kind in ("attack", "skill", "power"):
        f = C.card_frame(kind)
        assert f.shape == (C.FRAME_H, C.FRAME_W, 4)
        assert f[0, 0, 3] == 0 and f[40, 1, 3] == 255, "rounded corners, solid border"
    frames = [C.card_frame(k)[30, 2, :3].tolist() for k in ("attack", "skill", "power")]
    assert len({tuple(x) for x in frames}) == 3, "each card type has its own colour"
    for name in C.ICONS:
        px = C.icon(name)
        assert px.shape == (16, 16, 4) and (px[..., 3] > 0).sum() > 40, name
    assert not np.array_equal(C.icon("sword"), C.icon("shield"))


def test_animals_keep_natural_colours():
    assert natural_color("DireWolf", "#9b5de5") == "#8a8a9a" and natural_color("Slime", "#123456") == "#123456"


@pytest.mark.parametrize("theme", list(battle.THEMES))
def test_backdrops(theme):
    img = battle.backdrop(theme, 2)
    assert img.shape == (battle.H, battle.W, 4) and (img[..., 3] == 255).all()
    assert len(np.unique(img.reshape(-1, 4), axis=0)) > 40, "a painted scene, not a flat fill"
    assert np.array_equal(img, battle.backdrop(theme, 2)), "deterministic"


def test_effect_strips():
    for name, (size, n, _p) in fx.EFFECTS.items():
        strip = fx.strip(name)
        assert strip.shape == (size, size * n, 4)
        assert all((strip[:, i * size:(i + 1) * size, 3] > 0).any() for i in range(n)), name


def test_pixel_font():
    files = pixelfont.font_files("pf")
    fnt, png = files["pf.fnt"], files["pf.png"]
    ids = {int(m) for m in re.findall(r"char id=(\d+)", fnt)}
    needed = set(range(ord("A"), ord("Z") + 1)) | set(range(ord("a"), ord("z") + 1)) | set(range(48, 58)) | {ord(c) for c in " .,:!?/+-%()'"}
    assert needed <= ids
    assert 'file="pf.png"' in fnt and png.shape[1] == int(re.search(r"scaleW=(\d+)", fnt).group(1))
    plain = pixelfont.font_files("pp", outline=False)["pp.png"]
    assert (plain[..., 3] > 0).sum() < (png[..., 3] > 0).sum(), "the plain font has no outline"
