"""Demo site: discovery, the shared engine rewrite, the gallery page, and one real end-to-end build."""

import json
from pathlib import Path

import pytest

from spawnpoint import demo, godot
from spawnpoint.analyze import analyze
from spawnpoint.build import load_graph

TEMPLATES = Path.home() / ".local/share/godot/export_templates"
has_templates = any(TEMPLATES.glob("*/web_nothreads_release.zip"))

SHELL = ('<script src="index.js"></script><script>const GODOT_CONFIG = {"executable":"index",'
         '"fileSizes":{"index.pck":10,"index.wasm":20}};</script>')


def test_discover_lists_the_showcase_in_order():
    games = demo.discover()
    assert [g.slug for g in games] == ["pixel-hopper", "ninja-rescue", "knight-quest", "castle-defense", "star-run",
                                         "dino-eggs", "night-survivor", "sunny-farm", "pixel-arena"]
    assert all(g.title and g.blurb and g.controls.isascii() for g in games)


def test_showcase_graphs_are_valid_without_warnings(manifest):
    for g in demo.discover():
        a = analyze(load_graph(g.graph), manifest, g.graph.parent)
        assert a.ok and not a.diagnostics.warnings, (g.slug, [str(d) for d in a.diagnostics])


def _fake_game(root: Path, name: str, wasm: bytes = b"engine") -> Path:
    game = root / name
    game.mkdir(parents=True)
    (game / "index.html").write_text(SHELL)
    for f in demo.ENGINE_FILES:
        (game / f).write_bytes(wasm if f.endswith(".wasm") else b"js")
    (game / "index.pck").write_bytes(b"pck")
    return game


def test_share_engine_keeps_one_copy_and_rewrites_the_page(tmp_path):
    a, b = _fake_game(tmp_path, "a"), _fake_game(tmp_path, "b")
    demo.share_engine(tmp_path, a)
    demo.share_engine(tmp_path, b)
    assert sorted(p.name for p in (tmp_path / "engine").iterdir()) == sorted(demo.ENGINE_FILES)
    assert sorted(p.name for p in b.iterdir()) == ["index.html", "index.pck"]
    page = b.joinpath("index.html").read_text()
    assert 'src="../engine/index.js"' in page
    config = json.loads(page.split("GODOT_CONFIG = ")[1].split(";</script>")[0])
    assert config["executable"] == "../engine/index" and config["mainPack"] == "index.pck"
    assert "../engine/index.wasm" in config["fileSizes"]


def test_share_engine_refuses_mixed_engines(tmp_path):
    demo.share_engine(tmp_path, _fake_game(tmp_path, "a"))
    with pytest.raises(RuntimeError, match="differs"):
        demo.share_engine(tmp_path, _fake_game(tmp_path, "b", wasm=b"other"))


def test_index_html_escapes_text():
    g = demo.Game("x", Path("examples/x.json"), title="T <1>", tag="platformer", blurb='a "<b>" game',
                  controls="Jump: Space")
    page = demo.index_html([g])
    assert "&lt;b&gt;" in page and "<b>" not in page.split("<main")[1]
    assert 'href="x/"' in page and "x/thumb.png" in page and "Jump: Space" in page
    assert "Jump: Space" in demo.game_overlay("Jump: Space")


@pytest.mark.skipif(not godot.available(), reason="Godot not installed")
@pytest.mark.skipif(not has_templates, reason="Godot web export templates not installed")
def test_build_site_end_to_end(tmp_path):
    games = [g for g in demo.discover() if g.slug == "dino-eggs"]
    demo.build_site(tmp_path, games)
    assert not games[0].errors, games[0].errors
    assert (tmp_path / "engine" / "index.wasm").exists()
    assert (tmp_path / "dino-eggs" / "index.pck").exists()
    assert not (tmp_path / "dino-eggs" / "index.wasm").exists()
    assert "dino-eggs/" in (tmp_path / "index.html").read_text()
    assert (tmp_path / ".nojekyll").exists()
