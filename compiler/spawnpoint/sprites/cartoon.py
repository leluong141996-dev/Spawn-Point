"""Smooth cartoon sprites (the non-pixel art style). Deterministic, GPU-free.

Same kinds and animations as the pixel generator, drawn at 4x the pixel resolution with anti-aliasing
(4x supersampling on top), so they fill the same space in the game but look like vector art: a thick
"sticker" outline around the whole silhouette, gradient-shaded parts, a soft highlight, big eyes.
"""

from __future__ import annotations

import colorsys
import math
import random
import zlib
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .generate import KINDS, _hex, features_for
from .spriteset import SpriteSet, build_sheet, finalize

DETAIL = 4  # frame pixels per pixel-art pixel
SS = 4  # supersampling while drawing
SCALE = 0.5  # world px per frame px: the same on-screen size as the pixel sprites (2 / DETAIL)

RGB = tuple[int, int, int]


def _shade(color: str | RGB, k: float, hue: float = 0.0) -> RGB:
    """k > 1 lighter, k < 1 darker; a small hue drift keeps shadows lively (cool) and lights warm."""
    r, g, b = _hex(color) if isinstance(color, str) else (color[0] / 255, color[1] / 255, color[2] / 255)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if k >= 1:
        s, v = s * (1 - (k - 1) * 0.6), min(1.0, v * k + (k - 1) * 0.15)
    else:
        s, v = min(1.0, s * (1 + (1 - k) * 0.3)), v * k
    r, g, b = colorsys.hsv_to_rgb((h + hue) % 1, max(0.0, s), max(0.0, v))
    return round(r * 255), round(g * 255), round(b * 255)


@dataclass
class Palette:
    base: RGB
    light: RGB
    shadow: RGB
    outline: RGB
    accent: RGB  # a contrasting detail colour (cheeks, inner ears, gems)


def palette(color: str) -> Palette:
    base = _shade(color, 1.0)
    h = colorsys.rgb_to_hsv(*_hex(color))[0]
    ar, ag, ab = colorsys.hsv_to_rgb((h + 0.5) % 1, 0.45, 0.95)
    return Palette(base, _shade(color, 1.28, -0.02), _shade(color, 0.68, 0.03), _shade(color, 0.3, 0.05),
                   (round(ar * 255), round(ag * 255), round(ab * 255)))


EYE = (36, 30, 52)
WHITE = (255, 252, 246)
CHEEK = (255, 140, 160)


class Painter:
    """Draws parts in frame coordinates (the final sprite pixel grid) on a supersampled layer."""

    def __init__(self, w: int, h: int, pal: Palette):
        self.w, self.h, self.p = w, h, pal
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.detail = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))  # drawn on top, after the outline

    # -- primitives ----------------------------------------------------------------------------
    def _mask(self, fn) -> Image.Image:
        m = Image.new("L", self.img.size, 0)
        fn(ImageDraw.Draw(m))
        return m

    def _fill(self, mask: Image.Image, color: RGB, shade: bool, target: Image.Image | None = None) -> None:
        target = target or self.img
        box = mask.getbbox()
        if box is None:
            return
        if not shade:
            target.paste(Image.new("RGBA", target.size, (*color, 255)), (0, 0), mask)
            return
        light, dark = _shade(color, 1.22, -0.015), _shade(color, 0.72, 0.03)
        y0, y1 = box[1], box[3]
        grad = np.zeros((target.size[1], target.size[0], 4), np.uint8)
        t = np.clip((np.arange(target.size[1]) - y0) / max(1, y1 - y0), 0, 1)[:, None]
        # light at the top, the base in the middle, a darker belly: soft cel shading
        mid = np.array(color)
        top, bot = np.array(light), np.array(dark)
        col = np.where(t < 0.45, top + (mid - top) * (t / 0.45), mid + (bot - mid) * ((t - 0.45) / 0.55))
        grad[..., :3] = col[:, None, :].astype(np.uint8).repeat(target.size[0], axis=1)
        grad[..., 3] = 255
        target.paste(Image.fromarray(grad, "RGBA"), (0, 0), mask)

    def _box(self, x0, y0, x1, y1):
        return [x0 * SS, y0 * SS, x1 * SS, y1 * SS]

    def ellipse(self, cx, cy, rx, ry, color: RGB | None = None, shade=True, shine=False, top=False) -> None:
        color = color or self.p.base
        box = self._box(cx - rx, cy - ry, cx + rx, cy + ry)
        self._fill(self._mask(lambda d: d.ellipse(box, fill=255)), color, shade, self.detail if top else None)
        if shine:
            self.shine(cx - rx * 0.38, cy - ry * 0.42, rx * 0.32, ry * 0.22)

    def rrect(self, x0, y0, x1, y1, r, color: RGB | None = None, shade=True, top=False) -> None:
        color = color or self.p.base
        box = self._box(x0, y0, x1, y1)
        self._fill(self._mask(lambda d: d.rounded_rectangle(box, radius=r * SS, fill=255)), color, shade,
                   self.detail if top else None)

    def poly(self, pts, color: RGB | None = None, shade=True, top=False) -> None:
        color = color or self.p.base
        sp = [(x * SS, y * SS) for x, y in pts]
        self._fill(self._mask(lambda d: d.polygon(sp, fill=255)), color, shade, self.detail if top else None)

    def line(self, pts, width, color: RGB, top=True) -> None:
        d = ImageDraw.Draw(self.detail if top else self.img)
        d.line([(x * SS, y * SS) for x, y in pts], fill=(*color, 255), width=max(1, round(width * SS)), joint="curve")

    def shine(self, cx, cy, rx, ry, alpha=150) -> None:
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse(self._box(cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 255, 255, alpha))
        self.detail.alpha_composite(layer)

    def eyes(self, positions, r=3.2, hurt=False, look=(0.6, 0.2), lashes=False) -> None:
        d = ImageDraw.Draw(self.detail)
        for x, y in positions:
            if hurt:  # squeezed shut: two strokes
                for dy in (-1.0, 1.0):
                    d.line([((x - r) * SS, (y + dy * 0.6 - r * 0.3 * dy) * SS), ((x + r) * SS, (y + dy * 0.6) * SS)],
                           fill=(*EYE, 255), width=round(1.2 * SS))
                continue
            d.ellipse(self._box(x - r, y - r * 1.15, x + r, y + r * 1.15), fill=(*WHITE, 255))
            px, py = x + look[0] * r * 0.45, y + look[1] * r * 0.4
            d.ellipse(self._box(px - r * 0.62, py - r * 0.72, px + r * 0.62, py + r * 0.72), fill=(*EYE, 255))
            d.ellipse(self._box(px - r * 0.2 + r * 0.2, py - r * 0.45, px + r * 0.2 + r * 0.2, py - r * 0.05),
                      fill=(255, 255, 255, 255))
            if lashes:
                d.line([((x - r) * SS, (y - r) * SS), ((x - r * 1.5) * SS, (y - r * 1.5) * SS)], fill=(*EYE, 255),
                       width=round(0.8 * SS))

    def cheeks(self, positions, r=1.8) -> None:
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        for x, y in positions:
            ImageDraw.Draw(layer).ellipse(self._box(x - r, y - r * 0.6, x + r, y + r * 0.6), fill=(*CHEEK, 120))
        self.detail.alpha_composite(layer)

    # -- finishing -----------------------------------------------------------------------------
    def render(self, outline=1.6, flash=False) -> np.ndarray:
        """Sticker outline around the silhouette, details on top, then the anti-aliased downsample."""
        body = self.img
        a = body.getchannel("A")
        radius = max(1, round(outline * SS))
        grown = a.filter(ImageFilter.MaxFilter(radius * 2 + 1)) if radius > 0 else a
        out = Image.new("RGBA", body.size, (*self.p.outline, 0))
        out.putalpha(grown)
        out.alpha_composite(body)
        out.alpha_composite(self.detail)
        if flash:  # hurt: a white flash over everything
            white = Image.new("RGBA", out.size, (255, 255, 255, 0))
            white.putalpha(out.getchannel("A").point(lambda v: v * 0.55))
            out.alpha_composite(white)
        small = out.resize((self.w, self.h), Image.LANCZOS)
        return np.asarray(small).copy()


# --- painters ---------------------------------------------------------------------------------

@dataclass
class Pose:
    anim: str
    i: int
    feats: list[str]
    rng: random.Random
    extra: dict


def _bob(p: Pose) -> float:
    return {"idle": (0, 1.2)[p.i % 2], "run": (0, 1.6, 0, 1.6)[p.i % 4]}.get(p.anim, 0.0)


def draw_hero(P: Painter, p: Pose) -> None:
    f, c = p.feats, P.p
    b = _bob(p)
    hurt = p.anim == "hurt"
    # legs
    step = {"run": (-3, 2, 3, -2)[p.i % 4], "jump": 0, "fall": 2}.get(p.anim, 0)
    leg_len = 7 if p.anim != "jump" else 5
    for lx, sx in ((19, -step), (29, step)):
        P.rrect(lx - 3 + sx * 0.4, 50 + b * 0.3, lx + 3 + sx * 0.4, 50 + leg_len + 6, 3, c.shadow)
    if "tail" in f:
        wag = (0, 2)[p.i % 2] if p.anim in ("idle", "run") else 0
        P.ellipse(9, 42 + b + wag, 6, 3.5, c.base)
        P.ellipse(4.5, 39 + b + wag, 3, 3, c.light, shade=False)
    if "wings" in f:
        flap = (0, -4)[p.i % 2]
        P.poly([(14, 34 + b), (0, 24 + b + flap), (6, 40 + b)], c.light)
    if "hair" in f:
        P.rrect(8, 14 + b, 22, 46 + b, 6, (112, 66, 42))
    # body
    P.rrect(13, 32 + b, 35, 54 + b, 8, c.base)
    P.ellipse(24, 46 + b, 7, 5, c.light, shade=False)  # tummy
    arm_y = 30 + b if p.anim in ("jump", "fall") else 38 + b
    P.ellipse(11, arm_y, 3.6, 5.5, c.base)
    P.ellipse(37, arm_y, 3.6, 5.5, c.base)
    # head
    hy = 20 + b
    P.ellipse(24, hy, 15, 14, c.base, shine=True)
    if "ears" in f:
        for ex, d in ((12, -1), (36, 1)):
            P.poly([(ex - 4 * d, hy - 6), (ex + 2 * d, hy - 20), (ex + 7 * d, hy - 9)], c.base)
            P.poly([(ex - 1 * d, hy - 8), (ex + 2 * d, hy - 16), (ex + 4.5 * d, hy - 9)], c.accent, shade=False, top=True)
    if "long_ears" in f:
        for ex in (17, 31):
            P.ellipse(ex, hy - 18, 3.5, 10, c.base)
            P.ellipse(ex, hy - 18, 1.6, 7, c.accent, shade=False, top=True)
    if "horns" in f:
        for ex, d in ((14, -1), (34, 1)):
            P.poly([(ex, hy - 9), (ex + 4 * d, hy - 19), (ex + 6 * d, hy - 8)], WHITE)
    if "crest" in f:
        for i, x in enumerate((15, 21, 27)):
            P.poly([(x - 3, hy - 11 + i), (x, hy - 19 + i), (x + 3, hy - 11 + i)], c.accent)
    if "antenna" in f:
        P.line([(24, hy - 13), (24, hy - 21)], 1.2, c.outline)
        P.ellipse(24, hy - 22, 2.4, 2.4, c.accent, shade=False, top=True)
    if "helmet" in f:
        P.ellipse(24, hy - 4, 16, 11, (190, 198, 212), top=True)
        P.rrect(8, hy - 2, 40, hy + 1, 1.5, (150, 158, 176), shade=False, top=True)
    if "hat" in f:
        P.ellipse(24, hy - 9, 20, 4, (166, 110, 58), top=True)
        P.poly([(12, hy - 10), (24, hy - 30), (36, hy - 10)], (196, 140, 70), top=True)
    if "hair" in f:
        P.ellipse(24, hy - 9, 15, 7, (112, 66, 42), top=True)
    eyes = [(19, hy + 1), (30, hy + 1)]
    if "mask" in f:
        P.rrect(8, hy - 4, 40, hy + 5, 3, c.outline, shade=False, top=True)
        P.eyes(eyes, r=2.6, hurt=hurt)
        P.line([(8, hy), (3, hy + 4), (5, hy + 9)], 1.5, c.outline)  # the knot's tail
    else:
        P.eyes(eyes, r=3.4, hurt=hurt, lashes="hair" in f)
        P.cheeks([(15, hy + 6), (34, hy + 6)])
        if "beak" in f:
            P.poly([(26, hy + 4), (34, hy + 7), (26, hy + 10)], (255, 190, 60), top=True)
        else:
            P.line([(23, hy + 8), (25, hy + 9), (27, hy + 8)], 0.9, c.outline)


def draw_blob(P: Painter, p: Pose) -> None:
    """Slimes, bugs and other round critters."""
    f, c = p.feats, P.p
    sq = {"idle": ((0, 0), (2, -2))[p.i % 2], "run": ((0, 0), (3, -3), (0, 0), (-2, 2))[p.i % 4],
          "jump": (-5, 6), "fall": (-2, 3), "hurt": (5, -5)}.get(p.anim, (0, 0))
    w, h = P.w, P.h
    rx, ry = w / 2 - 3 + sq[0] * 0.6, h * 0.5 - 2 + sq[1] * 0.6
    cy = h - 2 - ry
    if "legs" in f:
        for i in range(3):
            lx = w / 2 - 12 + i * 12
            P.line([(lx, cy + ry * 0.4), (lx - 3, h - 1)], 1.6, c.shadow, top=False)
    P.ellipse(w / 2, cy, rx, ry, c.base, shine=True)
    if "spots" in f:
        for _ in range(3):
            P.ellipse(w / 2 + p.rng.uniform(-rx * 0.6, rx * 0.6), cy + p.rng.uniform(-ry * 0.1, ry * 0.5),
                      2.2, 1.8, c.shadow, shade=False, top=True)
    if "horns" in f:
        P.poly([(w / 2 - 9, cy - ry + 3), (w / 2 - 6, cy - ry - 6), (w / 2 - 3, cy - ry + 2)], WHITE)
        P.poly([(w / 2 + 3, cy - ry + 2), (w / 2 + 6, cy - ry - 6), (w / 2 + 9, cy - ry + 3)], WHITE)
    if "antenna" in f:
        P.line([(w / 2, cy - ry + 1), (w / 2 + 2, cy - ry - 7)], 1.2, c.outline)
        P.ellipse(w / 2 + 2, cy - ry - 8, 2.2, 2.2, c.accent, shade=False, top=True)
    one = p.extra.get("one_eye")
    eyes = [(w / 2 + 5, cy - ry * 0.15)] if one else [(w / 2 - 1, cy - ry * 0.15), (w / 2 + 9, cy - ry * 0.15)]
    P.eyes(eyes, r=4.2 if one else 3.4, hurt=p.anim == "hurt")
    P.line([(w / 2 + 1, cy + ry * 0.35), (w / 2 + 4, cy + ry * 0.48), (w / 2 + 7, cy + ry * 0.35)], 1.0, c.outline)


def draw_flyer(P: Painter, p: Pose) -> None:
    f, c = p.feats, P.p
    w, h = P.w, P.h
    flap = (-7, -2, 4, -2)[p.i % 4] if p.anim != "hurt" else 0
    cx, cy = w / 2, h / 2 + 2
    for d in (-1, 1):
        P.poly([(cx + 4 * d, cy - 2), (cx + 26 * d, cy - 8 + flap), (cx + 22 * d, cy + 6 + flap * 0.4),
                (cx + 6 * d, cy + 6)], c.shadow if "wings" in f else c.light)
    P.ellipse(cx, cy, 11, 10, c.base, shine=True)
    if "beak" in f:
        P.poly([(cx + 7, cy), (cx + 16, cy + 3), (cx + 7, cy + 6)], (255, 190, 60), top=True)
    P.eyes([(cx - 2, cy - 2), (cx + 6, cy - 2)], r=3.0, hurt=p.anim == "hurt")


def draw_robot(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    b = _bob(p)
    P.rrect(10, 22 + b, w - 10, h - 6, 4, c.base)
    for x in (16, w - 16):  # wheels
        P.ellipse(x, h - 6, 5, 5, (70, 74, 90))
    P.rrect(13, 6 + b, w - 13, 22 + b, 5, c.light)
    P.line([(w / 2, 6 + b), (w / 2, 1 + b)], 1.3, c.outline)
    P.ellipse(w / 2, 1 + b, 2, 2, c.accent, shade=False, top=True)
    P.rrect(16, 11 + b, w - 16, 18 + b, 3, (40, 44, 66), shade=False, top=True)  # visor
    glow = (255, 90, 90) if p.anim == "hurt" else (120, 240, 255)
    P.ellipse(w / 2 + 3, 14.5 + b, 2.4, 2.4, glow, shade=False, top=True)


def draw_turret(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    P.rrect(8, h - 16, w - 8, h - 2, 4, (110, 116, 132))
    P.ellipse(w / 2, h - 18, 15, 13, c.base, shine=True)
    recoil = (0, -2)[p.i % 2]
    P.rrect(w / 2 + 4 + recoil, h - 22, w - 2 + recoil, h - 15, 3, c.shadow)
    P.eyes([(w / 2 - 3, h - 20)], r=3.4, hurt=p.anim == "hurt")


def draw_coin(P: Painter, p: Pose) -> None:
    w, h = P.w, P.h
    squeeze = abs(math.cos(p.i / 6 * math.pi))
    rx = max(2.0, (w / 2 - 3) * squeeze)
    P.ellipse(w / 2, h / 2, rx, h / 2 - 3, (255, 205, 60), shine=squeeze > 0.4)
    if squeeze > 0.5:
        P.ellipse(w / 2, h / 2, rx * 0.6, h / 2 - 7, (255, 228, 120), shade=False, top=True)


def _star(cx, cy, ro, ri, rot=0.0):
    return [(cx + (ro if i % 2 == 0 else ri) * math.sin(i * math.pi / 5 + rot),
             cy - (ro if i % 2 == 0 else ri) * math.cos(i * math.pi / 5 + rot)) for i in range(10)]


def draw_star(P: Painter, p: Pose) -> None:
    w, h = P.w, P.h
    P.poly(_star(w / 2, h / 2 + 1, w / 2 - 3, w / 4 - 1, (p.i - 1.5) * 0.06), (255, 220, 70))
    P.eyes([(w / 2 - 3, h / 2 + 1), (w / 2 + 4, h / 2 + 1)], r=1.8)


def draw_gem(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    P.poly([(w / 2, 3), (w - 4, h * 0.38), (w / 2, h - 3), (4, h * 0.38)], c.base)
    P.poly([(w / 2, 3), (w - 4, h * 0.38), (w / 2, h * 0.45)], c.light, shade=False, top=True)
    if p.i % 4 == 0:
        P.shine(w / 2 - 3, h * 0.3, 2.2, 2.2, 230)


def draw_heart(P: Painter, p: Pose) -> None:
    w, h = P.w, P.h
    k = (1.0, 0.92)[p.i % 2]
    cx, cy, s = w / 2, h / 2 + 1, (w / 2 - 3) * k
    pts = [(cx + s * 16 * math.sin(t) ** 3 / 16, cy - s * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t)
            - math.cos(4 * t)) / 16) for t in np.linspace(0, 2 * math.pi, 40)]
    P.poly(pts, (255, 80, 120))
    P.shine(cx - s * 0.45, cy - s * 0.45, s * 0.25, s * 0.18, 200)


def draw_orb(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    P.ellipse(w / 2, h / 2, w / 2 - 3 - (p.i % 2), h / 2 - 3 - (p.i % 2), c.base, shine=True)


def draw_door(P: Painter, p: Pose) -> None:
    w, h = P.w, P.h
    P.rrect(2, 2, w - 2, h - 1, 6, (150, 96, 58))
    for y in range(12, h - 8, 26):
        P.rrect(6, y, w - 6, y + 18, 3, (176, 118, 72), top=True)
    P.ellipse(w - 9, h / 2, 2.2, 2.2, (255, 214, 90), shade=False, top=True)


def draw_exit(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    P.rrect(4, 4, w - 4, h - 1, w / 2 - 4, c.shadow)
    glow = 0.65 + 0.15 * (p.i % 3)
    P.rrect(9, 10, w - 9, h - 4, w / 2 - 9, _shade(c.light if isinstance(c.light, tuple) else c.base, glow + 0.4),
            shade=False, top=True)


def draw_portal(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    for k, col in ((1.0, c.shadow), (0.72, c.base), (0.44, c.light)):
        r = (w / 2 - 3) * k * (1 + 0.05 * math.sin(p.i * 1.6 + k * 4))
        P.ellipse(w / 2, h / 2, r, r, col, shade=False)


def draw_spikes(P: Painter, p: Pose) -> None:
    w, h = P.w, P.h
    n = 3
    for i in range(n):
        x0 = 2 + i * (w - 4) / n
        P.poly([(x0, h - 1), (x0 + (w - 4) / n / 2, 3), (x0 + (w - 4) / n, h - 1)], (200, 206, 220))


def draw_bullet(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    P.ellipse(w / 2, h / 2, w / 2 - 1.5, h / 2 - 1.5, c.light, shade=False)
    P.ellipse(w / 2, h / 2, w / 4, h / 4, (255, 255, 255), shade=False, top=True)


def draw_slash(P: Painter, p: Pose) -> None:
    c = P.p
    w, h = P.w, P.h
    cx, cy = w * 0.1, h / 2
    pts_out, pts_in = [], []
    for k in range(25):  # an outer arc and a thinner inner arc make a crescent
        a = -1.25 + 2.5 * k / 24
        pts_out.append((cx + math.cos(a) * w * 0.8, cy + math.sin(a) * h * 0.46))
        t = 1 - abs(k - 12) / 12  # thick in the middle, sharp at the tips
        thick = (0.42 - 0.09 * p.i) * t
        pts_in.append((cx + math.cos(a) * w * (0.8 - thick), cy + math.sin(a) * h * (0.46 - thick * 0.35)))
    P.poly(pts_out + pts_in[::-1], _shade(c.base, 1.5), shade=False)
    P.line([(cx + math.cos(a) * w * 0.76, cy + math.sin(a) * h * 0.44)
            for a in [-1.0 + 2.0 * k / 16 for k in range(17)]], 1.4, (255, 255, 255))


PAINTERS = {"hero": draw_hero, "slime": draw_blob, "hopper": draw_blob, "bug": draw_blob, "flyer": draw_flyer,
            "robot": draw_robot, "turret": draw_turret, "coin": draw_coin, "star": draw_star, "gem": draw_gem,
            "heart": draw_heart, "orb": draw_orb, "door": draw_door, "exit": draw_exit, "portal": draw_portal,
            "spikes": draw_spikes, "bullet": draw_bullet,
            "slash": draw_slash}
OUTLINE = {"bullet": 0.8, "slash": 0.8, "coin": 1.0, "gem": 1.0, "star": 1.1, "heart": 1.1, "spikes": 1.0, "orb": 1.0}


def generate_cartoon(name: str, kind: str, color: str, features: list[str] | None = None, seed: int = 0) -> SpriteSet:
    if kind not in KINDS:
        raise ValueError(f"unknown sprite kind '{kind}'")
    spec = KINDS[kind]
    feats = list(features) if features is not None else features_for(name)
    rng_seed = zlib.crc32(f"{name}:{kind}:{seed}".encode())
    extra = {"one_eye": random.Random(rng_seed).random() < 0.3}
    if kind == "slime" and random.Random(rng_seed + 1).random() < 0.5 and "spots" not in feats:
        feats.append("spots")
    if kind == "bug" and "legs" not in feats:
        feats.append("legs")
    pal = palette(color)
    size = (spec.size[0] * DETAIL, spec.size[1] * DETAIL)
    frames: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in spec.anims.items():
        frames[anim] = []
        for i in range(n):
            P = Painter(*size, pal)
            PAINTERS[kind](P, Pose(anim, i, feats, random.Random(rng_seed), extra))
            frames[anim].append(P.render(OUTLINE.get(kind, 1.6), flash=anim == "hurt"))
    sheet, anims = build_sheet(frames, {a: v[1] for a, v in spec.anims.items()},
                               {a: v[2] for a, v in spec.anims.items()})
    s = finalize(name, sheet, size, anims, SCALE, spec.anchor)
    s.smooth = True
    return s
