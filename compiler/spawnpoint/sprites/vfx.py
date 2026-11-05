"""A small pixel-art effects toolkit: a frame with two buffers (opaque colour faded by ordered dither, and additive
light composited on top), shapes and glows, simulated particles (sparks that streak and bounce, fire that cools into
smoke, smoke that swells and thins, embers, motes, twinkling stars, flakes, grit) and lights that flare and die.

Ported from pixelfx (https://github.com/patch-gg/pixelfx, MIT License, Copyright (c) 2026 Patch, Copyright (c) 2026
Hugo Duprez), whose particle simulation adapts Sprite Fusion's open-source pixel art VFX
(https://www.spritefusion.com/pixel-art-vfx, MIT License, Copyright (c) 2026 Hugo Duprez).

Units are art pixels and seconds. Effects draw in local coordinates: (0, 0) is the frame's anchor (`ox`, `oy`).

    f = Frame(64, 64, 32, 32); f.glow(0, 0, 20, PAL["fire"][4], 0.5); rgba = f.composite()
    render(make, size, frames, fps, anchor) -> RGBA strip of square frames, for an effect made by make(rng)
"""

from __future__ import annotations

import math
import random
from typing import Callable

import numpy as np

RGBA = tuple[int, int, int, int]


def hexc(h: str | RGBA, a: int = 255) -> RGBA:
    if not isinstance(h, str):
        return h
    s = h.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), a


def ramp(*cols: str) -> list[RGBA]:
    return [hexc(c) for c in cols]


def mix(a: RGBA, b: RGBA, t: float) -> RGBA:
    t = min(1.0, max(0.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)  # type: ignore[return-value]


def dim(c: RGBA, k: float) -> RGBA:
    return tuple(min(255, int(c[i] * k)) for i in range(3)) + (255,)  # type: ignore[return-value]


WHITE = (255, 255, 255, 255)

# Hue-shifted ramps, dark to bright: shadows lean cool or deep, highlights lean warm or white (from pixelfx).
PAL = {
    "fire": ramp("#1f0b10", "#4a1118", "#8c1d1c", "#cc3a1a", "#f2701f", "#ffae35", "#ffe27a", "#fff8d6"),
    "ice": ramp("#0c1430", "#162c5c", "#1f4f94", "#2f7fcc", "#58b4ec", "#9bdcff", "#d8f4ff", "#ffffff"),
    "electric": ramp("#0a0f2e", "#172a78", "#2550d0", "#3f8cff", "#7cc8ff", "#c8f0ff", "#ffffff"),
    "volt": ramp("#24160a", "#5e3a0c", "#a8680f", "#e8a218", "#ffd23c", "#fff08a", "#ffffff"),
    "poison": ramp("#0d1a0c", "#173a14", "#265e18", "#3f8a1e", "#6cb82a", "#a8e04a", "#e0ff8a"),
    "heal": ramp("#08201a", "#0f3f2c", "#17663e", "#24924e", "#3ec466", "#7ee88a", "#c8ffc4", "#ffffff"),
    "holy": ramp("#2a1c08", "#5a3e10", "#9a6c18", "#d8a428", "#ffd84a", "#fff09a", "#fffbe6", "#ffffff"),
    "arcane": ramp("#140a26", "#2b1252", "#481c88", "#6b2cc0", "#9a48ec", "#c684ff", "#ecc8ff", "#ffffff"),
    "shadow": ramp("#050308", "#0f0a18", "#1c1230", "#2c1a4a", "#432468", "#5e3290", "#8048b8", "#a970e0"),
    "metal": ramp("#0c0e14", "#1c2230", "#2e3648", "#4a5468", "#6e7a90", "#9aa6ba", "#d0d8e6", "#ffffff"),
    "ember": ramp("#1a0a0e", "#3d1012", "#701a14", "#a8301a", "#e0561e", "#ff8a2a", "#ffc46a"),
    "gold": ramp("#1e1206", "#4a2c08", "#86520c", "#c48412", "#f0b424", "#ffe066", "#fff6c4", "#ffffff"),
}
FIRE_RAMP = ramp("#ffffff", "#fff3a6", "#ffe26b", "#ffc23d", "#ff8a2a", "#f2561d", "#c9281f", "#8a1f17", "#4a1712")
SMOKE_RAMP = ramp("#7b6f72", "#5d5660", "#433d48", "#2b2630", "#1a171e")
HOT = ramp("#fff3a6", "#ffe26b", "#ff8a2a", "#f2561d")

# 4x4 ordered (Bayer) thresholds: a pixel at alpha a is drawn when a is above its cell's threshold.
BAYER = (np.array([0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5], float).reshape(4, 4) + 0.5) / 16
GRAVITY = 950.0


def ramp_at(r: list[RGBA], t: float) -> RGBA:
    """The ramp step for t in 0..1, no blending: pixel art picks a colour, it doesn't fade between two."""
    return r[min(len(r) - 1, max(0, int(t * len(r))))]


class Frame:
    """w x h pixels; local (0, 0) sits at pixel (ox, oy). `color` holds opaque pixels (RGBA, alpha below 255 only
    for translucent volumes), `light` additive glow (RGB, 0..255 floats)."""

    def __init__(self, w: int, h: int, ox: float, oy: float) -> None:
        self.w, self.h, self.ox, self.oy = w, h, ox, oy
        self.color = np.zeros((h, w, 4), np.float32)
        self.light = np.zeros((h, w, 3), np.float32)
        self.bayer = np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]

    # --- boxes and raw writes ------------------------------------------------------------------
    def _box(self, x0: float, y0: float, x1: float, y1: float):
        """The pixel box covering local [x0, x1] x [y0, y1], clipped, with the local centres of its pixels."""
        sx0, sx1 = max(0, int(math.floor(x0 + self.ox))), min(self.w, int(math.ceil(x1 + self.ox)) + 1)
        sy0, sy1 = max(0, int(math.floor(y0 + self.oy))), min(self.h, int(math.ceil(y1 + self.oy)) + 1)
        if sx0 >= sx1 or sy0 >= sy1:
            return None
        ys, xs = np.mgrid[sy0:sy1, sx0:sx1]
        return (slice(sy0, sy1), slice(sx0, sx1)), xs + 0.5 - self.ox, ys + 0.5 - self.oy

    def _write(self, sl, mask: np.ndarray, col, a) -> None:
        """Opaque pixels where mask, faded by dither at alpha a (scalar or array); col is a colour or (N, 4) array."""
        a = np.broadcast_to(np.asarray(a, np.float32), mask.shape)
        keep = mask & (a > self.bayer[sl])
        if not keep.any():
            return
        block = self.color[sl]
        if isinstance(col, np.ndarray) and col.ndim == 3:
            block[keep] = col[keep]
        else:
            block[keep] = col

    def put(self, x: float, y: float, c: RGBA, a: float = 1.0) -> None:
        sx, sy = int(math.floor(x + self.ox)), int(math.floor(y + self.oy))
        if 0 <= sx < self.w and 0 <= sy < self.h and (a >= 1 or a > self.bayer[sy, sx]):
            self.color[sy, sx] = c

    px = put

    def blend(self, x: float, y: float, c: RGBA, a: float) -> None:
        sx, sy = int(math.floor(x + self.ox)), int(math.floor(y + self.oy))
        if 0 <= sx < self.w and 0 <= sy < self.h and a > 0.004:
            self._blend_px(np.s_[sy:sy + 1, sx:sx + 1], np.ones((1, 1), bool), c, np.full((1, 1), a, np.float32))

    def _blend_px(self, sl, mask: np.ndarray, c: RGBA, a: np.ndarray) -> None:
        """Translucent colour over what's there, keeping the result's own alpha (soft smoke, vapour, mist)."""
        block = self.color[sl]
        a = np.where(mask, a, 0.0)[..., None]
        da = block[..., 3:4] / 255.0
        oa = a + da * (1 - a)
        k = np.divide(a, oa, out=np.zeros_like(a), where=oa > 0)
        block[..., :3] = np.asarray(c[:3], np.float32) * k + block[..., :3] * (1 - k)
        block[..., 3:4] = np.where(a > 0.004, oa * 255, block[..., 3:4])

    def add_light(self, sl, mask: np.ndarray, c: RGBA, k) -> None:
        k = np.where(mask, k, 0.0)[..., None]
        self.light[sl] += np.asarray(c[:3], np.float32) * k

    # --- shapes ----------------------------------------------------------------------------------
    def disc(self, cx: float, cy: float, r: float, c: RGBA, a: float) -> None:
        """A translucent disc: puffs of smoke, vapour, dust."""
        if r < 0.5:
            return self.blend(cx, cy, c, a)
        b = self._box(cx - r, cy - r, cx + r, cy + r)
        if b:
            sl, xs, ys = b
            m = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r
            self._blend_px(sl, m, c, np.full(m.shape, a, np.float32))

    def circle(self, cx: float, cy: float, r: float, c: RGBA | Callable, a: float = 1.0) -> None:
        """Filled disc; c may be a function of d (0 centre .. 1 rim, an array) returning an (…, 4) colour array."""
        if r < 0.6:
            return self.put(cx, cy, c if not callable(c) else tuple(c(np.zeros(1))[0]), a)
        b = self._box(cx - r, cy - r, cx + r, cy + r)
        if b:
            sl, xs, ys = b
            d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r
            self._write(sl, d <= 1, c(d) if callable(c) else c, a)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: RGBA, a=1.0) -> None:
        b = self._box(cx - rx, cy - ry, cx + rx, cy + ry)
        if b and rx > 0 and ry > 0:
            sl, xs, ys = b
            self._write(sl, ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1, c, a)

    def ring(self, cx: float, cy: float, r: float, w: float, c: RGBA, a=1.0, sy: float = 1.0,
             keep: Callable | None = None) -> None:
        """A ring from radius r - w to r, squashed vertically by sy (0.3 lies on the floor); keep(angle) picks a part."""
        b = self._box(cx - r, cy - r * sy, cx + r, cy + r * sy)
        if b and r > 0:
            sl, xs, ys = b
            d = np.sqrt((xs - cx) ** 2 + ((ys - cy) / max(sy, 1e-3)) ** 2)
            m = (d <= r) & (d >= max(0.0, r - w))
            if keep is not None:
                m &= keep(np.arctan2((ys - cy) / max(sy, 1e-3), xs - cx))
            self._write(sl, m, c, a)

    def arc(self, cx: float, cy: float, r: float, w: Callable[[np.ndarray], np.ndarray], a0: float, a1: float,
            c: Callable[[np.ndarray, np.ndarray], np.ndarray], a=1.0) -> None:
        """A band of a ring from angle a0 to a1 (a1 > a0), width w(u) inward from radius r: the slash shape.
        c(u, v) colours it (u 0 at a0 .. 1 at a1, v 0 inner .. 1 outer) and returns an (…, 4) array."""
        b = self._box(cx - r, cy - r, cx + r, cy + r)
        if not b:
            return
        sl, xs, ys = b
        dx, dy = xs - cx, ys - cy
        d = np.sqrt(dx * dx + dy * dy)
        ang = np.mod(np.arctan2(dy, dx) - a0, 2 * math.pi)
        span = a1 - a0
        u = ang / span
        ww = w(np.clip(u, 0, 1))
        m = (d <= r) & (ang <= span) & (ww > 0) & (d >= r - ww)
        v = np.clip((d - (r - ww)) / np.maximum(ww, 1e-3), 0, 1)
        self._write(sl, m, c(np.clip(u, 0, 1), v), a)

    def line(self, x0: float, y0: float, x1: float, y1: float, c: RGBA | Callable, a: float = 1.0) -> None:
        """1 px line; c may be a function of u (0 at the start, 1 at the end) returning a colour."""
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            u = i / n
            self.put(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, c(u) if callable(c) else c, a)

    def polyline(self, pts: list[tuple[float, float]], c: RGBA, a: float = 1.0) -> None:
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            self.line(xa, ya, xb, yb, c, a)

    def shade(self, x0: float, y0: float, x1: float, y1: float, fn: Callable) -> None:
        """A pixel shader over a local box: fn(xs, ys) -> (mask, colour or (…, 4) array, alpha) on pixel centres."""
        b = self._box(x0, y0, x1, y1)
        if b:
            sl, xs, ys = b
            m, c, a = fn(xs, ys)
            self._write(sl, m, c, a)

    # --- light -----------------------------------------------------------------------------------
    def glow(self, x: float, y: float, r: float, c: RGBA, k: float = 0.5) -> None:
        """Radial light: k at the centre, falling to 0 at radius r."""
        if r < 1 or k <= 0.004:
            return
        b = self._box(x - r, y - r, x + r, y + r)
        if b:
            sl, xs, ys = b
            d = np.sqrt((xs - x) ** 2 + (ys - y) ** 2) / r
            f = np.clip(1 - d, 0, 1)
            self.add_light(sl, d < 1, c, f * f * k)

    def glow_line(self, x0: float, y0: float, x1: float, y1: float, r: float, c: RGBA, k: float = 0.5) -> None:
        if r < 1 or k <= 0.004:
            return
        b = self._box(min(x0, x1) - r, min(y0, y1) - r, max(x0, x1) + r, max(y0, y1) + r)
        if b:
            sl, xs, ys = b
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-9
            u = np.clip(((xs - x0) * dx + (ys - y0) * dy) / L2, 0, 1)
            d = np.sqrt((x0 + dx * u - xs) ** 2 + (y0 + dy * u - ys) ** 2) / r
            f = np.clip(1 - d, 0, 1)
            self.add_light(sl, d < 1, c, f * f * k)

    def glow_ring(self, x: float, y: float, R: float, r: float, c: RGBA, k: float = 0.5, sy: float = 1.0) -> None:
        """Light hugging a circle of radius R (a shockwave's light), falling off over width r."""
        if r < 1 or k <= 0.004:
            return
        b = self._box(x - R - r, y - (R + r) * sy, x + R + r, y + (R + r) * sy)
        if b:
            sl, xs, ys = b
            d = np.abs(np.sqrt((xs - x) ** 2 + ((ys - y) / max(sy, 1e-3)) ** 2) - R) / r
            f = np.clip(1 - d, 0, 1)
            self.add_light(sl, d < 1, c, f * f * k)

    # --- out -------------------------------------------------------------------------------------
    def composite(self) -> np.ndarray:
        """Colour plus light over transparency, as RGBA bytes: light becomes colour with alpha (its brightest
        channel), which reads as additive over a dark background."""
        c, L = self.color, self.light
        rgb, a = c[..., :3].copy(), c[..., 3:4] / 255.0
        lit = L.max(axis=2, keepdims=True) > 0
        solid = a >= 1.0
        # over an opaque pixel: add the light
        out_rgb = np.where(solid, np.minimum(255, rgb + L), rgb)
        # over transparency: premultiply what's there, add the light, divide by the new alpha
        pr = rgb * a + L
        na = np.minimum(1.0, np.maximum(a, L.max(axis=2, keepdims=True) / 255.0))
        trans = ~solid & lit
        out_rgb = np.where(trans, np.minimum(255, np.divide(pr, na, out=np.zeros_like(pr), where=na > 0)), out_rgb)
        out_a = np.where(trans, na, a)
        return np.concatenate([np.clip(out_rgb, 0, 255), np.clip(out_a * 255, 0, 255)], axis=2).astype(np.uint8)


# --- simulated particles ---------------------------------------------------------------------------
SPARK, MOTE, STREAK, FLAKE, VAPOUR, DUST, STAR, EMBER, SMOKE, FIRE, GRIT = range(11)
SMOKES, BIG, BACK = 1, 2, 4  # flags: a FIRE puff leaves smoke when it dies; bigger, slower smoke; drawn behind
SOFT = {VAPOUR, DUST, SMOKE}
CROSS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAG = ((1, 1), (1, -1), (-1, 1), (-1, -1))


class Particles:
    """spawn(kind, x, y, vx, vy, life, color, size, delay, flags); update(dt); draw(frame, layer)."""

    def __init__(self, rng: random.Random, ground: float = math.inf, sparks: list[RGBA] | None = None,
                 haze: RGBA | None = None) -> None:
        self.R, self.ground, self.list, self.t = rng, ground, [], 0.0
        self.sparks = sparks or HOT
        self.haze = haze

    def spawn(self, k: int, x: float, y: float, vx: float, vy: float, life: float, col: RGBA | None = WHITE,
              size: float = 1.0, delay: float = 0.0, flag: int = 0) -> None:
        self.list.append({"k": k, "x": x, "y": y, "vx": vx, "vy": vy, "life": life, "max": life, "col": col,
                          "size": size, "seed": self.R.random() * 100, "delay": delay, "flag": flag})

    def update(self, dt: float) -> None:
        self.t += dt
        R, t, g = self.R, self.t, self.ground
        for p in list(self.list):
            if p["delay"] > 0:
                p["delay"] -= dt
                continue
            p["life"] -= dt
            if p["life"] <= 0:
                if p["k"] == FIRE and p["flag"] & SMOKES:
                    big = p["flag"] & BIG
                    self.spawn(SMOKE, p["x"], p["y"], p["vx"] * 0.6, p["vy"] * 0.6 - 6,
                               R.uniform(1.3, 2.3) if big else R.uniform(0.8, 1.4), None, p["size"] * (0.85 if big else 0.7),
                               0, BIG if big else 0)
                self.list.remove(p)
                continue
            k = p["k"]
            if k == FIRE:
                p["vy"] -= 95 * dt
                p["vx"] += math.sin(t * 17 + p["seed"]) * 30 * dt
                p["vx"] -= p["vx"] * 5 * dt
                p["vy"] -= p["vy"] * 3.2 * dt
            elif k in (SPARK, GRIT):
                p["vy"] += GRAVITY * (0.45 if k == SPARK else 1.0) * dt
                drag = 2.2 if k == SPARK else 0.8
                p["vx"] -= p["vx"] * drag * dt
                if k == SPARK:
                    p["vy"] -= p["vy"] * drag * dt
                ny = p["y"] + p["vy"] * dt
                p["x"] += p["vx"] * dt
                if p["vy"] > 0 and p["y"] <= g <= ny:
                    if k == SPARK:
                        p["vy"], p["vx"], p["y"] = -p["vy"] * 0.45, p["vx"] * 0.7, g - 0.25
                    elif p["vy"] > 130 and R.random() < 0.4:
                        p["vy"], p["vx"], p["y"] = -p["vy"] * 0.25, p["vx"] * 0.5 + R.uniform(-10, 10), g - 0.25
                    else:
                        p["vx"] = p["vy"] = 0
                        p["y"] = g - 0.25
                        p["life"] = min(p["life"], 0.5)
                else:
                    p["y"] = ny
                continue
            elif k == STREAK:
                p["vx"] += p["vx"] * 3 * dt
                p["vy"] += p["vy"] * 3 * dt
            elif k == FLAKE:
                p["vx"] -= p["vx"] * 2.2 * dt
                p["vy"] -= p["vy"] * 2.2 * dt - 35 * dt
                p["x"] += math.sin(t * 2.5 + p["seed"]) * 7 * dt
            elif k == EMBER:
                p["vy"] += (-30 + math.sin(t * 3 + p["seed"]) * 20) * dt
                p["vx"] += math.cos(t * 2.3 + p["seed"]) * 45 * dt
                p["vx"] -= p["vx"] * 1.6 * dt
                p["vy"] -= p["vy"] * 1.6 * dt
            elif k == SMOKE:
                p["vy"] -= (23 if p["flag"] & BIG else 16) * dt
                p["vx"] += math.sin(t * 1.3 + p["seed"]) * 8 * dt
                p["vx"] -= p["vx"] * 1.6 * dt
                p["vy"] -= p["vy"] * 1.2 * dt
            elif k == MOTE:
                p["vx"] -= p["vx"] * 0.6 * dt
                p["vy"] -= p["vy"] * 0.6 * dt
            else:
                drag = 4 if k in SOFT else 1.6
                p["vx"] -= p["vx"] * drag * dt
                p["vy"] -= p["vy"] * drag * dt + 5 * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt

    def draw(self, f: Frame, layer: str | None = None) -> None:
        S = self.sparks
        for q in self.list:
            if q["delay"] > 0:
                continue
            if layer and ("back" if q["k"] in SOFT or q["flag"] & BACK else "front") != layer:
                continue
            k, x, y = q["life"] / q["max"], q["x"], q["y"]
            sp = math.hypot(q["vx"], q["vy"]) or 1.0
            ux, uy = q["vx"] / sp, q["vy"] / sp
            kind, col = q["k"], q["col"] or WHITE
            if kind == SPARK:
                head = S[0] if k > 0.6 else S[1] if k > 0.3 else S[2]
                ln = min(9.0, 1 + sp * 0.022)
                f.line(x - ux * ln, y - uy * ln, x - ux * ln * 0.4, y - uy * ln * 0.4, head if k > 0.5 else S[-1])
                f.line(x - ux * ln * 0.45, y - uy * ln * 0.45, x, y, head)
                f.glow(x, y, 3, head, 0.45 * k)
            elif kind == MOTE:
                ln, a = min(16.0, 0.5 + sp * 0.026) * q["size"], (k / 0.35 if k < 0.35 else 1.0)
                f.line(x - ux * ln, y - uy * ln, x - ux * ln * 0.35, y - uy * ln * 0.35, dim(col, 0.55), a)
                f.line(x - ux * ln * 0.4, y - uy * ln * 0.4, x, y, col, a)
                f.glow(x, y, 2.5 + q["size"], col, 0.4 * k)
            elif kind == STREAK:
                L = min(7.0, max(1.0, sp / 30))
                d = L
                while d >= 0:
                    f.put(x - ux * d, y - uy * d, WHITE if d < 1 else col if d < L * 0.5 else dim(col, 0.6),
                          1.0 if d < L * 0.5 else 1.2 - d / L)
                    d -= 0.5
                f.glow(x, y, 4, col, 0.4)
            elif kind == FLAKE:
                a = min(1.0, k * 3)
                f.put(x, y, col, a)
                if q["size"] > 1.3:
                    for dx, dy in CROSS:
                        f.put(x + dx, y + dy, dim(col, 0.8), a * 0.8)
            elif kind == VAPOUR:
                r = q["size"] * (0.6 + (1 - k) * 0.9)
                f.disc(x, y, r, col, (k ** 1.3) * 0.45)
                if self.haze:
                    f.glow(x, y, r * 1.8, self.haze, 0.16 * k)
            elif kind == DUST:
                f.disc(x, y, q["size"] * (0.6 + (1 - k) * 0.9), col, (k ** 1.3) * 0.7)
            elif kind == SMOKE:
                age, big = 1 - k, q["flag"] & BIG
                r = q["size"] * (0.65 + min(1.0, age * 2.5) * 0.45 + age * (0.5 if big else 0.4))
                a = min(1.0, age * 12) * min(1.0, k * 2.4) * (0.7 if big else 0.58)
                c = mix(q["col"], ramp_at(SMOKE_RAMP, age), age) if q["col"] else ramp_at(SMOKE_RAMP, age * 1.05)
                f.disc(x, y, r, c, a * 0.45)
                f.disc(x + r * 0.05, y + r * 0.06, r * 0.74, c, a * 0.62)
                if age < 0.5:
                    f.disc(x - r * 0.22, y - r * 0.3, r * 0.5, mix(c, WHITE, 0.12), a * 0.4 * (1 - age * 2))
            elif kind == FIRE:
                age = 1 - k
                heat = min(0.999, age ** 0.62 + (q["seed"] % 1) * 0.1)
                F, n = FIRE_RAMP, len(FIRE_RAMP)
                idx = min(n - 2, int(heat * (n - 1)))
                r = q["size"] * (0.55 + 0.45 * min(1.0, age * 7)) * (1 - age * 0.55)
                c = F[idx]
                if idx >= n - 2:
                    f.disc(x, y, r, c, min(1.0, k * 3) * 0.85)
                else:
                    f.circle(x, y, r, F[min(n - 1, idx + 2)])
                    f.circle(x - r * 0.16, y - r * 0.22, r * 0.78, c)
                    if r > 1.6:
                        f.circle(x, y - r * 0.9, r * 0.42, c)
                    if idx <= 3 and r > 1.8:
                        f.circle(x - r * 0.28, y - r * 0.34, r * 0.36, F[max(0, idx - 1)])
                    if idx < 6:
                        f.glow(x, y, r * 2.4 + 2, c, 0.18 * k)
            elif kind == GRIT:
                if k > 0.125:
                    f.put(x, y, col)
                    if q["size"] >= 2:
                        f.put(x + 1, y, col)
                        f.put(x, y + 1, dim(col, 0.8))
            elif kind == EMBER:
                c = S[0] if k > 0.6 else S[1] if k > 0.3 else S[2]
                if k < 0.25 and math.sin(self.t * 40 + q["seed"]) < 0:
                    continue
                f.put(x, y, c)
                if q["size"] > 1.5:
                    f.put(x, y + 1, S[-1])
                f.glow(x, y, 3 + q["size"], c, 0.35 * k)
            else:  # STAR: a twinkling cross, arms set by size
                tw = 0.6 + 0.4 * math.sin(self.t * (8 + q["seed"] % 5) + q["seed"])
                if q["size"] < 1:
                    if tw * k > 0.25:
                        f.put(x, y, WHITE if tw > 0.8 else col)
                    f.glow(x, y, 3, col, 0.4 * k * tw)
                else:
                    sparkle(f, x, y, q["size"] * tw * min(1.0, k * 3), col, dim(col, 0.75), 0.5 * k * tw)


class Lights:
    """Lights that flare and die: add(x, y, r, color, k, life); update(dt); draw(frame)."""

    def __init__(self) -> None:
        self.list: list[list] = []

    def add(self, x: float, y: float, r: float, c: RGBA, k: float, life: float) -> None:
        self.list.append([x, y, r, c, k, life, life])

    def update(self, dt: float) -> None:
        for l in self.list:
            l[5] -= dt
        self.list = [l for l in self.list if l[5] > 0]

    def draw(self, f: Frame) -> None:
        for x, y, r, c, k, life, mx in self.list:
            q = life / mx
            f.glow(x, y, r * (0.55 + 0.45 * q), c, k * q * q)


def sparkle(f: Frame, x: float, y: float, arm: float, c: RGBA, tip: RGBA | None = None, k: float = 0.6) -> None:
    """A star glint: arms of length arm in colour c with tips in tip, a white heart, light."""
    n = int(round(arm))
    if n < 1:
        return
    tip = tip or c
    X, Y = math.floor(x), math.floor(y)
    for d in range(1, n + 1):
        cc = tip if d > n * 0.6 else c
        for dx, dy in CROSS:
            f.put(X + dx * d, Y + dy * d, cc)
    if n >= 3:
        for dx, dy in DIAG:
            f.put(X + dx, Y + dy, c)
    f.put(X, Y, WHITE)
    f.glow(x, y, 4 + n * 2, c, k)


def bolt(rng: random.Random, x0: float, y0: float, x1: float, y1: float, jag: float, steps: int) -> list[tuple[float, float]]:
    """A jagged path from (x0, y0) to (x1, y1): midpoints pushed sideways, less near the ends."""
    pts = [(x0, y0)]
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    for i in range(1, steps):
        u = i / steps
        off = rng.uniform(-jag, jag) * math.sin(math.pi * u)
        pts.append((x0 + dx * u + nx * off, y0 + dy * u + ny * off))
    pts.append((x1, y1))
    return pts


# --- rendering ---------------------------------------------------------------------------------------

def render(make: Callable[[random.Random], object], size: int, frames: int, fps: float, anchor: tuple[float, float],
           seed: int = 1) -> np.ndarray:
    """An effect object from make(rng) with update(dt) and draw(frame, t), rendered to a strip of square frames.
    The simulation steps at 120 Hz whatever the frame rate, so motion looks the same at any fps."""
    fx = make(random.Random(seed))
    out = np.zeros((size, size * frames, 4), np.uint8)
    t, step = 0.0, 1 / 120
    for i in range(frames):
        target = i / fps
        while t < target - 1e-9:
            fx.update(step)  # type: ignore[attr-defined]
            t += step
        f = Frame(size, size, *anchor)
        fx.draw(f, t)  # type: ignore[attr-defined]
        out[:, i * size:(i + 1) * size] = f.composite()
    return out
