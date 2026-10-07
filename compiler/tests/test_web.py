"""Web export + real browser check (skipped without Godot web templates or Chrome)."""

from pathlib import Path

import pytest

from spawnpoint import godot
from spawnpoint.build import build
from spawnpoint.studio import web, webcheck

from conftest import load_example

TEMPLATES = Path.home() / ".local/share/godot/export_templates"
has_templates = any(TEMPLATES.glob("*/web_nothreads_release.zip"))

pytestmark = [
    pytest.mark.skipif(not godot.available(), reason="Godot not installed"),
    pytest.mark.skipif(not has_templates, reason="Godot web export templates not installed"),
]


def test_export_serve_and_play_in_browser(tmp_path):
    out = tmp_path / "game"
    assert build(load_example("coin_hopper.json"), out).ok
    web.export(out)
    for f in ("index.html", "index.wasm", "index.pck", "index.js", "version.json"):
        assert (out / "web" / f).exists(), f
    assert "version.json" in (out / "web" / "index.html").read_text()  # live reload injected
    assert web.bump_version(out) == 2

    if webcheck.find_chrome() is None:
        pytest.skip("Chrome not installed")
    server = web.Server(out, 8090).start()
    try:
        res = webcheck.check(server.url, seconds=12)
    finally:
        server.stop()
    assert not res.errors, res.errors
    assert any("Godot Engine" in line for line in res.console), res.console
    assert res.canvas_size and res.canvas_size[0] > 0
    assert res.screenshot and len(res.screenshot) > 5000
