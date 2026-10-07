"""Component manifest: what the Godot library offers, generated from the scripts themselves.

`generate()` runs Godot headless to introspect every component script (exports, ranges, signals,
methods, metadata constants) and merges the `##` doc comments parsed from source. `load()` reads
the resulting manifest.json. Nobody edits the manifest by hand.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import godot

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_PROJECT = Path(os.environ.get("SPAWNPOINT_LIBRARY", REPO_ROOT / "godot"))
ADDON_DIR = LIBRARY_PROJECT / "addons" / "spawn_point"
MANIFEST_PATH = ADDON_DIR / "manifest.json"

BODY_CLASSES = {"character": "CharacterBody2D", "static": "StaticBody2D", "area": "Area2D"}


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # Godot type name: bool, int, float, String, Vector2, Color
    default: Any
    doc: str = ""
    min: float | None = None
    max: float | None = None
    choices: tuple[str, ...] | None = None

    def describe(self) -> str:
        s = f"{self.name}: {self.type} = {json.dumps(self.default)}"
        if self.min is not None:
            s += f" [{self.min:g}..{self.max:g}]"
        if self.choices:
            s += " one of " + "|".join(self.choices)
        return s


@dataclass(frozen=True)
class Arg:
    name: str
    type: str


@dataclass(frozen=True)
class Signal:
    name: str
    args: tuple[Arg, ...]
    doc: str = ""


@dataclass(frozen=True)
class Method:
    name: str
    args: tuple[Arg, ...]
    default_count: int
    doc: str = ""

    @property
    def min_args(self) -> int:
        return len(self.args) - self.default_count


@dataclass
class Component:
    name: str
    class_name: str
    script: str
    base: str
    hosts: list[str]
    requires: list[str]
    category: str
    entity_params: list[str]
    doc: str
    params: dict[str, Param] = field(default_factory=dict)
    state: dict[str, str] = field(default_factory=dict)
    signals: dict[str, Signal] = field(default_factory=dict)
    methods: dict[str, Method] = field(default_factory=dict)

    @property
    def is_area(self) -> bool:
        return self.base == "Area2D"


@dataclass
class Manifest:
    godot_version: str
    components: dict[str, Component]

    def get(self, name: str) -> Component | None:
        return self.components.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.components


# ---------------------------------------------------------------------------------------------
# Loading


def load(path: Path | None = None) -> Manifest:
    data = json.loads(Path(path or MANIFEST_PATH).read_text())
    return from_dict(data)


def from_dict(data: dict) -> Manifest:
    comps: dict[str, Component] = {}
    for c in data["components"]:
        comp = Component(
            name=c["name"],
            class_name=c["class"],
            script=c["script"],
            base=c["base"],
            hosts=list(c["hosts"]),
            requires=list(c["requires"]),
            category=c["category"],
            entity_params=list(c.get("entity_params", [])),
            doc=c.get("doc", ""),
            state={s["name"]: s["type"] for s in c.get("state", [])},
        )
        for p in c["params"]:
            comp.params[p["name"]] = _param(p)
        for s in c["signals"]:
            comp.signals[s["name"]] = Signal(s["name"], tuple(Arg(a["name"], a["type"]) for a in s["args"]), s.get("doc", ""))
        for m in c["methods"]:
            comp.methods[m["name"]] = Method(
                m["name"], tuple(Arg(a["name"], a["type"]) for a in m["args"]), m["default_count"], m.get("doc", "")
            )
        comps[comp.name] = comp
    return Manifest(data.get("godot", ""), comps)


def _param(p: dict) -> Param:
    lo = hi = None
    choices = None
    if p.get("hint") == "range":
        parts = [x.strip() for x in p["hint_string"].split(",")]
        lo, hi = float(parts[0]), float(parts[1])
    elif p.get("hint") == "enum":
        choices = tuple(x.split(":")[0] for x in p["hint_string"].split(","))
    return Param(p["name"], p["type"], p.get("default"), p.get("doc", ""), lo, hi, choices)


# ---------------------------------------------------------------------------------------------
# Generation


def generate(project: Path = LIBRARY_PROJECT, out: Path | None = None) -> dict:
    """Introspect the library in Godot and write manifest.json. Returns the manifest dict."""
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "raw.json"
        godot.run_scene(project, "res://addons/spawn_point/tools/dump_manifest.tscn", [str(raw_path)], import_first=True)
        raw = json.loads(raw_path.read_text())
    for comp in raw["components"]:
        docs = parse_docs((project / comp["script"].removeprefix("res://")).read_text())
        comp["doc"] = docs.get("@class", "")
        for group in ("params", "signals", "methods"):
            for item in comp[group]:
                item["doc"] = docs.get(item["name"], "")
    data = {"godot": raw["godot"], "components": raw["components"]}
    target = out or (project / "addons" / "spawn_point" / "manifest.json")
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return data


_DECL = re.compile(r"^(?:@export\w*(?:\([^)]*\))?\s+)?(?:var|signal|func|static func)\s+(\w+)")


def parse_docs(source: str) -> dict[str, str]:
    """Map declared names to their `##` doc comments. The class doc is stored under '@class'."""
    docs: dict[str, str] = {}
    pending: list[str] = []
    class_doc: list[str] = []
    seen_decl = False
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("##"):
            pending.append(line[2:].strip())
            continue
        if not line:
            if pending and not seen_decl and not class_doc:
                class_doc, pending = pending, []
            continue
        if line.startswith(("class_name", "extends")):
            if pending:
                class_doc += pending
                pending = []
            continue
        m = _DECL.match(line)
        if m:
            seen_decl = True
            if pending:
                docs[m.group(1)] = " ".join(p for p in pending if p).strip()
        elif not seen_decl and pending and line.startswith("const") and not class_doc:
            class_doc, pending = pending, []
        pending = []
    docs["@class"] = " ".join(p if p else "\n" for p in class_doc).replace(" \n ", "\n").strip()
    return docs
