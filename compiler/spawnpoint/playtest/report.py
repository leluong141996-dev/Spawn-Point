"""Aggregates bot telemetry into per-profile metrics, a Markdown report and a death heatmap."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass
class ProfileStats:
    profile: str
    runs: int
    wins: int
    mean_time: float
    deaths: int
    causes: dict[str, int]
    falls_after_jump: int
    jumps_intended: int
    jumps_missed: int
    pickup_rate: float
    stuck: int
    hits: int = 0  # times the player took damage (dying or not)

    @property
    def win_rate(self) -> float:
        return self.wins / self.runs if self.runs else 0.0

    @property
    def missed_rate(self) -> float:
        return self.jumps_missed / self.jumps_intended if self.jumps_intended else 0.0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d.update(win_rate=round(self.win_rate, 3), missed_rate=round(self.missed_rate, 3))
        return d


@dataclass
class Report:
    profiles: dict[str, ProfileStats]
    runs: list[dict]
    level_issues: list[str] = field(default_factory=list)

    def get(self, profile: str) -> ProfileStats | None:
        return self.profiles.get(profile)

    def to_dict(self) -> dict:
        return {"profiles": {k: v.to_dict() for k, v in self.profiles.items()},
                "level_issues": self.level_issues, "runs": self.runs}


def aggregate(runs: list[dict], goal_entities: set[str] | None = None) -> Report:
    """`goal_entities`: entity types the player must reach (pickups, exits); an unreachable one
    is a level problem. Enemies the bot could not path to are not."""
    by: dict[str, list[dict]] = {}
    for r in runs:
        by.setdefault(r["profile"], []).append(r)
    stats = {}
    for prof, rs in by.items():
        deaths = [d for r in rs for d in r["deaths"]]
        won = [r for r in rs if r["outcome"] == "won"]
        total = sum(r["pickups"]["total"] for r in rs)
        stats[prof] = ProfileStats(
            profile=prof, runs=len(rs), wins=len(won),
            mean_time=round(sum(r["time"] for r in won) / len(won), 2) if won else 0.0,
            deaths=len(deaths), causes=dict(Counter(d["cause"] for d in deaths).most_common()),
            falls_after_jump=sum(1 for d in deaths if d["cause"] == "fall" and d.get("after_jump")),
            jumps_intended=sum(r["jumps"]["intended"] for r in rs),
            jumps_missed=sum(len(r["jumps"]["missed"]) for r in rs),
            pickup_rate=round(sum(r["pickups"]["collected"] for r in rs) / total, 3) if total else 1.0,
            stuck=sum(len(r["stuck"]) for r in rs),
            hits=sum(len(r.get("damage", [])) for r in rs),
        )
    return Report(stats, runs, _level_issues(runs, stats, goal_entities))


def _level_issues(runs: list[dict], stats: dict[str, ProfileStats], goal_entities: set[str] | None) -> list[str]:
    issues = []
    no_path = Counter((u["entity"], u["x"], u["y"]) for r in runs for u in r.get("unreachable", [])
                      if u.get("reason") == "no_path" and (goal_entities is None or u["entity"] in goal_entities))
    for (entity, x, y), n in sorted(no_path.items()):
        if n == len(runs):  # no bot ever found a way: a level problem, not a skill problem
            issues.append(f"{entity} at ({x},{y}) has no path from the player")
    expert = stats.get("expert")
    if expert and expert.wins == 0:
        issues.append("even the expert bot never won — the goal may be impossible or the time too short")
    return issues


def markdown(rep: Report, title: str, changes: list[str] | None = None) -> str:
    lines = [f"# Playtest — {title}", "", "| profile | wins | mean win time | deaths | top causes | missed jumps | pickups | stuck |",
             "|---|---|---|---|---|---|---|---|"]
    for s in rep.profiles.values():
        causes = ", ".join(f"{k} {v}" for k, v in list(s.causes.items())[:3]) or "—"
        lines.append(f"| {s.profile} | {s.wins}/{s.runs} | {s.mean_time or '—'}s | {s.deaths} | {causes} | "
                     f"{s.jumps_missed}/{s.jumps_intended} | {s.pickup_rate:.0%} | {s.stuck} |")
    if rep.level_issues:
        lines += ["", "## Level issues", *[f"- {i}" for i in rep.level_issues]]
    if changes:
        lines += ["", "## Tuning applied", *[f"- {c}" for c in changes]]
    return "\n".join(lines) + "\n"


CAUSE_COLORS = [(255, 0, 77), (255, 163, 0), (41, 173, 255), (0, 228, 54), (255, 119, 168), (131, 118, 156)]


def heatmap(plan: dict, runs: list[dict], out: Path, cell: int = 12) -> Path:
    """Level drawn from the build plan; deaths as dots colored by cause, stuck spots as rings."""
    w, h = plan["map"]["width"], plan["map"]["height"]
    legend_h = 18
    img = Image.new("RGB", (w * cell, h * cell + legend_h), (29, 33, 46))
    d = ImageDraw.Draw(img, "RGBA")
    for x, y, kind in plan["map"]["cells"]:
        box = (x * cell, y * cell, x * cell + cell - 1, y * cell + cell - 1)
        if kind == "solid":
            d.rectangle(box, fill=(95, 87, 79))
        else:
            d.rectangle((box[0], box[1], box[2], box[1] + 2), fill=(171, 82, 54))
    ts = plan["tile_size"]
    players = {e["name"] for e in plan["entities"] if any(c["name"] == "PlayerInput" for c in e["components"])}
    for p in plan["placements"]:
        if p["entity"] in players:
            cx, cy = p["x"] / ts * cell, p["y"] / ts * cell
            d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), outline=(0, 228, 54), width=2)
    causes = sorted({dd["cause"] for r in runs for dd in r["deaths"]})
    colors = {c: CAUSE_COLORS[i % len(CAUSE_COLORS)] for i, c in enumerate(causes)}
    for r in runs:
        for s in r["stuck"]:
            cx, cy = (s["x"] + 0.5) * cell, (s["y"] + 0.5) * cell
            d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=(255, 236, 39, 200), width=1)
        for u in r.get("unreachable", []):
            cx, cy = (u["x"] + 0.5) * cell, (u["y"] + 0.5) * cell
            d.line((cx - 4, cy - 4, cx + 4, cy + 4), fill=(255, 255, 255, 200), width=2)
            d.line((cx - 4, cy + 4, cx + 4, cy - 4), fill=(255, 255, 255, 200), width=2)
        for dd in r["deaths"]:
            # Falls happen below the map: pin them to the bottom row so they stay visible.
            cx, cy = (min(max(dd["x"], 0), w - 1) + 0.5) * cell, (min(max(dd["y"], 0), h - 1) + 0.5) * cell
            c = colors[dd["cause"]]
            d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(*c, 150))
    x = 4
    for cause, c in colors.items():
        d.ellipse((x, h * cell + 5, x + 8, h * cell + 13), fill=c)
        d.text((x + 11, h * cell + 3), cause, fill=(255, 241, 232))
        x += 16 + len(cause) * 7
    d.text((x + 8, h * cell + 3), "o stuck   x bots gave up", fill=(255, 236, 39))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
