"""Battle fighters for card games: big side-view pixel characters (64x80 art pixels and up, shown at 2x), built
from shaded body parts the way a pixel artist blocks them out: each part is filled, lit from the top left, given
a shadow band on its lower right and a dark line where it overlaps what is behind it; the whole figure gets an
outline. Every kind has idle (breathing), attack and hurt animations; generate.py derives the death.

Kinds (FIGHTERS): fighter_hero (people: features pick the helmet, hood, hat, hair, beard, robe, cape, armor,
shield and weapon; "skull" makes a skeleton), fighter_beast, fighter_slime, fighter_flyer, fighter_treant
(golem when grey), fighter_ghost, fighter_spider, fighter_dragon (the big boss body), fighter_mushroom.

    frames(kind, color, features, seed) -> {anim: [RGBA frames]}
"""

from __future__ import annotations

import colorsys
import math
import random

import numpy as np

RGBA = tuple[int, int, int, int]
INK: RGBA = (29, 22, 38, 255)


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgba(rgb) -> RGBA:
    return (int(round(max(0, min(1, rgb[0])) * 255)), int(round(max(0, min(1, rgb[1])) * 255)),
            int(round(max(0, min(1, rgb[2])) * 255)), 255)


def ramp(color: str) -> tuple[RGBA, RGBA, RGBA, RGBA]:
    """(line, shadow, base, light) with pixel-art hue shifting: shadows cooler, lights warmer."""
    h, s, v = colorsys.rgb_to_hsv(*_hex(color))
    line = colorsys.hsv_to_rgb((h + 0.05) % 1, min(1, s * 0.8 + 0.25), v * 0.32)
    shadow = colorsys.hsv_to_rgb((h + 0.03) % 1, min(1, s * 1.08 + 0.04), v * 0.7)
    light = colorsys.hsv_to_rgb((h - 0.03) % 1, s * 0.72, min(1, v * 1.16 + 0.1))
    return _rgba(line), _rgba(shadow), _rgba(_hex(color)), _rgba(light)


SKIN = ramp("#f0b88a")
STEEL = ramp("#b8c4d8")
GOLD = ramp("#f0c040")
BONE = ramp("#e8e0c8")
LEATHER = ramp("#7a4a2e")
WOOD = ramp("#9a6238")
DARK_CLOTH = ramp("#3a3550")
EYE: RGBA = (24, 18, 30, 255)
WHITE: RGBA = (255, 250, 240, 255)


class Rig:
    """A canvas that composites shaded parts back to front."""

    def __init__(self, w: int, h: int, ox: int = 0) -> None:
        """`ox` widens the canvas on both sides (room to lunge) without moving the drawing coordinates."""
        self.w, self.h, self.ox = w + 2 * ox, h, ox
        self.px = np.zeros((h, self.w, 4), np.uint8)
        self.ys, self.xs = np.mgrid[0:h, 0:self.w]
        self.xs = self.xs - ox

    # -- masks
    def ellipse(self, cx: float, cy: float, rx: float, ry: float, angle: float = 0.0) -> np.ndarray:
        dx, dy = self.xs + 0.5 - cx, self.ys + 0.5 - cy
        if angle:
            ca, sa = math.cos(angle), math.sin(angle)
            dx, dy = dx * ca + dy * sa, -dx * sa + dy * ca
        return (dx / max(rx, 0.1)) ** 2 + (dy / max(ry, 0.1)) ** 2 <= 1.0

    def capsule(self, x0: float, y0: float, x1: float, y1: float, r0: float, r1: float | None = None) -> np.ndarray:
        r1 = r0 if r1 is None else r1
        px, py = self.xs + 0.5 - x0, self.ys + 0.5 - y0
        vx, vy = x1 - x0, y1 - y0
        L = vx * vx + vy * vy or 1e-6
        t = np.clip((px * vx + py * vy) / L, 0, 1)
        d = np.hypot(px - t * vx, py - t * vy)
        return d <= r0 + (r1 - r0) * t

    def poly(self, pts: list[tuple[float, float]]) -> np.ndarray:
        x, y = self.xs + 0.5, self.ys + 0.5
        inside = np.zeros((self.h, self.w), bool)
        n = len(pts)
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            cond = (ay > y) != (by > y)
            xint = ax + (y - ay) * (bx - ax) / ((by - ay) or 1e-9)
            inside ^= cond & (x < xint)
        return inside

    def rect(self, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
        return (self.xs >= x0) & (self.xs <= x1) & (self.ys >= y0) & (self.ys <= y1)

    # -- painting
    def part(self, m: np.ndarray, r: tuple[RGBA, RGBA, RGBA, RGBA], shade: int = 2, line: bool = True,
             flat: bool = False) -> None:
        """Paints a shaded part on top. `line` draws its edge where it covers something already painted."""
        if not m.any():
            return
        lc, sh, base, li = r
        under = self.px[..., 3] > 0
        self.px[m] = base
        if not flat:
            p = np.pad(m, shade)
            downright = p[2 * shade:, 2 * shade:]  # m shifted: the pixel `shade` down-right
            upleft = p[shade - 1:shade - 1 + self.h, shade - 1:shade - 1 + self.w] if shade >= 1 else m
            self.px[m & ~downright] = sh
            self.px[m & ~upleft] = li
        if line:
            q = np.pad(m, 1)
            ring = (q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]) & ~m
            self.px[ring & under] = lc

    def dot(self, x: float, y: float, c: RGBA) -> None:
        x, y = int(round(x)) + self.ox, int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y, x] = c

    def line(self, x0: float, y0: float, x1: float, y1: float, c: RGBA) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for k in range(n + 1):
            t = k / max(n, 1)
            self.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, c)

    def finish(self, outline: RGBA = INK) -> np.ndarray:
        a = self.px[..., 3] > 0
        q = np.pad(a, 1)
        ring = (q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]) & ~a
        self.px[ring] = outline
        return self.px


# --- people ----------------------------------------------------------------------------------------------------

def _pose(anim: str, i: int) -> dict:
    """Body offsets and the weapon arm's angle (degrees, 0 = straight ahead, negative = up)."""
    if anim == "attack":
        return [dict(bob=0, lean=-3, arm=-120, weapon=-150, step=0, back=40),
                dict(bob=1, lean=4, arm=-10, weapon=10, step=3, back=60, smear=True),
                dict(bob=1, lean=3, arm=30, weapon=60, step=3, back=60)][i]
    if anim == "hurt":
        return dict(bob=1, lean=-4, arm=40, weapon=-60, step=-1, back=20, hurt=True)
    return dict(bob=(0, 0, 1, 1)[i % 4], lean=0, arm=(25, 25, 22, 22)[i % 4], weapon=(-50, -50, -46, -46)[i % 4],
                step=0, back=50)


def _weapon_of(feats: list[str]) -> str:
    for w in ("staff", "bow", "axe", "spear", "dagger", "sword"):
        if w in feats:
            return w
    return "sword"


def paint_person(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    rng = random.Random(seed)
    p = _pose(anim, i)
    skel = "skull" in feats
    skin = BONE if skel else ramp(rng.choice(("#f0b88a", "#e0a070", "#c08058", "#f8d0a8")))
    if "monster" in feats or "tusks" in feats:  # goblins, orcs, trolls
        skin = ramp("#7ab84a")
    elif "zombie" in feats:
        skin = ramp("#9ab88a")
    cloth = ramp(color)
    armor = STEEL if "armor" in feats else cloth
    robe = "robe" in feats
    hair = ramp(rng.choice(("#5a3a28", "#2b2230", "#e8c060", "#b84a2a", "#e8e0d8" if "old" in feats else "#4a3a5a")))
    boots = LEATHER
    bob, lean, step = p["bob"], p["lean"], p["step"]
    hip = (32 + lean * 0.3, 50 + bob)
    sh_y = 31 + bob
    torso_x = 32 + lean
    # cape behind everything
    if "cape" in feats:
        sway = (0, 1, 2, 1)[i % 4] if anim == "idle" else 3
        g.part(g.poly([(torso_x - 7, sh_y), (torso_x + 3, sh_y), (torso_x - 4, 74), (torso_x - 18 - sway, 72)]),
               ramp("#a83040") if color.lower() not in ("#a83040",) else DARK_CLOTH)
    # back leg and back arm
    if not robe:
        knee = (hip[0] - 6 - step, 64)
        g.part(g.capsule(hip[0] - 2, hip[1], knee[0], knee[1], 4.5, 4), boots if skel is False and "armor" in feats else cloth)
        g.part(g.capsule(knee[0], knee[1], knee[0] - 1, 74, 4, 3.6), boots)
        g.part(g.ellipse(knee[0] + 1, 76, 6, 3), boots)
    ba = math.radians(p["back"] + 60)
    bsh = (torso_x - 6, sh_y + 3)
    bel = (bsh[0] - 4 * math.cos(ba) + 2, bsh[1] + 9)
    g.part(g.capsule(bsh[0], bsh[1], bel[0], bel[1], 3.8, 3.2), armor if "armor" in feats else cloth)
    g.part(g.capsule(bel[0], bel[1], bel[0] - 2, bel[1] + 9, 3.2, 3), skin)
    # torso
    if robe:
        g.part(g.poly([(torso_x - 9, sh_y), (torso_x + 8, sh_y), (torso_x + 14, 76), (torso_x - 15, 76)]), cloth)
        g.part(g.rect(torso_x - 9, 72, torso_x + 13, 76), ramp("#3a3550"), line=False)
    else:
        g.part(g.poly([(torso_x - 9, sh_y), (torso_x + 8, sh_y), (torso_x + 6, hip[1] + 2), (torso_x - 7, hip[1] + 2)]),
               armor)
        if "armor" in feats:  # a tabard over the mail in the character's colour
            g.part(g.poly([(torso_x - 4, sh_y + 4), (torso_x + 4, sh_y + 4), (torso_x + 3, hip[1] + 6), (torso_x - 3, hip[1] + 6)]), cloth)
        g.part(g.rect(torso_x - 8, hip[1] - 1, torso_x + 6, hip[1] + 1), LEATHER, shade=1)
        g.dot(torso_x - 1, hip[1], GOLD[3])
    if skel and not robe:  # ribs show through
        for k in range(3):
            g.line(torso_x - 5, sh_y + 5 + k * 4, torso_x + 4, sh_y + 5 + k * 4, BONE[1])
    # front leg
    if not robe:
        knee = (hip[0] + 7 + step, 63)
        g.part(g.capsule(hip[0] + 2, hip[1], knee[0], knee[1], 4.8, 4.2), cloth if "armor" not in feats else STEEL)
        g.part(g.capsule(knee[0], knee[1], knee[0] + 2, 74, 4.2, 3.8), boots)
        g.part(g.ellipse(knee[0] + 5, 76, 6.5, 3), boots)
    # head
    hx, hy = torso_x + 2 + (-2 if p.get("hurt") else 0), 20 + bob
    g.part(g.capsule(torso_x, sh_y - 3, hx, hy + 6, 3), skin)  # neck
    if "hair" in feats or "hat" in feats or not ({"helmet", "hood"} & set(feats)):
        if not skel:
            g.part(g.ellipse(hx - 2, hy - 1, 9.5, 9), hair)  # hair behind the face
            if "hair" in feats:
                g.part(g.poly([(hx - 10, hy - 2), (hx - 2, hy), (hx - 6, hy + 16), (hx - 13, hy + 12)]), hair)
    g.part(g.ellipse(hx, hy, 8.5, 9), skin)
    face_x = hx + 4
    if skel:
        g.part(g.ellipse(face_x, hy, 2.4, 2.6), (EYE, EYE, EYE, EYE), line=False, flat=True)
        g.dot(face_x, hy, (255, 90, 60, 255))
        g.line(hx + 1, hy + 6, hx + 7, hy + 6, BONE[0])
        for k in range(4):
            g.dot(hx + 2 + k * 1.5, hy + 7, BONE[0])
    else:
        if p.get("hurt"):
            g.line(face_x - 1, hy - 1, face_x + 1, hy + 1, EYE)
            g.line(face_x - 1, hy + 1, face_x + 1, hy - 1, EYE)
        else:
            g.part(g.rect(face_x, hy - 2, face_x + 1, hy + 1), (EYE, EYE, EYE, EYE), line=False, flat=True)
            g.dot(face_x, hy - 2, WHITE)
        g.line(face_x - 2, hy - 4, face_x + 2, hy - 4, hair[0])  # brow
        g.dot(hx + 8, hy + 2, skin[1])  # nose
        g.line(face_x, hy + 5, face_x + 2, hy + 5, skin[0])
        if "tusks" in feats:
            g.dot(face_x + 1, hy + 4, WHITE)
            g.dot(face_x + 3, hy + 4, WHITE)
        if "ears" in feats:  # pointed ears (goblins, elves)
            g.part(g.poly([(hx - 5, hy - 2), (hx - 15, hy - 7), (hx - 4, hy + 3)]), skin)
        if not ({"helmet", "hood", "hat"} & set(feats)):  # fringe
            g.part(g.poly([(hx - 9, hy - 3), (hx + 7, hy - 9), (hx + 9, hy - 4), (hx - 2, hy - 2)]), hair)
    if "beard" in feats:
        g.part(g.poly([(hx - 3, hy + 3), (hx + 8, hy + 3), (hx + 6, hy + 13), (hx, hy + 15), (hx - 4, hy + 9)]),
               hair if "old" not in feats else ramp("#e8e0d8"))
    if "helmet" in feats:
        g.part(g.ellipse(hx, hy - 3, 10, 9) & (g.ys < hy + 1), STEEL)
        g.part(g.rect(hx + 3, hy - 3, hx + 10, hy + 1) & g.ellipse(hx, hy - 1, 11, 10), STEEL)
        g.line(hx + 4, hy - 1, hx + 9, hy - 1, EYE)
        if "horns" in feats:
            g.part(g.capsule(hx - 6, hy - 8, hx - 12, hy - 16, 2.4, 1), BONE)
            g.part(g.capsule(hx + 5, hy - 9, hx + 10, hy - 17, 2.4, 1), BONE)
        else:
            g.part(g.capsule(hx - 2, hy - 12, hx - 8, hy - 18, 2, 1.4), ramp(color))  # a plume
    elif "hood" in feats:
        g.part(g.ellipse(hx - 1, hy - 1, 11, 11) & ~g.ellipse(hx + 4, hy + 2, 6.5, 7.5), cloth)
    elif "hat" in feats:
        g.part(g.ellipse(hx, hy - 8, 13, 3), cloth)
        g.part(g.poly([(hx - 8, hy - 8), (hx + 8, hy - 8), (hx - 4, hy - 28), (hx - 10, hy - 24)]), cloth)
        g.part(g.rect(hx - 8, hy - 10, hx + 7, hy - 8), GOLD, shade=1)
    if "crown" in feats:
        g.part(g.poly([(hx - 7, hy - 7), (hx - 7, hy - 14), (hx - 4, hy - 10), (hx, hy - 16), (hx + 4, hy - 10),
                       (hx + 7, hy - 14), (hx + 7, hy - 7)]), GOLD)
    # front arm and the weapon
    arm = math.radians(p["arm"])
    fsh = (torso_x + 5, sh_y + 3)
    el = (fsh[0] + 8 * math.cos(arm * 0.6 + 0.9), fsh[1] + 8 * math.sin(arm * 0.6 + 0.9))
    hand = (el[0] + 8 * math.cos(arm), el[1] + 8 * math.sin(arm))
    _weapon(g, _weapon_of(feats), hand, math.radians(p["weapon"]), p.get("smear", False))
    g.part(g.capsule(fsh[0], fsh[1], el[0], el[1], 4, 3.4), armor if "armor" in feats else cloth)
    g.part(g.capsule(el[0], el[1], hand[0], hand[1], 3.4, 3), skin if "armor" not in feats else STEEL)
    g.part(g.ellipse(hand[0], hand[1], 3.2, 3.2), skin if "armor" not in feats else LEATHER)
    if "shield" in feats:
        g.part(g.ellipse(torso_x - 3, sh_y + 14 + bob, 8, 11), ramp(color))
        g.part(g.ellipse(torso_x - 3, sh_y + 14 + bob, 4, 6), GOLD)


def _weapon(g: Rig, kind: str, hand: tuple[float, float], angle: float, smear: bool) -> None:
    hx, hy = hand
    ca, sa = math.cos(angle), math.sin(angle)
    if kind == "staff":
        tip = (hx + 22 * ca, hy + 22 * sa)
        g.part(g.capsule(hx - 12 * ca, hy - 12 * sa, tip[0], tip[1], 1.8), WOOD)
        g.part(g.ellipse(tip[0], tip[1], 4.5, 4.5), ramp("#9a5ad8"))
        g.dot(tip[0] - 1, tip[1] - 2, WHITE)
    elif kind == "bow":
        for k in range(-10, 11):
            a = angle + math.pi / 2
            bx = hx + math.cos(a) * k + ca * (6 - abs(k) * 0.45)
            by = hy + math.sin(a) * k + sa * (6 - abs(k) * 0.45)
            g.part(g.ellipse(bx, by, 1.6, 1.6), WOOD, shade=0, line=False)
        g.line(hx + math.cos(angle + math.pi / 2) * -10, hy + math.sin(angle + math.pi / 2) * -10,
               hx + math.cos(angle + math.pi / 2) * 10, hy + math.sin(angle + math.pi / 2) * 10, WHITE)
    else:
        length = {"dagger": 10, "axe": 18, "spear": 26, "sword": 22}[kind]
        tip = (hx + length * ca, hy + length * sa)
        if smear:  # the swing leaves an arc
            for k in range(1, 6):
                a2 = angle - k * 0.25
                g.part(g.capsule(hx + 6 * math.cos(a2), hy + 6 * math.sin(a2), hx + length * math.cos(a2),
                                 hy + length * math.sin(a2), 1.2), ((255, 255, 255, 255),) * 4, shade=0, line=False, flat=True)
        if kind == "spear":
            g.part(g.capsule(hx - 8 * ca, hy - 8 * sa, tip[0], tip[1], 1.6), WOOD)
            g.part(g.poly([(tip[0] + 6 * ca, tip[1] + 6 * sa), (tip[0] - 3 * sa, tip[1] + 3 * ca), (tip[0] + 3 * sa, tip[1] - 3 * ca)]), STEEL)
        elif kind == "axe":
            g.part(g.capsule(hx - 4 * ca, hy - 4 * sa, tip[0], tip[1], 1.8), WOOD)
            g.part(g.ellipse(tip[0] - 3 * sa, tip[1] + 3 * ca, 5.5, 4, angle), STEEL)
        else:
            g.part(g.capsule(hx + 3 * ca, hy + 3 * sa, tip[0], tip[1], 2.2, 1.2), STEEL)
            g.part(g.capsule(hx - 4 * sa, hy + 4 * ca, hx + 4 * sa, hy - 4 * ca, 1.6), GOLD)  # cross guard
            g.line(hx + 4 * ca, hy + 4 * sa - 1, tip[0], tip[1] - 1, STEEL[3])


# --- monsters --------------------------------------------------------------------------------------------------

def _eye(g: Rig, x: float, y: float, r: float = 2.2, glow: RGBA | None = None, shut: bool = False) -> None:
    if shut:
        g.line(x - r, y, x + r, y, EYE)
        return
    g.part(g.ellipse(x, y, r + 0.8, r + 1), (EYE, WHITE, WHITE, WHITE), shade=0, line=False, flat=True)
    g.part(g.ellipse(x + 0.6, y + 0.4, r * 0.6, r * 0.75), (EYE,) * 4 if glow is None else (glow,) * 4, line=False, flat=True)
    g.dot(x - 0.4, y - 0.8, WHITE)


def _bounce(anim: str, i: int) -> tuple[float, float, bool]:
    """(x shift, squash 0..1, hurt) for monster poses."""
    if anim == "attack":
        return ((-3, 0.1, False), (8, -0.08, False), (4, 0.0, False))[i]
    if anim == "hurt":
        return (-4, 0.06, True)
    return (0, (0.0, 0.04, 0.08, 0.04)[i % 4], False)


def paint_slime(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    cx, ry, rx = 32 + dx, 22 * (1 - sq), 26 * (1 + sq * 0.8)
    g.part(g.ellipse(cx, 54 - ry, rx, ry) & (g.ys < 54), r, shade=3)
    g.part(g.ellipse(cx - 10, 54 - ry * 1.4, 6, 4), (r[3], r[3], r[3], r[3]), line=False, flat=True)
    g.dot(cx - 13, 54 - ry * 1.5, WHITE)
    for k in range(4):  # drips at the foot
        g.part(g.ellipse(cx - 18 + k * 12, 53, 4, 2.4), r, line=False)
    _eye(g, cx + 6, 54 - ry * 0.95, 3, shut=hurt)
    _eye(g, cx + 16, 54 - ry * 0.9, 2.6, shut=hurt)
    mouth = 54 - ry * 0.45
    if anim == "attack" and i == 1:
        g.part(g.ellipse(cx + 12, mouth, 6, 4), (EYE, EYE, (120, 30, 50, 255), (160, 40, 60, 255)), line=False)
    else:
        g.line(cx + 8, mouth, cx + 15, mouth + 1, r[0])


def paint_mushroom(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    cx = 32 + dx
    g.part(g.capsule(cx - 8, 70, cx - 10, 78, 4), LEATHER)
    g.part(g.capsule(cx + 8, 70, cx + 10, 78, 4), LEATHER)
    g.part(g.ellipse(cx, 58 + sq * 8, 15, 16), ramp("#f0e0c0"), shade=3)
    _eye(g, cx + 4, 56, 2.6, shut=hurt)
    _eye(g, cx + 11, 56, 2.2, shut=hurt)
    g.line(cx + 5, 63, cx + 11, 63, ramp("#f0e0c0")[0])
    cap = ramp(color)
    g.part(g.ellipse(cx, 40 + sq * 8, 28, 18) & (g.ys < 48 + sq * 8), cap, shade=3)
    rng = random.Random(seed)
    for _ in range(6):
        sx, sy = cx + rng.uniform(-20, 20), 34 + rng.uniform(-8, 8) + sq * 8
        g.part(g.ellipse(sx, sy, 3.5, 2.6) & g.ellipse(cx, 40 + sq * 8, 27, 17), ((255, 250, 240, 255),) * 4, line=False, flat=True)


def paint_beast(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    belly = ramp(_lighter(color))
    bob = 1 if sq > 0.05 else 0
    bx, by = 34 + dx, 40 + bob
    for lx, front in ((bx - 16, False), (bx + 12, False)):  # far legs
        g.part(g.capsule(lx, by + 6, lx - 2, 54, 4.2, 3.6), (r[0], r[0], r[1], r[2]))
    if "tail" in feats or True:
        g.part(g.capsule(bx - 22, by - 2, bx - 32, by - 10 - bob * 2, 3.6, 2.2), r)
    g.part(g.ellipse(bx, by, 22, 12), r, shade=3)
    g.part(g.ellipse(bx + 2, by + 6, 16, 5), belly, line=False)
    if "mane" in feats:
        g.part(g.ellipse(bx + 14, by - 6, 11, 13), ramp("#b8642a"))
    for lx in (bx - 12, bx + 16):  # near legs
        g.part(g.capsule(lx, by + 6, lx + 1, 54, 4.6, 4), r)
        g.part(g.ellipse(lx + 2, 54, 4.8, 2.4), (r[0], r[0], r[0], r[1]))
    hx, hy = bx + 24 + (4 if anim == "attack" and i == 1 else 0), by - 10 - bob
    g.part(g.ellipse(hx, hy, 10, 9), r, shade=2)
    open_mouth = anim == "attack" and i >= 1
    g.part(g.poly([(hx + 4, hy - 1), (hx + 18, hy + 1), (hx + 17, hy + 5), (hx + 4, hy + 6)]), r)  # snout
    if open_mouth:
        g.part(g.poly([(hx + 5, hy + 6), (hx + 16, hy + 7), (hx + 6, hy + 11)]), (EYE, EYE, (150, 40, 60, 255), (190, 60, 70, 255)))
        for k in range(3):
            g.dot(hx + 8 + k * 3, hy + 6, WHITE)
    g.part(g.ellipse(hx + 17, hy + 1, 1.8, 1.6), (EYE,) * 4, line=False, flat=True)
    ears = "long_ears" in feats
    g.part(g.poly([(hx - 6, hy - 5), (hx - 1, hy - 7), (hx - 6, hy - (22 if ears else 15))]), r)
    g.part(g.poly([(hx - 1, hy - 7), (hx + 4, hy - 6), (hx + 1, hy - (22 if ears else 14))]), r)
    if "tusks" in feats:
        g.part(g.capsule(hx + 12, hy + 6, hx + 15, hy, 1.4), BONE)
    if "horns" in feats:
        g.part(g.capsule(hx - 2, hy - 7, hx - 10, hy - 14, 2.2, 1), BONE)
    _eye(g, hx + 5, hy - 2, 2, glow=(255, 200, 60, 255), shut=hurt)


def paint_spider(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    bx, by = 34 + dx, 30 + sq * 6
    for k in range(4):
        a = (k - 1.5) * 0.45 + (0.1 if (i + k) % 2 else -0.1)
        kx, ky = bx - 6 + k * 6, by - 8
        g.part(g.capsule(bx + k * 3 - 4, by, kx + math.sin(a) * 12, ky, 2), r)
        g.part(g.capsule(kx + math.sin(a) * 12, ky, kx + math.sin(a) * 20 + (k - 1.5) * 4, 46, 2, 1.4), r)
    g.part(g.ellipse(bx - 12, by - 2, 16, 13), r, shade=3)
    g.part(g.ellipse(bx - 14, by - 6, 5, 4), ramp("#ff4a4a"), line=False)
    g.part(g.ellipse(bx + 8, by + 4, 9, 8), r)
    for k in range(3):
        _eye(g, bx + 10 + k * 3, by + 2 - (k % 2) * 2, 1.4, glow=(255, 60, 60, 255), shut=hurt)
    g.part(g.capsule(bx + 14, by + 10, bx + 16, by + 15, 1.4), BONE)


def paint_flyer(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    flap = (0, 1, 2, 1)[i % 4] if anim == "idle" else (2 if anim == "attack" and i != 1 else 0)
    cx, cy = 32 + dx, 26 + flap * 2
    wing = ramp(_darker(color))
    tip_y = cy - 18 + flap * 10
    for side in (-1, 1):
        g.part(g.poly([(cx, cy - 2), (cx + side * 30, tip_y), (cx + side * 26, cy + 4), (cx + side * 18, cy + 2),
                       (cx + side * 12, cy + 8)]), wing, shade=2)
    g.part(g.ellipse(cx, cy + 2, 10, 11), r, shade=3)
    beak = "beak" in feats
    if beak:
        g.part(g.poly([(cx + 8, cy - 1), (cx + 17, cy + 2), (cx + 8, cy + 4)]), GOLD)
    else:
        g.part(g.poly([(cx - 7, cy - 6), (cx - 3, cy - 18), (cx, cy - 8)]), r)
        g.part(g.poly([(cx + 1, cy - 8), (cx + 5, cy - 18), (cx + 8, cy - 6)]), r)
        g.dot(cx + 4, cy + 7, WHITE)
        g.dot(cx + 7, cy + 7, WHITE)
    _eye(g, cx + 2, cy - 1, 2, glow=(255, 60, 80, 255) if not beak else None, shut=hurt)
    _eye(g, cx + 7, cy - 1, 1.8, glow=(255, 60, 80, 255) if not beak else None, shut=hurt)


def paint_treant(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    stone = "stone" in feats
    bark = ramp("#8a8a96" if stone else "#7a5232")
    leaf = ramp(color)
    cx, bob = 32 + dx * 0.6, int(sq * 20) % 2
    for lx in (cx - 10, cx + 8):  # root legs
        g.part(g.poly([(lx - 5, 60), (lx + 5, 60), (lx + 8, 86), (lx - 7, 86)]), bark)
    if stone:
        g.part(g.ellipse(cx, 44 + bob, 22, 22), bark, shade=3)
        g.part(g.ellipse(cx - 4, 18 + bob, 13, 11), bark, shade=2)
        for k in range(5):
            g.line(cx - 18 + k * 8, 30 + (k % 2) * 10 + bob, cx - 12 + k * 8, 44 + (k % 2) * 8 + bob, bark[0])
        if "moss" in feats or True:
            g.part(g.ellipse(cx - 6, 8 + bob, 10, 4), leaf, line=False)
    else:
        g.part(g.poly([(cx - 14, 64), (cx + 12, 64), (cx + 9, 24 + bob), (cx - 11, 24 + bob)]), bark, shade=3)
        for k in range(4):
            g.line(cx - 8 + k * 5, 30 + bob, cx - 9 + k * 5, 62, bark[1])
        g.part(g.ellipse(cx - 2, 18 + bob, 26, 18), ramp(_darker(color)), shade=3)
        for k in range(5):
            a = k / 5 * math.tau
            g.part(g.ellipse(cx - 2 + math.cos(a) * 14, 14 + bob + math.sin(a) * 8, 11, 8), leaf, line=False)
        g.part(g.ellipse(cx - 10, 8 + bob, 7, 4), (leaf[3],) * 4, line=False, flat=True)
    reach = (12 if anim == "attack" and i == 1 else 0)
    g.part(g.capsule(cx - 8, 36 + bob, cx - 22, 52, 4, 2.4), bark)  # back branch arm
    g.part(g.capsule(cx + 8, 36 + bob, cx + 20 + reach, 46 - reach * 0.5, 4.5, 3), bark)
    for k in range(3):
        g.part(g.capsule(cx + 20 + reach, 46 - reach * 0.5, cx + 26 + reach + k * 2, 40 + k * 5 - reach * 0.5, 1.6, 1), bark)
    glow = (120, 255, 140, 255) if not stone else (255, 160, 60, 255)
    ey = 18 + bob if stone else 38 + bob
    ex = cx - 1 if stone else cx + 2
    _eye(g, ex, ey, 2.2, glow=glow, shut=hurt)
    _eye(g, ex + 7, ey, 2.0, glow=glow, shut=hurt)
    if not stone:
        g.line(cx + 2, 47 + bob, cx + 9, 46 + bob, bark[0])


def paint_ghost(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    cx, cy = 28 + dx, 30 + (0, 1, 2, 1)[i % 4]
    tail = [(cx - 16, cy), (cx + 16, cy)]
    pts = [(cx - 16, cy - 2)]
    for k in range(7):
        pts.append((cx + 16 - k * 5, cy + 30 + (4 if k % 2 else 0) - k * 2 + ((i + k) % 2)))
    pts.append((cx - 22, cy + 20))
    g.part(g.ellipse(cx, cy - 4, 17, 17) | g.poly([(cx - 17, cy - 4), (cx + 17, cy - 4)] + pts[1:]), r, shade=3)
    del tail
    arm = 10 if anim == "attack" and i == 1 else 0
    g.part(g.capsule(cx + 8, cy + 14, cx + 18 + arm, cy + 18 - arm * 0.6, 3.6, 2.2), r)
    g.part(g.ellipse(cx + 3, cy - 4, 4, 5), (EYE,) * 4, line=False, flat=True)
    g.part(g.ellipse(cx + 12, cy - 4, 3.4, 4.6), (EYE,) * 4, line=False, flat=True)
    g.part(g.ellipse(cx + 8, cy + 6, 3, 4 if anim == "attack" else 2), (EYE,) * 4, line=False, flat=True)
    if not hurt:
        g.dot(cx + 3, cy - 6, (200, 255, 255, 255))
        g.dot(cx + 12, cy - 6, (200, 255, 255, 255))


def paint_dragon(g: Rig, color: str, anim: str, i: int, feats: list[str], seed: int) -> None:
    dx, sq, hurt = _bounce(anim, i)
    r = ramp(color)
    belly = ramp("#f0c878")
    wing = ramp(_darker(color))
    flap = (0, 2, 4, 2)[i % 4] if anim == "idle" else 6
    bx, by = 52 + dx, 62
    g.part(g.poly([(bx - 4, by - 18), (bx - 40, 8 + flap), (bx - 30, by - 30), (bx - 46, by - 20), (bx - 20, by - 8)]), wing, shade=3)
    g.part(g.capsule(bx - 20, by + 4, bx - 46, by + 20, 7, 3), r)  # tail
    g.part(g.poly([(bx - 48, by + 20), (bx - 56, by + 14), (bx - 52, by + 26)]), r)
    g.part(g.capsule(bx - 12, by + 10, bx - 16, 92, 6, 5), r)  # far leg
    g.part(g.ellipse(bx, by, 26, 18), r, shade=3)
    g.part(g.ellipse(bx + 4, by + 8, 18, 8), belly, line=False)
    for k in range(4):
        g.line(bx - 8 + k * 6, by + 3, bx - 6 + k * 6, by + 14, belly[1])
    g.part(g.capsule(bx + 10, by + 10, bx + 14, 92, 7, 6), r)  # near leg
    for k in range(3):
        g.part(g.capsule(bx + 14 + k * 3, 92, bx + 18 + k * 3, 94, 1.2), BONE, line=False)
    nx, ny = bx + 24, by - 28 + (6 if anim == "attack" and i == 1 else 0)
    g.part(g.capsule(bx + 14, by - 8, nx, ny, 9, 7), r)  # neck
    for k in range(4):
        g.part(g.poly([(bx + 6 + k * 5, by - 14 - k * 5), (bx + 10 + k * 5, by - 22 - k * 5), (bx + 13 + k * 5, by - 12 - k * 5)]),
               ramp(_darker(color)), line=False)
    hx, hy = nx + 8, ny - 4
    g.part(g.ellipse(hx, hy, 13, 10), r, shade=2)
    open_mouth = anim == "attack" and i >= 1
    g.part(g.poly([(hx + 6, hy - 4), (hx + 26, hy), (hx + 24, hy + 4), (hx + 6, hy + 4)]), r)
    if open_mouth:
        g.part(g.poly([(hx + 6, hy + 4), (hx + 24, hy + 8), (hx + 8, hy + 12)]), r)
        g.part(g.poly([(hx + 8, hy + 5), (hx + 22, hy + 7), (hx + 9, hy + 10)]), (EYE, EYE, (200, 60, 40, 255), (255, 120, 40, 255)), line=False)
    g.part(g.capsule(hx - 4, hy - 8, hx - 14, hy - 20, 2.6, 1.2), BONE)
    g.part(g.capsule(hx + 2, hy - 9, hx - 4, hy - 22, 2.6, 1.2), BONE)
    _eye(g, hx + 6, hy - 3, 2.4, glow=(255, 220, 40, 255), shut=hurt)
    g.dot(hx + 23, hy - 1, r[0])


def _lighter(color: str) -> str:
    h, s, v = colorsys.rgb_to_hsv(*_hex(color))
    r, g, b = colorsys.hsv_to_rgb(h, s * 0.45, min(1, v * 1.2 + 0.15))
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _darker(color: str) -> str:
    h, s, v = colorsys.rgb_to_hsv(*_hex(color))
    r, g, b = colorsys.hsv_to_rgb((h + 0.03) % 1, min(1, s * 1.1), v * 0.62)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


PAD = 20  # art pixels added left and right of every fighter, for lunges and swings
ANIMS = {"idle": (4, 5, True), "attack": (3, 12, False), "hurt": (1, 1, False)}
# kind -> (size, painter, default colour)
FIGHTERS: dict[str, tuple[tuple[int, int], object, str]] = {
    "fighter_hero": ((64, 80), paint_person, "#3a78c8"),
    "fighter_slime": ((64, 56), paint_slime, "#5cd84a"),
    "fighter_mushroom": ((64, 80), paint_mushroom, "#d8402a"),
    "fighter_beast": ((80, 58), paint_beast, "#8a6a4a"),
    "fighter_spider": ((72, 50), paint_spider, "#4a3a5a"),
    "fighter_flyer": ((72, 56), paint_flyer, "#6a4a8a"),
    "fighter_treant": ((64, 88), paint_treant, "#4a9a4a"),
    "fighter_ghost": ((64, 72), paint_ghost, "#b8e8f0"),
    "fighter_dragon": ((112, 96), paint_dragon, "#c83a3a"),
}


def size_of(kind: str) -> tuple[int, int]:
    (w, h), _p, _c = FIGHTERS[kind]
    return w + 2 * PAD, h


def frames(kind: str, color: str, features: list[str] | None = None, seed: int = 0) -> dict[str, list[np.ndarray]]:
    (w, h), painter, _default = FIGHTERS[kind]
    feats = list(features or [])
    out: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in ANIMS.items():
        out[anim] = []
        for i in range(n):
            g = Rig(w, h, PAD)
            painter(g, color, anim, i, feats, seed)  # type: ignore[operator]
            out[anim].append(g.finish())
    return out
