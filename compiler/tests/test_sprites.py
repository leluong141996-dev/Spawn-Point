import json

import numpy as np
import pytest
from PIL import Image

from spawnpoint.analyze import analyze
from spawnpoint.sprites import contour, importer
from spawnpoint.sprites.generate import KINDS, features_for, generate
from spawnpoint.sprites.resolve import convex_hull, plan_entry, safe_polygon
from spawnpoint.sprites.spriteset import SpriteError, load
from spawnpoint.studio.assemble import sprite_kind
from spawnpoint.studio.brief import GameBrief

from conftest import codes, load_example, minimal


def rgba(mask: np.ndarray) -> np.ndarray:
    img = np.zeros((*mask.shape, 4), np.uint8)
    img[mask] = (255, 0, 0, 255)
    return img


# --- contour ----------------------------------------------------------------------------------

def test_contour_of_rectangle_is_exact():
    m = np.zeros((8, 8), bool)
    m[2:6, 1:7] = True
    assert contour.outline(rgba(m)) == [(1.0, 2.0), (7.0, 2.0), (7.0, 6.0), (1.0, 6.0)]
    assert contour.bounds(m) == (1, 2, 6, 4)


def test_contour_circle_area_and_detached_detail():
    yy, xx = np.mgrid[:20, :20]
    m = ((yy - 10) ** 2 + (xx - 10) ** 2) <= 49
    m[2, 10] = True  # antenna tip one pixel above the head
    poly = contour.outline(rgba(m))
    assert abs(abs(contour.polygon_area(poly)) - np.pi * 49) < 15
    assert min(y for _, y in poly) == 2.0  # merged into the outline


def test_contour_empty():
    assert contour.outline(np.zeros((4, 4, 4), np.uint8)) == []


def test_safe_polygon_falls_back_to_hull_for_self_intersections():
    bowtie = [(0, 0), (4, 4), (4, 0), (0, 4)]
    assert sorted(safe_polygon(bowtie)) == sorted(convex_hull(bowtie)) == [(0, 0), (0, 4), (4, 0), (4, 4)]
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]
    assert safe_polygon(square) == square


# --- generator --------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_kind_renders(kind):
    s = generate("Thing", kind, "#ff004d")
    assert "idle" in s.animations
    w, h = s.frame_size
    for name, a in s.animations.items():
        for col, row in (a.frames[:-1] if name == "die" else a.frames):  # a death ends on an empty frame
            assert (s.frame(col, row)[..., 3] > 0).any(), f"{kind}.{name} frame empty"
    bx, by, bw, bh = s.bounds
    assert 0 <= bx and 0 <= by and bx + bw <= w and by + bh <= h
    assert len(s.polygon) >= 3
    assert generate("Thing", kind, "#ff004d").sheet.tobytes() == s.sheet.tobytes()  # deterministic


def test_features_from_names():
    assert features_for("NinjaFox") == ["mask", "ears", "tail", "bushy_tail"]
    assert features_for("fire bat") == ["wings"]
    assert features_for("Player") == []


def test_names_change_the_look():
    a = generate("Goblin", "hero", "#ff004d").sheet.tobytes()
    b = generate("Ninja", "hero", "#ff004d").sheet.tobytes()
    assert a != b


# --- import -----------------------------------------------------------------------------------

@pytest.fixture
def art(tmp_path):
    """An artist-style sheet (4 columns, 2px spacing) and a folder of frames, from a generated knight."""
    s = generate("Knight", "hero", "#c2c3c7", ["helmet"])
    two_idle = {"idle": s.animations["idle"].frames[:2], "run": s.animations["run"].frames}  # the sheet has 6 idle frames
    cells = [s.frame(*f) for a in ("idle", "run") for f in two_idle[a]]  # 2 idle + 4 run
    sheet = Image.new("RGBA", (4 * 26, 2 * 26))
    for i, f in enumerate(cells):
        sheet.paste(Image.fromarray(f), ((i % 4) * 26 + 6, (i // 4) * 26 + 4))
    sheet.save(tmp_path / "knight.png")
    frames = tmp_path / "frames"
    frames.mkdir()
    for a, fname in (("idle", "idle"), ("run", "walk")):
        for i, f in enumerate(two_idle[a]):
            Image.fromarray(s.frame(*f)).save(frames / f"knight_{fname}_{i}.png")
    return tmp_path


def test_parse_ranges():
    assert importer.parse_ranges("0-3, 7,9-10") == [0, 1, 2, 3, 7, 9, 10]


def test_import_grid_with_indices(art):
    s = importer.import_sheet(art / "knight.png", grid=(24, 24), spacing=2, anims={"idle": [0, 1], "run": [2, 3, 4, 5]})
    assert s.frame_size == (24, 24)
    assert {k: len(a.frames) for k, a in s.animations.items()} == {"idle": 2, "run": 4}
    assert s.name == "Knight"


def test_import_grid_rejects_empty_frames(art):
    with pytest.raises(SpriteError, match="empty frame"):
        importer.import_sheet(art / "knight.png", grid=(24, 24), spacing=2, anims={"run": [4, 5, 6, 7]})


def test_import_grid_rejects_out_of_range(art):
    with pytest.raises(SpriteError, match="has 8 frames"):
        importer.import_sheet(art / "knight.png", grid=(24, 24), spacing=2, anims={"idle": [0, 99]})


def test_import_auto_slices_by_gutters(art):
    s = importer.import_sheet(art / "knight.png")
    # Rows become animations in standard order; frames are trimmed and bottom-aligned.
    assert [len(a.frames) for a in s.animations.values()] == [4, 2]
    assert list(s.animations) == ["idle", "run"]
    w, h = s.frame_size
    assert w < 24 and h <= 24


def test_import_folder_groups_and_maps_synonyms(art):
    s = importer.import_folder(art / "frames")
    assert {k: len(a.frames) for k, a in s.animations.items()} == {"idle": 2, "run": 4}
    assert s.animations["run"].fps == 10.0


def test_save_load_roundtrip_and_preview(art, tmp_path):
    s = importer.import_folder(art / "frames", "Knight")
    path = s.save(tmp_path / "lib")
    back = load(path)
    assert back.frame_size == s.frame_size and back.polygon == s.polygon and back.bounds == s.bounds
    img = importer.preview(back)
    assert img.width > 100 and img.height > 50


def test_load_errors(tmp_path):
    with pytest.raises(SpriteError, match="cannot read"):
        load(tmp_path / "nope.sprite.json")
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(tmp_path / "a.png")
    (tmp_path / "a.sprite.json").write_text(json.dumps({
        "image": "a.png", "frame_size": [8, 8], "animations": {"idle": {"frames": [[1, 0]]}}}))
    with pytest.raises(SpriteError, match="outside"):
        load(tmp_path / "a.sprite.json")


# --- compiler integration ---------------------------------------------------------------------

def test_generated_sprite_derives_collision_and_plan(manifest):
    g = minimal()
    g["entities"]["Player"]["sprite"] = {"generate": {"kind": "hero"}}
    g["entities"]["Coin"]["sprite"] = {"generate": {"kind": "coin"}}
    a = analyze(g, manifest)
    assert a.ok, [str(d) for d in a.diagnostics]
    player = next(e for e in a.plan["entities"] if e["name"] == "Player")
    s = a.sprites["Player"]
    assert player["shape"]["type"] == "capsule"
    assert player["shape"]["size"][1] == s.bounds[3] * s.scale
    assert player["sprite"]["texture"] == "res://sprites/Player.png"
    assert "Animator" in [c["name"] for c in player["components"]]
    assert player["eye"] is False
    # Feet still rest on the floor row.
    p = next(p for p in a.plan["placements"] if p["entity"] == "Player")
    assert p["y"] + player["shape"]["size"][1] / 2 == pytest.approx(64)


def test_plan_entry_centers_the_opaque_box():
    s = generate("Coin", "coin", "#ffec27")
    e = plan_entry("Coin", s)
    bx, by, bw, bh = s.bounds
    xs = [p[0] for p in e["polygon"]]
    ys = [p[1] for p in e["polygon"]]
    assert min(xs) == pytest.approx(-bw, abs=bw) and max(xs) <= bw * s.scale / 2 + 0.01
    assert min(ys) >= -bh * s.scale / 2 - 0.01 and max(ys) <= bh * s.scale / 2 + 0.01


def test_explicit_shape_wins(manifest):
    g = minimal()
    g["entities"]["Player"]["sprite"] = {"generate": {"kind": "hero"}}
    g["entities"]["Player"]["shape"] = {"type": "rect", "size": [20, 20]}
    plan = analyze(g, manifest).plan
    player = next(e for e in plan["entities"] if e["name"] == "Player")
    assert player["shape"] == {"type": "rect", "size": [20.0, 20.0], "color": "#29adff"}


@pytest.mark.parametrize("sprite, fragment", [
    ({"generate": {"kind": "kraken"}}, "unknown sprite kind"),
    ("art/hero.sprite.json", "needs the graph's folder"),
])
def test_sprite_errors(manifest, sprite, fragment):
    g = minimal()
    g["entities"]["Player"]["sprite"] = sprite
    a = analyze(g, manifest)
    err = next(d for d in a.diagnostics.errors if d.code == "E_SPRITE")
    assert fragment in err.message and err.path == "entities.Player.sprite"


def test_sprite_path_relative_to_graph(manifest, tmp_path):
    generate("Hero", "hero", "#29adff").save(tmp_path / "art", "hero")
    g = minimal()
    g["entities"]["Player"]["sprite"] = "art/hero.sprite.json"
    assert analyze(g, manifest, base_dir=tmp_path).ok
    g["entities"]["Player"]["sprite"] = "art/missing.sprite.json"
    assert "E_SPRITE" in codes(analyze(g, manifest, base_dir=tmp_path).diagnostics)


def test_pixel_example_is_clean(manifest):
    a = analyze(load_example("pixel_hopper.json"), manifest)
    assert a.ok and not a.diagnostics.warnings, [str(d) for d in a.diagnostics]
    assert len(a.sprites) == 8


# --- studio kind mapping ----------------------------------------------------------------------

@pytest.mark.parametrize("name, comps, archetype, platformer, kind", [
    ("Player", {}, None, True, "hero"),
    ("Goblin", {}, "walker", True, "hero"),
    ("Slime", {}, "walker", True, "slime"),
    ("FireBat", {}, "chaser", True, "flyer"),
    ("LaserBot", {}, "shooter", False, "robot"),
    ("Beetle", {}, "chaser", False, "bug"),
    ("Thing", {}, "turret", False, "turret"),
    ("Star", {"Collectible": {}}, None, True, "star"),
    ("Acorn", {"Collectible": {}}, None, True, "orb"),
    ("Crystal", {"Collectible": {}}, None, True, "gem"),
    ("Exit", {}, None, False, "portal"),
    ("Archer", {}, "shooter", False, "hero"),
    ("Ogre", {}, "walker", True, "hero"),
    ("SkeletonKing", {}, "chaser", False, "hero"),
    ("Wolf", {}, "chaser", True, "beast"),
    ("CaveSpider", {}, "walker", True, "spider"),
    ("FireDragon", {}, "chaser", False, "dragon"),
    ("Ghost", {}, "chaser", False, "ghost"),
    ("Snake", {}, "walker", True, "snake"),
    ("Beetle", {}, "walker", True, "slime"),
])
def test_sprite_kind(name, comps, archetype, platformer, kind):
    b = GameBrief(title="t", genre="platformer" if platformer else "topdown")
    assert sprite_kind(name, {"components": comps}, archetype, b, platformer) == kind


# --- tiles & zoom -----------------------------------------------------------------------------

@pytest.mark.parametrize("genre", ["platformer", "topdown"])
def test_pixel_tileset(genre):
    from spawnpoint.sprites.tiles import tileset
    img = tileset(genre, "#5f574f", "#00e436", "#ab5236", 32, seed=3)
    assert img.size == (96, 32)
    px = np.asarray(img)
    assert (px[:, :64, 3] == 255).all()  # solid tiles are fully opaque
    assert (px[20:, 64:, 3] == 0).all()  # the one-way plank leaves the lower part open
    assert tileset(genre, "#5f574f", "#00e436", "#ab5236", 32, seed=3).tobytes() == img.tobytes()


def test_plan_carries_tiles_and_zoom(manifest):
    g = minimal(settings={"zoom": 1.5})
    a = analyze(g, manifest)
    assert a.plan["zoom"] == 1.5 and a.plan["tiles"]["texture"] == "res://sprites/tiles.png"
    assert a.tiles_image is not None
    flat = analyze(minimal(settings={"tile_style": "flat"}), manifest)
    assert "texture" not in flat.plan["tiles"] and flat.tiles_image is None
    assert "E_SCHEMA" in codes(analyze(minimal(settings={"zoom": 9}), manifest).diagnostics)


# --- cartoon style ----------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_kind_renders_in_cartoon(kind):
    from spawnpoint.sprites.cartoon import DETAIL, SCALE, generate_cartoon
    s = generate_cartoon("Thing", kind, "#29adff")
    assert s.smooth and s.scale == SCALE
    w, h = KINDS[kind].size
    assert s.frame_size == (w * DETAIL, h * DETAIL)  # same on-screen size as the pixel sprite
    for name, a in s.animations.items():
        for col, row in (a.frames[:-1] if name == "die" else a.frames):  # a death ends on an empty frame
            assert (s.frame(col, row)[..., 3] > 0).any(), f"{kind}.{name} frame empty"
    assert len(s.polygon) >= 3
    assert generate_cartoon("Thing", kind, "#29adff").sheet.tobytes() == s.sheet.tobytes()  # deterministic


def test_art_style_switches_sprites_and_tiles(manifest):
    g = minimal(settings={"art_style": "cartoon"})
    g["entities"]["Player"]["sprite"] = {"generate": {"kind": "hero"}}
    a = analyze(g, manifest)
    assert a.ok, [str(d) for d in a.diagnostics]
    player = next(e for e in a.plan["entities"] if e["name"] == "Player")
    assert player["sprite"]["smooth"] is True and player["sprite"]["scale"] == 0.5
    assert a.plan["art_style"] == "cartoon" and a.plan["tiles"]["smooth"] and a.plan["tiles"]["separation"] == 4
    px = np.asarray(a.tiles_image)
    assert a.tiles_image.size == (32 * 3 + 2 * 4, 32)
    assert px[14:, 2 * (32 + 4), 3].max() == 0  # nothing bleeds into the one-way plank's empty part
    pixel = analyze(minimal(), manifest)
    assert pixel.plan["art_style"] == "pixel" and not pixel.plan["tiles"].get("smooth")


# --- classic pixel palettes -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["pico8", "sweetie16", "endesga32"])
def test_palette_ramp_is_ordered_and_distinct(name):
    from spawnpoint.sprites import palettes
    from spawnpoint.sprites.generate import ramp

    pal = palettes.get(name)
    for color in ("#29adff", "#ff004d", "#00e436", "#ffec27", "#7e2553", "#ffffff", "#000000", "#808080"):
        r = ramp(color, pal)
        tones = [r.outline, r.shadow, r.base, r.light]
        assert len(set(tones)) == 4, (name, color, tones)
        assert all(t[:3] in {tuple(c) for c in pal.rgb.tolist()} for t in tones)


@pytest.mark.parametrize("name", ["pico8", "sweetie16", "endesga32"])
def test_palette_sprites_and_tiles_use_only_palette_colours(name):
    from spawnpoint.sprites import palettes
    from spawnpoint.sprites.generate import KINDS, generate
    from spawnpoint.sprites.tiles import tileset

    allowed = {tuple(c) for c in palettes.get(name).rgb.tolist()}

    def colours(img_or_arr) -> set:
        a = np.asarray(img_or_arr.convert("RGBA") if hasattr(img_or_arr, "convert") else img_or_arr)
        a = a.reshape(-1, 4)
        return {tuple(p[:3]) for p in a.tolist() if p[3] > 0}

    for kind in KINDS:
        s = generate("Thing", kind, "#ff004d", None, 1, palette=name)
        assert colours(s.sheet) <= allowed, (name, kind)
        assert set(np.asarray(s.sheet.convert("RGBA"))[..., 3].ravel().tolist()) <= {0, 255}
    for genre in ("platformer", "topdown"):
        assert colours(tileset(genre, "#5f574f", "#00e436", "#ab5236", 32, 1, palette=name)) <= allowed


def test_no_palette_keeps_the_free_colours():
    from spawnpoint.sprites.generate import generate

    a, b = generate("Fox", "hero", "#ff7733", None, 0), generate("Fox", "hero", "#ff7733", None, 0, palette=None)
    assert a.sheet.tobytes() == b.sheet.tobytes()
    assert len({tuple(p) for p in np.asarray(a.sheet.convert("RGBA")).reshape(-1, 4).tolist()}) > 5


def test_assembler_gives_pixel_games_a_theme_palette():
    from spawnpoint.sprites.palettes import THEME_PALETTE
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import GameBrief, normalize

    for theme, pal in THEME_PALETTE.items():
        b, _ = normalize(GameBrief(title="t", genre="platformer", palette=theme))
        assert assemble(b, 2, seed=1)["settings"]["pixel_palette"] == pal
        assert "pixel_palette" not in assemble(b, 1, seed=1)["settings"]  # layers 0-1 are placeholders
    b, _ = normalize(GameBrief(title="t", genre="platformer", art_style="cartoon"))
    assert "pixel_palette" not in assemble(b, 2, seed=1)["settings"]


# --- attack and death animations --------------------------------------------------------------

@pytest.mark.parametrize("style", ["pixel", "cartoon"])
def test_fighters_attack_and_everything_hurtable_dies(style):
    from spawnpoint.sprites.cartoon import generate_cartoon
    from spawnpoint.sprites.generate import ATTACKERS

    make = generate if style == "pixel" else generate_cartoon
    for kind, spec in KINDS.items():
        s = make("Thing", kind, "#29adff", None, 1)
        assert ("attack" in s.animations) == (kind in ATTACKERS), kind
        assert ("die" in s.animations) == ("hurt" in spec.anims), kind
        if "die" in s.animations:
            die = s.animations["die"]
            assert not die.loop and len(die.frames) == 5
            *_, last = die.frames
            assert s.frame(*last)[..., 3].max() == 0, "the last frame of the death is empty"
            assert s.frame(*die.frames[0])[..., 3].max() > 0
        if "attack" in s.animations:
            assert not s.animations["attack"].loop


def test_hero_breathes_blinks_and_holds_a_sword():
    plain, sword = generate("Fox", "hero", "#ff7733", [], 0), generate("Fox", "hero", "#ff7733", ["sword"], 0)
    assert len(plain.animations["idle"].frames) == 6
    frames = [plain.frame(*f).tobytes() for f in plain.animations["idle"].frames]
    assert len(set(frames)) >= 3, "breathing and a blink: at least three different poses"
    attack = [sword.frame(*f).tobytes() for f in sword.animations["attack"].frames]
    assert len(set(attack)) == 3
    assert sword.frame(*sword.animations["idle"].frames[0]).tobytes() != plain.frame(*plain.animations["idle"].frames[0]).tobytes()


def test_sword_players_get_the_sword_feature():
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import GameBrief, PlayerBrief, normalize

    b, _ = normalize(GameBrief(title="k", genre="platformer", player=PlayerBrief(character="Knight", abilities=["sword"])))
    assert "sword" in assemble(b, 2, seed=1)["entities"]["Player"]["sprite"]["generate"]["features"]
    b, _ = normalize(GameBrief(title="k", genre="platformer", player=PlayerBrief(character="Knight")))
    assert "sword" not in assemble(b, 2, seed=1)["entities"]["Player"]["sprite"]["generate"]["features"]


# --- neighbour-aware pixel tiles --------------------------------------------------------------

LEVEL = ["......", "..==..", ".###..", "######", "######"]


def _cells(rows):
    return {(x, y): ("solid" if c == "#" else "oneway") for y, r in enumerate(rows) for x, c in enumerate(r) if c in "#="}


def test_tiles_depend_on_their_neighbours():
    from spawnpoint.sprites.tiles import neighbour_key, tileset_auto

    cells = _cells(LEVEL)
    w, h = 6, 5
    top, inner = neighbour_key(cells, 2, 2, w, h), neighbour_key(cells, 2, 3, w, h)
    assert top[0] is False and all(inner), (top, inner)  # open above vs surrounded
    # the level border is not an edge: the bottom row and the sides read as ground
    assert neighbour_key(cells, 0, 4, w, h)[1:4] == (True, True, True)
    # a diagonal only matters when both its sides are ground (an inner corner)
    assert neighbour_key(cells, 3, 3, w, h)[4] is False  # (3,3): ground above and right, but (4,2) is empty
    assert neighbour_key(cells, 1, 3, w, h)[4] is True  # nothing above (1,3): its diagonal does not matter
    img, kinds, mapping = tileset_auto("platformer", "#4a3728", "#5fb83d", "#8a5a3b", 32, 1, "endesga32", cells, w, h)
    assert set(mapping) == set(cells) and img.height == 32 and img.width == 32 * len(kinds)
    assert max(mapping.values()) == len(kinds) - 1
    assert {kinds[mapping[c]] for c in cells if cells[c] == "oneway"} == {"oneway"}
    assert mapping[(2, 2)] != mapping[(2, 3)], "the grass-topped cell differs from one buried in the ground"
    # same level, same seed: identical atlas
    again = tileset_auto("platformer", "#4a3728", "#5fb83d", "#8a5a3b", 32, 1, "endesga32", cells, w, h)
    assert again[0].tobytes() == img.tobytes() and again[2] == mapping


def test_large_ground_areas_use_interior_variants():
    from spawnpoint.sprites.tiles import INTERIOR_VARIANTS, tileset_auto

    cells = {(x, y): "solid" for x in range(12) for y in range(6)}
    _, kinds, mapping = tileset_auto("platformer", "#4a3728", "#5fb83d", "#8a5a3b", 32, 0, None, cells, 12, 6)
    interior = {mapping[(x, y)] for x in range(1, 11) for y in range(1, 5)}
    assert 1 < len(interior) <= INTERIOR_VARIANTS, "a big block must not be one stamped tile"


def test_pixel_levels_get_variants_in_the_plan(manifest):
    a = analyze(minimal(), manifest)
    tiles, m = a.plan["tiles"], a.plan["map"]
    assert tiles["variants"] and len(m["cell_variants"]) == len(m["cells"])
    assert a.tiles_image.width == 32 * len(tiles["variants"])
    flat = analyze(minimal(settings={"tile_style": "flat"}), manifest)
    assert "variants" not in flat.plan["tiles"] and "cell_variants" not in flat.plan["map"]
    cartoon = analyze(minimal(settings={"art_style": "cartoon"}), manifest)
    assert "variants" not in cartoon.plan["tiles"]


# --- pixel scenery ----------------------------------------------------------------------------

@pytest.mark.parametrize("theme", ["night", "forest", "desert", "neon", "candy", "ocean", "lava", "snow"])
def test_scenery_themes_tile_and_stay_in_the_palette(theme):
    from spawnpoint.sprites import palettes, scenery
    from spawnpoint.studio.assemble import PALETTES

    name = palettes.THEME_PALETTE[theme]
    sky, layers = scenery.build(theme, PALETTES[theme]["bg"], name, 3)
    assert sky.shape == (scenery.SKY_H, scenery.SKY_W, 4) and (sky[..., 3] == 255).all()
    assert len(layers) >= 3 and (layers[0].name == "clouds") == (theme != "neon")  # a neon city has no clouds
    allowed = {tuple(c) for c in palettes.get(name).rgb.tolist()}
    for img in [sky] + [layer.image for layer in layers]:
        used = {tuple(p[:3]) for p in img.reshape(-1, 4).tolist() if p[3] > 0}
        assert used <= allowed, (theme, used - allowed)
    for layer in layers:
        assert layer.image.shape[1] == scenery.WIDTH
        alpha = layer.image[..., 3] > 0

        def jump(a: int, b: int) -> int:  # rows that differ between two neighbouring columns
            return int((alpha[:, a] != alpha[:, b]).sum())
        worst_inside = max(jump(x, x + 1) for x in range(scenery.WIDTH - 1))
        assert jump(scenery.WIDTH - 1, 0) <= worst_inside, (theme, layer.name)  # the repeat has no visible seam
    # the same inputs always give the same picture; another seed gives another
    again = scenery.build(theme, PALETTES[theme]["bg"], name, 3)
    assert again[0].tobytes() == sky.tobytes() and again[1][1].image.tobytes() == layers[1].image.tobytes()
    other = scenery.build(theme, PALETTES[theme]["bg"], name, 4)
    assert other[1][1].image.tobytes() != layers[1].image.tobytes()


def test_layers_are_told_apart_from_the_sky_and_each_other():
    from spawnpoint.sprites import palettes, scenery
    from spawnpoint.studio.assemble import PALETTES

    for theme in scenery.THEMES:
        sky, layers = scenery.build(theme, PALETTES[theme]["bg"], palettes.THEME_PALETTE[theme], 1)
        horizon = tuple(sky[int(scenery.SKY_H * 0.7), 0, :3].tolist())
        fills = []
        for layer in layers[1:]:
            bottom = layer.image[-1]  # the bottom row is solid body colour
            fills.append(tuple(bottom[np.argmax(bottom[:, 3] > 0)][:3].tolist()))
        assert horizon not in fills, theme
        assert len(set(fills)) == len(fills), (theme, fills)


def test_scenery_in_the_plan(manifest):
    plat = analyze(minimal(settings={"background": "#12261e"}), manifest)
    sc = plat.plan["scenery"]
    assert sc["sky"] == "res://sprites/scenery_sky.png" and sc["pixel"] == 2
    assert {layer["name"] for layer in sc["layers"]} >= {"clouds", "far", "mid", "near"}
    assert set(plat.scenery_images) == {"scenery_sky"} | {f"scenery_{layer['name']}" for layer in sc["layers"]}
    for name in ("flat",):
        assert "scenery" not in analyze(minimal(settings={"scenery": name}), manifest).plan
    assert "scenery" not in analyze(minimal(settings={"art_style": "cartoon"}), manifest).plan
    top = minimal(settings={"background": "#1d2b53"})
    top["genre"] = "topdown"
    arena = analyze(top, manifest)
    if arena.ok:
        assert arena.plan["scenery"]["floor"] == "res://sprites/scenery_floor.png" and "scenery_floor" in arena.scenery_images


# --- the fine (SNES-like) pixel size ----------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(KINDS))
def test_fine_sprites_are_twice_the_detail_at_the_same_size(kind):
    from spawnpoint.sprites import palettes

    chunky, fine = generate("Thing", kind, "#29adff", None, 1), generate("Thing", kind, "#29adff", None, 1, fine=True)
    assert fine.frame_size == (chunky.frame_size[0] * 2, chunky.frame_size[1] * 2) and fine.scale == 1
    assert fine.frame_size[0] * fine.scale == chunky.frame_size[0] * chunky.scale  # same size on screen
    assert set(fine.animations) == set(chunky.animations)
    assert fine.sheet.tobytes() == generate("Thing", kind, "#29adff", None, 1, fine=True).sheet.tobytes()
    bx, by, bw, bh = fine.bounds
    cx, cy, cw, ch = chunky.bounds
    # people are a different drawing in the fine style (the front-facing chibi): a little slimmer
    tol = 8 if kind == "hero" else 4
    assert abs(bw * fine.scale - cw * chunky.scale) <= tol and abs(bh * fine.scale - ch * chunky.scale) <= 4
    pal = palettes.get("endesga32")
    allowed = {tuple(c) for c in pal.rgb.tolist()}
    used = {tuple(p[:3]) for p in np.asarray(generate("Thing", kind, "#29adff", None, 1, palette="endesga32", fine=True)
                                           .sheet.convert("RGBA")).reshape(-1, 4).tolist() if p[3] > 0}
    assert used <= allowed


def test_pixel_size_one_in_a_graph(manifest):
    g = minimal(settings={"pixel_size": 1})
    g["entities"]["Player"]["sprite"] = {"generate": {"kind": "hero"}}
    a = analyze(g, manifest)
    assert a.ok, [str(d) for d in a.diagnostics]
    player = next(e for e in a.plan["entities"] if e["name"] == "Player")
    assert player["sprite"]["scale"] == 1 and player["sprite"]["frame_size"] == [24, 32]
    assert a.tiles_image.height == 32 and a.tiles_image.width == 32 * len(a.plan["tiles"]["variants"])
    default = analyze(minimal(), manifest)
    assert default.plan["tiles"]["variants"], "the default stays chunky"


# --- hero accessories (shields, weapons, crowns, skeletons...) --------------------------------

NEW_HERO_FEATURES = ["bow", "staff", "spear", "axe", "shield", "cape", "crown", "hood", "beard", "tusks", "skull",
                     "zombie", "bulky"]


@pytest.mark.parametrize("feature", NEW_HERO_FEATURES)
def test_hero_accessories_render_in_every_style(feature):
    from spawnpoint.sprites.cartoon import generate_cartoon
    for make in (lambda f: generate("Hero", "hero", "#29adff", f, 1),
                 lambda f: generate("Hero", "hero", "#29adff", f, 1, fine=True),
                 lambda f: generate("Hero", "hero", "#29adff", f, 1, palette="pico8"),
                 lambda f: generate_cartoon("Hero", "hero", "#29adff", f, 1)):
        plain, dressed = make([]), make([feature])
        assert set(dressed.animations) == set(plain.animations)
        assert dressed.sheet.tobytes() != plain.sheet.tobytes(), feature


def test_hero_holds_one_weapon():
    from spawnpoint.sprites.generate import held_weapon
    assert held_weapon(["bow", "sword", "staff"]) == "sword"
    assert held_weapon(["staff", "spear"]) == "spear"
    assert held_weapon(["shield", "cape"]) is None
    both = generate("Hero", "hero", "#29adff", ["sword", "bow"], 1).sheet.tobytes()
    assert both == generate("Hero", "hero", "#29adff", ["sword"], 1).sheet.tobytes()


def test_skeletons_and_zombies_have_their_own_skin():
    red, blue = (generate("Skeleton", "hero", c, ["skull"], 1).sheet.tobytes() for c in ("#ff004d", "#29adff"))
    assert red == blue
    red, blue = (generate("Zombie", "hero", c, ["zombie"], 1).sheet.tobytes() for c in ("#ff004d", "#29adff"))
    assert red == blue


def test_names_pick_accessories():
    assert features_for("SkeletonArcher") == ["skull", "bow"]
    assert features_for("OrcBrute") == ["tusks", "bulky"]
    assert features_for("DarkKnight") == ["helmet", "shield", "armor"]
    assert features_for("King") == ["crown", "cape", "beard"]
    assert features_for("VikingRaider") == ["helmet", "horns", "beard", "axe"]
    assert features_for("Wizard") == ["hat", "staff", "robe", "beard", "old"]


# Pixel-exact fingerprints of sprites that existed before the accessories were added: new kinds and
# features must never change them by accident. (Cartoon art is anti-aliased, so it is not pinned here.)
GOLDEN = {
    ("hero", "Hero", None, None, False): "af63917791d7af74",
    ("hero", "Fox", ("ears", "tail", "sword"), None, True): "3d46e8c9913a7865",  # creatures keep the generic painter
    ("hero", "Ninja", None, None, False): "c67e6bf0b5f4dbb8",
    ("slime", "Hero", None, None, False): "fabad4c1ad5daca8",
    ("flyer", "Hero", None, "pico8", False): "9e6d05469a67e369",
    ("coin", "Hero", None, "endesga32", False): "2f5e97ae3b47d84b",
    ("ship", "Hero", None, None, True): "fea8002c6221948c",
    ("bug", "Fox", None, None, True): "4f3ffaa4982862b8",
}


@pytest.mark.parametrize("key", list(GOLDEN))
def test_existing_sprites_are_unchanged(key):
    import hashlib
    kind, name, feats, palette, fine = key
    s = generate(name, kind, "#3fa7d6", list(feats) if feats else None, 3, palette=palette, fine=fine)
    digest = hashlib.sha256(s.sheet.tobytes() + json.dumps(s.to_dict("x"), sort_keys=True).encode()).hexdigest()[:16]
    assert digest == GOLDEN[key]


# --- the fine-style chibi people --------------------------------------------------------------

def test_people_get_the_chibi_and_creatures_keep_the_generic_hero():
    from spawnpoint.sprites import chibi
    assert chibi.is_human(features_for("Knight")) and chibi.is_human(features_for("SkeletonArcher"))
    assert not chibi.is_human(features_for("NinjaFox")) and not chibi.is_human(features_for("Puppy"))
    knight = generate("Knight", "hero", "#3a6fd0", None, 1, fine=True)
    assert knight.frame_size == (24, 32) and knight.scale == 1 and knight.anchor == "bottom"
    assert {"idle", "run", "jump", "fall", "hurt", "attack", "die"} <= set(knight.animations)
    colours = {tuple(p) for p in np.asarray(knight.sheet).reshape(-1, 4).tolist() if p[3] > 0}
    assert len(colours) >= 12  # skin, hair, clothes, steel... not a one-colour blob
    assert knight.sheet.tobytes() == generate("Knight", "hero", "#3a6fd0", None, 1, fine=True).sheet.tobytes()


def test_chibi_people_vary_by_name_but_not_by_frame_call():
    from spawnpoint.sprites import chibi
    looks = {(c.skin, c.hair, c.hair_style) for c in (chibi.choose(n, "#d04040", [], 0)
                                                      for n in ("Ana", "Bo", "Cid", "Dee", "Eve", "Fay", "Gus", "Hal"))}
    assert len(looks) >= 4
    goblin = chibi.choose("Goblin", "#ff77a8", features_for("Goblin"), 0)
    assert goblin.skin in chibi.MONSTER_GREENS and goblin.shirt == "#ff77a8"  # green whatever the entity colour
    assert chibi.choose("Imp", "#29adff", features_for("Imp"), 0).skin == chibi.DEVIL_SKIN
    assert chibi.choose("Zombie", "#d04040", ["zombie"], 0).skin == chibi.ZOMBIE_SKIN


@pytest.mark.parametrize("name", ["Hero", "Knight", "Wizard", "Archer", "Princess", "VikingRaider", "Ninja",
                                  "Skeleton", "Farmer", "Orc", "Zombie", "King", "Priest"])
def test_chibi_people_in_both_styles(name):
    from spawnpoint.sprites.cartoon import generate_cartoon
    fine = generate(name, "hero", "#3a6fd0", None, 1, fine=True)
    pal = generate(name, "hero", "#3a6fd0", None, 1, fine=True, palette="sweetie16")
    toon = generate_cartoon(name, "hero", "#3a6fd0", None, 1)
    assert fine.frame_size == pal.frame_size == (24, 32)
    assert set(toon.animations) >= {"idle", "run", "jump", "fall", "hurt", "die"}
    bx, by, bw, bh = fine.bounds
    assert 10 <= bw <= 24 and 24 <= bh <= 32  # about the old hero's size on screen


def test_assembler_draws_pixel_games_in_the_fine_style():
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import GameBrief, normalize

    b, _ = normalize(GameBrief(title="t", genre="platformer"))
    assert assemble(b, 2, seed=1)["settings"]["pixel_size"] == 1
    b, _ = normalize(GameBrief(title="t", genre="platformer", art_style="cartoon"))
    assert "pixel_size" not in assemble(b, 2, seed=1)["settings"]


# --- chibi creatures (beast, spider, dragon, ghost, snake) -------------------------------------

CREATURE_KINDS = ["beast", "spider", "dragon", "ghost", "snake"]


@pytest.mark.parametrize("kind", CREATURE_KINDS)
def test_creatures_are_painted_at_the_fine_size_and_shrunk_for_coarse(kind):
    fine, coarse = generate("Thing", kind, "#c04040", None, 1, fine=True), generate("Thing", kind, "#c04040", None, 1)
    w, h = KINDS[kind].size
    assert fine.frame_size == (w * 2, h * 2) and fine.scale == 1
    assert coarse.frame_size == (w, h) and coarse.scale == 2
    assert "attack" in fine.animations and "die" in fine.animations
    # the eyes survive the 2:1 shrink
    from spawnpoint.sprites.chibi import EYE
    idle = coarse.frame(*coarse.animations["idle"].frames[0])
    inner = idle[1:-1, 1:-1]
    assert ((inner[..., :3] == EYE[:3]).all(-1) & (inner[..., 3] > 0)).sum() > 0


def test_beast_variants_come_from_names():
    plain = generate("Wolf", "beast", "#8a8aa0", None, 1, fine=True).sheet.tobytes()
    for name in ("Fox", "Bear", "Boar", "Lion", "Tiger", "Puppy"):
        assert generate(name, "beast", "#8a8aa0", None, 1, fine=True).sheet.tobytes() != plain, name


@pytest.mark.parametrize("kind", CREATURE_KINDS)
def test_creatures_follow_the_theme_palette(kind):
    from spawnpoint.sprites import palettes
    pal = palettes.get("sweetie16")
    allowed = {tuple(c) for c in pal.rgb.tolist()}
    sheet = np.asarray(generate("Thing", kind, "#c04040", None, 1, palette="sweetie16", fine=True).sheet.convert("RGBA"))
    used = {tuple(p[:3]) for p in sheet.reshape(-1, 4).tolist() if p[3] > 0}
    assert used <= allowed


# --- items and decorative props -----------------------------------------------------------------

ITEM_KINDS = ["key", "potion", "scroll", "bomb", "chest", "arrow", "tree", "bush", "rock"]


@pytest.mark.parametrize("kind", ITEM_KINDS)
def test_items_render_in_every_style(kind):
    from spawnpoint.sprites import palettes
    from spawnpoint.sprites.cartoon import generate_cartoon
    w, h = KINDS[kind].size
    fine, coarse = generate("Thing", kind, "#c04040", None, 1, fine=True), generate("Thing", kind, "#c04040", None, 1)
    assert fine.frame_size == (w * 2, h * 2) and coarse.frame_size == (w, h)
    assert generate_cartoon("Thing", kind, "#c04040", None, 1).animations
    pal = palettes.get("endesga32")
    allowed = {tuple(c) for c in pal.rgb.tolist()}
    sheet = np.asarray(generate("Thing", kind, "#c04040", None, 1, palette="endesga32", fine=True).sheet.convert("RGBA"))
    assert {tuple(p[:3]) for p in sheet.reshape(-1, 4).tolist() if p[3] > 0} <= allowed


@pytest.mark.parametrize("name, comps, kind", [
    ("CageKey", {}, "key"),
    ("XpGem", {}, "gem"),
    ("GoldKey", {"Collectible": {}}, "key"),
    ("HealthPotion", {"Collectible": {}}, "potion"),
    ("MagicScroll", {"Collectible": {}}, "scroll"),
    ("TreasureChest", {"Collectible": {}}, "chest"),
    ("Arrow", {"Projectile": {}}, "arrow"),
])
def test_items_route_by_name(name, comps, kind):
    b = GameBrief(title="t", genre="platformer")
    assert sprite_kind(name, {"components": comps}, None, b, True) == kind


def test_archers_shoot_arrows():
    from spawnpoint.studio.brief import EnemyBrief, PlayerBrief
    b = GameBrief(title="t", genre="platformer", player=PlayerBrief(character="Ranger"),
                  enemies=[EnemyBrief(name="SkeletonArcher", archetype="shooter")])
    assert sprite_kind("Bullet", {}, None, b, True) == "arrow"
    assert sprite_kind("EnemyBullet", {}, None, b, True) == "arrow"
    b = GameBrief(title="t", genre="platformer", enemies=[EnemyBrief(name="SkeletonArcher", archetype="shooter"),
                                                           EnemyBrief(name="LaserBot", archetype="shooter")])
    assert sprite_kind("Bullet", {}, None, b, True) == "bullet"
    assert sprite_kind("EnemyBullet", {}, None, b, True) == "bullet"  # shared by a robot: keep the bolt


def test_layer_two_scatters_decor_behind_everything(manifest):
    from spawnpoint.studio.assemble import assemble
    from spawnpoint.studio.brief import normalize

    b, _ = normalize(GameBrief(title="t", genre="platformer", palette="forest"))
    g = assemble(b, 2, seed=3)
    decor = {n for n, e in g["entities"].items() if e.get("decor")}
    assert decor and decor <= {"Tree", "PineTree", "BerryBush", "MossyRock"}
    symbols = {s for s, n in g["level"]["legend"].items() if n in decor}
    assert any(ch in symbols for row in g["level"]["map"] for ch in row)
    assert not any(e.get("decor") for e in assemble(b, 1, seed=3)["entities"].values())  # layer 2 only
    neon, _ = normalize(GameBrief(title="t", genre="platformer", palette="neon"))
    assert not any(e.get("decor") for e in assemble(neon, 2, seed=3)["entities"].values())
    a = analyze(g, manifest)
    assert a.ok, [str(d) for d in a.diagnostics]
    for e in a.plan["entities"]:
        if e["name"] in decor:
            assert e["z"] == -1 and e["layer"] == 0 and e["mask"] == 0 and e["sprite"]
        else:
            assert e["z"] == 0


def test_prompt_art_words_draw_something_specific():
    """Every noun the prompts suggest for its art must actually pick a kind or features (not the fallbacks)."""
    from spawnpoint.studio.prompts import ART_HEROES, ART_MONSTERS, ART_PICKUPS, BRIEF_SYSTEM, BRIEF_SYSTEM_V5, ART_LINE
    from spawnpoint.studio.brief import EnemyBrief

    assert ART_LINE in BRIEF_SYSTEM and ART_LINE in BRIEF_SYSTEM_V5
    b = GameBrief(title="t", genre="platformer")
    for name in ART_HEROES:
        assert features_for(name), name
    for name in ART_MONSTERS:
        mb = GameBrief(title="t", genre="platformer", enemies=[EnemyBrief(name=name, archetype="walker")])
        assert sprite_kind(name, {}, "walker", mb, True) != "slime" or features_for(name), name
    for name in ART_PICKUPS:
        assert sprite_kind(name, {"components": {"Collectible": {}}}, None, b, True) != "orb", name
    assert features_for("SkeletonArcher") == ["skull", "bow"]


# --- snapshots of the chibi people, creatures and items (reviewed by eye in `spawnpoint sprites gallery`) ----

GOLDEN_CHIBI = {
    ("hero", "Knight", True): "2b749cacf3e38c76",
    ("hero", "Wizard", True): "67aeb17bc5009bcd",
    ("hero", "SkeletonArcher", True): "30f2b68b5b9ee619",
    ("hero", "Princess", False): "3eea5a1547b11521",
    ("beast", "Wolf", True): "8a40d3d5c05d2462",
    ("spider", "Spider", False): "86575329a057e41c",
    ("dragon", "Dragon", True): "b19425466e7079e4",
    ("ghost", "Ghost", True): "f9d3307b0196929e",
    ("snake", "Snake", False): "708871bd66a9151e",
    ("key", "GoldKey", True): "565b40551f28dd87",
    ("potion", "HealthPotion", False): "a6310c661d227ff3",
    ("chest", "TreasureChest", True): "d5c37d44ce5cec11",
    ("arrow", "Arrow", True): "d1b6109270cad18c",
    ("tree", "PineTree", True): "945b135084085ba9",
    ("bush", "BerryBush", False): "437766a715c27d3e",
    ("rock", "MossyRock", True): "875970aa5edddefe",
}


@pytest.mark.parametrize("key", list(GOLDEN_CHIBI))
def test_reviewed_sprites_are_unchanged(key):
    """A failure here means the art changed: look at the gallery, and if it is better, update the digest."""
    import hashlib
    kind, name, fine = key
    s = generate(name, kind, "#3fa7d6", features_for(name), 3, fine=fine)
    digest = hashlib.sha256(s.sheet.tobytes() + json.dumps(s.to_dict("x"), sort_keys=True).encode()).hexdigest()[:16]
    assert digest == GOLDEN_CHIBI[key]


@pytest.mark.parametrize("style", ["pixel", "cartoon"])
def test_gallery_shows_every_kind(style):
    from spawnpoint.sprites.gallery import CAST, gallery
    assert {kind for _, kind, _ in CAST} == set(KINDS)
    img = gallery(style, columns=4, cast=[c for c in CAST if c[1] in ("hero", "dragon", "key", "tree")])
    assert img.size[0] > 0 and img.getbbox()
