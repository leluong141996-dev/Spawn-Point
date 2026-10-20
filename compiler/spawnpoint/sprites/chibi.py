"""Front-facing chibi humans for the fine (pixel_size 1) pixel style, drawn natively at 24x32.

The look: a big head (about half the height), two dot eyes and blush, separate flat colour blocks for
skin, hair, shirt, trousers and shoes (each with one shadow tone and a touch of light from the top-left),
a dark outline around the figure, and the silhouette made by hair, hats and what the character holds.
The entity colour is the clothing colour; skin tone, hair colour and hair style come from the name and
seed, so every character looks a little different but always the same for the same name.

Creatures (anything with a tail, wings, beak, antenna...) keep the generic hero painter in generate.py.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass

import numpy as np

from . import palettes

RGBA = tuple[int, int, int, int]
W, H = 24, 32

OUTLINE: RGBA = (30, 24, 42, 255)
EYE: RGBA = (30, 24, 42, 255)
WHITE: RGBA = (255, 250, 240, 255)
BLUSH: RGBA = (240, 140, 140, 255)

SKIN_TONES = ["#f6c9a4", "#e8b088", "#c88a5e", "#9c6440", "#6e4430"]
HAIR_COLORS = ["#6b4026", "#2b2230", "#e8c060", "#b84a2a", "#8a5a34", "#3a2a1e"]
GRAY_HAIR = "#c8c8d0"
PANTS = ["#3a5aa0", "#5a4a3a", "#4a4a56", "#6a5236"]
SHOES = "#4a2e22"
LEATHER = "#7a5234"
STEEL = "#b4bccc"
GOLD = "#ffcc40"
WOOD = "#96603a"
CAPE = "#b02638"
JEWEL = "#e03a5a"
MAGIC = "#6ed6ff"
STRING: RGBA = (236, 232, 220, 255)
BONE = "#ece6d2"
ZOMBIE_SKIN = "#9cbc84"
MONSTER_GREENS = ["#6aa84f", "#7aa040", "#5a9a5a"]
DEVIL_SKIN = "#c8423a"
STRAW = "#e6c880"

# Features that mark a creature rather than a person (they keep the generic painter).
CREATURE_FEATURES = {"tail", "long_ears", "crest", "wings", "beak", "antenna", "ghost", "legs", "spots"}
# Features whose wearer has monster skin (the entity colour) and leather clothes.
MONSTER_SKIN = {"tusks", "monster"}


def is_human(feats: list[str]) -> bool:
    return not any(f in CREATURE_FEATURES for f in feats)


@dataclass
class Tone:
    outline: RGBA
    shadow: RGBA
    base: RGBA
    light: RGBA


def tone(color: str, pal: palettes.Palette | None) -> Tone:
    """The free 4-tone ramp. With a theme palette the finished frame is snapped pixel by pixel instead
    (palette-picked ramps can jump hue, e.g. a yellow highlight on grey steel)."""
    from .generate import ramp  # local import: generate imports this module
    r = ramp(color)
    return Tone(r.outline, r.shadow, r.base, r.light)


@dataclass
class Look:
    """Everything that stays the same across the frames of one character."""
    feats: set[str]
    skin: Tone
    hair: Tone
    shirt: Tone
    pants: Tone
    shoes: Tone
    hair_style: str
    steel: Tone
    gold: Tone
    wood: Tone
    cape: Tone
    magic: Tone
    leather: Tone
    straw: Tone


@dataclass
class Colors:
    """The per-character choices, shared by the pixel and the cartoon painters."""
    skin: str
    hair: str
    shirt: str
    pants: str
    hair_style: str


def choose(name: str, color: str, feats: list[str], seed: int) -> Colors:
    rng = random.Random(zlib.crc32(f"chibi:{name}:{seed}".encode()))
    f = set(feats)
    skin_hex = rng.choice(SKIN_TONES)
    hair_hex = GRAY_HAIR if "old" in f else rng.choice(HAIR_COLORS)
    pants_hex = rng.choice(PANTS)
    shirt_hex = color
    if f & MONSTER_SKIN:  # goblins, orcs and trolls are green, devils red; the entity colour stays their clothes
        skin_hex = DEVIL_SKIN if "horns" in f else rng.choice(MONSTER_GREENS)
        pants_hex = "#4a3a2e"
    if "zombie" in f:
        skin_hex = ZOMBIE_SKIN
    if "skull" in f:
        skin_hex = BONE
    style = "long" if "hair" in f else rng.choice(["short", "short", "spiky", "parted"])
    return Colors(skin_hex, hair_hex, shirt_hex, pants_hex, style)


def make_look(name: str, color: str, feats: list[str], seed: int, pal: palettes.Palette | None) -> Look:
    c = choose(name, color, feats, seed)
    t = lambda h: tone(h, pal)  # noqa: E731
    return Look(set(feats), t(c.skin), t(c.hair), t(c.shirt), t(c.pants), t(SHOES), c.hair_style, t(STEEL), t(GOLD),
                t(WOOD), t(CAPE), t(MAGIC), t(LEATHER), t(STRAW))


@dataclass
class Pose:
    bob: int = 0          # head + body sink (breathing, running)
    lift_l: int = 0       # a raised foot (running, jumping)
    lift_r: int = 0
    arm_l: str = "down"   # down | up | out | swing_f | swing_b
    arm_r: str = "down"
    eyes: str = "open"    # open | blink | hurt
    lean: int = 0         # horizontal shift of the upper body (hurt)
    attack: int = -1      # attack frame index, -1 when not attacking


def pose_for(anim: str, i: int, weapon: str | None) -> Pose:
    if anim == "idle":
        return Pose(bob=(0, 0, 0, 1, 1, 1)[i % 6], eyes="blink" if i % 6 == 2 else "open")
    if anim == "run":
        k = i % 4
        return Pose(bob=(0, 1, 0, 1)[k], lift_l=(1, 0, 0, 0)[k], lift_r=(0, 0, 1, 0)[k],
                    arm_l=("swing_b", "down", "swing_f", "down")[k], arm_r=("swing_f", "down", "swing_b", "down")[k])
    if anim == "jump":
        return Pose(lift_l=1, lift_r=1, arm_l="up", arm_r="up")
    if anim == "fall":
        return Pose(arm_l="out", arm_r="out", lift_l=0, lift_r=1)
    if anim == "hurt":
        return Pose(eyes="hurt", lean=-1, arm_l="out", arm_r="out")
    if anim == "attack":
        k = i % 3
        if weapon in ("sword", "axe", None):
            arm = ("up", "out", "down")[k]
        elif weapon in ("spear", "bow"):
            arm = "out"
        else:  # staff
            arm = ("up", "up", "down")[k]
        return Pose(arm_r=arm, attack=k)
    return Pose()


class Fig:
    """A small pixel canvas in frame coordinates (24x32 for people; creatures pass their own size)."""

    def __init__(self, w: int = W, h: int = H) -> None:
        self.w, self.h = w, h
        self.px = np.zeros((h, w, 4), dtype=np.uint8)

    def set(self, x: int, y: int, c: RGBA) -> None:
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y, x] = c

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: RGBA) -> None:
        x0, x1 = max(0, int(round(x0))), min(self.w - 1, int(round(x1)))
        y0, y1 = max(0, int(round(y0))), min(self.h - 1, int(round(y1)))
        if x0 <= x1 and y0 <= y1:
            self.px[y0:y1 + 1, x0:x1 + 1] = c

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: RGBA) -> None:
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        m = ((xs + 0.5 - cx) / max(rx, 0.01)) ** 2 + ((ys + 0.5 - cy) / max(ry, 0.01)) ** 2 <= 1.0
        self.px[m] = c

    def poly(self, pts: list[tuple[float, float]], c: RGBA) -> None:
        from .generate import _inside
        for y in range(self.h):
            for x in range(self.w):
                if _inside(x + 0.5, y + 0.5, pts):
                    self.px[y, x] = c

    def line(self, x0: float, y0: float, x1: float, y1: float, c: RGBA, width: int = 1) -> None:
        n = max(int(abs(x1 - x0)), int(abs(y1 - y0)), 1)
        for k in range(n + 1):
            x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
            self.rect(x, y, x + width - 1, y + width - 1, c)

    def outline(self) -> None:
        a = self.px[..., 3] > 0
        p = np.pad(a, 1)
        ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
        self.px[ring] = OUTLINE


# --- body parts ---------------------------------------------------------------------------------

def _legs(g: Fig, L: Look, p: Pose, robe: bool, bulky: bool) -> None:
    pa, sh = L.pants, L.shoes
    lx0, lx1, rx0, rx1 = (7, 10, 13, 16) if bulky else (8, 10, 13, 15)
    if robe:  # only the shoes peek out under the hem
        g.rect(lx0, 30 - p.lift_l, lx1, 31 - p.lift_l, sh.base)
        g.rect(rx0, 30 - p.lift_r, rx1, 31 - p.lift_r, sh.shadow)
        return
    for x0, x1, lift, side in ((lx0, lx1, p.lift_l, 0), (rx0, rx1, p.lift_r, 1)):
        top, foot = 26, 30 - lift
        g.rect(x0, top, x1, foot - 1, pa.shadow if side else pa.base)
        g.rect(x0 - (0 if side else 1), foot, x1 + (1 if side else 0), foot + 1, sh.base)
        g.rect(x0 - (0 if side else 1), foot + 1, x1 + (1 if side else 0), foot + 1, sh.shadow)
    g.set(lx0, 26, pa.light)


def _torso(g: Fig, L: Look, p: Pose, robe: bool, bulky: bool) -> tuple[int, int]:
    f, s, y = L.feats, L.shirt, 19 + p.bob
    x0, x1 = (6, 17) if bulky else (8, 15)
    x0 += p.lean
    x1 += p.lean
    if robe:  # long robe or dress flaring to the ankles
        for row in range(y, 30):
            spread = (row - y) // 4
            g.rect(x0 - spread, row, x1 + spread, row, s.base)
            g.set(x1 + spread, row, s.shadow)
        g.rect(x0 + 1, y, x0 + 3, y + 3, s.light)
        g.rect(x0, 29, x1 + 2, 29, s.shadow)
        if "dress" in f:
            g.rect(x0, y, x1, y + 1, s.light)
        else:  # a rope belt
            g.rect(x0, y + 5, x1, y + 5, L.gold.shadow)
        return x0, x1
    g.rect(x0, y, x1, 25, s.base)
    g.rect(x1 - 1, y, x1, 25, s.shadow)
    g.rect(x0 + 1, y, x0 + 3, y, s.light)
    if "armor" in f:  # steel breastplate with a tabard stripe in the entity colour
        st = L.steel
        g.rect(x0, y, x1, y + 4, st.base)
        g.rect(x0 + 1, y, x0 + 3, y + 1, st.light)
        g.rect(x1 - 1, y + 1, x1, y + 4, st.shadow)
        g.rect(x0 + 3, y + 2, x1 - 3, 25, s.base)
    g.rect(x0, 25, x1, 25, L.leather.shadow)  # belt
    g.set((x0 + x1) // 2 + 1, 25, L.gold.base)
    if "zombie" in f:  # torn hem
        for x in (x0, x0 + 3, x1 - 1):
            g.set(x, 25, (0, 0, 0, 0))
        g.set(x0 + 2, y + 3, s.shadow)
    return x0, x1


def _arm(g: Fig, L: Look, p: Pose, side: str, x0: int, x1: int, robe: bool) -> tuple[int, int]:
    """Draws one arm; returns the hand position."""
    mode = p.arm_l if side == "l" else p.arm_r
    sleeve = L.shirt if not ("armor" in L.feats) else L.steel
    tone_ = sleeve.base if side == "l" else sleeve.shadow
    y = 19 + p.bob
    if "zombie" in L.feats and mode == "down" and p.attack < 0:
        mode = "out"
    if side == "l":
        ax0, ax1 = x0 - 2, x0 - 1
    else:
        ax0, ax1 = x1 + 1, x1 + 2
    if mode in ("down", "swing_f", "swing_b"):
        dy = {"swing_f": -1, "swing_b": 1}.get(mode, 0)
        g.rect(ax0, y, ax1, y + 5 + dy, tone_)
        hand = (ax0, y + 6 + dy)
        g.rect(ax0, hand[1], ax1, hand[1], L.skin.base if side == "l" else L.skin.shadow)
        return (ax1 if side == "r" else ax0, hand[1])
    if mode == "up":
        d = -1 if side == "l" else 1
        g.rect(ax0 + d, y - 6, ax1 + d, y + 1, tone_)
        g.rect(ax0 + d, y - 7, ax1 + d, y - 7, L.skin.base)
        return (ax1 + d if side == "r" else ax0 + d, y - 7)
    # out: the arm held sideways
    if side == "l":
        g.rect(ax0 - 2, y + 1, ax1, y + 2, tone_)
        g.rect(ax0 - 3, y + 1, ax0 - 3, y + 2, L.skin.base)
        return (ax0 - 3, y + 1)
    g.rect(ax0, y + 1, ax1 + 2, y + 2, tone_)
    g.rect(ax1 + 3, y + 1, ax1 + 3, y + 2, L.skin.shadow)
    return (ax1 + 3, y + 1)


def _head(g: Fig, L: Look, p: Pose) -> None:
    s, y, x = L.skin, p.bob, p.lean
    g.rect(7 + x, 6 + y, 16 + x, 18 + y, s.base)
    g.rect(6 + x, 7 + y, 17 + x, 17 + y, s.base)
    g.rect(17 + x, 8 + y, 17 + x, 17 + y, s.shadow)
    g.rect(8 + x, 18 + y, 16 + x, 18 + y, s.shadow)
    g.rect(7 + x, 7 + y, 9 + x, 8 + y, s.light)
    if "ears" in L.feats:  # pointy goblin / elf ears
        for ex, d in ((5, -1), (18, 1)):
            g.rect(ex + x, 11 + y, ex + x, 13 + y, s.base if d < 0 else s.shadow)
            g.set(ex + d + x, 10 + y, s.base if d < 0 else s.shadow)


def _face(g: Fig, L: Look, p: Pose) -> None:
    f, y, x = L.feats, p.bob, p.lean
    if "skull" in f:
        return
    if p.eyes == "blink":
        g.rect(8 + x, 13 + y, 9 + x, 13 + y, EYE)
        g.rect(14 + x, 13 + y, 15 + x, 13 + y, EYE)
    elif p.eyes == "hurt":  # squeezed shut: > <
        for ex, d in ((9, 1), (14, -1)):
            g.set(ex - d + x, 11 + y, EYE)
            g.set(ex + x, 12 + y, EYE)
            g.set(ex - d + x, 13 + y, EYE)
    else:
        g.rect(9 + x, 12 + y, 9 + x, 13 + y, EYE)
        g.rect(14 + x, 12 + y, 14 + x, 13 + y, EYE)
        if "zombie" in f:
            g.set(14 + x, 12 + y, WHITE)
    if not (f & ({"zombie", "beard"} | MONSTER_SKIN)):
        g.set(8 + x, 15 + y, BLUSH)
        g.set(15 + x, 15 + y, BLUSH)
    if "beard" in f:
        b = L.hair
        g.rect(7 + x, 15 + y, 16 + x, 19 + y, b.base)
        g.rect(8 + x, 20 + y, 15 + x, 21 + y, b.base)
        g.rect(10 + x, 22 + y, 13 + x, 22 + y, b.base)
        g.rect(15 + x, 16 + y, 16 + x, 20 + y, b.shadow)
        g.rect(9 + x, 15 + y, 14 + x, 15 + y, b.light)  # moustache
    if "tusks" in f:
        for tx in (9, 14):
            g.rect(tx + x, 16 + y, tx + x, 17 + y, WHITE)


def _hair(g: Fig, L: Look, p: Pose, back: bool) -> None:
    """Hair is drawn in two passes: long hair behind the body, the cap and fringe over the head."""
    h, y, x, f = L.hair, p.bob, p.lean, L.feats
    covered = f & {"helmet", "hood", "mask"}
    if back:
        if L.hair_style == "long" and not covered:
            g.rect(5 + x, 9 + y, 6 + x, 24 + y, h.base)
            g.rect(17 + x, 9 + y, 18 + x, 24 + y, h.shadow)
        return
    if covered or L.hair_style == "bald":
        return
    g.rect(8 + x, 4 + y, 15 + x, 4 + y, h.base)
    g.rect(6 + x, 5 + y, 17 + x, 9 + y, h.base)
    g.rect(6 + x, 10 + y, 6 + x, 12 + y, h.base)
    g.rect(17 + x, 10 + y, 17 + x, 11 + y, h.shadow)
    g.rect(17 + x, 6 + y, 17 + x, 9 + y, h.shadow)
    g.rect(9 + x, 5 + y, 12 + x, 5 + y, h.light)
    if L.hair_style == "spiky":
        for sx in (7, 10, 13, 16):
            g.set(sx + x, 3 + y, h.base)
        g.rect(8 + x, 10 + y, 9 + x, 10 + y, h.base)
        g.rect(13 + x, 10 + y, 15 + x, 10 + y, h.base)
    elif L.hair_style == "parted":
        g.rect(7 + x, 10 + y, 10 + x, 10 + y, h.base)
        g.set(12 + x, 6 + y, h.shadow)
    else:  # short with a fringe
        g.rect(8 + x, 10 + y, 15 + x, 10 + y, h.base)
        g.set(11 + x, 10 + y, L.skin.base)
    if L.hair_style == "long":
        g.rect(16 + x, 10 + y, 16 + x, 13 + y, h.base)


def _headgear(g: Fig, L: Look, p: Pose) -> None:
    f, y, x = L.feats, p.bob, p.lean
    st = L.steel
    if "skull" in f:
        return
    if "mask" in f:  # ninja wrap with an eye slit and a headband
        m = L.shirt
        g.rect(6 + x, 4 + y, 17 + x, 18 + y, m.shadow)
        g.rect(7 + x, 3 + y, 16 + x, 3 + y, m.shadow)
        g.rect(8 + x, 4 + y, 11 + x, 5 + y, m.base)
        g.rect(8 + x, 11 + y, 15 + x, 14 + y, L.skin.base)
        g.rect(9 + x, 12 + y, 9 + x, 13 + y, EYE)
        g.rect(14 + x, 12 + y, 14 + x, 13 + y, EYE)
        band = L.cape
        g.rect(6 + x, 8 + y, 17 + x, 8 + y, band.base)
        g.rect(2 + x, 9 + y, 5 + x, 9 + y, band.base)
        g.rect(1 + x, 10 + y, 3 + x, 10 + y, band.shadow)
    if "helmet" in f:
        g.rect(6 + x, 4 + y, 17 + x, 10 + y, st.base)
        g.rect(7 + x, 3 + y, 16 + x, 3 + y, st.base)
        g.rect(8 + x, 4 + y, 11 + x, 5 + y, st.light)
        g.rect(17 + x, 5 + y, 17 + x, 10 + y, st.shadow)
        g.rect(6 + x, 10 + y, 17 + x, 10 + y, st.shadow)
        g.rect(11 + x, 7 + y, 12 + x, 10 + y, st.shadow)  # nose guard
        if "horns" in f:
            for hx, d in ((5, -1), (18, 1)):
                g.rect(hx + x, 4 + y, hx + x, 8 + y, WHITE)
                g.set(hx + d + x, 3 + y, WHITE)
                g.set(hx + d + x, 2 + y, WHITE)
    elif "horns" in f:  # little devil horns through the hair
        for hx in (8, 15):
            g.rect(hx + x, 3 + y, hx + x, 4 + y, WHITE)
    if "hood" in f:
        hd = L.shirt if "mask" not in f else L.leather
        g.rect(6 + x, 4 + y, 17 + x, 10 + y, hd.base)
        g.rect(7 + x, 3 + y, 16 + x, 3 + y, hd.base)
        g.rect(5 + x, 6 + y, 6 + x, 19 + y, hd.base)
        g.rect(17 + x, 6 + y, 18 + x, 19 + y, hd.shadow)
        g.rect(8 + x, 4 + y, 11 + x, 5 + y, hd.light)
        g.rect(7 + x, 10 + y, 16 + x, 10 + y, hd.shadow)
    if "hat" in f:
        if f & {"staff", "robe"}:  # tall pointed wizard hat
            hat = L.shirt
            for row in range(-2, 9):
                half = max(1, (row + 3) * 9 // 11)
                g.rect(12 - half + x, row + y, 11 + half + x, row + y, hat.base)
                g.set(11 + half + x, row + y, hat.shadow)
            g.rect(3 + x, 9 + y, 20 + x, 10 + y, hat.shadow)
            g.rect(10 + x, 1 + y, 11 + x, 3 + y, hat.light)
            g.set(13 + x, 4 + y, L.gold.base)
            g.set(9 + x, 6 + y, L.gold.base)
        else:  # wide straw hat
            sw = L.straw
            g.rect(6 + x, 4 + y, 17 + x, 8 + y, sw.base)
            g.rect(7 + x, 3 + y, 16 + x, 3 + y, sw.base)
            g.rect(8 + x, 4 + y, 11 + x, 5 + y, sw.light)
            g.rect(6 + x, 8 + y, 17 + x, 8 + y, L.cape.base)
            g.rect(2 + x, 9 + y, 21 + x, 10 + y, sw.base)
            g.rect(2 + x, 10 + y, 21 + x, 10 + y, sw.shadow)
    if "crown" in f:
        go = L.gold
        g.rect(8 + x, 3 + y, 15 + x, 4 + y, go.base)
        for cx in (8, 11, 12, 15):
            g.set(cx + x, 2 + y, go.base)
        g.rect(14 + x, 3 + y, 15 + x, 4 + y, go.shadow)
        g.set(11 + x, 3 + y, tone(JEWEL, None).base)


def _skeleton(g: Fig, L: Look, p: Pose) -> None:
    b, y, x = L.skin, p.bob, p.lean
    for lx, lift in ((9, p.lift_l), (14, p.lift_r)):
        g.rect(lx, 26, lx, 29 - lift, b.base)
        g.rect(lx - 1, 30 - lift, lx + 1, 31 - lift, b.base)
    g.rect(11 + x, 19 + y, 12 + x, 25 + y, b.base)  # spine
    for row in (20, 22):
        g.rect(8 + x, row + y, 15 + x, row + y, b.base)
    g.rect(9 + x, 25 + y, 14 + x, 25 + y, b.base)  # pelvis
    g.rect(7 + x, 7 + y, 16 + x, 16 + y, b.base)
    g.rect(6 + x, 8 + y, 17 + x, 15 + y, b.base)
    g.rect(17 + x, 9 + y, 17 + x, 15 + y, b.shadow)
    g.rect(8 + x, 17 + y, 15 + x, 18 + y, b.base)
    g.rect(7 + x, 8 + y, 9 + x, 9 + y, b.light)
    if p.eyes == "hurt":
        g.rect(8 + x, 12 + y, 10 + x, 12 + y, EYE)
        g.rect(13 + x, 12 + y, 15 + x, 12 + y, EYE)
    else:
        g.rect(8 + x, 11 + y, 10 + x, 13 + y, EYE)
        g.rect(13 + x, 11 + y, 15 + x, 13 + y, EYE)
    g.rect(11 + x, 14 + y, 12 + x, 14 + y, EYE)
    for tx in (9, 11, 13, 15):
        g.set(tx + x, 18 + y, b.shadow)


# --- held things --------------------------------------------------------------------------------

def _shield(g: Fig, L: Look, p: Pose) -> None:
    w, st, y = L.wood, L.steel, 20 + p.bob
    g.rect(1, y, 5, y + 8, w.base)
    g.rect(1, y, 5, y, st.base)
    g.rect(1, y + 8, 5, y + 8, st.shadow)
    g.rect(1, y, 1, y + 8, st.base)
    g.rect(3, y + 2, 3, y + 6, L.shirt.base)
    g.rect(2, y + 4, 4, y + 4, L.shirt.base)


def _cape(g: Fig, L: Look, p: Pose) -> None:
    c, y = L.cape, 19 + p.bob
    flare = 1 if p.lift_l or p.lift_r else 0
    g.rect(5 - flare, y, 18 + flare, 29, c.base)
    g.rect(16 + flare, y, 18 + flare, 29, c.shadow)


def _weapon(g: Fig, L: Look, p: Pose, weapon: str, hand: tuple[int, int]) -> None:
    hx, hy = hand
    st, wd, go = L.steel, L.wood, L.gold
    blade = (214, 222, 236, 255)
    k = p.attack
    if weapon == "sword":
        if k == 1:  # horizontal slash
            g.rect(hx + 1, hy, W - 1, hy, blade)
            g.set(W - 1, hy, WHITE)
            g.rect(hx + 1, hy - 1, hx + 1, hy + 1, go.base)
            return
        if k == 2:  # follow-through, low
            g.line(hx + 1, hy + 1, min(W - 1, hx + 6), hy + 6, blade)
            g.rect(hx, hy, hx + 1, hy, go.base)
            return
        tx = hx + 2
        g.rect(tx, hy - 13, tx, hy - 2, blade)
        g.set(tx, hy - 14, WHITE)
        g.rect(tx - 1, hy - 1, tx + 1, hy - 1, go.base)
        g.rect(tx, hy, tx, hy + 1, wd.shadow)
    elif weapon == "axe":
        if k in (1, 2):
            ex, ey = (W - 1, hy) if k == 1 else (min(W - 1, hx + 5), hy + 5)
            g.line(hx + 1, hy, ex - 1, ey, wd.base)
            g.rect(ex - 2, ey - 2, ex, ey + 1, st.base)
            return
        tx = hx + 2
        g.rect(tx, hy - 11, tx, hy + 1, wd.base)
        g.rect(tx + 1, hy - 11, tx + 3, hy - 7, st.base)
        g.rect(tx + 3, hy - 11, tx + 3, hy - 7, st.light)
        g.rect(tx - 1, hy - 10, tx - 1, hy - 8, st.shadow)
    elif weapon == "spear":
        if k >= 0:  # levelled and thrust
            reach = (0, 2, 1)[k]
            g.rect(hx - 4, hy, min(W - 1, hx + 4 + reach), hy, wd.base)
            g.rect(min(W - 2, hx + 4 + reach), hy - 1, min(W - 1, hx + 5 + reach), hy + 1, st.base)
            return
        tx = hx + 2
        g.rect(tx, 3, tx, min(H - 1, hy + 5), wd.base)
        g.rect(tx, 0, tx, 2, st.base)
        g.rect(tx - 1, 1, tx + 1, 1, st.base)
        g.set(tx, 0, st.light)
    elif weapon == "bow":
        tx = hx + 2
        top, bot = hy - 9, hy + 3
        for yy in range(top, bot + 1):
            t = (yy - top) / max(1, bot - top)
            bulge = 2 if 0.2 < t < 0.8 else 1
            g.set(tx + bulge, yy, wd.base)
        g.rect(tx, top, tx, bot, STRING)
        if k in (0, 1):  # an arrow nocked, then loosed
            g.rect(tx - 6 + 3 * k, hy - 3, min(W - 1, tx + 3 + 2 * k), hy - 3, st.base)
            g.set(min(W - 1, tx + 3 + 2 * k), hy - 3, WHITE)
    elif weapon == "staff":
        tx = min(W - 2, hx + 2)
        g.rect(tx, hy - 14, tx, H - 1, wd.base)
        glow = L.magic.light if k == 1 else L.magic.base
        g.rect(tx - 1, hy - 17, tx + 1, hy - 15, glow)
        g.set(tx - 1, hy - 17, WHITE)
        if k == 1:  # a spark
            for sx, sy in ((tx - 2, hy - 18), (tx + 2, hy - 18), (tx, hy - 19)):
                g.set(sx, sy, WHITE)


# --- the painter --------------------------------------------------------------------------------

def paint(L: Look, anim: str, i: int, weapon: str | None) -> np.ndarray:
    f = L.feats
    p = pose_for(anim, i, weapon)
    g = Fig()
    robe = bool(f & {"robe", "dress"})
    bulky = "bulky" in f
    if "cape" in f:
        _cape(g, L, p)
    _hair(g, L, p, back=True)
    if "skull" in f:
        _skeleton(g, L, p)
        xl, xr = 8 + p.lean, 15 + p.lean
        bone = L.skin
        for side in ("l", "r"):
            mode = p.arm_l if side == "l" else p.arm_r
            if mode == "up":
                ax = xr + 2 if side == "r" else xl - 3
                g.rect(ax, 12 + p.bob, ax, 19 + p.bob, bone.base if side == "l" else bone.shadow)
                hand = (ax, 12 + p.bob)
            elif mode == "out":
                ax0 = xr + 1 if side == "r" else xl - 5
                g.rect(ax0, 20 + p.bob, ax0 + 4, 20 + p.bob, bone.base)
                hand = (ax0 + 4 if side == "r" else ax0, 20 + p.bob)
            else:
                ax = xr + 2 if side == "r" else xl - 2
                g.rect(ax, 19 + p.bob, ax, 24 + p.bob, bone.base if side == "l" else bone.shadow)
                hand = (ax, 25 + p.bob)
            if side == "r":
                right_hand = hand
    else:
        _legs(g, L, p, robe, bulky)
        x0, x1 = _torso(g, L, p, robe, bulky)
        _arm(g, L, p, "l", x0, x1, robe)
        right_hand = _arm(g, L, p, "r", x0, x1, robe)
        _head(g, L, p)
        _face(g, L, p)
        _hair(g, L, p, back=False)
        _headgear(g, L, p)
    if "shield" in f:
        _shield(g, L, p)
    if weapon:
        _weapon(g, L, p, weapon, right_hand)
    elif p.attack == 1:  # unarmed: a flash at the outstretched hand (a punch or a shot)
        hx, hy = right_hand
        for dx, dy in ((1, 0), (2, 0), (1, -1), (1, 1)):
            g.set(hx + dx, hy + dy, WHITE)
    g.outline()
    return g.px


ANIMS = {"idle": (6, 4, True), "run": (4, 10, True), "jump": (1, 1, False), "fall": (1, 1, False),
         "hurt": (1, 1, False), "attack": (3, 14, False)}


def frames(name: str, color: str, feats: list[str], seed: int, pal: palettes.Palette | None,
           weapon: str | None) -> dict[str, list[np.ndarray]]:
    L = make_look(name, color, feats, seed, pal)
    out: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in ANIMS.items():
        out[anim] = []
        for i in range(n):
            px = paint(L, anim, i, weapon)
            out[anim].append(pal.snap(px) if pal else px)
    return out
