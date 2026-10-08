"""Edits of a built game from the cockpit: direct parameter changes and LLM edits scoped to one entity.

Every edit is a graph patch (add_entities / add_components / set_params / add_rules). Studio games keep
it as an override in studio.json (re-applied after every assemble); hand-written graphs are patched in
place. The compiler judges every patch before anything is built.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import manifest as manifest_mod
from ..analyze import analyze
from ..build import BuildResult, build
from ..manifest import Manifest
from . import web
from .assemble import LAYERS, assemble
from .brief import GameBrief
from .creative import apply_patch
from .llm import ChatModel, LLMError
from .orchestrator import SESSION_FILE, _save_session, finalize_graph, load_session
from .prompts import needs_translation, repair_message, translate_messages, TRANSLATE_SCHEMA

VALUE = {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "boolean"}]}
ENTITY_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "set_params": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False, "required": ["component", "param", "value"],
            "properties": {"component": {"type": "string"}, "param": {"type": "string"}, "value": VALUE}}},
        "add_components": {"type": "array", "maxItems": 3, "items": {
            "type": "object", "additionalProperties": False, "required": ["component", "params"],
            "properties": {"component": {"type": "string"}, "params": {"type": "array", "maxItems": 6, "items": {
                "type": "object", "additionalProperties": False, "required": ["param", "value"],
                "properties": {"param": {"type": "string"}, "value": VALUE}}}}}},
        "add_rules": {"type": "array", "maxItems": 2, "items": {
            "type": "object", "additionalProperties": False, "required": ["on", "if", "do"],
            "properties": {"on": {"type": "string"}, "if": {"type": "string"},
                           "do": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3}}}},
    },
    "required": ["set_params", "add_components", "add_rules"],
    "additionalProperties": False,
}

ADDABLE = ("Health", "Hurtbox", "Hitbox", "Weapon", "ChaseAI", "PatrolAI", "Spawner", "Stomp",
           "PlatformerMovement", "TopDownMovement", "Collectible", "Gate")

ENTITY_SYSTEM = """You edit ONE entity of a 2D game built from components. Return a small patch for it.
- set_params: change parameters of components the entity already has (use the exact names below, stay in range).
- add_components: give it a new component (only from the list of addable components).
- add_rules: optional extra rules, e.g. {"on": "Slime.died", "if": "", "do": ["shake(0.6)"]}.
Common requests:
- "more health" / "x2 health" -> Health.max_health. "faster" -> the movement component's max_speed.
- "make it shoot" -> add Weapon with projectile "EnemyBullet" (it will be created) and auto_fire true,
  or with ChaseAI so it aims at the player. "fire bullets" -> projectile "Fireball".
- "jump higher" -> PlatformerMovement.jump_velocity. "hits harder" -> Hitbox.damage.
Keep it minimal: change only what is asked."""


@dataclass
class EditResult:
    ok: bool
    patch: dict | None = None
    build: BuildResult | None = None
    errors: list[str] = field(default_factory=list)
    rounds: int = 0
    english: str = ""


def current_graph(project: Path) -> dict:
    return json.loads((project / "spawnpoint.json").read_text())


def _entity_view(graph: dict, entity: str, manifest: Manifest) -> str:
    ent = graph["entities"][entity]
    lines = [f"Entity {entity}: body {ent.get('body', 'character')}, team {ent.get('team', 'auto')}"]
    for cname, params in ent.get("components", {}).items():
        comp = manifest.get(cname)
        if comp is None:
            continue
        values = {p.name: params.get(p.name, p.default) for p in comp.params.values()}
        ranges = "; ".join(p.describe() for p in comp.params.values())
        lines.append(f"- {cname} current {json.dumps(values)} | params: {ranges}")
    addable = [c for c in ADDABLE if c not in ent.get("components", {}) and manifest.get(c)]
    lines.append("Addable components:")
    for cname in addable:
        comp = manifest.get(cname)
        lines.append(f"- {cname}: {comp.doc.splitlines()[0] if comp.doc else ''} params: "
                     + "; ".join(p.describe() for p in comp.params.values()))
    lines.append("Other entities: " + ", ".join(n for n in graph["entities"] if n != entity))
    return "\n".join(lines)


def scope_patch(entity: str, raw: dict) -> dict:
    """LLM output (entity-relative) -> generic graph patch."""
    return {
        "set_params": [dict(sp, entity=entity) for sp in raw.get("set_params", [])],
        "add_components": [{"entity": entity, "component": ac["component"],
                            "params": {p["param"]: p["value"] for p in ac.get("params", [])}}
                           for ac in raw.get("add_components", [])],
        "add_rules": [{k: v for k, v in r.items() if not (k == "if" and not str(v).strip())}
                      for r in raw.get("add_rules", [])],
    }


def add_missing_projectiles(graph: dict, patch: dict) -> dict:
    """A new Weapon may name a projectile that does not exist yet: create a sensible one."""
    patched = apply_patch(graph, patch)
    extra = dict(patch.get("add_entities") or {})
    for name, ent in patched["entities"].items():
        weapon = ent.get("components", {}).get("Weapon")
        if weapon is None:
            continue
        proj = weapon.get("projectile", "Bullet")
        if proj in patched["entities"] or proj in extra:
            continue
        fiery = any(w in proj.lower() for w in ("fire", "flame", "lava", "magma"))
        team = ent.get("team") or ("player" if "PlayerInput" in ent.get("components", {}) else "enemy")
        extra[proj] = {
            "body": "area", "team": team,
            "sprite": {"generate": {"kind": "bullet", "color": "#ff6c11" if fiery else "#ff77a8"}},
            "components": {"Projectile": {"speed": 320.0 if team == "enemy" else 700.0, "lifetime": 2.5},
                           "Hitbox": {"damage": 1, "knockback": 220.0}},
        }
    if extra:
        patch = dict(patch, add_entities=extra)
    return patch


def ask_entity(project: Path, entity: str, request: str, llm: ChatModel, manifest: Manifest | None = None,
               max_repairs: int = 2) -> tuple[dict | None, list[str], int, str]:
    """LLM -> validated patch for one entity. Returns (patch or None, last errors, rounds, english)."""
    manifest = manifest or manifest_mod.load()
    graph = current_graph(project)
    if entity not in graph["entities"]:
        return None, [f"unknown entity '{entity}'"], 0, request
    english = request
    if needs_translation(request):
        english = llm.chat_json(translate_messages(request), TRANSLATE_SCHEMA, "Translation",
                                temperature=0.1, max_tokens=300).get("english") or request
    messages = [{"role": "system", "content": ENTITY_SYSTEM},
                {"role": "user", "content": f"{_entity_view(graph, entity, manifest)}\n\nRequest: {english}"}]
    errors: list[str] = []
    for round_no in range(1 + max_repairs):
        raw = llm.chat_json(messages, ENTITY_PATCH_SCHEMA, "EntityPatch", temperature=0.2, max_tokens=700)
        patch = add_missing_projectiles(graph, scope_patch(entity, raw))
        if not any(patch.get(k) for k in ("set_params", "add_components", "add_rules")):
            errors = ["the patch is empty"]
        else:
            analysis = analyze(apply_patch(graph, patch), manifest, base_dir=project)
            errors = [str(d) for d in analysis.diagnostics.errors]
            if not errors:
                return patch, [], round_no + 1, english
        messages = messages + [{"role": "assistant", "content": json.dumps(raw)}, repair_message(errors)]
    return None, errors, 1 + max_repairs, english


def apply_override(project: Path, patch: dict, *, manifest: Manifest | None = None, web_export: bool = True,
                   smoke: bool = True) -> EditResult:
    """Validates, persists and builds a patch. Studio games keep it in studio.json overrides."""
    manifest = manifest or manifest_mod.load()
    studio = (project / SESSION_FILE).exists()
    if studio:
        session = load_session(project)
        brief = GameBrief.model_validate(session["brief"])
        trial = dict(session, overrides=(session.get("overrides") or []) + [patch])
        base = assemble(brief, LAYERS[-1], session["seed"], session.get("chunks"))
        graph = finalize_graph(base, trial, manifest)
        # finalize_graph silently skips patches that no longer fit; this one must fit now.
        check = analyze(apply_patch(finalize_graph(base, session, manifest), patch), manifest)
    else:
        graph = apply_patch(current_graph(project), patch)
        check = analyze(graph, manifest, base_dir=project)
    errors = [str(d) for d in check.diagnostics.errors]
    if errors:
        return EditResult(False, patch, errors=errors)
    res = build(graph, project, manifest=manifest, smoke=smoke)
    if not res.ok:
        return EditResult(False, patch, res, [str(d) for d in res.diagnostics.errors])
    if studio:
        session["overrides"] = trial["overrides"]
        _save_session(project, session)
    if web_export and (project / web.WEB_DIR / "index.html").exists():
        web.export(project)
    return EditResult(True, patch, res)


def set_param_patch(entity: str, component: str, param: str, value) -> dict:
    return {"set_params": [{"entity": entity, "component": component, "param": param, "value": value}]}


def edit_entity(project: Path, entity: str, request: str, llm: ChatModel, *, manifest: Manifest | None = None,
                web_export: bool = True) -> EditResult:
    manifest = manifest or manifest_mod.load()
    try:
        patch, errors, rounds, english = ask_entity(project, entity, request, llm, manifest)
    except LLMError as e:
        return EditResult(False, None, errors=[str(e)])
    if patch is None:
        return EditResult(False, None, errors=errors, rounds=rounds, english=english)
    res = apply_override(project, copy.deepcopy(patch), manifest=manifest, web_export=web_export)
    res.rounds, res.english = rounds, english
    return res
