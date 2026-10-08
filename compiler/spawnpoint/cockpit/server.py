"""Cockpit backend: standard-library HTTP server, JSON API, Server-Sent Events, one build worker."""

from __future__ import annotations

import itertools
import json
import mimetypes
import queue
import threading
import time
import traceback
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .. import godot, manifest as manifest_mod
from ..project import slugify
from ..studio import web
from ..studio.llm import ChatModel, LLMError, OpenAICompatible

STATIC = Path(__file__).parent / "static"
FILE_DIRS = ("sprites", "playtest")  # project sub-folders the page may read


# --- events -----------------------------------------------------------------------------------

class Hub:
    """Fan-out of events to every connected SSE client."""

    def __init__(self) -> None:
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def publish(self, event: dict) -> None:
        event = dict(event, time=round(time.time(), 3))
        with self._lock:
            for q in list(self._clients):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


@dataclass
class Job:
    id: int
    kind: str
    project: str | None
    status: str = "queued"  # queued | running | done | error
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "project": self.project, "status": self.status,
                "result": self.result, "error": self.error}


class Jobs:
    """Runs jobs one at a time (Godot builds must not overlap) and reports through the hub."""

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self._q: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self.jobs: dict[int, Job] = {}
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, kind: str, project: str | None, fn: Callable[[Callable[[str], None]], Any]) -> Job:
        job = Job(next(self._ids), kind, project)
        self.jobs[job.id] = job
        self._q.put((job, fn))
        self.hub.publish({"type": "queued", "job": job.to_dict()})
        return job

    def _worker(self) -> None:
        while True:
            job, fn = self._q.get()
            job.status = "running"
            self.hub.publish({"type": "started", "job": job.to_dict()})

            def log(msg: str, job=job) -> None:
                self.hub.publish({"type": "log", "job": job.id, "message": msg})

            try:
                job.result = fn(log)
                job.status = "done"
                self.hub.publish({"type": "done", "job": job.to_dict()})
            except Exception as e:  # report every failure to the page instead of dying
                job.status, job.error = "error", f"{type(e).__name__}: {e}"
                log(traceback.format_exc(limit=3))
                self.hub.publish({"type": "error", "job": job.to_dict()})

    def wait(self, job_id: int, timeout: float = 600) -> Job:
        end = time.time() + timeout
        while time.time() < end:
            job = self.jobs[job_id]
            if job.status in ("done", "error"):
                return job
            time.sleep(0.05)
        raise TimeoutError(f"job {job_id} still {self.jobs[job_id].status}")


# --- application ------------------------------------------------------------------------------

class Cockpit:
    def __init__(self, workspace: Path, llm_factory: Callable[[], ChatModel] = OpenAICompatible,
                 web_export: bool = True) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.llm_factory = llm_factory
        self.web_export = web_export
        self.hub = Hub()
        self.jobs = Jobs(self.hub)
        self.manifest = manifest_mod.load()

    # -- helpers -----------------------------------------------------------------------------
    def project_dir(self, name: str) -> Path:
        p = (self.workspace / name).resolve()
        if p.parent != self.workspace or not (p / "spawnpoint.json").exists():
            raise KeyError(name)
        return p

    def projects(self) -> list[dict]:
        out = []
        for d in sorted(self.workspace.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            g = d / "spawnpoint.json"
            if not g.exists():
                continue
            try:
                graph = json.loads(g.read_text())
            except ValueError:
                continue
            out.append({"name": d.name, "title": graph.get("name", d.name), "genre": graph.get("genre"),
                        "studio": (d / "studio.json").exists(), "web": (d / "web" / "index.html").exists(),
                        "updated": round(g.stat().st_mtime)})
        return out

    def detail(self, name: str) -> dict:
        p = self.project_dir(name)
        graph = json.loads((p / "spawnpoint.json").read_text())
        session = json.loads((p / "studio.json").read_text()) if (p / "studio.json").exists() else None
        entities = {}
        for ename, ent in graph["entities"].items():
            comps = {}
            for cname, params in (ent.get("components") or {}).items():
                spec = self.manifest.get(cname)
                comps[cname] = {
                    "doc": spec.doc.split("\n")[0] if spec else "",
                    "params": [{"name": prm.name, "type": prm.type, "value": params.get(prm.name, prm.default),
                                "default": prm.default, "min": prm.min, "max": prm.max,
                                "choices": list(prm.choices) if prm.choices else None, "doc": prm.doc,
                                "set": prm.name in params}
                               for prm in (spec.params.values() if spec else [])],
                }
            entities[ename] = {"body": ent.get("body", "character"), "team": ent.get("team"),
                               "components": comps, "sprite": (p / "sprites" / f"{ename}.png").exists()}
        report = p / "playtest" / "report.json"
        return {
            "name": name, "title": graph.get("name"), "genre": graph.get("genre"), "graph": graph,
            "entities": entities, "rules": graph.get("rules", []),
            "brief": session.get("brief") if session else None,
            "history": session.get("history", []) if session else [],
            "overrides": session.get("overrides", []) if session else [],
            "tuning": session.get("tuning", []) if session else [],
            "playtest": json.loads(report.read_text()) if report.exists() else None,
            "web": (p / "web" / "index.html").exists(),
        }

    def status(self) -> dict:
        llm = self.llm_factory()
        up = True
        model = None
        try:
            if isinstance(llm, OpenAICompatible):
                urllib.request.urlopen(llm.base_url.rstrip("/") + "/models", timeout=2)
                model = llm.resolve_model()
            else:
                model = llm.name
        except Exception:
            up = False
        return {"llm": up, "model": model, "base_url": getattr(llm, "base_url", None), "godot": godot.available(),
                "workspace": str(self.workspace)}

    # -- jobs --------------------------------------------------------------------------------
    def create(self, prompt: str, creative: bool = False, playtest: bool = False) -> Job:
        from ..studio.orchestrator import create

        def run(log):
            holder: dict[str, Path] = {}

            def out_for(brief):
                holder["out"] = self.workspace / slugify(brief.title)
                log(f"designing done: “{brief.title}” ({brief.genre}, goal {brief.goal})")
                return holder["out"]

            def on_layer(r):
                log(f"layer {r.layer}: {'ok' if r.build.ok else 'FAILED'} "
                    f"({r.build.timings.get('total', 0):.1f}s build, {r.web_seconds or 0:.1f}s web)")
                if r.build.ok:
                    self.hub.publish({"type": "reload", "project": holder["out"].name})

            res = create(prompt, out_for, self.llm_factory(), creative=creative, web_export=self.web_export,
                         on_layer=on_layer, playtest=playtest, on_progress=lambda m: log(f"playtest: {m}"))
            if not res.ok:
                raise RuntimeError("build failed: " + "; ".join(
                    str(d) for r in res.layers for d in r.build.diagnostics.errors))
            return {"project": holder["out"].name, "notes": res.notes}

        return self.jobs.submit("create", None, run)

    def tweak(self, name: str, request: str) -> Job:
        from ..studio.orchestrator import tweak

        p = self.project_dir(name)

        def run(log):
            res = tweak(p, request, self.llm_factory(), web_export=self.web_export)
            for c in res.changes:
                log(f"changed {c}")
            if not res.ok:
                raise RuntimeError("build failed")
            self.hub.publish({"type": "reload", "project": name})
            return {"changes": res.changes, "notes": res.notes}

        return self.jobs.submit("tweak", name, run)

    def edit_entity(self, name: str, entity: str, request: str) -> Job:
        from ..studio.edits import edit_entity

        p = self.project_dir(name)

        def run(log):
            res = edit_entity(p, entity, request, self.llm_factory(), manifest=self.manifest,
                              web_export=self.web_export)
            if not res.ok:
                raise RuntimeError("; ".join(res.errors[:3]) or "edit failed")
            log(f"applied after {res.rounds} round(s): {json.dumps(res.patch)}")
            self.hub.publish({"type": "reload", "project": name})
            return {"patch": res.patch, "rounds": res.rounds}

        return self.jobs.submit("entity", name, run)

    def set_param(self, name: str, entity: str, component: str, param: str, value: Any) -> Job:
        from ..studio.edits import apply_override, set_param_patch

        p = self.project_dir(name)

        def run(log):
            res = apply_override(p, set_param_patch(entity, component, param, value), manifest=self.manifest,
                                 web_export=self.web_export)
            if not res.ok:
                raise RuntimeError("; ".join(res.errors[:3]))
            log(f"{entity}.{component}.{param} = {value}")
            self.hub.publish({"type": "reload", "project": name})
            return {"patch": res.patch}

        return self.jobs.submit("params", name, run)

    def playtest(self, name: str, tune: bool, runs: int = 3) -> Job:
        from .. import playtest as pt
        from ..studio.orchestrator import studio_playtest

        p = self.project_dir(name)

        def run(log):
            if (p / "studio.json").exists():
                res = studio_playtest(p, runs=runs, tune=tune, web_export=self.web_export, manifest=self.manifest,
                                      on_progress=log)
            else:
                res = pt.playtest(p, runs=runs, tune=tune, manifest=self.manifest, on_progress=log)
                if self.web_export and tune and res.changes and (p / "web" / "index.html").exists():
                    web.export(p)
            if res.changes:
                self.hub.publish({"type": "reload", "project": name})
            return {"changes": [str(c) for c in res.changes], "issues": res.final.level_issues}

        return self.jobs.submit("playtest", name, run)

    def export(self, name: str) -> Job:
        p = self.project_dir(name)

        def run(log):
            secs = web.export(p)
            log(f"web build ready in {secs:.1f}s")
            self.hub.publish({"type": "reload", "project": name})
            return {}

        return self.jobs.submit("export", name, run)


# --- HTTP -------------------------------------------------------------------------------------

def make_handler(app: Cockpit):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:  # quiet
            pass

        # -- responses ------------------------------------------------------------------------
        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, code: int = 200) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _error(self, code: int, msg: str) -> None:
            self._json({"error": msg}, code)

        def _file(self, path: Path, root: Path) -> None:
            try:
                path = path.resolve()
                path.relative_to(root.resolve())
            except (ValueError, OSError):
                return self._error(403, "forbidden")
            if path.is_dir():
                path = path / "index.html"
            if not path.is_file():
                return self._error(404, "not found")
            ctype = {".wasm": "application/wasm", ".pck": "application/octet-stream", ".js": "text/javascript",
                     ".css": "text/css"}.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), ctype)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n == 0:
                return {}
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                raise ValueError("invalid JSON body")
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        # -- routing --------------------------------------------------------------------------
        def do_GET(self) -> None:
            path = unquote(urlparse(self.path).path)
            parts = [p for p in path.split("/") if p]
            try:
                if not parts:
                    return self._file(STATIC / "index.html", STATIC)
                if parts[0] == "static":
                    return self._file(STATIC.joinpath(*parts[1:]), STATIC)
                if parts[0] == "game" and len(parts) >= 2:
                    root = app.project_dir(parts[1]) / "web"
                    return self._file(root.joinpath(*parts[2:]) if len(parts) > 2 else root, root)
                if parts[0] == "files" and len(parts) >= 3 and parts[2] in FILE_DIRS:
                    proj = app.project_dir(parts[1])
                    return self._file(proj.joinpath(*parts[2:]), proj / parts[2])
                if parts[:2] == ["api", "events"]:
                    return self._events()
                if parts[:2] == ["api", "status"]:
                    return self._json(app.status())
                if parts[:2] == ["api", "projects"] and len(parts) == 2:
                    return self._json(app.projects())
                if parts[:2] == ["api", "projects"] and len(parts) == 3:
                    return self._json(app.detail(parts[2]))
                if parts[:2] == ["api", "jobs"] and len(parts) == 3:
                    return self._json(app.jobs.jobs[int(parts[2])].to_dict())
            except KeyError:
                return self._error(404, "no such project or job")
            return self._error(404, "not found")

        def do_POST(self) -> None:
            parts = [p for p in unquote(urlparse(self.path).path).split("/") if p]
            try:
                body = self._body()
                if parts == ["api", "create"]:
                    prompt = str(body.get("prompt", "")).strip()
                    if not prompt:
                        return self._error(400, "prompt is required")
                    job = app.create(prompt, bool(body.get("creative")), bool(body.get("playtest")))
                elif len(parts) == 4 and parts[:2] == ["api", "projects"]:
                    name, action = parts[2], parts[3]
                    if action == "tweak":
                        job = app.tweak(name, _required(body, "request"))
                    elif action == "entity":
                        job = app.edit_entity(name, _required(body, "entity"), _required(body, "request"))
                    elif action == "params":
                        if "value" not in body:
                            return self._error(400, "value is required")
                        job = app.set_param(name, _required(body, "entity"), _required(body, "component"),
                                            _required(body, "param"), body["value"])
                    elif action == "playtest":
                        job = app.playtest(name, bool(body.get("tune")), int(body.get("runs", 3)))
                    elif action == "export":
                        job = app.export(name)
                    else:
                        return self._error(404, "unknown action")
                else:
                    return self._error(404, "not found")
            except KeyError:
                return self._error(404, "no such project")
            except ValueError as e:
                return self._error(400, str(e))
            self._json(job.to_dict(), 202)

        def _events(self) -> None:
            q = app.hub.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = q.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.hub.unsubscribe(q)

    return Handler


def _required(body: dict, key: str) -> str:
    value = str(body.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


class CockpitServer:
    def __init__(self, app: Cockpit, port: int = 8070) -> None:
        self.app = app
        self.port = web.free_port(port)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), make_handler(app))
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def start(self) -> "CockpitServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


__all__ = ["Cockpit", "CockpitServer", "Hub", "Jobs", "LLMError"]
