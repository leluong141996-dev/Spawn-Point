"""Skill effects for card battles: short pixel animations played over a fighter (slash, fire vortex, ice shards,
lightning, poison cloud, healing sparkles, shield shimmer, strength aura, curse swirl, hit spark). Each is one
horizontal strip of square frames, drawn from code.

    strip(name) -> RGBA array (size, size * frames, 4); EFFECTS lists names, sizes and frame counts
"""

from __future__ import annotations

import math
import random

import numpy as np

RGBA = tuple[int, int, int, int]


def _c(h: str, a: int = 255) -> RGBA:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


class _F:
    def __init__(self, n: int) -> None:
        self.n = n
        self.px = np.zeros((n, n, 4), np.uint8)
        self.ys, self.xs = np.mgrid[0:n, 0:n]

    def disc(self, cx: float, cy: float, r: float, c: RGBA) -> None:
        self.px[(self.xs + 0.5 - cx) ** 2 + (self.ys + 0.5 - cy) ** 2 <= r * r] = c

    def ring(self, cx: float, cy: float, r0: float, r1: float, c: RGBA, a0: float = -9, a1: float = 9) -> None:
        dx, dy = self.xs + 0.5 - cx, self.ys + 0.5 - cy
        d = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        self.px[(d >= r0) & (d <= r1) & (ang >= a0) & (ang <= a1)] = c

    def dot(self, x: float, y: float, c: RGBA, s: int = 1) -> None:
        x, y = int(round(x)), int(round(y))
        self.px[max(0, y):max(0, y + s), max(0, x):max(0, x + s)] = c

    def line(self, x0: float, y0: float, x1: float, y1: float, c: RGBA, w: int = 1) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for k in range(n + 1):
            t = k / n
            self.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, c, w)

    def edge(self, c: RGBA) -> None:
        a = self.px[..., 3] > 0
        q = np.pad(a, 1)
        self.px[(q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]) & ~a] = c


def _slash(f: _F, i: int, n: int) -> None:
    """A wide crescent swept from top left to bottom right, thick in the middle of the swing."""
    c = f.n / 2
    t = i / (n - 1)
    a1 = -2.2 + t * 3.0
    a0 = a1 - 1.6
    w = 9 * math.sin(math.pi * min(1.0, t + 0.2))
    if i < n - 1:
        f.ring(c, c + 2, c - 4 - w, c - 3, _c("#9ad4ff"), a0, a1)
        f.ring(c, c + 2, c - 4 - w * 0.6, c - 3, _c("#ffffff"), a0 + 0.4, a1)
    for k in range(6):
        a = a1 - k * 0.28
        f.dot(c + math.cos(a) * (c - 1), c + 2 + math.sin(a) * (c - 1), _c("#fff8c0"), 2 if k % 2 else 1)
    f.edge(_c("#2a4a8a"))


def _fire(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    rng = random.Random(i)
    grow = min(1.0, (i + 1) / 3)
    fade = 1.0 if i < n - 2 else 0.6
    for k in range(70):
        a = k * 0.35 + i * 0.9
        r = (2 + k * 0.32) * grow
        x, y = c + math.cos(a) * r, c + math.sin(a) * r * 0.75 - k * 0.12
        col = ("#fff4a0", "#ffd04a", "#ff8a2a", "#e8402a")[min(3, k // 18)]
        f.disc(x, y, (3.6 - k * 0.03) * fade, _c(col))
    for k in range(10):
        f.dot(c + rng.uniform(-c, c) * 0.8, c - rng.uniform(0, c) * grow, _c("#ffd04a"), 2)
    f.edge(_c("#7a1a10"))


def _ice(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    t = (i + 1) / n
    for k in range(7):
        a = k / 7 * math.tau + 0.3
        L = (c - 4) * min(1.0, t * 1.6)
        x1, y1 = c + math.cos(a) * L, c + math.sin(a) * L
        f.line(c, c, x1, y1, _c("#9ad4ff"), 3)
        f.line(c, c, x1, y1, _c("#ffffff"), 1)
    f.disc(c, c, 5 * (1.2 - t * 0.5), _c("#e8f8ff"))
    f.edge(_c("#2a5a9a"))


def _bolt(f: _F, i: int, n: int) -> None:
    """A zigzag strike from the top down to a burst."""
    rng = random.Random(7 + i // 2)
    c = f.n / 2
    x, y = c, 0.0
    if i < n - 1:
        while y < f.n - 10:
            nx = min(c + 7, max(c - 7, x + rng.uniform(-7, 7)))
            ny = y + rng.uniform(5, 8)
            f.line(x, y, nx, ny, _c("#fff08a"), 3)
            f.line(x, y, nx, ny, _c("#ffffff"), 1)
            x, y = nx, ny
    r = 4 + i * 2
    f.disc(c, f.n - 8, r, _c("#fff08a"))
    f.disc(c, f.n - 8, max(1, r - 3), _c("#ffffff"))
    f.edge(_c("#8a6a10"))


def _poison(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    rng = random.Random(3)
    for k in range(12):
        bx, by = c + rng.uniform(-c * 0.7, c * 0.7), c + rng.uniform(-4, c * 0.6)
        r = rng.uniform(3, 6) * (0.6 + i / n)
        rise = i * rng.uniform(1.5, 3)
        if i < n - 1 or k % 2:
            f.disc(bx, by - rise, r, _c("#5cd84a" if k % 3 else "#a8f070"))
            f.dot(bx - r * 0.4, by - rise - r * 0.4, _c("#e8ffd0"))
    f.edge(_c("#1e5a2a"))


def _heal(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    rng = random.Random(5)
    for k in range(9):
        x = c + rng.uniform(-c * 0.8, c * 0.8)
        y = f.n - 4 - ((i * 5 + k * 7) % f.n)
        s = 2 if k % 2 else 3
        col = _c("#7cf07c") if k % 3 else _c("#e8ffe8")
        f.line(x - s, y, x + s, y, col, 2)
        f.line(x, y - s, x, y + s, col, 2)
    f.edge(_c("#1e6a2a"))


def _shield(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    t = i / (n - 1)
    r = c - 3
    pts = [(c + math.cos(a) * r, c + math.sin(a) * r) for a in np.linspace(-math.pi / 2, 1.5 * math.pi, 7)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        f.line(x0, y0, x1, y1, _c("#9ad4ff"), 2)
    sweep = -math.pi / 2 + t * math.tau
    f.ring(c, c, r - 4, r - 1, _c("#ffffff"), sweep - 0.6, sweep)
    if i % 2 == 0:
        f.disc(c, c, 3, _c("#e8f8ff"))


def _buff(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    for k in range(3):
        x = c - 10 + k * 10
        y = f.n - 6 - ((i * 6 + k * 9) % (f.n - 8))
        f.line(x, y, x - 5, y + 5, _c("#ffb03a"), 2)
        f.line(x, y, x + 5, y + 5, _c("#ffb03a"), 2)
        f.line(x, y + 1, x, y + 10, _c("#ffe080"), 2)
    f.edge(_c("#7a3a10"))


def _curse(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    for k in range(40):
        a = k * 0.4 - i * 0.8
        r = c - 3 - k * 0.45
        f.disc(c + math.cos(a) * r, c + math.sin(a) * r * 0.7, 2.2, _c("#b06ae8" if k % 2 else "#e0b0ff"))
    f.edge(_c("#3a1a5a"))


def _hit(f: _F, i: int, n: int) -> None:
    c = f.n / 2
    r = 4 + i * 4
    for k in range(8):
        a = k / 8 * math.tau + (0.2 if k % 2 else 0)
        L = r if k % 2 else r * 0.55
        f.line(c, c, c + math.cos(a) * L, c + math.sin(a) * L, _c("#ffffff") if i < 2 else _c("#fff0a0"), 2)
    if i < 2:
        f.disc(c, c, 4 - i, _c("#ffffff"))


# name -> (frame size, frames, painter)
EFFECTS = {"slash": (48, 5, _slash), "fire": (48, 6, _fire), "ice": (48, 5, _ice), "bolt": (48, 5, _bolt),
           "poison": (48, 6, _poison), "heal": (48, 6, _heal), "shield": (48, 5, _shield), "buff": (48, 5, _buff),
           "curse": (48, 5, _curse), "hit": (32, 4, _hit)}


def strip(name: str) -> np.ndarray:
    size, n, painter = EFFECTS[name]
    out = np.zeros((size, size * n, 4), np.uint8)
    for i in range(n):
        f = _F(size)
        painter(f, i, n)
        out[:, i * size:(i + 1) * size] = f.px
    return out
