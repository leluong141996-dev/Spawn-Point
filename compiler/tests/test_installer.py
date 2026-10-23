"""`spawnpoint setup`, `spawnpoint share` and changing a game with words after `create`."""

import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from spawnpoint import installer, studio_cli
from spawnpoint.build import build
from spawnpoint.studio import web

from conftest import load_example


@pytest.mark.parametrize("system,machine,asset,binary", [
    ("Linux", "x86_64", "Godot_v4.6.2-stable_linux.x86_64.zip", "Godot_v4.6.2-stable_linux.x86_64"),
    ("Linux", "aarch64", "Godot_v4.6.2-stable_linux.arm64.zip", "Godot_v4.6.2-stable_linux.arm64"),
    ("Darwin", "arm64", "Godot_v4.6.2-stable_macos.universal.zip", "Godot.app/Contents/MacOS/Godot"),
    ("Windows", "AMD64", "Godot_v4.6.2-stable_win64.exe.zip", "Godot_v4.6.2-stable_win64_console.exe"),
])
def test_the_right_godot_download_for_each_computer(system, machine, asset, binary):
    assert installer.godot_asset(system, machine) == (asset, binary)


def test_templates_go_where_godot_looks(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert installer.templates_dir() == tmp_path / "godot" / "export_templates" / "4.6.2.stable"
    assert installer.data_dir() == tmp_path / "spawnpoint"
    assert not installer.web_templates_ready()


class _RangeHandler(SimpleHTTPRequestHandler):
    """A static server that answers Range requests (like GitHub's release downloads)."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        data = path.read_bytes()
        rng = self.headers.get("Range")
        if rng:
            start, end = (int(x) for x in rng.split("=")[1].split("-"))
            body = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        else:
            body = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = Path(self.translate_path(self.path))
        self.send_response(200)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()


def test_web_templates_are_read_out_of_the_archive_with_ranges(monkeypatch, tmp_path):
    archive = tmp_path / "srv" / "templates.tpz"
    archive.parent.mkdir()
    big = b"x" * 3_000_000  # other platforms' templates, never downloaded
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("templates/linux_release.x86_64", big)
        z.writestr("templates/web_nothreads_release.zip", b"release-template")
        z.writestr("templates/web_nothreads_debug.zip", b"debug-template")
        z.writestr("templates/version.txt", "4.6.2.stable")
    handler = lambda *a, **k: _RangeHandler(*a, directory=str(archive.parent), **k)  # noqa: E731
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/templates.tpz"
        f = installer.HttpRangeFile(url, block=64 * 1024)
        assert f.size == archive.stat().st_size
        out = installer.install_web_templates(lambda m: None, url=url)
    finally:
        server.shutdown()
    assert (out / "web_nothreads_release.zip").read_bytes() == b"release-template"
    assert (out / "version.txt").read_text() == "4.6.2.stable"
    assert installer.web_templates_ready()


def test_setup_check_reports_what_is_missing(monkeypatch, capsys):
    monkeypatch.setattr(installer, "web_templates_ready", lambda: False)
    monkeypatch.setattr(installer, "check_llm", lambda: installer.LLMCheck(False, False, False, False))
    code = installer.run(SimpleNamespace(check=True, no_web=False))
    out = capsys.readouterr().out
    assert code == 1 and "✗ web export templates" in out and "✗ model" in out and "ollama.com" in out


def test_changing_a_game_with_words(monkeypatch, capsys, tmp_path):
    asked = iter(["make the jump higher", "cho nhảy cao hơn", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(asked))
    calls = []

    def fake_tweak(project, request, llm, web_export, on_layer):
        calls.append(request)
        return SimpleNamespace(ok=True, changes=[f"player.jump_tiles: 3.5 -> {3.5 + len(calls)}"])

    monkeypatch.setattr(studio_cli, "do_tweak", fake_tweak)
    studio_cli._chat(tmp_path, llm=None, web_export=True)
    out = capsys.readouterr().out
    assert calls == ["make the jump higher", "cho nhảy cao hơn"], "one rebuild per request, stops at an empty line"
    assert "player.jump_tiles: 3.5 -> 5.5" in out and "reloads" in out


@pytest.mark.skipif(not installer.web_templates_ready(), reason="Godot web export templates not installed")
def test_share_zips_a_web_build_without_live_reload(tmp_path):
    out = tmp_path / "game"
    assert build(load_example("coin_hopper.json"), out).ok
    zip_path = web.share_zip(out)
    assert zip_path == tmp_path / "game-web.zip"
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        assert {"index.html", "index.wasm", "index.pck", "index.js"} <= names
        assert all("/" not in n for n in names), "index.html at the top level, as itch.io wants"
        assert "version.json" not in z.read("index.html").decode(), "no live-reload polling in a shared game"
