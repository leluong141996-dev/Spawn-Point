"""Studio orchestrator: prompt -> brief -> layered builds -> web; and tweaks of an existing game."""

from __future__ import annotations

import json
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import manifest as manifest_mod
from ..analyze import analyze
from ..build import BuildResult, build
from ..manifest import Manifest
from . import web
from .assemble import LAYERS, assemble, chunks_fit, plan_chunks
from .brief import GameBrief, json_schema, normalize
from .creative import CreativeResult, creative_pass
from .llm import ChatModel, LLMError, Usage
from .prompts import (TRANSLATE_SCHEMA, brief_messages, needs_translation, translate_messages,
                      tweak_messages)

SESSION_FILE = "studio.json"
SEED_ATTEMPTS = 8

TWEAK_SCHEMA_NAME = "BriefUpdate"


class StudioError(RuntimeError):
    pass


@dataclass
class LayerReport:
    layer: int
    build: BuildResult
    web_seconds: float | None = None


@dataclass
class StudioResult:
    out_dir: Path
    brief: GameBrief
    notes: list[str]
    seed: int
    layers: list[LayerReport] = field(default_factory=list)
    creative: CreativeResult | None = None
    changes: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.layers) and all(r.build.ok for r in self.layers)


LayerCallback = Callable[[LayerReport], None]


# --- brief ------------------------------------------------------------------------------------


def design_brief(prompt: str, llm: ChatModel) -> tuple[GameBrief, list[str], str]:
    """Returns (normalized brief, notes, the English prompt actually used)."""
    english = prompt
    if needs_translation(prompt):
        english = llm.chat_json(translate_messages(prompt), TRANSLATE_SCHEMA, "Translation",
                                temperature=0.1, max_tokens=300).get("english") or prompt
    raw = llm.chat_json(brief_messages(english), json_schema(), "GameBrief", temperature=0.4)
    try:
        brief = GameBrief.model_validate(raw)
    except Exception as e:  # guided decoding makes this rare; retry once with the error
        raise StudioError(f"the LLM produced an invalid brief: {e}") from e
    brief, notes = normalize(brief)
    return brief, notes, english


def _playable(brief: GameBrief, seed: int, chunks: list[str] | None, manifest: Manifest) -> bool:
    analysis = analyze(assemble(brief, LAYERS[-1], seed, chunks), manifest)
    return analysis.ok and not any(d.code == "W_UNREACHABLE" for d in analysis.diagnostics)


def choose_seed(brief: GameBrief, seed: int, manifest: Manifest) -> tuple[int, list[str] | None]:
    """First seed (from `seed`) whose full game has no reachability warnings, and its chunk plan."""
    for s in range(seed, seed + SEED_ATTEMPTS):
        chunks = plan_chunks(brief, s)
        if _playable(brief, s, chunks, manifest):
            return s, chunks
    return seed, plan_chunks(brief, seed)


def default_seed(prompt: str) -> int:
    return zlib.crc32(prompt.encode()) % 100_000


# --- create -----------------------------------------------------------------------------------


def create(prompt: str, out_dir: Path | Callable[[GameBrief], Path], llm: ChatModel, *, seed: int | None = None, creative: bool = False,
           brief: GameBrief | None = None, web_export: bool = True,
           on_layer: LayerCallback | None = None, on_brief: Callable[[GameBrief, list[str]], None] | None = None,
           manifest: Manifest | None = None) -> StudioResult:
    manifest = manifest or manifest_mod.load()
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    english = prompt
    if brief is None:
        brief, notes, english = design_brief(prompt, llm)
    else:
        brief, notes = normalize(brief)
    timings["design"] = time.perf_counter() - t0
    if on_brief:
        on_brief(brief, notes)
    if callable(out_dir):  # e.g. a folder named after the designed title
        out_dir = out_dir(brief)

    seed, chunks = choose_seed(brief, default_seed(prompt) if seed is None else seed, manifest)
    result = StudioResult(out_dir, brief, notes, seed, usage=llm.usage)
    creative_result = None
    for layer in LAYERS:
        graph = assemble(brief, layer, seed, chunks)
        if layer == LAYERS[-1] and creative:
            t = time.perf_counter()
            creative_result = creative_pass(graph, english, llm, manifest)
            timings["creative"] = time.perf_counter() - t
            graph = creative_result.graph
        report = _build_layer(layer, graph, out_dir, manifest, web_export)
        result.layers.append(report)
        if on_layer:
            on_layer(report)
        if not report.build.ok:
            break
    result.creative = creative_result
    timings["total"] = time.perf_counter() - t0
    result.timings = timings
    _save_session(out_dir, {"prompt": prompt, "english": english, "brief": brief.model_dump(), "seed": seed,
                            "chunks": chunks,
                            "creative_patch": creative_result.patch if creative_result else None,
                            "model": llm.name, "history": []})
    return result


def _build_layer(layer: int, graph: dict, out_dir: Path, manifest: Manifest, web_export: bool) -> LayerReport:
    res = build(graph, out_dir, manifest=manifest, smoke=True)
    report = LayerReport(layer, res)
    if res.ok and web_export:
        report.web_seconds = web.export(out_dir)
    return report


# --- tweak ------------------------------------------------------------------------------------


def tweak_schema() -> dict:
    schema = json_schema()
    defs = schema.pop("$defs", {})
    return {"type": "object", "$defs": defs,
            "properties": {"brief": schema, "new_level": {"type": "boolean"}},
            "required": ["brief", "new_level"], "additionalProperties": False}


def tweak(out_dir: Path, request: str, llm: ChatModel, *, web_export: bool = True,
          on_layer: LayerCallback | None = None, manifest: Manifest | None = None) -> StudioResult:
    manifest = manifest or manifest_mod.load()
    session = load_session(out_dir)
    old = GameBrief.model_validate(session["brief"])
    t0 = time.perf_counter()
    english = request
    if needs_translation(request):
        english = llm.chat_json(translate_messages(request), TRANSLATE_SCHEMA, "Translation",
                                temperature=0.1, max_tokens=300).get("english") or request
    raw = llm.chat_json(tweak_messages(old.model_dump(), english), tweak_schema(), TWEAK_SCHEMA_NAME,
                        temperature=0.1)
    try:
        new = GameBrief.model_validate(raw["brief"])
    except Exception as e:
        raise StudioError(f"the LLM produced an invalid brief update: {e}") from e
    new, notes = normalize(new)
    seed, chunks = session["seed"], session.get("chunks")
    if raw.get("new_level"):
        seed, chunks = choose_seed(new, seed + 1000, manifest)
    elif new.genre != "platformer":
        if new.genre != old.genre or not _playable(new, seed, None, manifest):
            seed, chunks = choose_seed(new, seed, manifest)
    elif not (chunks_fit(new, chunks) and _playable(new, seed, chunks, manifest)):
        # The kept layout no longer works for the changed player (e.g. lower jump): re-plan.
        seed, chunks = choose_seed(new, seed, manifest)
    changes = diff_briefs(old.model_dump(), new.model_dump())
    if raw.get("new_level"):
        changes.append("new level layout")
    timings = {"design": time.perf_counter() - t0}

    result = StudioResult(out_dir, new, notes, seed, changes=changes, usage=llm.usage)
    graph = assemble(new, LAYERS[-1], seed, chunks)
    report = _build_layer(LAYERS[-1], graph, out_dir, manifest, web_export)
    result.layers.append(report)
    if on_layer:
        on_layer(report)
    timings["total"] = time.perf_counter() - t0
    result.timings = timings
    if report.build.ok:
        session["history"].append({"request": request, "english": english, "changes": changes})
        session.update(brief=new.model_dump(), seed=seed, chunks=chunks)
        _save_session(out_dir, session)
    return result


def diff_briefs(old: dict, new: dict, prefix: str = "") -> list[str]:
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        path = f"{prefix}{key}"
        if isinstance(a, dict) and isinstance(b, dict):
            out += diff_briefs(a, b, path + ".")
        elif a != b:
            out.append(f"{path}: {json.dumps(a, ensure_ascii=False)} -> {json.dumps(b, ensure_ascii=False)}")
    return out


# --- session ----------------------------------------------------------------------------------


def load_session(out_dir: Path) -> dict:
    path = out_dir / SESSION_FILE
    if not path.exists():
        raise StudioError(f"{out_dir} was not created by `spawnpoint create` (no {SESSION_FILE})")
    return json.loads(path.read_text())


def _save_session(out_dir: Path, data: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SESSION_FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


__all__ = ["create", "tweak", "design_brief", "StudioError", "StudioResult", "LLMError"]
