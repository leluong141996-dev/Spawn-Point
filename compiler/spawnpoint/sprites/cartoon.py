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

from . import chibi, creatures, motion
from .generate import KINDS, _hex, add_derived, body_color, features_for, held_weapon
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
# accessory colours (the same hues as the pixel style's accents)
CAPE = (176, 38, 56)
CROWN = (255, 204, 64)
JEWEL = (222, 58, 84)
WOOD = (150, 96, 52)
STEEL = (196, 204, 218)
MAGIC = (110, 214, 255)
STRING = (232, 228, 214)


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
    b = (0, 0.5, 1.2, 1.2, 0.5, 0)[p.i % 6] if p.anim == "idle" else _bob(p)  # a slow breath over six frames
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
    if "cape" in f:  # behind the back, flaring out when running
        flare = (0, 4, 0, 4)[p.i % 4] if p.anim == "run" else 0
        P.poly([(12, 33 + b), (24, 33 + b), (18, 62), (2 - flare, 60)], CAPE)
    # body (ogres and trolls are wider)
    bulky = "bulky" in f
    bx0, bx1, ax0, ax1 = (9, 39, 7, 41) if bulky else (13, 35, 11, 37)
    P.rrect(bx0, 32 + b, bx1, 54 + b, 8, c.base)
    P.ellipse(24, 46 + b, 7, 5, c.light, shade=False)  # tummy
    arm_y = 30 + b if p.anim in ("jump", "fall") else 38 + b
    P.ellipse(ax0, arm_y, 3.6, 5.5, c.base)
    if "zombie" in f and p.anim in ("idle", "run"):  # arms reach forward
        P.ellipse(ax1 + 3, arm_y - 2, 7, 3.4, c.base)
    else:
        P.ellipse(ax1, arm_y, 3.6, 5.5, c.base)
    if "skull" in f:  # ribs under bone-white skin
        for k in range(3):
            P.line([(19, 37 + k * 5 + b), (29, 37 + k * 5 + b)], 1.4, c.shadow)
    if "zombie" in f:  # torn hem
        P.poly([(bx0 + 2, 54 + b), (bx0 + 6, 49 + b), (bx0 + 9, 54 + b)], c.shadow, shade=False, top=True)
    if "shield" in f:
        P.rrect(1, 33 + b, 17, 53 + b, 5, STEEL)
        P.rrect(3, 35 + b, 15, 51 + b, 4, WOOD)
        P.ellipse(9, 43 + b, 2.6, 2.6, STEEL, shade=False, top=True)
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
    if "hood" in f:  # cloth over the head and down the back, the face peeking out
        P.ellipse(22, hy - 5, 17, 12, c.shadow, top=True)
        P.rrect(6, hy - 4, 18, hy + 14, 5, c.shadow, top=True)
        P.ellipse(27, hy + 3, 10, 8.5, c.base, top=True)
    if "crown" in f:
        P.poly([(13, hy - 9), (13, hy - 20), (18.5, hy - 14), (24, hy - 23), (29.5, hy - 14), (35, hy - 20), (35, hy - 9)],
               CROWN, top=True)
        P.ellipse(24, hy - 12.5, 2.2, 2.2, JEWEL, shade=False, top=True)
    eyes = [(19, hy + 1), (30, hy + 1)]
    if "skull" in f:  # empty sockets, a nose hole and a row of teeth
        for ex, ey in eyes:
            P.ellipse(ex, ey, 3.8, 4.2, EYE, shade=False, top=True)
        P.poly([(24, hy + 5), (22.5, hy + 8), (25.5, hy + 8)], EYE, shade=False, top=True)
        P.line([(19, hy + 10.5), (30, hy + 10.5)], 1.0, c.shadow)
        for x in (21.5, 24.5, 27.5):
            P.line([(x, hy + 9.5), (x, hy + 11.5)], 0.8, c.shadow)
    elif "mask" in f:
        P.rrect(8, hy - 4, 40, hy + 5, 3, c.outline, shade=False, top=True)
        P.eyes(eyes, r=2.6, hurt=hurt)
        P.line([(8, hy), (3, hy + 4), (5, hy + 9)], 1.5, c.outline)  # the knot's tail
    else:
        P.eyes(eyes, r=3.4, hurt=hurt, lashes="hair" in f)
        if "zombie" not in f:  # no rosy cheeks on the undead
            P.cheeks([(15, hy + 6), (34, hy + 6)])
        if "beak" in f:
            P.poly([(26, hy + 4), (34, hy + 7), (26, hy + 10)], (255, 190, 60), top=True)
        else:
            P.line([(23, hy + 8), (25, hy + 9), (27, hy + 8)], 0.9, c.outline)
    if "beard" in f:
        P.poly([(18, hy + 5), (36, hy + 4), (34, hy + 15), (28, hy + 21), (21, hy + 15)], (112, 66, 42), top=True)
    if "tusks" in f:
        for x in (25, 32):
            P.poly([(x - 1.6, hy + 9), (x, hy + 4.5), (x + 1.6, hy + 9)], WHITE, shade=False, top=True)
    weapon = held_weapon(f)
    if weapon == "sword":  # held upright beside the body
        P.rrect(41, 14 + b, 45, 40 + b, 1.5, (214, 220, 232), top=True)
        P.rrect(38, 39 + b, 48, 42 + b, 1.2, (160, 104, 56), shade=False, top=True)
        P.rrect(41, 41 + b, 45, 47 + b, 1.2, (120, 76, 44), shade=False, top=True)
    elif weapon == "bow":
        P.line([(42, 13 + b), (46, 22 + b), (46.5, 30 + b), (46, 38 + b), (42, 47 + b)], 2.2, WOOD)
        P.line([(42, 13 + b), (42, 47 + b)], 0.7, STRING)
    elif weapon == "staff":
        P.rrect(41, 10 + b, 44, 62, 1.5, WOOD, top=True)
        P.ellipse(42.5, 7 + b, 4.6, 4.6, MAGIC, shine=True, top=True)
    elif weapon == "spear":
        P.rrect(42, 9 + b, 44.5, 60, 1.0, WOOD, top=True)
        P.poly([(40, 10 + b), (43.25, -1 + b), (46.5, 10 + b)], STEEL, top=True)
    elif weapon == "axe":
        P.rrect(41, 16 + b, 44, 49 + b, 1.5, WOOD, top=True)
        P.poly([(43, 15 + b), (48, 11 + b), (48, 29 + b), (43, 25 + b)], STEEL, top=True)


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


def draw_ship(P: Painter, p: Pose) -> None:
    c = P.p
    P.poly([(12, 13), (40, 12), (22, 1.5)], c.shadow)  # wings
    P.poly([(12, 27), (40, 28), (22, 38.5)], c.shadow)
    P.poly([(10, 14), (46, 9), (62, 20), (46, 31), (10, 26)], c.base)
    P.line([(16, 20), (50, 20)], 1.4, c.light)
    P.ellipse(40, 17, 7, 5, (190, 228, 252), shine=True)
    tip = 4 - 3 * (p.i % 2)  # the flame flickers
    P.poly([(10, 16), (tip, 20), (10, 24)], (255, 176, 60), shade=False, top=True)
    P.poly([(10, 18), (tip + 4, 20), (10, 22)], (255, 236, 150), shade=False, top=True)


def draw_ufo(P: Painter, p: Pose) -> None:
    c = P.p
    P.ellipse(28, 26, 26, 9, c.base)
    P.ellipse(28, 32, 13, 3, c.shadow)
    P.ellipse(28, 16, 12, 11, (190, 228, 252), shine=True)
    for k, x in enumerate((9, 19, 37, 47)):
        P.ellipse(x, 27, 2.3, 2.3, (255, 236, 120) if (k + p.i) % 2 == 0 else c.shadow, shade=False, top=True)


def _hexrgb(h: str) -> RGB:
    r, g, b = _hex(h)
    return round(r * 255), round(g * 255), round(b * 255)


# --- chibi creatures (twins of creatures.py; frame coordinates are twice the fine pixel art's) --

def draw_beast(P: Painter, p: Pose) -> None:
    f, c = set(p.feats), P.p
    belly, dark = _shade(c.base, 1.35), _shade(c.base, 0.6)
    bear = "round_ears" in f
    k = p.i % 4
    b = {"idle": (0, 1.6)[p.i % 2], "run": (0, 2, 0, 2)[k]}.get(p.anim, 0)
    if "bushy_tail" in f:
        P.ellipse(10, 18 + b, 9, 7, c.base)
        P.ellipse(5, 14 + b, 5, 4.4, belly, shade=False)
    elif "thin_tail" in f:
        P.line([(14, 22 + b), (6, 12 + b), (4, 6 + b)], 2.2, c.base, top=False)
    elif not bear:
        P.line([(14, 22 + b), (6, 16 + b)], 4, c.shadow, top=False)
    swing = ((-4, 4), (0, 0), (4, -4), (0, 0))[k] if p.anim == "run" else {"jump": (-4, 4), "fall": (4, -4)}.get(p.anim, (0, 0))
    for x, d, col in ((20, swing[1], c.shadow), (40, swing[0], c.shadow), (16, swing[0], c.base), (36, swing[1], c.base)):
        P.rrect(x - 3 + d * 0.5, 30 + b, x + 3 + d * 0.5, 44, 3, col)
        P.ellipse(x + d, 45, 5, 2.6, dark)
    P.ellipse(28, 26 + b, 19, 13 if bear else 11, c.base)
    P.ellipse(28, 32 + b, 13, 4.4, belly, shade=False)
    if "stripes" in f:
        for sx in (18, 26, 34):
            P.line([(sx, 17 + b), (sx + 2, 27 + b)], 2, dark)
    if "mane" in f:
        P.ellipse(46, 18 + b, 14, 14, _hexrgb(creatures.MANE))
    hx, hy = 48, 16 + b
    P.ellipse(hx, hy, 12, 11, c.base, shine=True)
    if bear:
        for ex, col in ((hx - 8, c.base), (hx + 2, c.shadow)):
            P.ellipse(ex, hy - 10, 4.4, 4.4, col)
        P.ellipse(hx + 8, hy + 4, 5.2, 4.4, belly, shade=False, top=True)
        P.ellipse(hx + 12, hy + 2, 1.8, 1.5, EYE, shade=False, top=True)
    else:
        if "floppy_ears" in f:
            P.ellipse(hx - 8, hy - 2, 4, 7, dark)
        else:
            P.poly([(hx - 12, hy - 6), (hx - 9, hy - 18), (hx - 3, hy - 8)], c.base)
            P.poly([(hx - 2, hy - 8), (hx + 2, hy - 19), (hx + 7, hy - 7)], c.shadow)
        P.ellipse(hx + 10, hy + 4, 6.4, 4.8, belly, shade=False, top=True)
        P.ellipse(hx + 15, hy + 1.5, 2.2, 1.7, EYE, shade=False, top=True)
    if "tusks" in f:
        for x in (hx + 10, hx + 14):
            P.poly([(x - 1.4, hy + 8), (x, hy + 12), (x + 1.4, hy + 8)], WHITE, shade=False, top=True)
    P.eyes([(hx + 3, hy - 1)], r=2.8, hurt=p.anim == "hurt")


def draw_spider(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    b = {"idle": (0, 1.6)[p.i % 2], "run": (0, 2, 0, 2)[k]}.get(p.anim, 0)
    legs = [((22, 16), (12, 4), (2, 38)), ((22, 20), (12, 12), (10, 42)), ((24, 26), (16, 20), (18, 42)),
            ((26, 30), (22, 30), (24, 42))]
    for n, (hip, knee, foot) in enumerate(legs):
        for side in (-1, 1):
            lift = 4 if p.anim == "run" and (n + (side > 0) + k) % 2 else (4 if p.anim == "jump" else 0)
            mx = (lambda x: x) if side < 0 else (lambda x: 64 - x)  # noqa: E731
            P.line([(mx(hip[0]), hip[1] + b), (mx(knee[0]), knee[1] + b - lift / 2), (mx(foot[0]), foot[1] - lift)],
                   2.2, c.shadow if side < 0 else _shade(c.base, 0.55), top=False)
    P.ellipse(32, 16 + b, 13, 11, c.base, shine=True)
    P.ellipse(32, 27 + b, 10, 8, c.base)
    for x in (27, 37):
        P.ellipse(x, 16 + b, 2.2, 1.6, _shade(c.base, 1.4), shade=False, top=True)
    P.eyes([(27.5, 25 + b), (36.5, 25 + b)], r=3.2, hurt=p.anim == "hurt")
    for x in (30, 34):
        P.poly([(x - 1.3, 33 + b), (x, 37 + b), (x + 1.3, 33 + b)], WHITE, shade=False, top=True)


def draw_dragon(P: Painter, p: Pose) -> None:
    c = P.p
    belly = _shade(c.base, 1.35)
    k = p.i % 4
    flap = (0, 1, 2, 1)[k] if p.anim in ("idle", "run") else 1
    b = (0, 2, 2, 0)[k] if p.anim in ("idle", "run") else 0
    wy = (-8, 0, 6)[flap]
    horn = _hexrgb(creatures.HORN)
    P.poly([(30, 26 + b), (14, 4 + wy + b), (8, 20 + wy + b), (22, 30 + b)], _shade(c.base, 0.62))
    P.line([(24, 40 + b), (10, 44 + b), (4, 36 + b)], 5, c.base, top=False)
    P.poly([(0, 32 + b), (6, 28 + b), (6, 38 + b)], horn)
    P.ellipse(32, 36 + b, 14, 12, c.base)
    for y in (32, 36, 40):
        P.rrect(28, y + b, 40, y + 2 + b, 1, belly, shade=False, top=True)
    for x in (26, 38):
        P.rrect(x - 3, 44 + b, x + 3, 52, 2.5, c.shadow)
    P.poly([(34, 26 + b), (24, 2 + wy + b), (16, 18 + wy + b), (28, 30 + b)], c.base)
    hx, hy = 50, 20 + b
    P.ellipse(hx, hy, 14, 12, c.base, shine=True)
    P.ellipse(hx + 12, hy + 4, 8, 6, c.base)
    P.rrect(hx + 6, hy + 6, hx + 19, hy + 9, 1.5, belly, shade=False, top=True)
    for x in (hx - 8, hx - 2):
        P.poly([(x - 2, hy - 9), (x, hy - 19), (x + 2.5, hy - 10)], horn)
    P.ellipse(hx + 16, hy + 2, 1.4, 1.2, EYE, shade=False, top=True)
    P.eyes([(hx + 2, hy - 1)], r=3.2, hurt=p.anim == "hurt")


def draw_ghost(P: Painter, p: Pose) -> None:
    c = P.p
    k = p.i % 4
    b = (0, 2, 4, 2)[k] if p.anim in ("idle", "run") else 0
    P.ellipse(24, 20 + b, 18, 18, c.base, shine=True)
    P.rrect(6, 20 + b, 42, 44 + b, 4, c.base)
    for n in range(4):
        x = 10 + n * 9.5 + (2 if k % 2 else 0)
        P.ellipse(x, 45 + b, 5.2, 4.6, c.base)
    arm = (0, -2)[k % 2]
    P.ellipse(4, 28 + b + arm, 4, 3.2, c.base)
    P.ellipse(44, 26 + b - arm, 4, 3.2, c.shadow)
    if p.anim == "hurt":
        P.eyes([(17, 20 + b), (31, 20 + b)], r=3.4, hurt=True)
    else:
        for x in (17, 31):
            P.ellipse(x, 20 + b, 3, 4.6, EYE, shade=False, top=True)
            P.ellipse(x - 1, 18 + b, 1.1, 1.4, WHITE, shade=False, top=True)
        P.ellipse(24, 29 + b, 2.2, 2.8, EYE, shade=False, top=True)


def draw_snake(P: Painter, p: Pose) -> None:
    c = P.p
    belly = _shade(c.base, 1.35)
    k = p.i % 4
    wave = (0, 2, 0, -2)[k] if p.anim == "run" else 0
    lift = {"jump": -4}.get(p.anim, 0)
    pts = [(4, 24 + lift), (12, 20 + wave + lift), (22, 24 + lift), (32, 26 - wave + lift), (42, 24 + lift)]
    P.line(pts, 8, c.base, top=False)
    P.line([(x, y + 4) for x, y in pts], 2.2, belly)
    P.line([(42, 24 + lift), (48, 12 + lift)], 8, c.base, top=False)
    P.ellipse(52, 10 + lift, 10, 8, c.base, shine=True)
    P.rrect(54, 13 + lift, 61, 15 + lift, 1, belly, shade=False, top=True)
    P.eyes([(53, 7 + lift)], r=2.8, hurt=p.anim == "hurt")
    if p.i % 2 == 0:
        P.line([(61, 12 + lift), (64, 12 + lift), (66, 10 + lift)], 1.0, _hexrgb(creatures.TONGUE))


def draw_human(P: Painter, p: Pose) -> None:
    """The front-facing chibi person (the cartoon twin of chibi.py): big head, dot eyes, skin/hair/clothes."""
    f = set(p.feats)
    col: chibi.Colors = p.extra["colors"]
    weapon = p.extra["weapon"]
    q = chibi.pose_for(p.anim, p.i, weapon)
    skin, hair, shirt, pants = (_hexrgb(c) for c in (col.skin, col.hair, col.shirt, col.pants))
    shoes, leather, steel = _hexrgb(chibi.SHOES), _hexrgb(chibi.LEATHER), STEEL
    b, lx = q.bob * 1.6, q.lean * 2
    robe, bulky = bool(f & {"robe", "dress"}), "bulky" in f
    covered = f & {"helmet", "hood", "mask"}
    if "cape" in f:
        flare = 3 if q.lift_l or q.lift_r else 0
        P.poly([(10, 38 + b), (38, 38 + b), (42 + flare, 60), (6 - flare, 60)], CAPE)
    if col.hair_style == "long" and not covered and "skull" not in f:
        P.rrect(9 + lx, 18 + b, 39 + lx, 50 + b, 8, hair)
    if "skull" in f:
        bone = skin
        for x, lift in ((19, q.lift_l), (29, q.lift_r)):
            P.line([(x, 52), (x, 59 - lift * 3)], 2.6, bone, top=False)
            P.ellipse(x, 61 - lift * 3, 4.5, 2.6, bone)
        P.line([(24 + lx, 38 + b), (24 + lx, 52 + b)], 3.0, bone, top=False)
        for k in range(3):
            P.rrect(15 + lx, 39 + k * 4 + b, 33 + lx, 41 + k * 4 + b, 1.2, bone)
        P.ellipse(24 + lx, 52 + b, 7, 3, bone)
    else:
        # legs and shoes
        if robe:
            for x, lift in ((19, q.lift_l), (29, q.lift_r)):
                P.ellipse(x, 61 - lift * 3, 5, 3, shoes)
        else:
            lw = 5 if bulky else 4
            for x, lift, sh in ((19, q.lift_l, 0), (29, q.lift_r, 1)):
                P.rrect(x - lw, 50, x + lw, 59 - lift * 3, 3, _shade(pants, 0.85) if sh else pants)
                P.ellipse(x + (1 if sh else -1), 60.5 - lift * 3, lw + 2, 3.5, shoes)
        # torso
        x0, x1 = (11, 37) if bulky else (15, 33)
        x0, x1 = x0 + lx, x1 + lx
        if robe:
            P.poly([(x0, 37 + b), (x1, 37 + b), (x1 + 5, 61), (x0 - 5, 61)], shirt)
            if "dress" in f:
                P.rrect(x0, 37 + b, x1, 41 + b, 3, _shade(shirt, 1.2), shade=False)
            else:
                P.line([(x0, 47 + b), (x1, 47 + b)], 1.6, CROWN)
        else:
            P.rrect(x0, 37 + b, x1, 53 + b, 6, shirt)
            if "armor" in f:
                P.rrect(x0, 37 + b, x1, 47 + b, 5, steel)
                P.rrect(21 + lx, 42 + b, 27 + lx, 53 + b, 2, shirt)
            P.rrect(x0, 49 + b, x1, 52 + b, 1.2, leather, shade=False)
            P.rrect(23 + lx, 49 + b, 26 + lx, 52 + b, 0.8, CROWN, shade=False, top=True)
            if "zombie" in f:
                for tx in (x0 + 3, x1 - 5):
                    P.poly([(tx, 53 + b), (tx + 2, 49 + b), (tx + 4, 53 + b)], _shade(shirt, 0.6), shade=False, top=True)
    # arms; returns the right hand
    hand_r = (36.0, 51.0)
    for side in ("l", "r"):
        mode = q.arm_l if side == "l" else q.arm_r
        if "zombie" in f and mode == "down" and q.attack < 0:
            mode = "out"
        d = -1 if side == "l" else 1
        ax = (8 if bulky else 12) if side == "l" else (40 if bulky else 36)
        ax += lx
        sleeve = skin if "skull" in f else (steel if "armor" in f else shirt)
        if mode in ("down", "swing_f", "swing_b"):
            dy = {"swing_f": -2, "swing_b": 2}.get(mode, 0)
            P.ellipse(ax, 44 + b + dy, 3.8 if "skull" not in f else 2, 7, sleeve)
            hx, hy = ax, 51 + b + dy
        elif mode == "up":
            P.ellipse(ax + d * 3, 32 + b, 3.8, 7, sleeve)
            hx, hy = ax + d * 3, 24 + b
        else:
            P.ellipse(ax + d * 6, 41 + b, 7, 3.6, sleeve)
            hx, hy = ax + d * 12, 41 + b
        P.ellipse(hx, hy, 3.2, 3.2, skin)
        if side == "r":
            hand_r = (hx, hy)
    # head
    hy0 = 24 + b
    hc = 24 + lx
    P.ellipse(hc, hy0, 15, 14, skin, shine=True)
    if "ears" in f and "skull" not in f:
        for ex, d in ((9, -1), (39, 1)):
            P.poly([(ex + lx, hy0 - 3), (ex + d * 7 + lx, hy0 - 8), (ex + lx, hy0 + 4)], skin)
    eyes = [(hc - 5, hy0 + 2), (hc + 5, hy0 + 2)]
    if "skull" in f:
        for ex, ey in eyes:
            P.ellipse(ex, ey, 4, 4.4, EYE, shade=False, top=True)
        P.poly([(hc, hy0 + 6), (hc - 1.6, hy0 + 9), (hc + 1.6, hy0 + 9)], EYE, shade=False, top=True)
        for x in (hc - 4.5, hc - 1.5, hc + 1.5, hc + 4.5):
            P.line([(x, hy0 + 10.5), (x, hy0 + 12.5)], 0.9, _shade(skin, 0.6))
    else:
        if "beard" in f:
            P.poly([(hc - 13, hy0 + 4), (hc + 13, hy0 + 4), (hc + 11, hy0 + 16), (hc, hy0 + 23), (hc - 11, hy0 + 16)], hair)
        if not covered or "mask" not in f:
            if q.eyes == "blink":
                for ex, ey in eyes:
                    P.line([(ex - 2.5, ey + 1), (ex + 2.5, ey + 1)], 1.3, EYE)
            else:
                P.eyes(eyes, r=3.0, hurt=q.eyes == "hurt", lashes=col.hair_style == "long")
            if not (f & ({"zombie", "beard"} | chibi.MONSTER_SKIN)):
                P.cheeks([(hc - 9, hy0 + 7), (hc + 9, hy0 + 7)])
            if "beard" not in f:
                P.line([(hc - 1.5, hy0 + 9), (hc, hy0 + 10), (hc + 1.5, hy0 + 9)], 0.9, _shade(skin, 0.45))
        if "tusks" in f:
            for x in (hc - 4, hc + 4):
                P.poly([(x - 1.6, hy0 + 11), (x, hy0 + 6), (x + 1.6, hy0 + 11)], WHITE, shade=False, top=True)
        # hair over the head
        if not covered and "skull" not in f:
            P.ellipse(hc, hy0 - 7, 15.5, 8.5, hair)
            P.rrect(hc - 15, hy0 - 8, hc - 11, hy0 + 4, 2.5, hair)
            P.rrect(hc + 11, hy0 - 8, hc + 15, hy0 + 2, 2.5, _shade(hair, 0.85))
            if col.hair_style == "spiky":
                for sx in (-10, -4, 2, 8):
                    P.poly([(hc + sx - 3, hy0 - 12), (hc + sx, hy0 - 19), (hc + sx + 3, hy0 - 12)], hair)
            elif col.hair_style == "parted":
                P.poly([(hc - 13, hy0 - 6), (hc + 2, hy0 - 6), (hc - 9, hy0 - 1)], hair)
            else:
                P.poly([(hc - 12, hy0 - 6), (hc + 12, hy0 - 6), (hc + 9, hy0 - 2), (hc + 2, hy0 - 4), (hc - 6, hy0 - 1)], hair)
        # headgear
        if "mask" in f:
            wrap = _shade(shirt, 0.7)
            P.ellipse(hc, hy0, 15.5, 14.5, wrap)
            P.rrect(hc - 11, hy0 - 3, hc + 11, hy0 + 6, 3, skin)
            P.eyes(eyes, r=2.6, hurt=q.eyes == "hurt")
            P.rrect(hc - 15, hy0 - 8, hc + 15, hy0 - 5, 1.5, CAPE, shade=False)
            P.line([(hc - 15, hy0 - 6), (hc - 21, hy0 - 2), (hc - 19, hy0 + 3)], 1.6, CAPE, top=False)
        if "helmet" in f:
            P.ellipse(hc, hy0 - 6, 16, 11, steel)
            P.rrect(hc - 16, hy0 - 2, hc + 16, hy0 + 1, 1.5, _shade(steel, 0.8), shade=False)
            P.rrect(hc - 1.5, hy0 - 6, hc + 1.5, hy0 + 2, 1, _shade(steel, 0.8), shade=False)
            if "horns" in f:
                for ex, d in ((hc - 15, -1), (hc + 15, 1)):
                    P.poly([(ex, hy0 - 5), (ex + d * 6, hy0 - 19), (ex + d * 2, hy0 - 3)], WHITE)
        elif "horns" in f:
            for ex, d in ((hc - 8, -1), (hc + 8, 1)):
                P.poly([(ex - 2, hy0 - 11), (ex + d * 2, hy0 - 19), (ex + 2, hy0 - 11)], WHITE)
        if "hood" in f:
            hood = shirt
            P.ellipse(hc, hy0 - 1, 18, 16, hood)
            P.ellipse(hc + 1, hy0 + 4, 11, 9.5, skin)
            if q.eyes == "blink":
                for ex, ey in eyes:
                    P.line([(ex - 2.5, ey + 1), (ex + 2.5, ey + 1)], 1.3, EYE)
            else:
                P.eyes(eyes, r=3.0, hurt=q.eyes == "hurt")
        if "hat" in f:
            if f & {"staff", "robe"}:
                P.poly([(hc - 18, hy0 - 6), (hc + 1, hy0 - 32), (hc + 18, hy0 - 6)], shirt)
                P.ellipse(hc, hy0 - 6, 21, 3.6, _shade(shirt, 0.8))
                P.ellipse(hc + 3, hy0 - 18, 1.6, 1.6, CROWN, shade=False, top=True)
            else:
                straw = _hexrgb(chibi.STRAW)
                P.rrect(hc - 12, hy0 - 19, hc + 12, hy0 - 7, 5, straw)
                P.rrect(hc - 12, hy0 - 10, hc + 12, hy0 - 7, 1, CAPE, shade=False)
                P.ellipse(hc, hy0 - 6, 22, 4.2, straw)
        if "crown" in f:
            P.poly([(hc - 9, hy0 - 10), (hc - 9, hy0 - 19), (hc - 4.5, hy0 - 14), (hc, hy0 - 21), (hc + 4.5, hy0 - 14),
                    (hc + 9, hy0 - 19), (hc + 9, hy0 - 10)], CROWN)
            P.ellipse(hc, hy0 - 13, 1.8, 1.8, JEWEL, shade=False, top=True)
    if "shield" in f:
        P.rrect(0, 36 + b, 15, 56 + b, 5, steel)
        P.rrect(2, 38 + b, 13, 54 + b, 4, WOOD)
        P.rrect(6.5, 41 + b, 8.5, 51 + b, 0.8, shirt, shade=False, top=True)
        P.rrect(3.5, 45 + b, 11.5, 47 + b, 0.8, shirt, shade=False, top=True)
    hx, hy = hand_r
    if weapon == "sword":
        P.rrect(hx + 2, hy - 27, hx + 6, hy - 4, 1.5, (214, 220, 232), top=True)
        P.rrect(hx - 1, hy - 5, hx + 9, hy - 2, 1.2, CROWN, shade=False, top=True)
        P.rrect(hx + 2.5, hy - 2, hx + 5.5, hy + 3, 1.2, (120, 76, 44), shade=False, top=True)
    elif weapon == "axe":
        P.rrect(hx + 2, hy - 22, hx + 5, hy + 3, 1.5, WOOD, top=True)
        P.poly([(hx + 4, hy - 23), (hx + 11, hy - 27), (hx + 11, hy - 11), (hx + 4, hy - 15)], STEEL, top=True)
    elif weapon == "spear":
        P.rrect(hx + 2, 5, hx + 4.5, min(63, hy + 10), 1.0, WOOD, top=True)
        P.poly([(hx, 6), (hx + 3.25, -4), (hx + 6.5, 6)], STEEL, top=True)
    elif weapon == "bow":
        P.line([(hx + 3, hy - 18), (hx + 8, hy - 10), (hx + 8.5, hy - 3), (hx + 8, hy + 4), (hx + 3, hy + 10)], 2.2, WOOD)
        P.line([(hx + 3, hy - 18), (hx + 3, hy + 10)], 0.7, STRING)
    elif weapon == "staff":
        P.rrect(hx + 2, hy - 28, hx + 5, 63, 1.5, WOOD, top=True)
        P.ellipse(hx + 3.5, hy - 31, 4.6, 4.6, MAGIC, shine=True, top=True)


PAINTERS = {"hero": draw_hero, "slime": draw_blob, "hopper": draw_blob, "bug": draw_blob, "flyer": draw_flyer,
            "robot": draw_robot, "turret": draw_turret, "coin": draw_coin, "star": draw_star, "gem": draw_gem,
            "heart": draw_heart, "orb": draw_orb, "door": draw_door, "exit": draw_exit, "portal": draw_portal,
            "spikes": draw_spikes, "bullet": draw_bullet,
            "slash": draw_slash, "ship": draw_ship, "ufo": draw_ufo,
            "beast": draw_beast, "spider": draw_spider, "dragon": draw_dragon, "ghost": draw_ghost, "snake": draw_snake}
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
    if kind == "ghost":  # pale, like the pixel ghost
        color = creatures._mix(color, (240, 244, 255), 0.82)
    pal = palette(body_color(color, feats) if kind == "hero" else color)
    size = (spec.size[0] * DETAIL, spec.size[1] * DETAIL)
    frames: dict[str, list[np.ndarray]] = {}
    painter = PAINTERS[kind]
    if kind == "hero" and chibi.is_human(feats):  # people: the chibi twin of the fine pixel style
        painter = draw_human
        extra["colors"] = chibi.choose(name, color, feats, seed)
        extra["weapon"] = held_weapon(feats)
    for anim, (n, _fps, _loop) in spec.anims.items():
        frames[anim] = []
        for i in range(n):
            P = Painter(*size, pal)
            painter(P, Pose(anim, i, feats, random.Random(rng_seed), extra))
            frames[anim].append(P.render(OUTLINE.get(kind, 1.6), flash=anim == "hurt"))
    fps, loop = add_derived(kind, frames, spec.anims, False, spec.anchor, motion.FLASH, rng_seed)
    sheet, anim_set = build_sheet(frames, fps, loop)
    s = finalize(name, sheet, size, anim_set, SCALE, spec.anchor)
    s.smooth = True
    return s
