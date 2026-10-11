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
        for col, row in a.frames:
            assert (s.frame(col, row)[..., 3] > 0).any(), f"{kind}.{name} frame empty"
    bx, by, bw, bh = s.bounds
    assert 0 <= bx and 0 <= by and bx + bw <= w and by + bh <= h
    assert len(s.polygon) >= 3
    assert generate("Thing", kind, "#ff004d").sheet.tobytes() == s.sheet.tobytes()  # deterministic


def test_features_from_names():
    assert features_for("NinjaFox") == ["mask", "ears", "tail"]
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
    cells = [s.frame(*f) for a in ("idle", "run") for f in s.animations[a].frames]  # 2 idle + 4 run
    sheet = Image.new("RGBA", (4 * 26, 2 * 26))
    for i, f in enumerate(cells):
        sheet.paste(Image.fromarray(f), ((i % 4) * 26 + 6, (i // 4) * 26 + 4))
    sheet.save(tmp_path / "knight.png")
    frames = tmp_path / "frames"
    frames.mkdir()
    for a, fname in (("idle", "idle"), ("run", "walk")):
        for i, f in enumerate(s.animations[a].frames):
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
    ({"generate": {"kind": "dragon"}}, "unknown sprite kind"),
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
        for col, row in a.frames:
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
