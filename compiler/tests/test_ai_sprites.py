"""AI sprite providers against fake A1111 / OpenAI-images servers."""

import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from PIL import Image, ImageDraw

from spawnpoint.analyze import analyze
from spawnpoint.sprites import ai
from spawnpoint.sprites.generate import KINDS
from spawnpoint.studio.assemble import assemble
from spawnpoint.studio.brief import GameBrief, normalize

from conftest import codes, minimal


def fake_art() -> bytes:
    img = Image.new("RGB", (512, 512), (255, 0, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((180, 220, 330, 470), fill=(41, 120, 220))      # body
    d.ellipse((170, 60, 340, 230), fill=(240, 190, 140))        # head
    d.ellipse((280, 120, 310, 150), fill=(255, 255, 255))       # eye (white, inside the head)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def server():
    calls = {"n": 0}
    png = base64.b64encode(fake_art()).decode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            calls["n"] += 1
            self.rfile.read(int(self.headers["Content-Length"]))
            body = {"images": [png]} if self.path.startswith("/sdapi") else {"data": [{"b64_json": png}]}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", calls
    httpd.shutdown()


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE", tmp_path / "cache")
    for k in ("SPAWNPOINT_IMAGE_PROVIDER", "SPAWNPOINT_IMAGE_URL"):
        monkeypatch.delenv(k, raising=False)


def test_background_removal_keeps_inner_white():
    rgba = ai.remove_background(Image.open(io.BytesIO(fake_art())))
    assert rgba[0, 0, 3] == 0 and rgba[300, 250, 3] == 255
    assert rgba[135, 295, 3] == 255  # the white eye is enclosed by the head, so it stays opaque


@pytest.mark.parametrize("provider_cls", ["a1111", "openai"])
def test_ai_sprite_from_provider_and_cache(server, provider_cls):
    url, calls = server
    provider = ai.A1111Provider(url) if provider_cls == "a1111" else ai.OpenAIImagesProvider(url + "/v1", "k", "m")
    s = ai.ai_sprite("Hero", "hero", "a tiny knight", provider, seed=1)
    assert s.frame_size == KINDS["hero"].size
    assert set(s.animations) == {"idle", "run", "jump", "fall", "hurt"}
    assert len(s.polygon) >= 3
    idle = s.frame(0, 0)
    assert idle[0, 0, 3] == 0 and (idle[..., 3] > 0).sum() > 60
    assert len({tuple(p) for p in idle[idle[..., 3] > 0][:, :3].tolist()}) <= 16  # small palette
    ai.ai_sprite("Hero", "hero", "a tiny knight", provider, seed=1)
    assert calls["n"] == 1  # second call came from the cache


def test_graph_ai_sprite_uses_provider(server, monkeypatch, manifest):
    url, calls = server
    monkeypatch.setenv("SPAWNPOINT_IMAGE_PROVIDER", "a1111")
    monkeypatch.setenv("SPAWNPOINT_IMAGE_URL", url)
    g = minimal()
    g["entities"]["Player"]["sprite"] = {"ai": {"prompt": "a tiny knight", "kind": "hero"}}
    a = analyze(g, manifest)
    assert a.ok and "W_AI_SPRITE" not in codes(a.diagnostics), [str(d) for d in a.diagnostics]
    assert calls["n"] == 1 and "Player" in a.sprites


@pytest.mark.parametrize("env", [{}, {"SPAWNPOINT_IMAGE_PROVIDER": "a1111", "SPAWNPOINT_IMAGE_URL": "http://127.0.0.1:9"}])
def test_falls_back_to_generated_sprite(env, monkeypatch, manifest):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    g = minimal()
    g["entities"]["Player"]["sprite"] = {"ai": {"prompt": "a tiny knight", "kind": "hero"}}
    a = analyze(g, manifest)
    assert a.ok and "W_AI_SPRITE" in codes(a.diagnostics, "warning")
    assert a.sprites["Player"].frame_size == KINDS["hero"].size


def test_sprite_ref_needs_exactly_one_form(manifest):
    g = minimal()
    g["entities"]["Player"]["sprite"] = {"ai": {"prompt": "x", "kind": "hero"}, "generate": {"kind": "hero"}}
    assert "E_SCHEMA" in codes(analyze(g, manifest).diagnostics)


def test_studio_ai_art_flag():
    b, _ = normalize(GameBrief.model_validate({"title": "Knight Run", "genre": "platformer",
                                               "player": {"character": "Knight"},
                                               "enemies": [{"name": "Slime", "archetype": "walker"}]}))
    g = assemble(b, 2, 1, ai_art=True)
    assert g["entities"]["Player"]["sprite"]["ai"]["prompt"].startswith("knight")
    assert g["entities"]["Slime"]["sprite"]["ai"]["kind"] == "slime"
    assert "generate" in assemble(b, 2, 1)["entities"]["Player"]["sprite"]
