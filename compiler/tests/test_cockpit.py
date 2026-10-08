"""Cockpit API against a live server (stdlib HTTP + SSE), with a scripted LLM."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from spawnpoint import godot
from spawnpoint.build import build
from spawnpoint.cockpit.server import Cockpit, CockpitServer
from spawnpoint.studio.llm import ScriptedModel
from spawnpoint.studio import webcheck

from conftest import load_example

pytestmark = pytest.mark.skipif(not godot.available(), reason="Godot not installed")


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    assert build(load_example("pixel_hopper.json"), ws / "pixel-hopper").ok
    return ws


@pytest.fixture
def cockpit(workspace):
    llm = {"model": None}
    app = Cockpit(workspace, llm_factory=lambda: llm["model"], web_export=False)
    srv = CockpitServer(app, 8095).start()
    yield srv, app, llm
    srv.stop()


def get(srv, path):
    with urllib.request.urlopen(srv.url.rstrip("/") + path, timeout=10) as r:
        return r.status, r.read()


def post(srv, path, body):
    req = urllib.request.Request(srv.url.rstrip("/") + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_static_and_projects(cockpit):
    srv, _, _ = cockpit
    code, html = get(srv, "/")
    assert code == 200 and b"Spawn Point" in html
    _, data = get(srv, "/api/projects")
    (p,) = json.loads(data)
    assert p["name"] == "pixel-hopper" and p["genre"] == "platformer" and not p["studio"]
    _, data = get(srv, "/api/projects/pixel-hopper")
    d = json.loads(data)
    health = d["entities"]["Player"]["components"]["Health"]
    mh = next(x for x in health["params"] if x["name"] == "max_health")
    assert mh["value"] == 3 and mh["set"] and mh["min"] == 1
    assert d["entities"]["Slime"]["sprite"] is True


@pytest.mark.parametrize("path", ["/game/../../etc/passwd", "/api/projects/..", "/files/pixel-hopper/../spawnpoint.json",
                                  "/files/pixel-hopper/rules/main_rules.gd", "/static/../server.py"])
def test_paths_stay_inside(cockpit, path):
    srv, _, _ = cockpit
    with pytest.raises(urllib.error.HTTPError) as e:
        get(srv, path)
    assert e.value.code in (403, 404)


def test_bad_requests(cockpit):
    srv, _, _ = cockpit
    assert post(srv, "/api/create", {"prompt": " "})[0] == 400
    assert post(srv, "/api/projects/nope/tweak", {"request": "x"})[0] == 404
    assert post(srv, "/api/projects/pixel-hopper/params", {"entity": "Player"})[0] == 400


def test_param_edit_job_and_events(cockpit, workspace):
    srv, app, _ = cockpit
    events = []
    ready = threading.Event()

    def listen():
        with urllib.request.urlopen(srv.url + "api/events", timeout=60) as r:
            ready.set()
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    events.append(ev)
                    if ev["type"] in ("done", "error"):
                        return

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    ready.wait(5)
    code, job = post(srv, "/api/projects/pixel-hopper/params",
                     {"entity": "Player", "component": "Health", "param": "max_health", "value": 5})
    assert code == 202
    done = app.jobs.wait(job["id"])
    assert done.status == "done", done.error
    t.join(10)
    assert [e["type"] for e in events][-1] == "done"
    graph = json.loads((workspace / "pixel-hopper" / "spawnpoint.json").read_text())
    assert graph["entities"]["Player"]["components"]["Health"]["max_health"] == 5


def test_invalid_param_is_rejected_before_building(cockpit):
    srv, app, _ = cockpit
    _, job = post(srv, "/api/projects/pixel-hopper/params",
                  {"entity": "Player", "component": "Health", "param": "max_health", "value": 0})
    done = app.jobs.wait(job["id"])
    assert done.status == "error" and "outside" in done.error


def test_entity_edit_repairs_and_creates_projectile(cockpit, workspace):
    srv, app, llm = cockpit
    bad = {"set_params": [{"component": "Health", "param": "max_hp", "value": 2}], "add_components": [], "add_rules": []}
    good = {"set_params": [{"component": "Health", "param": "max_health", "value": 2}],
            "add_components": [{"component": "Weapon", "params": [{"param": "projectile", "value": "Fireball"},
                                                                  {"param": "auto_fire", "value": True}]}],
            "add_rules": []}
    llm["model"] = ScriptedModel([bad, good])
    _, job = post(srv, "/api/projects/pixel-hopper/entity", {"entity": "Slime", "request": "tougher, shoots fire"})
    done = app.jobs.wait(job["id"])
    assert done.status == "done", done.error
    assert done.result["rounds"] == 2
    graph = json.loads((workspace / "pixel-hopper" / "spawnpoint.json").read_text())
    slime = graph["entities"]["Slime"]["components"]
    assert slime["Health"]["max_health"] == 2 and slime["Weapon"]["projectile"] == "Fireball"
    assert "Bullet" not in graph["entities"]  # only entities that have a Weapon get projectiles
    fireball = graph["entities"]["Fireball"]
    assert "Projectile" in fireball["components"] and fireball["team"] == "enemy"


def test_cockpit_page_in_browser(cockpit):
    if webcheck.find_chrome() is None:
        pytest.skip("Chrome not installed")
    srv, _, _ = cockpit
    res = webcheck.check(srv.url, seconds=4, size=(1400, 900),
                         expression="[...document.querySelectorAll('#project-list li')].map(li => li.textContent)")
    assert not res.errors, res.errors
    assert res.value and "Pixel Hopper" in res.value[0]
