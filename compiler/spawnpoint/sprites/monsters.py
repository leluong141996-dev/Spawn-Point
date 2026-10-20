"""More chibi monsters in the creatures.py language (big faces, flat colour blocks, one shadow tone, a touch of
light, a dark outline), painted natively at the fine size: a biting plant, a mushroom, a reaper, a flame,
a snail and a little alien. The entity colour is the creature's main colour (cap, shell, flame, skin...).
"""

from __future__ import annotations

import numpy as np

from .chibi import EYE, WHITE, Fig, tone
from .creatures import FANG, Look, _eye

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
LEAF = "#58b848"
MOUTH = "#8a1a3a"
TONGUE = "#ff7a96"
STEM = "#f4e6c6"
CLOAK = "#3c3058"
BONE = "#f2ecd8"
GLOW = (255, 90, 90, 255)
FLAME_MID = "#ffb02e"
FLAME_CORE = "#fff0a0"
SNAIL_BODY = "#d8c4cc"
WOOD = "#8a5a34"
STEEL = "#c4ccdc"


def _clip(g: Fig, cx: float, cy: float, rx: float, ry: float, c: RGBA, y0: float = -99, y1: float = 99) -> None:
    """An ellipse restricted to the rows y0..y1 (a cap with a flat underside, a head with a cut-out mouth)."""
    ys, xs = np.mgrid[0:g.h, 0:g.w]
    m = ((xs + 0.5 - cx) / rx) ** 2 + ((ys + 0.5 - cy) / ry) ** 2 <= 1.0
    m &= (ys >= y0) & (ys <= y1)
    g.px[m] = c


def _tri(g: Fig, x: float, y: float, w: float, h: float, c: RGBA) -> None:
    g.poly([(x, y), (x + w / 2, y + h), (x + w, y)] if h > 0 else [(x, y), (x + w / 2, y + h), (x + w, y)], c)


# --- a biting plant ----------------------------------------------------------------------------

def paint_plant(g: Fig, L: Look, anim: str, i: int) -> None:
    leaf, cap = tone(LEAF, None), L.body
    k = i % 4
    sway = (0, 1, 0, -1)[k]
    hurt = anim == "hurt"
    gape = 1 if hurt else {"idle": (3, 5, 7, 4)[k], "run": (5, 2, 5, 2)[k]}.get(anim, 4)
    cx, cy = 14 + sway, 11
    g.line(14, 31, 14 + sway, 19, leaf.base, 4)                  # stem
    g.line(16, 30, 16 + sway, 19, leaf.shadow, 1)
    g.ellipse(7 - sway, 26, 5.5, 2.6, leaf.base)                   # leaves
    g.ellipse(21 + sway, 26, 5.5, 2.6, leaf.base)
    g.rect(4, 26, 9, 26, leaf.light)
    g.ellipse(cx, cy, 11, 9.5, cap.base)                           # head
    g.ellipse(cx - 3, cy - 4, 5, 3, cap.light)
    g.ellipse(cx + 5, cy + 3, 5.5, 5, cap.shadow)
    for sx, sy, r in ((cx - 7, cy - 3, 1.6), (cx + 1, cy - 7, 1.9), (cx + 7, cy - 3, 1.5)):
        g.ellipse(sx, sy, r, r, WHITE)                             # spots
    my = cy + 1                                                    # the mouth
    _clip(g, cx, my, 8.5, gape / 2 + 1.2, tone(MOUTH, None).base, 0, 99)
    g.ellipse(cx, my + gape / 2, 4.6, max(1.0, gape / 3), tone(TONGUE, None).base) if gape > 3 else None
    for x in range(int(cx - 7), int(cx + 7), 3):                   # fangs
        _tri(g, x, my - gape / 2 - 1, 3, 2.5, FANG)
        g.poly([(x + 1, my + gape / 2 + 1.4), (x + 2.5, my + gape / 2 - 1.6), (x + 4, my + gape / 2 + 1.4)], FANG)
    if hurt:
        g.set(cx - 5, cy - 4, EYE)
        g.set(cx + 5, cy - 4, EYE)


# --- a mushroom --------------------------------------------------------------------------------

def paint_mushroom(g: Fig, L: Look, anim: str, i: int) -> None:
    cap, stem = L.body, tone(STEM, None)
    k = i % 4
    bob = {"idle": (0, 1)[i % 2], "run": (0, 1, 0, 1)[k]}.get(anim, 0)
    hurt = anim == "hurt"
    foot = (0, 1, 0, -1)[k] if anim == "run" else 0
    g.ellipse(9, 25.5, 3.2, 2, L.dark.base)                        # feet
    g.ellipse(19, 25.5, 3.2, 2, L.dark.base)
    g.rect(7 + foot, 25, 9 + foot, 26, L.dark.shadow)
    g.rect(10, 15 + bob, 18, 25, stem.base)                         # stem
    g.rect(16, 16 + bob, 18, 25, stem.shadow)
    g.rect(9, 20 + bob, 9, 24, stem.base)
    g.rect(19, 20 + bob, 19, 24, stem.shadow)
    _clip(g, 14, 11 + bob, 13, 9.5, cap.base, 0, 16 + bob)       # cap, flat underneath
    _clip(g, 10, 8 + bob, 6, 3.4, cap.light, 0, 16 + bob)
    _clip(g, 20, 14 + bob, 6, 3, cap.shadow, 12 + bob, 16 + bob)
    for sx, sy, r in ((7, 9, 2.2), (15, 5.5, 2.4), (21, 10, 2), (12, 13, 1.4)):
        g.ellipse(sx, sy + bob, r, r, WHITE)
    g.rect(4, 15 + bob, 24, 16 + bob, cap.shadow)                  # the rim
    _eye(g, 11, 18 + bob, closed=(anim == "idle" and i == 1), hurt=hurt)
    _eye(g, 15, 18 + bob, closed=(anim == "idle" and i == 1), hurt=hurt)
    g.rect(13, 22 + bob, 15, 22 + bob, EYE)                        # tiny mouth
    g.set(10, 21 + bob, tone("#f0a0a0", None).base)                # blush
    g.set(17, 21 + bob, tone("#f0a0a0", None).base)


# --- a reaper ----------------------------------------------------------------------------------

def paint_reaper(g: Fig, L: Look, anim: str, i: int) -> None:
    robe, bone = tone(CLOAK, None), tone(BONE, None)
    k = i % 4
    bob = (0, 1, 1, 0)[k] if anim in ("idle", "run") else 0
    hurt = anim == "hurt"
    wave = (0, 1, 0, -1)[k]
    pole = tone(WOOD, None)
    g.line(24, 6 + bob, 24, 30 + bob, pole.base, 2)                # the scythe
    g.poly([(24, 3 + bob), (14, 2 + bob), (8, 7 + bob), (14, 5 + bob), (24, 8 + bob)], tone(STEEL, None).base)
    g.poly([(24, 3 + bob), (14, 2 + bob), (10, 5 + bob), (24, 5 + bob)], tone(STEEL, None).light)
    g.poly([(8, 16 + bob), (20, 16 + bob), (24, 30 + bob), (3, 30 + bob)], robe.base)   # robe
    g.poly([(15, 16 + bob), (20, 16 + bob), (24, 30 + bob), (16, 30 + bob)], robe.shadow)
    for x in range(3, 24, 4):                                       # ragged hem
        g.poly([(x, 29 + bob), (x + 2 + wave, 32), (x + 4, 29 + bob)], robe.base)
    g.ellipse(14, 10 + bob, 9.5, 9, robe.base)                     # hood
    g.ellipse(17, 12 + bob, 6, 6, robe.shadow)
    g.ellipse(13, 11 + bob, 6.6, 6.4, tone("#14101e", None).base)
    g.ellipse(13, 12 + bob, 4.6, 4.8, bone.base)                    # skull
    g.rect(9, 12 + bob, 10, 12 + bob, bone.light)
    for ex in (10, 14):                                              # eye sockets with a red glint
        g.rect(ex, 11 + bob, ex + 1, 13 + bob, EYE)
        if not hurt:
            g.set(ex + 1, 12 + bob, GLOW)
    g.rect(11, 15 + bob, 15, 15 + bob, EYE)                         # teeth line
    for tx in (12, 14):
        g.set(tx, 15 + bob, bone.base)
    g.ellipse(21, 20 + bob, 2.4, 2.4, bone.base)                   # bony hand on the pole


# --- a flame spirit ----------------------------------------------------------------------------

def paint_flame(g: Fig, L: Look, anim: str, i: int) -> None:
    outer, mid, core = L.body, tone(FLAME_MID, None), tone(FLAME_CORE, None)
    k = i % 4
    f = (0, 1, 0, -1)[k]
    bob = (0, 1)[i % 2] if anim == "idle" else 0
    hurt = anim == "hurt"
    g.poly([(12 + f, 0 + bob), (17, 8 + bob), (22, 14), (21, 21), (17, 26), (7, 26), (3, 21), (2, 14), (7, 8 + bob)], outer.base)
    g.poly([(3 - f, 9 + bob), (6, 14), (3, 18)], outer.base)       # side tongues
    g.poly([(21 + f, 8 + bob), (19, 14), (22, 18)], outer.base)
    g.poly([(12 - f, 8 + bob), (17, 15), (18, 21), (14, 25), (9, 25), (6, 21), (7, 15)], mid.base)
    g.poly([(12, 14), (15, 19), (14, 24), (10, 24), (9, 19)], core.base)
    g.rect(5, 17, 6, 22, outer.shadow)
    angry = not hurt
    for ex in (7, 14):                                               # slanted angry eyes
        g.rect(ex, 15 + bob, ex + 2, 17 + bob, WHITE)
        g.rect(ex + 1, 16 + bob, ex + 2, 17 + bob, EYE)
    if angry:
        g.line(6, 13 + bob, 10, 15 + bob, EYE, 1)
        g.line(17, 13 + bob, 13, 15 + bob, EYE, 1)
    g.rect(9, 21, 14, 22, EYE)                                       # jagged grin
    for tx in (9, 11, 13):
        g.set(tx, 21, WHITE)


# --- a snail -----------------------------------------------------------------------------------

def paint_snail(g: Fig, L: Look, anim: str, i: int) -> None:
    shell, body = L.body, tone(SNAIL_BODY, None)
    k = i % 4
    stretch = (0, 1, 2, 1)[k] if anim == "run" else 0
    bob = (0, 1)[i % 2] if anim == "idle" else 0
    hurt = anim == "hurt"
    g.ellipse(13 + stretch / 2, 20, 12 + stretch / 2, 4.2, body.base)  # the foot
    g.rect(3, 22, 23 + stretch, 23, body.shadow)
    g.ellipse(25 + stretch, 17 + bob, 4.5, 4.5, body.base)             # head
    g.ellipse(24 + stretch, 15 + bob, 2.5, 1.8, body.light)
    for sx, wig in ((23, 0), (27, 1)):                                  # eye stalks
        x = sx + stretch
        g.line(x, 14 + bob, x - 1 + (wig if k % 2 else 0), 7 + bob, body.base, 2)
        g.ellipse(x - 1 + (wig if k % 2 else 0), 6 + bob, 2.3, 2.3, WHITE)
        g.rect(x - 1 + (wig if k % 2 else 0), 5 + bob, x + (wig if k % 2 else 0), 7 + bob, EYE) if not hurt else g.set(x - 1, 6 + bob, EYE)
    g.rect(26 + stretch, 20 + bob, 28 + stretch, 20 + bob, EYE)         # smile
    g.ellipse(11, 12 + bob, 10, 9.5, shell.base)                        # shell with a spiral
    g.ellipse(8, 8 + bob, 5, 3.4, shell.light)
    g.ellipse(14, 15 + bob, 6.5, 5, shell.shadow)
    for r, c in ((8.2, L.dark.base), (6.4, shell.base), (4.6, L.dark.base), (3.0, shell.base), (1.4, L.dark.base)):
        _clip(g, 11, 12 + bob, r, r, c, 5 + bob, 23)
    g.rect(1, 19, 5, 19, body.base)                                      # tail end


# --- a little alien ----------------------------------------------------------------------------

ALIEN = "#6fd24a"


def paint_alien(g: Fig, L: Look, anim: str, i: int) -> None:
    sk = L.body
    k = i % 4
    bob = {"idle": (0, 1)[i % 2], "run": (0, 1, 0, 1)[k]}.get(anim, 0)
    swing = ((-2, 2), (0, 0), (2, -2), (0, 0))[k] if anim == "run" else (0, 0)
    hurt = anim == "hurt"
    g.line(12, 4 + bob, 9, 0 + bob, sk.shadow, 1)                         # antennae
    g.line(16, 4 + bob, 19, 0 + bob, sk.shadow, 1)
    g.ellipse(9, 0.5 + bob, 1.4, 1.4, sk.light)
    g.ellipse(19, 0.5 + bob, 1.4, 1.4, sk.light)
    g.rect(9 + swing[0], 26, 11 + swing[0], 30, sk.shadow)                # legs
    g.rect(15 + swing[1], 26, 17 + swing[1], 30, sk.base)
    g.rect(8 + swing[0], 30, 12 + swing[0], 31, L.dark.base)
    g.rect(14 + swing[1], 30, 18 + swing[1], 31, L.dark.base)
    g.ellipse(13.5, 24 + bob, 6, 5, sk.base)                              # body
    g.ellipse(11.5, 23 + bob, 3, 2.5, sk.light)
    g.line(7, 22 + bob, 3, 24 + bob + swing[0] // 2, sk.base, 2)           # arms
    g.line(20, 22 + bob, 24, 24 + bob + swing[1] // 2, sk.shadow, 2)
    g.ellipse(14, 12 + bob, 11.5, 10, sk.base)                            # the big head
    g.ellipse(10, 7 + bob, 6, 3.4, sk.light)
    g.ellipse(18.5, 14 + bob, 5, 6, sk.shadow)
    for ex, flip in ((8.5, -1), (19.5, 1)):                                # big black almond eyes
        if hurt:
            g.line(ex - 2, 10 + bob, ex + 2, 14 + bob, EYE, 1)
            g.line(ex + 2, 10 + bob, ex - 2, 14 + bob, EYE, 1)
        else:
            g.poly([(ex - 3.2, 10 + bob), (ex + 3.2, 11.5 + bob + flip * 0.0), (ex + 1.5 * flip, 17 + bob), (ex - 1.5 * flip, 17 + bob)],
                   EYE)
            g.set(ex - 1, 12 + bob, WHITE)
    g.rect(12, 18 + bob, 15, 18 + bob, L.dark.base)                       # mouth


PAINTERS = {"plant": paint_plant, "mushroom": paint_mushroom, "reaper": paint_reaper, "flame": paint_flame,
            "snail": paint_snail, "alien": paint_alien}
