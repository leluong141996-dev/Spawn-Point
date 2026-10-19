"""Chibi creatures in the same language as the people in chibi.py: big heads and eyes, flat colour blocks
with one shadow tone and a touch of light, a dark neutral outline.

Painted natively at the fine size (twice the kind's size). The coarse style shrinks the painted frame 2:1
(majority colour per 2x2 block) and outlines it again, so both sizes share one drawing.
"""

from __future__ import annotations

import random
import zlib

import numpy as np

from . import palettes
from .chibi import EYE, OUTLINE, WHITE, Fig, Tone, tone

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
FANG: RGBA = (250, 246, 236, 255)
TONGUE = "#e04858"
MANE = "#a8602c"
HORN = "#f0e6c8"


class Look:
    def __init__(self, color: str, feats: list[str], seed: int, pal: palettes.Palette | None):
        self.f = set(feats)
        self.body: Tone = tone(color, pal)
        self.belly: Tone = tone(_lighter(color), pal)
        self.dark: Tone = tone(_darker(color), pal)
        self.mane: Tone = tone(MANE, pal)
        self.horn: Tone = tone(HORN, pal)
        self.tongue: Tone = tone(TONGUE, pal)
        self.rng = random.Random(seed)


def _hex_to_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(c: str, t: tuple[int, int, int], k: float) -> str:
    r, g, b = _hex_to_rgb(c)
    return "#%02x%02x%02x" % tuple(round(a + (b_ - a) * k) for a, b_ in zip((r, g, b), t))


def _lighter(c: str) -> str:
    return _mix(c, (255, 244, 224), 0.55)


def _darker(c: str) -> str:
    return _mix(c, (24, 18, 36), 0.45)


def _eye(g: Fig, x: int, y: int, closed: bool = False, hurt: bool = False, big: bool = True) -> None:
    """A cute 2x3 eye: white with a dark pupil toward the facing side (right)."""
    if hurt:
        g.set(x, y, EYE)
        g.set(x + 1, y + 1, EYE)
        g.set(x, y + 2, EYE)
        return
    if closed:
        g.rect(x, y + 1, x + 1, y + 1, EYE)
        return
    if big:
        g.rect(x, y, x + 1, y + 2, WHITE)
        g.rect(x + 1, y, x + 1, y + 2, EYE)
        g.set(x + 1, y, WHITE)
    else:
        g.rect(x, y, x, y + 1, EYE)


# --- beast: wolves, foxes, dogs, cats, bears, boars, lions, tigers ------------------------------

def paint_beast(g: Fig, L: Look, anim: str, i: int) -> None:
    f, b, be = L.f, L.body, L.belly
    bear = "round_ears" in f
    k = i % 4
    bob = {"idle": (0, 1)[i % 2], "run": (0, 1, 0, 1)[k]}.get(anim, 0)
    hurt = anim == "hurt"
    # tail behind the body
    if "bushy_tail" in f:
        g.ellipse(5, 9 + bob, 4.5, 3.5, b.base)
        g.ellipse(2.5, 7 + bob, 2.5, 2.2, be.base)
    elif "thin_tail" in f:
        g.line(7, 11 + bob, 3, 6 + bob, b.base)
        g.line(3, 6 + bob, 2, 3 + bob, b.base)
    elif not bear:
        g.line(7, 11 + bob, 3, 8 + bob, b.shadow, 2)
    # legs: far pair in shadow, near pair in base; a gallop when running
    if anim == "run":
        swing = ((-2, 2), (0, 0), (2, -2), (0, 0))[k]
    elif anim in ("jump", "fall"):
        swing = (-2, 2) if anim == "jump" else (2, -2)
    else:
        swing = (0, 0)
    top = 16 + bob
    for x, d, col in ((10, swing[1], b.shadow), (20, swing[0], b.shadow), (8, swing[0], b.base), (18, swing[1], b.base)):
        g.line(x, top, x + d, 21, col, 3)
        g.rect(x + d - 1, 22, x + d + 2, 23, L.dark.base)
    # body
    g.ellipse(14, 13 + bob, 9.5, 5.5 if not bear else 6.5, b.base)
    g.ellipse(14, 16 + bob, 6.5, 2.2, be.base)
    g.rect(8, 9 + bob, 13, 10 + bob, b.light)
    if "stripes" in f:
        for sx in (9, 13, 17):
            g.line(sx, 9 + bob, sx + 1, 13 + bob, L.dark.base)
    if "mane" in f:
        g.ellipse(23, 9 + bob, 7, 7, L.mane.base)
        g.ellipse(21.5, 10 + bob, 5, 5.5, L.mane.shadow)
    # head
    hx, hy = 24, 8 + bob
    g.ellipse(hx, hy, 6, 5.5, b.base)
    g.rect(hx - 4, hy - 4, hx - 1, hy - 3, b.light)
    if "snout" in f or not bear:  # muzzle toward the facing side
        g.ellipse(hx + 5, hy + 2, 3.2, 2.4, be.base)
        g.rect(hx + 7, hy, hx + 8, hy + 1, EYE)  # nose
    else:
        g.ellipse(hx + 4, hy + 2, 2.6, 2.2, be.base)
        g.rect(hx + 6, hy + 1, hx + 6, hy + 1, EYE)
    if "tusks" in f:
        g.rect(hx + 5, hy + 4, hx + 5, hy + 5, FANG)
        g.rect(hx + 7, hy + 4, hx + 7, hy + 5, FANG)
    # ears
    if bear:
        g.ellipse(hx - 4, hy - 5, 2.2, 2.2, b.base)
        g.ellipse(hx + 1, hy - 5.5, 2.2, 2.2, b.shadow)
    elif "floppy_ears" in f:
        g.ellipse(hx - 4, hy - 1, 2, 3.5, L.dark.base)
    else:
        g.poly([(hx - 6, hy - 3), (hx - 4.5, hy - 9), (hx - 1.5, hy - 4)], b.base)
        g.poly([(hx - 1, hy - 4), (hx + 1, hy - 9.5), (hx + 3.5, hy - 3.5)], b.shadow)
        g.set(hx - 4, hy - 5, be.base)
    blink = anim == "idle" and i == 1
    _eye(g, hx + 1, hy - 2, closed=blink, hurt=hurt)
    if anim == "attack" or (anim == "run" and k == 0) or "fangs" in f:
        g.set(hx + 7, hy + 3, FANG)


# --- spider ------------------------------------------------------------------------------------

def paint_spider(g: Fig, L: Look, anim: str, i: int) -> None:
    """Front-facing: a round body with two big eyes, four thin legs a side reaching up, out and down."""
    b, be = L.body, L.belly
    k = i % 4
    bob = {"idle": (0, 1)[i % 2], "run": (0, 1, 0, 1)[k]}.get(anim, 0)
    hurt = anim == "hurt"
    # (hip, knee, foot) for the left side; the right side mirrors it
    legs = [((11, 8), (6, 2), (1, 19)), ((11, 10), (6, 6), (5, 21)), ((12, 13), (8, 10), (9, 21)),
            ((13, 15), (11, 15), (12, 21))]
    for n, (hip, knee, foot) in enumerate(legs):
        for side in (-1, 1):
            lift = 2 if anim == "run" and (n + (side > 0) + k) % 2 else (2 if anim == "jump" else 0)
            mx = (lambda x: x) if side < 0 else (lambda x: 31 - x)  # noqa: E731
            hx, hy = mx(hip[0]), hip[1] + bob
            kx, ky = mx(knee[0]), knee[1] + bob - lift // 2
            fx, fy = mx(foot[0]), foot[1] - lift
            col = b.shadow if side < 0 else L.dark.base
            g.line(hx, hy, kx, ky, col)
            g.line(kx, ky, fx, fy, col)
    g.ellipse(16, 8 + bob, 6.5, 5.5, b.base)  # abdomen
    g.ellipse(14, 5.5 + bob, 3, 2, b.light)
    g.ellipse(16, 13.5 + bob, 5, 4, b.base)   # head
    g.rect(13, 8 + bob, 14, 8 + bob, be.base)  # two spots on the back
    g.rect(18, 8 + bob, 19, 8 + bob, be.base)
    blink = anim == "idle" and i == 1
    if hurt:
        _eye(g, 13, 11 + bob, hurt=True)
        _eye(g, 18, 11 + bob, hurt=True)
    elif blink:
        g.rect(13, 13 + bob, 14, 13 + bob, EYE)
        g.rect(17, 13 + bob, 18, 13 + bob, EYE)
    else:  # big front eyes with a glint
        g.rect(13, 11 + bob, 14, 13 + bob, EYE)
        g.rect(17, 11 + bob, 18, 13 + bob, EYE)
        g.set(13, 11 + bob, WHITE)
        g.set(17, 11 + bob, WHITE)
    fang = 1 if anim == "attack" or (anim == "run" and k == 2) else 0
    g.rect(15, 17 + bob, 15, 17 + bob + fang, FANG)
    g.rect(16, 17 + bob, 16, 17 + bob + fang, FANG)


# --- dragon ------------------------------------------------------------------------------------

def paint_dragon(g: Fig, L: Look, anim: str, i: int) -> None:
    b, be, h = L.body, L.belly, L.horn
    k = i % 4
    flap = (0, 1, 2, 1)[k] if anim in ("idle", "run") else 1
    bob = (0, 1, 1, 0)[k] if anim in ("idle", "run") else 0
    hurt = anim == "hurt"
    # far wing, tail, body, near wing, head
    wy = (-4, 0, 3)[flap]
    g.poly([(15, 13 + bob), (7, 2 + wy + bob), (4, 10 + wy + bob), (11, 15 + bob)], L.dark.base)
    g.line(12, 20 + bob, 5, 22 + bob, b.base, 3)
    g.line(5, 22 + bob, 2, 18 + bob, b.base, 2)
    g.poly([(0, 16 + bob), (3, 14 + bob), (3, 19 + bob)], h.base)  # tail spade
    g.ellipse(16, 18 + bob, 7, 6, b.base)
    for y in (16, 18, 20):
        g.rect(15, y + bob, 19, y + bob, be.base)
    g.rect(11, 14 + bob, 14, 15 + bob, b.light)
    g.rect(12, 23 + bob, 14, 25, b.shadow)  # little legs
    g.rect(18, 23 + bob, 20, 25, b.shadow)
    g.poly([(17, 13 + bob), (12, 1 + wy + bob), (8, 9 + wy + bob), (14, 15 + bob)], b.base)
    g.line(17, 13 + bob, 12, 1 + wy + bob, b.shadow)
    hx, hy = 25, 10 + bob
    g.ellipse(hx, hy, 7, 6, b.base)
    g.ellipse(hx + 6, hy + 2, 4, 3, b.base)
    g.rect(hx + 3, hy + 3, hx + 9, hy + 4, be.base)
    g.rect(hx - 4, hy - 4, hx - 1, hy - 3, b.light)
    for x, y in ((hx - 4, hy - 6), (hx - 1, hy - 7)):
        g.rect(x, y - 2, x + 1, y, h.base)
        g.set(x, y - 3, h.base)
    g.set(hx + 8, hy + 1, EYE)  # nostril
    blink = anim == "idle" and i == 3
    _eye(g, hx + 1, hy - 2, closed=blink, hurt=hurt)
    if anim == "attack":  # a puff of fire
        for n, c in enumerate(("#ffd84a", "#ff9a3a", "#e8482a")):
            g.ellipse(hx + 11 + n, hy + 3, 2 - n * 0.4, 1.6, tone(c, None).base)


# --- ghost -------------------------------------------------------------------------------------

def paint_ghost(g: Fig, L: Look, anim: str, i: int) -> None:
    b = L.body
    k = i % 4
    bob = (0, 1, 2, 1)[k] if anim in ("idle", "run") else 0
    hurt = anim == "hurt"
    g.ellipse(12, 10 + bob, 9, 9, b.base)
    g.rect(3, 10 + bob, 20, 21 + bob, b.base)
    g.rect(18, 8 + bob, 20, 21 + bob, b.shadow)
    for n in range(4):  # a wavy hem that ripples
        x = 3 + n * 5 + (k % 2)
        g.ellipse(x + 2, 22 + bob, 2.6, 2.4, b.base if n < 3 else b.shadow)
    g.rect(5, 4 + bob, 9, 6 + bob, b.light)
    arm = (0, -1)[k % 2]
    g.ellipse(2, 14 + bob + arm, 2, 1.6, b.base)
    g.ellipse(22, 13 + bob - arm, 2, 1.6, b.shadow)
    if hurt:
        _eye(g, 8, 9 + bob, hurt=True)
        _eye(g, 14, 9 + bob, hurt=True)
    else:
        g.rect(8, 8 + bob, 9, 11 + bob, EYE)
        g.rect(14, 8 + bob, 15, 11 + bob, EYE)
        g.set(8, 8 + bob, WHITE)
        g.set(14, 8 + bob, WHITE)
        mouth = 2 if anim == "attack" else 1
        g.rect(11, 14 + bob, 12, 14 + bob + mouth, EYE)


# --- snake -------------------------------------------------------------------------------------

def paint_snake(g: Fig, L: Look, anim: str, i: int) -> None:
    b, be = L.body, L.belly
    k = i % 4
    wave = (0, 1, 0, -1)[k] if anim == "run" else 0
    hurt = anim == "hurt"
    lift = {"jump": -2, "fall": 0}.get(anim, 0)
    # body: an S along the ground, thick, belly underneath
    pts = [(2, 12), (6, 10 + wave), (11, 12), (16, 13 - wave), (21, 12)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        g.line(x0, y0 + lift, x1, y1 + lift, b.base, 4)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        g.line(x0, y0 + 3 + lift, x1, y1 + 3 + lift, be.base)
    for x, y in ((6, 10 + wave), (16, 13 - wave)):
        g.rect(x, y + lift, x + 1, y + lift, L.dark.base)  # markings
    g.line(0, 13 + lift, 3, 12 + lift, b.shadow, 2)  # tail tip
    # neck and raised head
    g.line(21, 12 + lift, 24, 6 + lift, b.base, 4)
    g.ellipse(26, 5 + lift, 5, 4, b.base)
    g.rect(23, 2 + lift, 25, 2 + lift, b.light)
    g.rect(27, 7 + lift, 30, 7 + lift, be.base)
    blink = anim == "idle" and i == 1
    _eye(g, 26, 3 + lift, closed=blink, hurt=hurt)
    if (anim == "idle" and i == 0) or anim == "attack" or (anim == "run" and k == 1):
        tg = L.tongue.base
        g.rect(31, 6 + lift, 31, 6 + lift, tg)
        g.set(31, 5 + lift, tg)
        g.set(31, 7 + lift, tg)


PAINTERS = {"beast": paint_beast, "spider": paint_spider, "dragon": paint_dragon, "ghost": paint_ghost,
            "snake": paint_snake}


# --- frames ------------------------------------------------------------------------------------

def _outline(px: np.ndarray) -> np.ndarray:
    a = px[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    out = px.copy()
    out[ring] = OUTLINE
    return out


def shrink(px: np.ndarray) -> np.ndarray:
    """2:1 downscale for the coarse style: a block is opaque when at least 2 of its 4 pixels are, and takes
    the most common opaque colour (darkest wins ties, so eyes survive)."""
    h, w = px.shape[0] // 2, px.shape[1] // 2
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            block = px[2 * y:2 * y + 2, 2 * x:2 * x + 2].reshape(-1, 4)
            solid = [tuple(int(v) for v in c) for c in block if c[3] > 0]
            if len(solid) < 2:
                continue
            counts: dict[tuple, int] = {}
            for c in solid:
                counts[c] = counts.get(c, 0) + 1
            if tuple(EYE) in counts:  # eyes are tiny but must survive the shrink
                best = tuple(EYE)
            else:
                best = max(counts.items(), key=lambda kv: (kv[1], -sum(kv[0][:3])))[0]
            out[y, x] = best
    return out


def frames(kind: str, name: str, color: str, feats: list[str], seed: int, pal: palettes.Palette | None,
           size: tuple[int, int], anims: dict[str, tuple[int, float, bool]], fine: bool) -> dict[str, list[np.ndarray]]:
    w, h = size[0] * 2, size[1] * 2
    if kind == "ghost":  # ghosts keep their hue but stay pale
        color = _mix(color, (240, 244, 255), 0.82)
    L = Look(color, feats, zlib.crc32(f"{name}:{kind}:{seed}".encode()), pal)
    out: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in anims.items():
        out[anim] = []
        for i in range(n):
            g = Fig(w, h)
            PAINTERS[kind](g, L, anim, i)
            px = g.px if fine else shrink(g.px)
            px = _outline(px)
            out[anim].append(pal.snap(px) if pal else px)
    return out
