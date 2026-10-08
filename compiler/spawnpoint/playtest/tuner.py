"""Deterministic tuning rules: telemetry symptoms -> bounded parameter changes (a set_params patch).

Every change is bounded relative to the *original* graph (before any tuning), so repeated rounds can
never drift into absurd values, and every change carries a human-readable reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..manifest import Manifest
from .report import Report

MOVEMENT = ("PlatformerMovement", "TopDownMovement")


def targets(difficulty: int) -> dict[str, float]:
    """Win-rate targets per profile; novices are allowed to struggle more on harder games."""
    d = min(max(difficulty, 1), 5)
    return {"novice": round(0.8 - (d - 1) * 0.125, 3), "average": 0.8, "expert": 0.95}


def score(rep: Report, difficulty: int) -> float:
    """Distance from the targets (lower is better). Too easy only counts on hard games."""
    t = targets(difficulty)
    total = 0.0
    for prof, goal in t.items():
        s = rep.get(prof)
        if s is None:
            continue
        total += max(0.0, goal - s.win_rate) * (2.0 if prof == "expert" else 1.0)
        if difficulty >= 3 and prof == "novice" and s.win_rate > goal + 0.35:
            total += s.win_rate - goal - 0.35
    return round(total, 4)


@dataclass
class Change:
    entity: str
    component: str
    param: str
    value: float | int
    reason: str

    def to_patch(self) -> dict:
        return {"entity": self.entity, "component": self.component, "param": self.param, "value": self.value}

    def __str__(self) -> str:
        return f"{self.entity}.{self.component}.{self.param} = {self.value:g} — {self.reason}"


class _Params:
    """Reads current and original parameter values (graph value or manifest default)."""

    def __init__(self, graph: dict, original: dict, manifest: Manifest):
        self.g, self.o, self.m = graph, original, manifest

    def _get(self, graph: dict, entity: str, comp: str, param: str):
        value = graph["entities"].get(entity, {}).get("components", {}).get(comp, {}).get(param)
        if value is None:
            spec = self.m.get(comp)
            value = spec.params[param].default if spec and param in spec.params else None
        return value

    def now(self, entity: str, comp: str, param: str):
        return self._get(self.g, entity, comp, param)

    def base(self, entity: str, comp: str, param: str):
        return self._get(self.o, entity, comp, param)


def propose(rep: Report, graph: dict, original: dict, manifest: Manifest, difficulty: int = 2) -> list[Change]:
    t = targets(difficulty)
    p = _Params(graph, original, manifest)
    ents = graph["entities"]
    player = ents.get("Player", {}).get("components", {})
    novice, average = rep.get("novice"), rep.get("average")
    too_hard = bool((novice and novice.win_rate < t["novice"] - 0.1) or (average and average.win_rate < t["average"] - 0.1))
    changes: list[Change] = []

    def bump(entity, comp, param, factor=None, add=None, lo=None, hi=None, reason="", integer=False):
        cur = p.now(entity, comp, param)
        base = p.base(entity, comp, param)
        if cur is None or base is None:
            return
        new = cur * factor if factor is not None else cur + add
        if lo is not None:
            new = max(new, lo(base))
        if hi is not None:
            new = min(new, hi(base))
        new = int(round(new)) if integer else round(float(new), 3)
        if new != cur:
            changes.append(Change(entity, comp, param, new, reason))

    deaths = [s for s in (novice, average) if s]
    all_causes: dict[str, int] = {}
    for s in deaths:
        for k, v in s.causes.items():
            all_causes[k] = all_causes.get(k, 0) + v
    n_deaths = sum(all_causes.values())

    # 1. Missed jumps: the player pressed jump a moment too late.
    missed = max((s.missed_rate for s in deaths), default=0.0)
    if "PlatformerMovement" in player and missed > 0.15:
        why = f"{missed:.0%} of jumps were pressed too late"
        bump("Player", "PlatformerMovement", "coyote_time", add=0.04, hi=lambda b: max(0.2, b), reason=why)
        bump("Player", "PlatformerMovement", "jump_buffer", add=0.04, hi=lambda b: max(0.2, b), reason=why)

    if too_hard and n_deaths:
        top, top_n = max(all_causes.items(), key=lambda kv: kv[1])
        share = top_n / n_deaths
        falls = sum(s.falls_after_jump for s in deaths)
        # 2. Falling into pits after jumping: more air control, slightly higher jump.
        if "PlatformerMovement" in player and falls / n_deaths >= 0.3:
            why = f"{falls}/{n_deaths} deaths were falls right after a jump"
            bump("Player", "PlatformerMovement", "air_acceleration", factor=1.2, hi=lambda b: b * 2.0, reason=why)
            bump("Player", "PlatformerMovement", "jump_velocity", factor=1.05, hi=lambda b: b * 1.15, reason=why)
        ent = ents.get(top, {})
        comps = ent.get("components", {})
        mv = next((m for m in MOVEMENT if m in comps), None)
        if share >= 0.4 and top != "fall":
            why = f"{top} caused {top_n}/{n_deaths} deaths"
            if mv:  # 3. A moving enemy dominates: slow it down.
                bump(top, mv, "max_speed", factor=0.85, lo=lambda b: b * 0.5, reason=why)
            elif "Projectile" in comps:  # 4. Bullets: the shooters fire less often.
                for name, e in ents.items():
                    if e.get("components", {}).get("Weapon", {}).get("projectile") == top:
                        bump(name, "Weapon", "fire_rate", factor=0.85, lo=lambda b: b * 0.5, reason=why)
            elif "Hitbox" in comps and "Hurtbox" in player:  # 5. Static hazards: a more forgiving hurtbox.
                bump("Player", "Hurtbox", "size_scale", add=-0.1, lo=lambda b: min(0.6, b), reason=why)
        # 6. Still far too hard: more health and longer invincibility.
        if novice and novice.win_rate < t["novice"] - 0.25 and "Health" in player:
            why = f"novice bots won only {novice.wins}/{novice.runs}"
            bump("Player", "Health", "max_health", add=1, hi=lambda b: max(6, b), reason=why, integer=True)
            bump("Player", "Health", "invincibility_time", add=0.2, hi=lambda b: max(1.5, b), reason=why)
    # 7. Too easy on a game meant to be hard: enemies get faster.
    if difficulty >= 3 and novice and novice.win_rate > t["novice"] + 0.35 and novice.deaths == 0:
        for name, e in ents.items():
            comps = e.get("components", {})
            mv = next((m for m in MOVEMENT if m in comps), None)
            if mv and name != "Player" and any(k in comps for k in ("PatrolAI", "ChaseAI")):
                bump(name, mv, "max_speed", factor=1.1, hi=lambda b: b * 1.5,
                     reason=f"too easy for difficulty {difficulty}: novices won {novice.wins}/{novice.runs} without dying")
    # Deduplicate (first reason wins).
    seen, out = set(), []
    for c in changes:
        key = (c.entity, c.component, c.param)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
