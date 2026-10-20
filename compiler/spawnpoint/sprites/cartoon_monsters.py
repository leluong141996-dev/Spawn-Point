"""Cartoon twins of the monsters in monsters.py: the same characters in the smooth vector style."""

from __future__ import annotations

import math

from .cartoon import EYE, WHITE, Painter, Pose, _hexrgb, _shade
from . import monsters

LEAF = _hexrgb(monsters.LEAF)
MOUTH = _hexrgb(monsters.MOUTH)
TONGUE = _hexrgb(monsters.TONGUE)
STEM = _hexrgb(monsters.STEM)
CLOAK = _hexrgb(monsters.CLOAK)
BONE = _hexrgb(monsters.BONE)
FLAME_MID = _hexrgb(monsters.FLAME_MID)
FLAME_CORE = _hexrgb(monsters.FLAME_CORE)
SNAIL_BODY = _hexrgb(monsters.SNAIL_BODY)
WOOD = _hexrgb(monsters.WOOD)
STEEL = _hexrgb(monsters.STEEL)
GLOW = (255, 90, 90)


def _top_half(cx: float, cy: float, rx: float, ry: float, n: int = 24) -> list[tuple[float, float]]:
    return [(cx + rx * math.cos(math.pi + math.pi * k / n), cy + ry * math.sin(math.pi + math.pi * k / n)) for k in range(n + 1)]


def draw_plant(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    sw = (0, 2, 0, -2)[k]
    hurt = p.anim == "hurt"
    gape = 2 if hurt else {"idle": (6, 10, 14, 8)[k], "run": (10, 4, 10, 4)[k]}.get(p.anim, 8)
    P.line([(28, 62), (28 + sw, 36)], 9, LEAF, top=False)
    P.ellipse(14 - sw, 52, 12, 5.5, LEAF)
    P.ellipse(42 + sw, 52, 12, 5.5, LEAF)
    P.ellipse(28 + sw, 22, 24, 20, c.base, shine=True)
    for x, y, r in ((14, 15, 3.4), (30, 8, 3.8), (43, 15, 3.0)):
        P.ellipse(x + sw, y, r, r, WHITE, shade=False, top=True)
    my = 25
    P.ellipse(28 + sw, my, 17, gape / 2 + 2.4, MOUTH, shade=False, top=True)
    if gape > 6:
        P.ellipse(28 + sw, my + gape / 2, 9, max(2, gape / 3), TONGUE, shade=False, top=True)
    for x in range(14, 40, 6):
        P.poly([(x + sw, my - gape / 2 - 2), (x + 3 + sw, my - gape / 2 + 3.5), (x + 6 + sw, my - gape / 2 - 2)], WHITE, shade=False, top=True)
        P.poly([(x + 2 + sw, my + gape / 2 + 3), (x + 5 + sw, my + gape / 2 - 3.5), (x + 8 + sw, my + gape / 2 + 3)], WHITE, shade=False, top=True)


def draw_mushroom(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    bob = {"idle": (0, 2)[p.i % 2], "run": (0, 2, 0, 2)[k]}.get(p.anim, 0)
    hurt = p.anim == "hurt"
    foot = (0, 2, 0, -2)[k] if p.anim == "run" else 0
    P.ellipse(18 + foot, 51, 6.5, 4, _shade(c.base, 0.5))
    P.ellipse(38 - foot, 51, 6.5, 4, _shade(c.base, 0.5))
    P.rrect(20, 30 + bob, 37, 51, 6, STEM)
    P.poly(_top_half(28, 32 + bob, 26, 20) + [(2, 33 + bob), (54, 33 + bob)], c.base, top=True)
    P.ellipse(20, 17 + bob, 11, 6, c.light, shade=False)
    for x, y, r in ((14, 19, 4.4), (30, 11, 4.8), (42, 20, 4), (24, 26, 2.8)):
        P.ellipse(x, y + bob, r, r, WHITE, shade=False, top=True)
    if hurt:
        P.eyes([(22, 38 + bob), (33, 38 + bob)], r=3.2, hurt=True)
    else:
        P.eyes([(22, 38 + bob), (33, 38 + bob)], r=3.2)
    P.line([(26, 45 + bob), (30, 45 + bob)], 1.6, EYE)


def draw_reaper(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    bob = (0, 2, 2, 0)[k] if p.anim in ("idle", "run") else 0
    P.line([(48, 12 + bob), (48, 60 + bob)], 4, WOOD, top=False)
    P.poly([(48, 6 + bob), (28, 4 + bob), (16, 14 + bob), (28, 10 + bob), (48, 16 + bob)], STEEL, top=True)
    P.poly([(14, 34 + bob), (40, 34 + bob), (48, 62 + bob), (6, 62 + bob)], CLOAK)
    P.ellipse(28, 21 + bob, 19, 18, CLOAK, shine=True)
    P.ellipse(26, 22 + bob, 13, 13, _shade(CLOAK, 0.35), shade=False, top=True)
    P.ellipse(26, 24 + bob, 9.4, 9.8, BONE, shade=False, top=True)
    for ex in (21, 29):
        P.ellipse(ex, 23 + bob, 2.8, 3.4, EYE, shade=False, top=True)
        if p.anim != "hurt":
            P.ellipse(ex, 23 + bob, 1.1, 1.1, GLOW, shade=False, top=True)
    P.line([(22, 31 + bob), (30, 31 + bob)], 1.6, EYE)
    P.ellipse(42, 40 + bob, 4.6, 4.6, BONE, shade=False, top=True)


def draw_flame(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    f = (0, 2, 0, -2)[k]
    bob = (0, 2)[p.i % 2] if p.anim == "idle" else 0
    P.poly([(24 + f, 0 + bob), (34, 16 + bob), (44, 28), (42, 42), (34, 52), (14, 52), (6, 42), (4, 28), (14, 16 + bob)], c.base, top=True)
    P.poly([(6 - f, 18 + bob), (12, 28), (6, 36)], c.base)
    P.poly([(42 + f, 16 + bob), (38, 28), (44, 36)], c.base)
    P.poly([(24 - f, 16 + bob), (34, 30), (36, 42), (28, 50), (18, 50), (12, 42), (14, 30)], FLAME_MID, shade=False, top=True)
    P.poly([(24, 28), (30, 38), (28, 48), (20, 48), (18, 38)], FLAME_CORE, shade=False, top=True)
    for ex in (15, 29):
        P.ellipse(ex + 2, 33 + bob, 3.4, 3.4, WHITE, shade=False, top=True)
        P.ellipse(ex + 3, 34 + bob, 1.7, 1.9, EYE, shade=False, top=True)
    if p.anim != "hurt":
        P.line([(12, 26 + bob), (20, 30 + bob)], 1.8, EYE)
        P.line([(36, 26 + bob), (28, 30 + bob)], 1.8, EYE)
    P.line([(18, 43), (24, 44), (30, 43)], 2.0, EYE)


def draw_snail(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    st = (0, 2, 4, 2)[k] if p.anim == "run" else 0
    bob = (0, 2)[p.i % 2] if p.anim == "idle" else 0
    P.ellipse(30 + st / 2, 40, 26 + st / 2, 8.4, SNAIL_BODY)
    P.ellipse(54 + st, 34 + bob, 9, 9, SNAIL_BODY, shine=True)
    for sx in (50, 58):
        x = sx + st
        P.line([(x, 28 + bob), (x - 2, 14 + bob)], 4, SNAIL_BODY, top=False)
        P.ellipse(x - 2, 12 + bob, 4.6, 4.6, WHITE, shade=False, top=True)
        P.ellipse(x - 1, 12 + bob, 2.2, 2.6, EYE, shade=False, top=True)
    P.line([(56 + st, 40 + bob), (60 + st, 40 + bob)], 1.6, EYE)
    P.ellipse(24, 24 + bob, 20, 19, c.base, shine=True)
    for r, col in ((16, _shade(c.base, 0.6)), (13, c.base), (9.6, _shade(c.base, 0.6)), (6.4, c.base), (3, _shade(c.base, 0.6))):
        P.ellipse(24, 24 + bob, r, r, col, shade=False, top=True)


def draw_alien(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    bob = {"idle": (0, 2)[p.i % 2], "run": (0, 2, 0, 2)[k]}.get(p.anim, 0)
    sw = ((-4, 4), (0, 0), (4, -4), (0, 0))[k] if p.anim == "run" else (0, 0)
    hurt = p.anim == "hurt"
    P.line([(24, 8 + bob), (18, 0 + bob)], 2.4, c.shadow)
    P.line([(32, 8 + bob), (38, 0 + bob)], 2.4, c.shadow)
    P.ellipse(18, 1 + bob, 3, 3, c.light, shade=False, top=True)
    P.ellipse(38, 1 + bob, 3, 3, c.light, shade=False, top=True)
    P.rrect(18 + sw[0], 52, 24 + sw[0], 62, 2.4, c.shadow)
    P.rrect(30 + sw[1], 52, 36 + sw[1], 62, 2.4, c.base)
    P.ellipse(27, 48 + bob, 12, 10, c.base, shine=True)
    P.line([(14, 44 + bob), (6, 48 + bob)], 4.4, c.base, top=False)
    P.line([(40, 44 + bob), (48, 48 + bob)], 4.4, c.shadow, top=False)
    P.ellipse(28, 24 + bob, 23, 20, c.base, shine=True)
    for ex in (17, 39):
        if hurt:
            P.line([(ex - 4, 20 + bob), (ex + 4, 28 + bob)], 2, EYE)
            P.line([(ex + 4, 20 + bob), (ex - 4, 28 + bob)], 2, EYE)
        else:
            sgn = -1 if ex < 28 else 1
            P.poly([(ex - 6.4, 20 + bob), (ex + 6.4, 23 + bob), (ex + 3 * sgn, 34 + bob), (ex - 3 * sgn, 34 + bob)], EYE, shade=False, top=True)
            P.ellipse(ex - 2, 25 + bob, 1.6, 1.6, WHITE, shade=False, top=True)
    P.line([(24, 37 + bob), (32, 37 + bob)], 1.8, _shade(c.base, 0.4))


PAINTERS = {"plant": draw_plant, "mushroom": draw_mushroom, "reaper": draw_reaper, "flame": draw_flame,
            "snail": draw_snail, "alien": draw_alien}
