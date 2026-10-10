"""Web export of a built project and a tiny live-reloading static server."""

from __future__ import annotations

import functools
import json
import socket
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import godot

WEB_DIR = "web"
VERSION_FILE = "version.json"

# Polls version.json and reloads the page when a new build lands.
LIVE_RELOAD = (
    "<script>(function(){var v=null;setInterval(function(){"
    "fetch('version.json?'+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null})"
    ".then(function(j){if(!j)return;if(v!==null&&j.version!==v)location.reload();v=j.version;})"
    ".catch(function(){});},1000);})();</script>"
)


def export_preset(head_include: str = LIVE_RELOAD) -> str:
    return "\n".join([
        "[preset.0]",
        "",
        'name="Web"',
        'platform="Web"',
        "runnable=true",
        "dedicated_server=false",
        'custom_features=""',
        'export_filter="all_resources"',
        'include_filter=""',
        'exclude_filter="build_plan.json,spawnpoint.json,studio.json"',
        f'export_path="{WEB_DIR}/index.html"',
        "",
        "[preset.0.options]",
        "",
        'custom_template/debug=""',
        'custom_template/release=""',
        "variant/extensions_support=false",
        # Single-threaded build: plays from any static server, no COOP/COEP headers needed.
        "variant/thread_support=false",
        "vram_texture_compression/for_desktop=true",
        "vram_texture_compression/for_mobile=false",
        "html/export_icon=true",
        'html/custom_html_shell=""',
        f"html/head_include={json.dumps(head_include)}",
        "html/canvas_resize_policy=2",
        "html/focus_canvas_on_start=true",
        "html/experimental_virtual_keyboard=false",
        "progressive_web_app/enabled=false",
        "",
    ])


def export(project: Path, head_include: str = LIVE_RELOAD) -> float:
    """Exports the project to <project>/web and bumps the live-reload version. Returns seconds."""
    t0 = time.perf_counter()
    web = project / WEB_DIR
    web.mkdir(exist_ok=True)
    (web / ".gdignore").write_text("")  # keep Godot from importing the build output
    (project / "export_presets.cfg").write_text(export_preset(head_include))
    result = godot.run(project, ["--export-release", "Web", f"{WEB_DIR}/index.html"], timeout=300)
    if result.returncode != 0 or not (web / "index.html").exists():
        raise godot.GodotError("web export failed (are the Godot web export templates installed?)", result.output)
    bump_version(project)
    return time.perf_counter() - t0


def bump_version(project: Path) -> int:
    path = project / WEB_DIR / VERSION_FILE
    try:
        version = json.loads(path.read_text())["version"] + 1
    except (OSError, ValueError, KeyError):
        version = 1
    path.write_text(json.dumps({"version": version}))
    return version


class _Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm",
                      ".pck": "application/octet-stream", ".js": "text/javascript"}

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # quiet
        pass


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise OSError(f"no free port in {start}..{start + 49}")


class Server:
    """Serves <project>/web on localhost in a background thread."""

    def __init__(self, project: Path, port: int = 8060):
        self.port = free_port(port)
        handler = functools.partial(_Handler, directory=str(project / WEB_DIR))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def start(self) -> "Server":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
