"""The cozy farm: map generation (farmgen), its art (sprites/farm.py) and how the assembler wires them."""

import numpy as np
import pytest

from spawnpoint.analyze import analyze
from spawnpoint.sprites import farm as F
from spawnpoint.studio import farmgen
from spawnpoint.studio.assemble import assemble
from spawnpoint.studio.brief import EnemyBrief, GameBrief, normalize


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("length", ["short", "medium", "long"])
def test_every_farm_map_is_playable(seed, length):
    fm = farmgen.cozy_farm(seed, length)
    assert len(fm.terrain) == fm.height and all(len(r) == fm.width for r in fm.terrain)
    reach = farmgen.reachable(fm)
    # every plot, the shipping bin and the pen can be reached from the door
    assert fm.bin in reach and fm.door in reach
    blocked = fm.blocked()
    for p in fm.plots:
        assert p not in blocked and p in reach, p
    x0, y0, x1, y1 = fm.pen
    assert any((x, y) in reach for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)), "the pen has a gate"
    for c in fm.animals:
        assert x0 <= c[0] <= x1 and y0 <= c[1] <= y1
    # nothing stands on a path, and objects stay on the map
    paths = {(x, y) for y, r in enumerate(fm.terrain) for x, ch in enumerate(r) if ch == ":"}
    for kind, c in fm.objects:
        assert kind in farmgen.OBJECT_KINDS
        assert 0 <= c[0] < fm.width and 0 <= c[1] < fm.height
        assert kind == "farmhouse" or c not in paths
    assert farmgen.cozy_farm(seed, length).terrain == fm.terrain  # deterministic


def test_islands_have_water_all_round_and_meadows_do_not():
    kinds = {farmgen.cozy_farm(s).island for s in range(20)}
    assert kinds == {True, False}, "both kinds of map turn up"
    for s in range(20):
        fm = farmgen.cozy_farm(s)
        edge = fm.terrain[0] + fm.terrain[-1]
        assert (set(edge) == {"~"}) == fm.island
        assert all(c in fm.solid for c in ((0, 0), (fm.width - 1, fm.height - 1)))


def test_terrain_draws_paths_water_and_cliffs():
    rows = ["~~~~~~~~", "~......~", "~.::::.~", "~......~", "~~~~~~~~"]
    img = F.terrain_image(rows, 1)
    assert img.shape == (5 * 16, 8 * 16, 4) and (img[..., 3] == 255).all()
    colours = {tuple(p) for p in img.reshape(-1, 4).tolist()}
    for c in (F.DIRT, F.WATER, F.CLIFF, F.GRASS_EDGE):
        assert tuple(c) in colours, c
    # land drops into the water to the south: the cliff face is just below the bottom row of land
    assert tuple(img[4 * 16 + 2, 4 * 16]) in {tuple(F.CLIFF), tuple(F.CLIFF_LIGHT), tuple(F.CLIFF_DARK)}
    assert np.array_equal(F.terrain_image(rows, 1), img)


@pytest.mark.parametrize("name,kind", [("Strawberry", "strawberry"), ("GoldenCarrots", "carrot"), ("Potatoes", "potato"),
                                       ("Watermelon", "pumpkin"), ("Rice", "wheat"), ("Moonbloom", "berry")])
def test_crops_pick_their_drawing_from_the_name(name, kind):
    assert F.crop_kind(name) == kind


def test_crop_growth_stages_and_icons():
    sheet = F.crop_sheet("Pumpkin", "#ff9a2a")
    assert sheet.shape == (16, 80, 4)
    sizes = [(sheet[:, i * 16:(i + 1) * 16, 3] > 0).sum() for i in range(5)]
    assert all(s > 0 for s in sizes) and sizes[4] > sizes[1] > sizes[0], "the plant grows"
    for item in ("egg", "milk", "wood", "stone"):
        assert (F.item_icon(item)[..., 3] > 0).sum() > 30
    assert (F.crop_icon("Carrot", "#ff8a2a")[..., 3] > 0).sum() > 30
    wet, dry = F.soil_tile(True), F.soil_tile(False)
    assert wet[..., :3].mean() < dry[..., :3].mean(), "watered soil is darker"


@pytest.mark.parametrize("kind", sorted(F.SPRITES))
def test_farm_sprites_stand_on_their_base(kind):
    fr = F.frames(kind, F.SPRITES[kind][3])
    for anim, frames in fr.items():
        for f in frames:
            assert (f[..., 3] == 255).any(), (kind, anim)
    if kind == "farmer":
        assert {"idle", "run", "idle_up", "run_up", "idle_side", "run_side"} <= set(fr)
        assert not np.array_equal(fr["idle"][0], fr["idle_up"][0]), "front and back views differ"


def _farm_brief(**kw):
    b, _ = normalize(GameBrief(title="Sunny Farm", genre="farm", crops=["Strawberry", "Carrot", "Pumpkin"],
                               enemies=[EnemyBrief(name="Crow", archetype="walker", count=3)], **kw))
    return b


def test_assembled_farm_uses_the_cozy_map(manifest):
    g = assemble(_farm_brief(), 2, seed=3)
    s, ents = g["settings"], g["entities"]
    assert s["y_sort"] and s["terrain"] and s["tile_style"] == "flat"
    assert "pixel_palette" not in s and "pixel_size" not in s  # its own colours, chunky 16 px tiles
    assert {"crop_Strawberry", "icon_Strawberry", "soil", "soil_wet", "icon_egg"} <= set(s["art"])
    farmer = ents["Player"]["components"]["Farmer"]
    assert "res://sprites/art_crop_Strawberry.png" in farmer["crops"] and farmer["goods"].startswith("Egg|")
    assert ents["Player"]["sprite"]["generate"]["kind"] == "farmer"
    assert ents["ShippingBin"]["components"]["Market"]["stall"] is False
    assert ents["Chicken"]["components"]["FarmAnimal"]["product"] == "Egg"
    assert ents["Cow"]["components"]["FarmAnimal"]["product"] == "Milk"
    assert ents["Oak"]["components"]["Gatherable"]["leaves"] == "Stump" and "Stump" in ents
    assert ents["Farmhouse"]["base"] and ents["Farmhouse"]["body"] == "static"
    assert all("farm_kind" not in e for e in ents.values())
    a = analyze(g, manifest)
    assert a.ok, a.diagnostics.render()
    assert a.plan["scenery"] == {"ground": "res://sprites/scenery_ground.png", "pixel": 2} and a.plan["y_sort"]
    assert {"scenery_ground", "art_crop_Strawberry", "art_soil", "art_icon_milk"} <= set(a.scenery_images)
    house = next(e for e in a.plan["entities"] if e["name"] == "Farmhouse")
    assert house["sprite"]["polygon"] == [] and house["shape_offset"][1] < 0  # the footprint collides, at its feet


@pytest.mark.parametrize("layer", [0, 1])
def test_placeholder_farm_layers_still_compile(manifest, layer):
    g = assemble(_farm_brief(), layer, seed=5)
    assert all("sprite" not in e and "farm_kind" not in e for e in g["entities"].values())
    a = analyze(g, manifest)
    assert a.ok, a.diagnostics.render()


def test_ocean_farms_are_islands_and_forest_farms_are_meadows():
    for seed in range(4):
        assert assemble(_farm_brief(palette="ocean"), 2, seed=seed)["settings"]["terrain"][0].strip("~") == ""
        assert "~" not in assemble(_farm_brief(palette="forest"), 2, seed=seed)["settings"]["terrain"][0]


def test_only_farm_prompts_get_the_farm_vocabulary():
    from spawnpoint.studio.prompts import BRIEF_SYSTEM_V5, FARM_LINE, brief_messages_v5
    assert brief_messages_v5("a ninja platformer with slimes")[0]["content"] == BRIEF_SYSTEM_V5
    for p in ("game nông trại trên đảo, trồng dâu tây", "a farming game with pumpkins", "thu hoạch cà rốt"):
        assert FARM_LINE in brief_messages_v5(p)[0]["content"], p
