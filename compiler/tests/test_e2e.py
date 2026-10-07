"""End-to-end: build the examples with real Godot and smoke-run them."""

import pytest

from spawnpoint import godot
from spawnpoint.build import build

from conftest import load_example, minimal

pytestmark = pytest.mark.skipif(not godot.available(), reason="Godot not installed")


@pytest.mark.parametrize("example", ["coin_hopper.json", "neon_arena.json", "pixel_hopper.json"])
def test_examples_build_and_run(tmp_path, example):
    result = build(load_example(example), tmp_path / "game")
    assert result.ok, "\n".join(str(d) for d in result.diagnostics) + "\n" + result.log[-2000:]
    assert not result.diagnostics.warnings, [str(d) for d in result.diagnostics]
    out = tmp_path / "game"
    for f in ("project.godot", "levels/main.tscn", "levels/tiles.tres", "rules/main_rules.gd", "sfx/jump.wav"):
        assert (out / f).exists(), f
    smoke = result.smoke
    assert smoke["player_found"] and smoke["player_alive"]
    assert smoke["moved_px"] > 50
    assert result.timings["total"] < 30


def test_invalid_graph_never_reaches_godot(tmp_path):
    g = minimal()
    g["entities"]["Player"]["components"]["Helth"] = {}
    result = build(g, tmp_path / "game")
    assert not result.ok
    assert not (tmp_path / "game").exists()
    assert "godot_import" not in result.timings
