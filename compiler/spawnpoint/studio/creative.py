"""Creative pass: the LLM proposes a small graph patch; the compiler is the judge.

The patch is applied to a copy of the graph and analyzed. Diagnostics go back to the LLM for up to
`max_repairs` rounds. If it still does not compile, the patch is dropped — the working build is kept.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from ..analyze import analyze
from ..manifest import Manifest
from .llm import ChatModel, LLMError
from .prompts import creative_messages, repair_message

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "set_params": {
            "type": "array", "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"}, "component": {"type": "string"}, "param": {"type": "string"},
                    "value": {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "boolean"}]},
                },
                "required": ["entity", "component", "param", "value"], "additionalProperties": False,
            },
        },
        "add_rules": {
            "type": "array", "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {"on": {"type": "string"}, "if": {"type": "string"},
                               "do": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4}},
                "required": ["on", "if", "do"], "additionalProperties": False,
            },
        },
    },
    "required": ["set_params", "add_rules"], "additionalProperties": False,
}


@dataclass
class CreativeResult:
    graph: dict
    applied: bool
    patch: dict | None = None
    rounds: int = 0
    errors: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # per round: {"patch", "errors"}


def apply_patch(graph: dict, patch: dict) -> dict:
    """Applies a graph patch: add_entities, add_components, set_params, add_rules (in that order)."""
    g = copy.deepcopy(graph)
    for name, ent in (patch.get("add_entities") or {}).items():
        g["entities"].setdefault(name, copy.deepcopy(ent))
    for ac in patch.get("add_components", []):
        ent = g["entities"].setdefault(ac["entity"], {"components": {}})
        ent.setdefault("components", {}).setdefault(ac["component"], {}).update(ac.get("params") or {})
    for sp in patch.get("set_params", []):
        ent = g["entities"].get(sp["entity"])
        if ent is None:
            # Unknown entity: create the reference so the compiler reports it with a hint.
            g["entities"].setdefault(sp["entity"], {"components": {}})
            ent = g["entities"][sp["entity"]]
        ent.setdefault("components", {}).setdefault(sp["component"], {})[sp["param"]] = sp["value"]
    for r in patch.get("add_rules", []):
        rule = {"on": r["on"], "do": r["do"]}
        if r.get("if", "").strip():
            rule["if"] = r["if"]
        g.setdefault("rules", []).append(rule)
    return g


def summarize_graph(graph: dict) -> str:
    lines = [f"genre: {graph['genre']}", "entities:"]
    for name, ent in graph["entities"].items():
        comps = ", ".join(f"{c}{params if params else ''}" for c, params in ent.get("components", {}).items())
        lines.append(f"  {name}: {comps}")
    lines.append("rules:")
    for r in graph.get("rules", []):
        cond = f" if {r['if']}" if r.get("if") else ""
        lines.append(f"  on {r['on']}{cond} do {r['do']}")
    return "\n".join(lines)


def reference(graph: dict, manifest: Manifest) -> str:
    """Only the components the game uses, to keep the prompt small."""
    used = {c for ent in graph["entities"].values() for c in ent.get("components", {})}
    lines = []
    for name in sorted(used):
        comp = manifest.get(name)
        if comp is None:
            continue
        params = "; ".join(p.describe() for p in comp.params.values())
        sigs = ", ".join(f"{s.name}({', '.join(a.name for a in s.args)})" for s in comp.signals.values())
        methods = ", ".join(f"{m.name}({', '.join(a.name for a in m.args)})" for m in comp.methods.values())
        lines.append(f"{name}: params {params}" + (f" | signals {sigs}" if sigs else "")
                     + (f" | methods {methods}" if methods else ""))
    return "\n".join(lines)


def creative_pass(graph: dict, prompt: str, llm: ChatModel, manifest: Manifest, max_repairs: int = 2) -> CreativeResult:
    messages = creative_messages(prompt, summarize_graph(graph), reference(graph, manifest))
    errors: list[str] = []
    history: list[dict] = []
    for round_no in range(1 + max_repairs):
        try:
            patch = llm.chat_json(messages, PATCH_SCHEMA, "GraphPatch", temperature=0.5, max_tokens=800)
        except LLMError as e:
            return CreativeResult(graph, False, None, round_no, [str(e)], history)
        candidate = apply_patch(graph, patch)
        analysis = analyze(candidate, manifest)
        errors = [str(d) for d in analysis.diagnostics.errors]
        errors += [str(d) for d in analysis.diagnostics.warnings if d.code == "W_UNREACHABLE"]
        history.append({"patch": patch, "errors": errors})
        if not errors:
            return CreativeResult(candidate, True, patch, round_no + 1, [], history)
        messages = messages + [{"role": "assistant", "content": json.dumps(patch)}, repair_message(errors)]
    return CreativeResult(graph, False, None, 1 + max_repairs, errors, history)
