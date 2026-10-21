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
        edge = fm.terrain[0] + fm.terrain[fm.outdoor_height - 1]
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
    assert a.ok, [str(x) for x in a.diagnostics]
    assert a.plan["scenery"] == {"ground": "res://sprites/scenery_ground.png", "pixel": 2} and a.plan["y_sort"]
    assert {"scenery_ground", "art_crop_Strawberry", "art_soil", "art_icon_milk"} <= set(a.scenery_images)
    house = next(e for e in a.plan["entities"] if e["name"] == "Farmhouse")
    assert house["sprite"]["polygon"] == [] and house["shape_offset"][1] < 0  # the footprint collides, at its feet


@pytest.mark.parametrize("layer", [0, 1])
def test_placeholder_farm_layers_still_compile(manifest, layer):
    g = assemble(_farm_brief(), layer, seed=5)
    assert all("sprite" not in e and "farm_kind" not in e for e in g["entities"].values())
    a = analyze(g, manifest)
    assert a.ok, [str(x) for x in a.diagnostics]


def test_ocean_farms_are_islands_and_forest_farms_are_meadows():
    for seed in range(4):
        assert assemble(_farm_brief(palette="ocean"), 2, seed=seed)["settings"]["terrain"][0].strip("~") == ""
        assert "~" not in assemble(_farm_brief(palette="forest"), 2, seed=seed)["settings"]["terrain"][0]


def test_only_farm_prompts_get_the_farm_vocabulary():
    from spawnpoint.studio.prompts import BRIEF_SYSTEM_V5, FARM_LINE, brief_messages_v5
    assert brief_messages_v5("a ninja platformer with slimes")[0]["content"] == BRIEF_SYSTEM_V5
    for p in ("game nông trại trên đảo, trồng dâu tây", "a farming game with pumpkins", "thu hoạch cà rốt"):
        assert FARM_LINE in brief_messages_v5(p)[0]["content"], p



@pytest.mark.parametrize("seed", range(6))
def test_the_farmhouse_has_a_room_inside(seed):
    fm = farmgen.cozy_farm(seed)
    x0, y0, x1, y1 = fm.room
    assert y0 > fm.outdoor_height + farmgen.SEA_GAP, "past the sea and the darkness"
    inside = farmgen.reachable(fm, fm.door_mat)
    assert fm.player not in inside, "only the warps connect the house and the farm"
    furniture = [c for k, c in fm.objects if k in ("bed", "fireplace", "table", "dresser")]
    assert len(furniture) == 4 and all(x0 <= c[0] <= x1 and y0 <= c[1] <= y1 for c in furniture)
    assert sum(1 for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if (x, y) in inside) >= 20, "room to walk"
    g = assemble(_farm_brief(), 2, seed=seed)
    warps = {n: e["components"]["Warp"] for n, e in g["entities"].items() if "Warp" in e["components"]}
    assert set(warps) == {"HouseDoor", "DoorMat"}
    assert warps["HouseDoor"]["to"][1] > fm.outdoor_height * 32 and warps["DoorMat"]["to"][1] < fm.outdoor_height * 32


def test_doorways_stay_invisible():
    g = assemble(_farm_brief(), 2, seed=1)
    for name in ("HouseDoor", "DoorMat"):
        assert "sprite" not in g["entities"][name] and g["entities"][name]["shape"]["color"] == "#00000000"


def test_the_farmer_faces_where_it_walks_even_with_a_sword():
    for abilities in ([], ["sword"]):
        b, _ = normalize(GameBrief(title="t", genre="farm", crops=["Carrot"], player={"character": "Farmer", "abilities": abilities},
                                   enemies=[EnemyBrief(name="Crow", archetype="walker", count=2)]))
        assert assemble(b, 2, seed=1)["entities"]["Player"]["components"]["Aim"]["mode"] == "movement"


def test_a_farm_is_a_season_of_days_with_a_bed_and_seeds_to_buy():
    g = assemble(_farm_brief(length="medium"), 2, seed=2)
    player = g["entities"]["Player"]["components"]
    assert player["FarmDays"]["days"] == 3 and player["Farmer"]["buy_seeds"]
    assert "SleepSpot" in g["entities"]["Bed"]["components"]
    rules = str(g["rules"])
    assert "Player.FarmDays.season_ended" in rules and "time_limit" not in rules and "add_score(15)" in rules


@pytest.mark.parametrize("palette,season", [("snow", "winter"), ("desert", "desert"), ("forest", "spring")])
def test_seasons_change_how_crops_grow(palette, season):
    g = assemble(_farm_brief(palette=palette), 2, seed=2)
    plot = g["entities"]["Plot"]["components"]["FarmPlot"]
    assert g["settings"]["season"] == season
    assert (plot["growth_rate"] < 1.0) == (season in ("winter", "desert"))


def test_farm_pests_and_animals_use_the_farm_style():
    g = assemble(_farm_brief(), 2, seed=2)
    assert g["entities"]["Crow"]["sprite"]["generate"]["kind"] == "crow"
    chick = g["entities"]["Chick"]["components"]["FarmAnimal"]
    assert chick["grows_into"] == "Chicken" and g["entities"]["Chicken"]["components"]["FarmAnimal"]["needs_food"]


def test_farm_animals_and_fish_are_never_pests():
    b, notes = normalize(GameBrief(title="t", genre="farm", crops=["Corn"],
                                   enemies=[EnemyBrief(name="Fish", archetype="walker"), EnemyBrief(name="Crow", archetype="walker")]))
    assert [e.name for e in b.enemies] == ["Crow"] and any("not pests" in n for n in notes)
