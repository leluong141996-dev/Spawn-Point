"""Procedural pixel-art sprites with animations. Deterministic, GPU-free.

Every kind is a painter on a small canvas (drawn at 2x). Colors come from a 4-tone ramp derived from
one base color; extra features (ears, mask, wings, horns...) come from the entity name and a seed.
"""

from __future__ import annotations

import colorsys
import math
import random
import re
import zlib
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import chibi, creatures, items, monsters, motion, palettes
from .spriteset import SpriteSet, build_sheet, finalize

RGBA = tuple[int, int, int, int]


# --- color ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Ramp:
    outline: RGBA
    shadow: RGBA
    base: RGBA
    light: RGBA
    eye: RGBA = (29, 27, 42, 255)
    white: RGBA = (255, 250, 240, 255)


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgba(r: float, g: float, b: float) -> RGBA:
    return (round(max(0, min(1, r)) * 255), round(max(0, min(1, g)) * 255), round(max(0, min(1, b)) * 255), 255)


def ramp(color: str, pal: "palettes.Palette | None" = None) -> Ramp:
    """The 4-tone ramp for one base colour. With a palette, every tone is a palette colour (distinct, ordered by
    lightness: outline < shadow < base < light)."""
    h, s, v = colorsys.rgb_to_hsv(*_hex(color))
    # Shadows drift toward blue/purple, highlights toward warm: classic pixel-art hue shifting.
    shadow = colorsys.hsv_to_rgb((h + 0.04) % 1, min(1, s * 1.1 + 0.05), v * 0.68)
    light = colorsys.hsv_to_rgb((h - 0.03) % 1, s * 0.75, min(1, v * 1.18 + 0.08))
    outline = colorsys.hsv_to_rgb((h + 0.06) % 1, min(1, s * 0.9 + 0.2), v * 0.28)
    if pal is not None:
        def px(c) -> tuple[int, int, int]:
            return tuple(round(max(0.0, min(1.0, x)) * 255) for x in c)  # type: ignore[return-value]

        def rgba(c: tuple[int, int, int]) -> RGBA:
            return (c[0], c[1], c[2], 255)
        bi = pal.nearest_index(px(_hex(color)))
        lum = pal.lab[bi, 0]
        si = pal.nearest_index(px(shadow), {bi}, (0.0, lum - 6))
        li = pal.nearest_index(px(light), {bi, si}, (lum + 6, 100.0))
        oi = pal.nearest_index(px(outline), {bi, si, li}, (0.0, pal.lab[si, 0] - 3))
        c = pal.rgb
        return Ramp(rgba(tuple(c[oi])), rgba(tuple(c[si])), rgba(tuple(c[bi])), rgba(tuple(c[li])),
                    rgba(tuple(c[pal.dark])), rgba(tuple(c[pal.light])))
    return Ramp(_rgba(*outline), _rgba(*shadow), _rgba(*_hex(color)), _rgba(*light))


# --- canvas -----------------------------------------------------------------------------------

class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.px = np.zeros((h, w, 4), dtype=np.uint8)
        self.skip_outline = False  # the fine style outlines after upscaling instead

    def set(self, x: float, y: float, c: RGBA) -> None:
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y, x] = c

    def rect(self, x0: float, y0: float, x1: float, y1: float, c: RGBA) -> None:
        for y in range(int(round(y0)), int(round(y1)) + 1):
            for x in range(int(round(x0)), int(round(x1)) + 1):
                self.set(x, y, c)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: RGBA, shade: Ramp | None = None) -> None:
        """Filled ellipse; with `shade`, top-left gets the light tone and bottom-right the shadow."""
        for y in range(self.h):
            for x in range(self.w):
                dx, dy = (x + 0.5 - cx) / max(rx, 0.01), (y + 0.5 - cy) / max(ry, 0.01)
                if dx * dx + dy * dy <= 1.0:
                    col = c
                    if shade:
                        t = dx * 0.55 + dy * 0.85
                        col = shade.light if t < -0.55 else shade.shadow if t > 0.5 else c
                    self.px[y, x] = col

    def poly(self, pts: list[tuple[float, float]], c: RGBA) -> None:
        for y in range(self.h):
            for x in range(self.w):
                if _inside(x + 0.5, y + 0.5, pts):
                    self.px[y, x] = c

    def outline(self, c: RGBA) -> None:
        """1px outline around everything opaque (4-neighbourhood)."""
        if self.skip_outline:
            return
        a = self.px[..., 3] > 0
        p = np.pad(a, 1)
        ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
        self.px[ring] = c

    def copy(self) -> np.ndarray:
        return self.px.copy()


def _inside(x: float, y: float, pts: list[tuple[float, float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


# --- features from names ----------------------------------------------------------------------

FEATURE_WORDS: dict[str, tuple[str, ...]] = {
    "ninja": ("mask",), "samurai": ("mask",), "thief": ("mask",),
    "fox": ("ears", "tail", "bushy_tail"), "cat": ("ears", "tail", "thin_tail"), "kitty": ("ears", "tail", "thin_tail"),
    "wolf": ("ears", "tail"), "lion": ("ears", "tail", "mane", "thin_tail"), "tiger": ("ears", "tail", "stripes", "thin_tail"),
    "boar": ("ears", "tail", "tusks", "snout"), "pig": ("ears", "tail", "snout"), "hog": ("ears", "tail", "tusks", "snout"),
    "dog": ("ears", "tail", "floppy_ears"), "puppy": ("ears", "tail", "floppy_ears"), "bear": ("ears", "tail", "round_ears"), "mouse": ("ears", "tail"),
    "monkey": ("ears", "tail"), "panda": ("ears", "tail"), "duck": ("wings", "beak"), "penguin": ("wings", "beak"), "bunny": ("long_ears",), "rabbit": ("long_ears",),
    "spider": ("legs",), "ant": ("legs", "antenna"), "beetle": ("legs",), "bug": ("legs", "antenna"),
    "bat": ("wings",), "bird": ("wings", "beak"), "crow": ("wings", "beak"), "dragon": ("wings", "horns"),
    "robot": ("antenna",), "bot": ("antenna",), "droid": ("antenna",), "mech": ("antenna",),
    "devil": ("horns", "monster"), "demon": ("horns", "monster"), "imp": ("horns", "monster"), "goblin": ("ears", "monster"),
    "elf": ("ears",),
    "orc": ("tusks", "bulky"), "ogre": ("tusks", "bulky"), "troll": ("tusks", "bulky"), "giant": ("bulky",),
    "brute": ("bulky",), "golem": ("bulky",),
    "knight": ("helmet", "shield", "armor"), "paladin": ("helmet", "shield", "sword", "armor"),
    "templar": ("helmet", "shield", "sword", "armor"),
    "soldier": ("helmet", "spear", "armor"), "guard": ("helmet", "spear", "armor"), "spearman": ("helmet", "spear"),
    "wizard": ("hat", "staff", "robe", "beard", "old"), "witch": ("hat", "staff", "robe", "hair"),
    "mage": ("hat", "staff", "robe"), "sorcerer": ("hat", "staff", "robe"),
    "warlock": ("hood", "staff", "robe"), "necromancer": ("hood", "staff", "robe"), "druid": ("hood", "staff", "robe"),
    "shaman": ("hood", "staff"),
    "priest": ("hood", "staff", "robe"), "cleric": ("hood", "staff", "robe"), "healer": ("hood", "staff", "robe"),
    "monk": ("hood", "robe"),
    "rogue": ("hood",), "assassin": ("hood",), "bandit": ("hood",),
    "archer": ("bow",), "hunter": ("bow",), "ranger": ("bow", "hood"), "bowman": ("bow",),
    "viking": ("helmet", "horns", "beard", "axe"), "barbarian": ("axe",), "berserker": ("axe",), "dwarf": ("beard", "helmet", "axe"),
    "lumberjack": ("beard", "axe"), "woodcutter": ("beard", "axe"),
    "king": ("crown", "cape", "beard"), "queen": ("crown", "cape", "hair", "dress"), "emperor": ("crown", "cape"), "prince": ("crown",),
    "lord": ("cape",), "vampire": ("cape",), "dracula": ("cape",),
    "old": ("beard", "old"), "elder": ("beard", "old"), "sage": ("beard", "old"), "hermit": ("beard", "old"),
    "grandpa": ("beard", "old"), "grandma": ("hair", "old"),
    "skeleton": ("skull",), "skelly": ("skull",), "bones": ("skull",), "lich": ("skull", "hood", "staff"),
    "zombie": ("zombie",), "ghoul": ("zombie",),
    "ghost": ("ghost",), "spirit": ("ghost",),
    "dino": ("tail", "crest"), "dinosaur": ("tail", "crest"), "rex": ("tail", "crest"), "lizard": ("tail",),
    "pine": ("pine",), "fir": ("pine",), "spruce": ("pine",), "berry": ("berries",), "berries": ("berries",),
    "mossy": ("moss",), "cage": ("bars",), "gate": ("bars",), "portcullis": ("bars",), "jail": ("bars",),
    "mom": ("hair",), "mother": ("hair",), "mama": ("hair",), "mum": ("hair",), "princess": ("hair", "crown", "dress"),
    "lady": ("hair",), "girl": ("hair",), "farmer": ("hat",), "farmhand": ("hat",), "gardener": ("hat",),
}


def features_for(name: str) -> list[str]:
    words = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)
    out: list[str] = []
    for w in words:
        for f in FEATURE_WORDS.get(w.lower(), ()):
            if f not in out:
                out.append(f)
    return out


# --- kinds ------------------------------------------------------------------------------------

@dataclass
class Kind:
    size: tuple[int, int]
    anims: dict[str, tuple[int, float, bool]]  # name -> (frames, fps, loop)
    paint: Callable[["Ctx"], None] | None  # None: painted by creatures.py at the fine size
    anchor: str = "center"


@dataclass
class Ctx:
    cv: Canvas
    r: Ramp
    feats: list[str]
    anim: str
    i: int
    rng: random.Random
    extra: dict = field(default_factory=dict)


def _eyes(c: Ctx, positions: list[tuple[int, int]], big: bool = False) -> None:
    hurt = c.anim == "hurt"
    blink = c.anim == "idle" and c.i == 2 and c.extra.get("blinks", False)
    for x, y in positions:
        if blink:  # eyes shut for one frame of the idle breath
            c.cv.set(x, y, c.r.eye)
            if big:
                c.cv.set(x - 1, y, c.r.eye)
        elif hurt:
            c.cv.set(x, y, c.r.eye)
            c.cv.set(x - 1, y - 1, c.r.eye)
            c.cv.set(x + 1, y + 1, c.r.eye)
        elif big:
            c.cv.rect(x - 1, y - 1, x, y, c.r.white)
            c.cv.set(x, y, c.r.eye)
        else:
            c.cv.rect(x, y - 1, x, y, c.r.eye)


def paint_hero(c: Ctx) -> None:
    cv, r, f = c.cv, c.r, c.feats
    atk = c.anim == "attack"
    weapon = held_weapon(f)
    sword = weapon == "sword"
    bulky = "bulky" in f
    c.extra["blinks"] = "skull" not in f  # empty sockets do not blink
    # A slow breath: the upper body sinks one pixel for half of the six idle frames.
    bob = {"idle": (0, 0, 0, 1, 1, 1)[c.i % 6], "run": (0, 1, 0, 1)[c.i % 4]}.get(c.anim, 0)
    # Legs (in shadow tone), positions per animation.
    legs = {"run": ((-1, 1), (0, 0), (1, -1), (0, 0))[c.i % 4], "jump": (0, 0), "fall": (-1, 1),
            "attack": (-1, 1)}.get(c.anim, (0, 0))
    leg_h = {"jump": 1}.get(c.anim, 2)
    cv.rect(4 + legs[0], 13, 5 + legs[0], 13 + leg_h, r.shadow)
    cv.rect(7 + legs[1], 13, 8 + legs[1], 13 + leg_h, r.shadow)
    # Tail behind the body.
    if "tail" in f:
        wag = (0, -1)[c.i % 2] if c.anim in ("idle", "run") else 0
        cv.rect(1, 10 + bob + wag, 2, 11 + bob + wag, r.base)
        cv.set(0, 9 + bob + wag, r.light)
    if "cape" in f:  # hangs from the shoulders behind the back; flutters when running
        _cape(c, bob)
    # Body and arms (ogres and trolls are a pixel wider on each side).
    bx0, bx1 = (2, 9) if bulky else (3, 8)
    cv.rect(bx0, 8 + bob, bx1, 12 + bob, r.base)
    cv.rect(bx0, 11 + bob, bx1, 12 + bob, r.shadow)
    arm_y = 7 + bob if c.anim in ("jump", "fall") else 9 + bob
    cv.rect(bx0 - 1, arm_y, bx0 - 1, arm_y + 2, r.shadow)
    if atk and weapon in ("sword", "axe"):  # the weapon arm winds up, chops, follows through
        ax, ay = ((9, 6), (9, 8), (9, 10))[c.i % 3]
        cv.rect(ax, ay, ax, ay + 2, r.shadow)
    elif atk:  # reach out to shoot, thrust or cast
        cv.rect(bx1 + 1, arm_y + 1, 11, arm_y + 1, r.shadow)
        if weapon in (None, "staff"):
            cv.set(11, arm_y + 1, r.white if c.i == 1 else r.light)
    elif "zombie" in f and c.anim in ("idle", "run"):  # arms reach forward
        cv.rect(bx1 + 1, arm_y, 11, arm_y, r.shadow)
    else:
        cv.rect(bx1 + 1, arm_y, bx1 + 1, arm_y + 2, r.shadow)
    if "skull" in f:  # ribs and a spine show through
        for y in (9, 11):
            cv.rect(bx0 + 1, y + bob, bx1 - 1, y + bob, r.shadow)
        cv.rect(5, 8 + bob, 6, 12 + bob, r.base)
    if "zombie" in f:  # torn hem and a patch
        cv.set(bx0, 12 + bob, r.outline)
        cv.set(bx1 - 1, 12 + bob, r.outline)
        cv.set(bx0 + 2, 9 + bob, r.shadow)
    if "shield" in f:  # carried on the back arm, in front of the body
        _shield(c, bob)
    hair = HAIR
    if "hair" in f:  # long hair falls behind the head (the sprite faces right)
        cv.rect(1, 3 + bob, 3, 10 + bob, hair)
    # Head.
    cv.ellipse(6, 5 + bob, 4, 4, r.base, shade=r)
    if "hair" in f:
        cv.rect(3, 1 + bob, 8, 2 + bob, hair)
        cv.rect(2, 2 + bob, 3, 5 + bob, hair)
    if "crest" in f:  # a row of back plates over the head
        for x, y in ((3, 1), (5, 0), (7, 1)):
            cv.set(x, y + bob, r.light)
    if "ears" in f:
        cv.poly([(2.2, 3 + bob), (3.6, -0.2 + bob), (5, 2.5 + bob)], r.base)
        cv.poly([(7, 2.5 + bob), (8.4, -0.2 + bob), (9.8, 3 + bob)], r.base)
    if "long_ears" in f:
        cv.rect(4, -1 + bob, 4, 2 + bob, r.light)
        cv.rect(7, -1 + bob, 7, 2 + bob, r.light)
    if "horns" in f:
        cv.set(3, 1 + bob, r.white)
        cv.set(8, 1 + bob, r.white)
    if "helmet" in f:
        cv.rect(2, 1 + bob, 9, 3 + bob, (190, 196, 206, 255))
    if "hat" in f:
        cv.poly([(1.5, 3.5 + bob), (6, -4 + bob), (10.5, 3.5 + bob)], r.shadow)
    if "hood" in f:  # cloth over the crown and down the back of the head, face left open
        cv.rect(2, 1 + bob, 9, 2 + bob, r.shadow)
        cv.rect(2, 3 + bob, 4, 8 + bob, r.shadow)
        cv.set(9, 3 + bob, r.shadow)
    if "crown" in f:
        cv.rect(3, 1 + bob, 8, 2 + bob, CROWN)
        for x in (3, 5, 8):
            cv.set(x, 0 + bob, CROWN)
        cv.set(6, 2 + bob, JEWEL)
    if "skull" in f:  # empty sockets, a nose hole and teeth instead of eyes
        cv.rect(6, 4 + bob, 7, 5 + bob, r.eye)
        cv.rect(9, 4 + bob, 9, 5 + bob, r.eye)
        cv.set(8, 6 + bob, r.eye)
        for x in (6, 8):
            cv.set(x, 8 + bob, r.shadow)
    elif "mask" in f:
        cv.rect(2, 4 + bob, 10, 6 + bob, r.outline)
        ribbon = (0, 1)[c.i % 2] if c.anim == "run" else 0
        cv.set(1, 5 + bob, r.outline)
        cv.set(0, 6 + bob + ribbon, r.outline)
        if c.anim == "hurt":
            _eyes(c, [(7, 5 + bob), (9, 5 + bob)])
        else:  # eyes glint through the mask slit
            cv.set(7, 5 + bob, r.white)
            cv.set(9, 5 + bob, r.white)
    else:
        _eyes(c, [(7, 5 + bob), (9, 5 + bob)])
    if "beard" in f:  # from the cheek down over the chest, so it never reads as an open mouth
        cv.rect(6, 7 + bob, 9, 9 + bob, HAIR)
        cv.rect(7, 10 + bob, 9, 10 + bob, HAIR)
        cv.set(8, 11 + bob, HAIR)
    if "tusks" in f:
        cv.set(7, 8 + bob, r.white)
        cv.set(9, 8 + bob, r.white)
    if weapon == "sword":
        _sword(c, bob, arm_y)
    elif weapon is not None:
        WEAPONS[weapon](c, bob, arm_y)
    cv.outline(r.outline)


BLADE = (214, 220, 232, 255)
GRIP = (120, 76, 44, 255)


def _line(cv: Canvas, x0: int, y0: int, x1: int, y1: int, color: RGBA) -> None:
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for k in range(n + 1):
        cv.set(round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n), color)


def _sword(c: Ctx, bob: int, arm_y: int) -> None:
    """Held upright beside the body; during `attack` it is raised, chopped down and followed through."""
    cv = c.cv
    if c.anim == "attack":
        hx, hy, tx, ty = ((10, 6, 7, 0), (10, 8, 11, 12), (10, 10, 11, 15))[c.i % 3]
        _line(cv, hx, hy, tx, ty, BLADE)
        cv.set(hx, hy, GRIP)
        cv.set(hx + (1 if hx < 11 else 0), hy, GRIP)
        return
    cv.rect(11, 3 + bob, 11, 8 + bob, BLADE)
    cv.set(11, 2 + bob, c.r.white)
    cv.rect(10, 9 + bob, 11, 9 + bob, GRIP)
    cv.set(10, 10 + bob, GRIP)


# Fixed accent colours (snapped to the theme palette like everything else).
HAIR = (92, 52, 34, 255)
CROWN = (255, 204, 64, 255)
JEWEL = (222, 58, 84, 255)
CAPE = (176, 38, 56, 255)
WOOD = (150, 96, 52, 255)
STEEL = (176, 184, 198, 255)
MAGIC = (110, 214, 255, 255)
STRING = (232, 228, 214, 255)
BONE = "#e6dfc8"  # skeletons are bone-coloured whatever their entity colour
ZOMBIE = "#8fb070"  # pallid green skin

WEAPON_PRIORITY = ("sword", "axe", "spear", "bow", "staff")  # a hero holds one weapon


def held_weapon(feats: list[str]) -> str | None:
    return next((w for w in WEAPON_PRIORITY if w in feats), None)


def body_color(color: str, feats: list[str]) -> str:
    """Skeletons and zombies get their own skin; everyone else is drawn in the entity colour."""
    if "skull" in feats:
        return BONE
    if "zombie" in feats:
        return ZOMBIE
    return color


def _cape(c: Ctx, bob: int) -> None:
    cv = c.cv
    flutter = (0, 1, 0, 1)[c.i % 4] if c.anim == "run" else (1 if c.anim == "fall" else 0)
    cv.rect(1, 7 + bob, 3, 13, CAPE)
    cv.rect(1 - flutter, 11, 1, 14, CAPE)
    cv.set(3, 7 + bob, CAPE)


def _shield(c: Ctx, bob: int) -> None:
    cv = c.cv
    cv.rect(0, 8 + bob, 3, 12 + bob, WOOD)
    cv.rect(0, 8 + bob, 3, 8 + bob, STEEL)
    cv.rect(0, 12 + bob, 3, 12 + bob, STEEL)
    cv.rect(1, 10 + bob, 2, 10 + bob, STEEL)


def _bow(c: Ctx, bob: int, arm_y: int) -> None:
    """A tall bow in the front hand; during `attack` an arrow is nocked and loosed."""
    cv = c.cv
    for x, y in ((10, 4), (11, 5), (11, 6), (11, 7), (11, 8), (11, 9), (10, 10)):
        cv.set(x, y + bob, WOOD)
    cv.rect(10, 5 + bob, 10, 9 + bob, STRING)
    if c.anim == "attack" and c.i < 2:
        cv.rect(5 + 2 * c.i, arm_y + 1, 11, arm_y + 1, STEEL if c.i else STRING)


def _staff(c: Ctx, bob: int, arm_y: int) -> None:
    """A staff planted beside the hero, a glowing orb on top that flares when casting."""
    cv = c.cv
    cv.rect(11, 2 + bob, 11, 15, WOOD)
    glow = c.r.white if c.anim == "attack" and c.i == 1 else MAGIC
    cv.rect(10, 0 + bob, 11, 1 + bob, glow)


def _spear(c: Ctx, bob: int, arm_y: int) -> None:
    """Upright spear; during `attack` it is levelled and thrust forward."""
    cv = c.cv
    if c.anim == "attack":
        x0 = (4, 6, 5)[c.i % 3]
        cv.rect(x0, arm_y + 1, 10, arm_y + 1, WOOD)
        cv.rect(10, arm_y, 11, arm_y + 2, STEEL)
        cv.set(11, arm_y + 1, c.r.white)
        return
    cv.rect(11, 2 + bob, 11, 14, WOOD)
    cv.rect(11, 0 + bob, 11, 1 + bob, STEEL)
    cv.set(10, 1 + bob, STEEL)


def _axe(c: Ctx, bob: int, arm_y: int) -> None:
    """Short-handled axe; chopped like the sword during `attack`."""
    cv = c.cv
    if c.anim == "attack":
        hx, hy, tx, ty = ((10, 6, 8, 1), (10, 8, 11, 12), (10, 10, 11, 15))[c.i % 3]
        _line(cv, hx, hy, tx, ty, WOOD)
        cv.rect(tx - 1, ty - 1, tx, ty, STEEL)
        return
    cv.rect(10, 4 + bob, 10, 10 + bob, WOOD)
    cv.rect(11, 3 + bob, 11, 6 + bob, STEEL)
    cv.set(9, 4 + bob, STEEL)


WEAPONS = {"bow": _bow, "staff": _staff, "spear": _spear, "axe": _axe}


def paint_slime(c: Ctx) -> None:
    cv, r, f = c.cv, c.r, c.feats
    w, h = cv.w, cv.h
    sq = {"idle": ((0, 0), (1, -1))[c.i % 2], "run": ((0, 0), (1, -1), (0, 0), (-1, 1))[c.i % 4],
          "jump": (-2, 2), "fall": (-1, 1), "hurt": (2, -2)}[c.anim]
    rx, ry = w / 2 - 1 + sq[0] * 0.6, h * 0.55 - 0.5 + sq[1] * 0.7
    cy = h - ry
    cv.ellipse(w / 2, cy, rx, ry, r.base, shade=r)
    cv.rect(w / 2 - rx + 1, h - 2, w / 2 + rx - 2, h - 2, r.shadow)
    if "spots" in f:
        top = int(h - 2 * ry) + 2
        for _ in range(3):  # same rng sequence every frame, so spots stay put
            x, dy = c.rng.randint(3, w - 5), c.rng.random()
            cv.set(x, top + dy * max(0, h - 3 - top), r.shadow)
    if "horns" in f:
        cv.set(w / 2 - 2, h - 2 * ry - 1, r.white)
        cv.set(w / 2 + 2, h - 2 * ry - 1, r.white)
    if "antenna" in f:
        cv.rect(w / 2, h - 2 * ry - 2, w / 2, h - 2 * ry, r.shadow)
        cv.set(w / 2, h - 2 * ry - 3, r.light)
    ey = int(round(h - ry - 0.5))
    eyes = [(int(w / 2) + 3, ey)] if c.extra.get("one_eye") else [(int(w / 2) + 1, ey), (int(w / 2) + 4, ey)]
    _eyes(c, eyes, big=True)
    cv.outline(r.outline)


def paint_hopper(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    up = {"jump": 2, "fall": 1}.get(c.anim, (0, 1)[c.i % 2] if c.anim == "idle" else 0)
    # Back legs
    if c.anim in ("jump", "fall"):
        cv.rect(1, h - 4, 3, h - 1, r.shadow)
        cv.rect(w - 4, h - 4, w - 2, h - 1, r.shadow)
    else:
        cv.rect(0, h - 3, 3, h - 1, r.shadow)
        cv.rect(w - 4, h - 3, w - 1, h - 1, r.shadow)
    cv.ellipse(w / 2, h - 4.5 - up, w / 2 - 1.5, 3.8, r.base, shade=r)
    # Eye bumps
    cv.ellipse(w / 2 - 2.5, h - 8.5 - up, 2, 2, r.base)
    cv.ellipse(w / 2 + 2.5, h - 8.5 - up, 2, 2, r.base)
    _eyes(c, [(int(w / 2) - 2, int(h - 8.5 - up)), (int(w / 2) + 3, int(h - 8.5 - up))], big=True)
    cv.rect(w / 2 - 2, h - 3 - up, w / 2 + 3, h - 3 - up, r.shadow)  # mouth
    cv.outline(r.outline)


def paint_flyer(c: Ctx) -> None:
    cv, r, f = c.cv, c.r, c.feats
    w, h = cv.w, cv.h
    flap = (0, 1, 2, 1)[c.i % 4] if c.anim in ("idle", "run") else 1
    bob = (0, 1)[c.i % 2]
    if "ghost" in f:
        cv.ellipse(w / 2, h / 2 + bob - 1, w / 2 - 2, h / 2 - 1, r.light, shade=r)
        for x in range(3, w - 3, 2):
            cv.set(x, h - 2 + bob, r.light)
    else:
        wing_y = [h / 2 - 3, h / 2 - 1, h / 2 + 1][flap]
        cv.poly([(w / 2 - 2, h / 2 + bob), (0.5, wing_y + bob), (2.5, h / 2 + 2 + bob)], r.shadow)
        cv.poly([(w / 2 + 2, h / 2 + bob), (w - 0.5, wing_y + bob), (w - 2.5, h / 2 + 2 + bob)], r.shadow)
        cv.ellipse(w / 2, h / 2 + bob, 3.5, 3.2, r.base, shade=r)
        if "beak" in f:
            cv.set(w / 2 + 4, h / 2 + bob, (255, 196, 64, 255))
    _eyes(c, [(int(w / 2) + 1, int(h / 2 + bob) - 1), (int(w / 2) + 3, int(h / 2 + bob) - 1)])
    cv.outline(r.outline)


def paint_robot(c: Ctx) -> None:
    cv, r, f = c.cv, c.r, c.feats
    w, h = cv.w, cv.h
    bob = (0, 1)[c.i % 2] if c.anim in ("idle", "run") else 0
    # Treads
    cv.rect(1, h - 3, w - 2, h - 1, r.outline)
    for x in range(1 + (c.i % 2 if c.anim == "run" else 0), w - 1, 2):
        cv.set(x, h - 2, r.shadow)
    cv.rect(1, 3 + bob, w - 2, h - 4 + bob, r.base)
    cv.rect(1, h - 6 + bob, w - 2, h - 4 + bob, r.shadow)
    cv.rect(2, 4 + bob, w - 3, 4 + bob, r.light)
    # Visor
    cv.rect(w / 2 - 1, 6 + bob, w - 2, 7 + bob, r.outline)
    if c.anim == "hurt":
        cv.rect(w / 2, 6 + bob, w - 3, 7 + bob, (255, 80, 80, 255))
    else:
        blink = c.anim == "idle" and c.i % 2 == 1
        cv.rect(w - 4, 6 + bob, w - 3, 7 + bob, r.white if not blink else r.light)
    cv.rect(4, bob, 4, 2 + bob, r.shadow)  # robots always get an antenna
    cv.set(4, bob - 1, (255, 90, 90, 255) if c.i % 2 else r.light)
    cv.outline(r.outline)


def paint_turret(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    metal, metal_dark = (170, 172, 190, 255), (96, 98, 118, 255)
    recoil = 1 if c.anim == "hurt" else 0
    # Barrel first (pointing right), then the head over its base.
    cv.rect(6 - recoil, 5, w - 2 - recoil, 6, metal)
    cv.rect(6 - recoil, 7, w - 2 - recoil, 7, metal_dark)
    cv.rect(w - 2 - recoil, 4, w - 2 - recoil, 7, metal_dark)
    cv.poly([(1, h - 0.5), (w - 3, h - 0.5), (w - 5, h - 4), (3, h - 4)], r.shadow)
    cv.ellipse(5.5, 7.5, 4.2, 4.2, r.base, shade=r)
    light = (255, 80, 80, 255) if c.i % 2 else r.light
    cv.set(4, 6, light)
    cv.outline(r.outline)


def paint_bug(c: Ctx) -> None:
    cv, r, f = c.cv, c.r, c.feats
    w, h = cv.w, cv.h
    step = c.i % 2 if c.anim == "run" else 0
    for k, x in enumerate((3, 6, 9)):
        off = 1 if (k + step) % 2 else 0
        cv.rect(x - off, 1, x - off, 3, r.outline)
        cv.rect(x + off - 1, h - 4, x + off - 1, h - 2, r.outline)
    cv.ellipse(w / 2 - 1, h / 2, 4.5, 3.2, r.base, shade=r)
    cv.ellipse(w - 3.5, h / 2, 2.3, 2.2, r.shadow)
    cv.rect(w / 2 - 1, h / 2 - 3, w / 2 - 1, h / 2 + 2, r.shadow)
    if "antenna" in f:
        cv.set(w - 1, h / 2 - 3, r.outline)
        cv.set(w - 1, h / 2 + 2, r.outline)
    _eyes(c, [(w - 2, int(h / 2) - 1)])
    cv.outline(r.outline)


def paint_coin(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    widths = (3.5, 2.8, 1.6, 0.8, 1.6, 2.8)
    rx = widths[c.i % len(widths)]
    cv.ellipse(w / 2, h / 2, rx, h / 2 - 0.5, r.base, shade=r)
    if rx > 1.5:
        cv.rect(w / 2, h / 2 - 1, w / 2, h / 2 + 1, r.shadow)
    cv.outline(r.outline)


def _star_points(cx: float, cy: float, ro: float, ri: float) -> list[tuple[float, float]]:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rad = ro if k % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    return pts


def paint_star(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    s = (1.0, 0.92, 1.0, 1.06)[c.i % 4]
    cv.poly(_star_points(w / 2, h / 2 + 0.3, (w / 2 - 0.5) * s, (w / 4.2) * s), r.base)
    cv.set(w / 2 - 1, h / 2 - 1, r.light)
    cv.set(w / 2, h / 2 + 2, r.shadow)
    cv.outline(r.outline)
    if c.i % 4 == 3:
        cv.set(w - 1, 0, r.white)


def paint_gem(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cv.poly([(w / 2, 0.5), (w - 0.5, h / 3), (w / 2, h - 0.5), (0.5, h / 3)], r.base)
    cv.poly([(w / 2, 0.5), (w / 2, h - 0.5), (0.5, h / 3)], r.light)
    cv.rect(1, h / 3, w - 2, h / 3, r.shadow)
    cv.outline(r.outline)
    sparkle = c.i % 4
    if sparkle == 1:
        cv.set(1, 1, r.white)
    elif sparkle == 3:
        cv.set(w - 2, h - 3, r.white)


def paint_heart(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    s = (0.0, 0.4)[c.i % 2]
    cv.ellipse(w / 2 - 1.8, 2.8, 2.2 + s, 2.2 + s, r.base, shade=r)
    cv.ellipse(w / 2 + 1.8, 2.8, 2.2 + s, 2.2 + s, r.base, shade=r)
    cv.poly([(0.5 - s, 3.5), (w - 0.5 + s, 3.5), (w / 2, h - 0.2 + s)], r.base)
    cv.set(2, 2, r.white)
    cv.outline(r.outline)


def paint_orb(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cv.ellipse(w / 2, h / 2, w / 2 - 1, h / 2 - 1, r.base, shade=r)
    cv.set(w / 2 - 1 + (c.i % 2), h / 2 - 2, r.white)
    cv.outline(r.outline)


def paint_exit(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cv.ellipse(w / 2, w / 2, w / 2 - 0.5, w / 2 - 0.5, r.base)
    cv.rect(0.5, w / 2, w - 1.5, h - 1, r.base)
    cv.ellipse(w / 2, w / 2 + 1, w / 2 - 2.5, w / 2 - 2.5, (20, 16, 36, 255))
    cv.rect(2.5, w / 2 + 1, w - 3.5, h - 1, (20, 16, 36, 255))
    rng = random.Random(c.i)
    for _ in range(4):
        cv.set(rng.randint(3, w - 4), rng.randint(4, h - 2), r.light)
    cv.outline(r.outline)


def paint_portal(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cv.ellipse(w / 2, h / 2, w / 2 - 0.5, h / 2 - 0.5, r.shadow)
    cv.ellipse(w / 2, h / 2, w / 2 - 3, h / 2 - 3, (20, 16, 36, 255))
    for k in range(4):
        a = c.i * math.pi / 8 + k * math.pi / 2
        for t in range(3):
            rad = w / 2 - 2 - t * 2.2
            cv.set(w / 2 + math.cos(a + t * 0.6) * rad, h / 2 + math.sin(a + t * 0.6) * rad, r.light)
    cv.outline(r.outline)


def paint_spikes(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    teeth = 3
    tw = w / teeth
    for k in range(teeth):
        x0 = k * tw
        cv.poly([(x0 + 0.2, h), (x0 + tw / 2, 0.3), (x0 + tw - 0.2, h)], r.base)
        cv.rect(x0 + tw / 2, 2, x0 + tw / 2, h - 1, r.light)
    cv.outline(r.outline)


def paint_bullet(c: Ctx) -> None:
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cv.ellipse(w / 2, h / 2, w / 2, h / 2, r.light)
    cv.set(w / 2 - 1 + (c.i % 2), h / 2 - 1, r.white)


def paint_slash(c: Ctx) -> None:
    """A crescent swipe pointing right (projectiles rotate to their direction); it thins out as it fades."""
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    cx, cy, ro = w * 0.15, h / 2, w * 0.82
    inner = ro * (0.62 + 0.12 * c.i)
    for y in range(h):
        for x in range(w):
            dx, dy = x + 0.5 - cx, (y + 0.5 - cy) * (w / h) * 1.35
            d_out = math.hypot(dx / ro, dy / ro)
            d_in = math.hypot((x + 0.5 - cx + ro * 0.32) / inner, dy / inner)
            if d_out <= 1.0 and d_in > 1.0 and dx > -0.5:
                cv.set(x, y, r.white if d_out > 0.86 else r.light)
    cv.outline(r.outline)


def paint_ship(c: Ctx) -> None:
    """A fighter facing right: swept wings, a cockpit and an engine flame that flickers."""
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    hurt = c.anim == "hurt"
    hull = r.white if hurt else r.base
    cv.poly([(1.5, 0.2), (10.5, 3.4), (4.8, 3.6)], r.shadow)  # upper wing
    cv.poly([(1.5, h - 0.2), (10.5, h - 3.4), (4.8, h - 3.6)], r.shadow)  # lower wing
    cv.poly([(3, 3.3), (12, 2.4), (w - 0.5, h / 2), (12, h - 2.4), (3, h - 3.3)], hull)
    cv.rect(4, h / 2 + 1, 11, h / 2 + 1, r.shadow)  # a darker belly line
    cv.ellipse(10.6, h / 2 - 0.9, 2.0, 1.3, r.light)  # cockpit
    cv.set(10, h / 2 - 1.8, r.white)
    flame = 1 + c.i % 2
    for x in range(3 - flame - 1, 3):
        cv.set(x, h / 2 - 1, (255, 190, 60, 255))
        cv.set(x, h / 2, (255, 120, 40, 255))
    cv.outline(r.outline)


def paint_ufo(c: Ctx) -> None:
    """A flying saucer with a glass dome and blinking rim lights."""
    cv, r = c.cv, c.r
    w, h = cv.w, cv.h
    hurt = c.anim == "hurt"
    cv.ellipse(w / 2, 3.8, 3.4, 2.8, (170, 215, 240, 255) if not hurt else r.white)  # the dome first
    cv.ellipse(w / 2, h - 3.4, w / 2 - 0.5, 2.4, r.white if hurt else r.base, shade=r)  # then the disc over its base
    cv.set(w / 2 - 1, 2, r.white)
    for k, x in enumerate((2, 5, 8, 11)):
        cv.set(x, h - 4, (255, 236, 120, 255) if (k + c.i) % 2 == 0 else r.shadow)
    cv.rect(w / 2 - 2, h - 1, w / 2 + 1, h - 1, r.shadow)
    cv.outline(r.outline)


KINDS: dict[str, Kind] = {
    "hero": Kind((12, 16), {"idle": (6, 4, True), "run": (4, 10, True), "jump": (1, 1, False),
                            "fall": (1, 1, False), "hurt": (1, 1, False)}, paint_hero, "bottom"),
    "slime": Kind((14, 10), {"idle": (2, 3, True), "run": (4, 8, True), "jump": (1, 1, False),
                             "fall": (1, 1, False), "hurt": (1, 1, False)}, paint_slime, "bottom"),
    "hopper": Kind((13, 11), {"idle": (2, 2, True), "run": (2, 6, True), "jump": (1, 1, False),
                              "fall": (1, 1, False), "hurt": (1, 1, False)}, paint_hopper, "bottom"),
    "flyer": Kind((14, 10), {"idle": (4, 10, True), "run": (4, 14, True), "hurt": (1, 1, False)}, paint_flyer),
    "robot": Kind((13, 13), {"idle": (2, 2, True), "run": (2, 8, True), "hurt": (1, 1, False)}, paint_robot, "bottom"),
    "turret": Kind((14, 14), {"idle": (2, 2, True), "hurt": (1, 1, False)}, paint_turret, "bottom"),
    "bug": Kind((12, 12), {"idle": (2, 3, True), "run": (2, 10, True), "hurt": (1, 1, False)}, paint_bug),
    "coin": Kind((7, 7), {"idle": (6, 10, True)}, paint_coin),
    "star": Kind((9, 9), {"idle": (4, 6, True)}, paint_star),
    "gem": Kind((7, 9), {"idle": (4, 4, True)}, paint_gem),
    "heart": Kind((8, 7), {"idle": (2, 3, True)}, paint_heart),
    "orb": Kind((8, 8), {"idle": (2, 3, True)}, paint_orb),
    "door": Kind((9, 63), {"idle": (1, 1, False)}, None, "bottom"),  # painted by items.py
    "exit": Kind((14, 24), {"idle": (3, 6, True)}, paint_exit, "bottom"),
    "portal": Kind((20, 20), {"idle": (4, 8, True)}, paint_portal),
    "spikes": Kind((15, 7), {"idle": (1, 1, False)}, paint_spikes, "bottom"),
    "bullet": Kind((4, 4), {"idle": (2, 12, True)}, paint_bullet),
    "slash": Kind((10, 16), {"idle": (3, 20, False)}, paint_slash),
    "ship": Kind((16, 10), {"idle": (2, 10, True), "hurt": (1, 1, False)}, paint_ship),
    "ufo": Kind((14, 10), {"idle": (3, 8, True), "hurt": (1, 1, False)}, paint_ufo),
    # chibi creatures, painted natively at the fine size by creatures.py
    "beast": Kind((16, 12), {"idle": (2, 3, True), "run": (4, 10, True), "jump": (1, 1, False), "fall": (1, 1, False),
                             "hurt": (1, 1, False)}, None, "bottom"),
    "spider": Kind((16, 11), {"idle": (2, 3, True), "run": (4, 12, True), "jump": (1, 1, False), "fall": (1, 1, False),
                              "hurt": (1, 1, False)}, None, "bottom"),
    "dragon": Kind((18, 14), {"idle": (4, 8, True), "run": (4, 12, True), "hurt": (1, 1, False)}, None),
    "ghost": Kind((12, 14), {"idle": (4, 6, True), "run": (4, 8, True), "hurt": (1, 1, False)}, None),
    "snake": Kind((16, 8), {"idle": (2, 3, True), "run": (4, 8, True), "jump": (1, 1, False), "fall": (1, 1, False),
                            "hurt": (1, 1, False)}, None, "bottom"),
    # more chibi monsters, painted natively at the fine size by monsters.py
    "plant": Kind((14, 16), {"idle": (4, 6, True), "run": (4, 8, True), "hurt": (1, 1, False)}, None, "bottom"),
    "mushroom": Kind((14, 14), {"idle": (2, 3, True), "run": (4, 8, True), "jump": (1, 1, False), "fall": (1, 1, False),
                                "hurt": (1, 1, False)}, None, "bottom"),
    "reaper": Kind((14, 16), {"idle": (4, 5, True), "run": (4, 8, True), "hurt": (1, 1, False)}, None),
    "flame": Kind((12, 14), {"idle": (4, 8, True), "run": (4, 10, True), "hurt": (1, 1, False)}, None, "bottom"),
    "snail": Kind((16, 12), {"idle": (2, 3, True), "run": (4, 5, True), "jump": (1, 1, False), "fall": (1, 1, False),
                             "hurt": (1, 1, False)}, None, "bottom"),
    "alien": Kind((12, 16), {"idle": (2, 3, True), "run": (4, 10, True), "jump": (1, 1, False), "fall": (1, 1, False),
                             "hurt": (1, 1, False)}, None, "bottom"),
    # chibi items and decorative props, painted natively by items.py
    "key": Kind((8, 8), {"idle": (4, 6, True)}, None),
    "potion": Kind((8, 10), {"idle": (4, 6, True)}, None),
    "scroll": Kind((9, 8), {"idle": (2, 3, True)}, None),
    "bomb": Kind((9, 9), {"idle": (4, 12, True)}, None),
    "chest": Kind((12, 10), {"idle": (4, 4, True)}, None, "bottom"),
    "arrow": Kind((10, 4), {"idle": (1, 1, True)}, None),
    "tree": Kind((16, 24), {"idle": (4, 2, True)}, None, "bottom"),
    "bush": Kind((14, 8), {"idle": (2, 2, True)}, None, "bottom"),
    "rock": Kind((12, 8), {"idle": (1, 1, True)}, None, "bottom"),
}


# --- the fine (SNES-like) style: the same art at twice the resolution ----------------------------

def _epx(f: np.ndarray) -> np.ndarray:
    """Scale2x / EPX: doubles the resolution and smooths diagonal steps without blurring anything."""
    h, w = f.shape[:2]
    p = np.ascontiguousarray(f).view(np.uint32).reshape(h, w)
    pad = np.pad(p, 1, mode="edge")
    a, b, c, d = pad[:-2, 1:-1], pad[1:-1, 2:], pad[1:-1, :-2], pad[2:, 1:-1]
    out = np.empty((h * 2, w * 2), np.uint32)
    out[0::2, 0::2] = np.where((c == a) & (c != d) & (a != b), a, p)
    out[0::2, 1::2] = np.where((a == b) & (a != c) & (b != d), b, p)
    out[1::2, 0::2] = np.where((d == c) & (d != b) & (c != a), c, p)
    out[1::2, 1::2] = np.where((b == d) & (b != a) & (d != c), d, p)
    return out.view(np.uint8).reshape(h * 2, w * 2, 4)


def refine(f: np.ndarray, outline: RGBA) -> np.ndarray:
    """A 1x frame without an outline -> a 2x frame: smoothed, lit from the top left, with a thin outline."""
    g = _epx(f)
    a = g[..., 3] > 0
    pad = np.pad(a, 1)
    up, down, left, right = pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]
    lit = a & (~up | ~left) & ~(~down | ~right)  # the rim facing the light, unless the part is one pixel thin
    shadow = a & (~down | ~right) & ~(~up | ~left)
    rgb = g[..., :3].astype(np.float32)
    rgb[lit] = rgb[lit] * 0.78 + 255 * 0.22
    rgb[shadow] *= 0.78
    g = g.copy()
    g[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    ring = (up | down | left | right) & ~a
    g[ring] = outline
    return g


# Animations a painter draws itself (on top of the kind's own), and the kinds that get a derived attack pulse.
DRAWN_EXTRA: dict[str, dict[str, tuple[int, float, bool]]] = {"hero": {"attack": (3, 14, False)}}
NATIVE = {**creatures.PAINTERS, **items.PAINTERS, **monsters.PAINTERS}  # kinds painted at the fine size (coarse = 2:1 shrink)
ATTACKERS = {"hero", "slime", "hopper", "flyer", "robot", "bug", "beast", "spider", "dragon", "ghost", "snake"}
DERIVED = {"attack": (3, 14.0, False), "die": (5, 10.0, False)}


def add_derived(kind: str, frames: dict[str, list[np.ndarray]], anims: dict[str, tuple[int, float, bool]],
                pixel: bool, anchor: str, flash_color: tuple[int, int, int], seed: int) -> tuple[dict, dict]:
    """Adds `attack` (for fighters) and `die` (for anything that can be hurt) built from the painted frames.
    Returns the fps and loop tables for build_sheet."""
    if "attack" not in frames and kind in ATTACKERS and "idle" in frames:
        frames["attack"] = motion.attack_frames(frames["idle"][0], anchor, pixel)
    if "die" not in frames and "hurt" in frames:
        # Pixel art dies from the hurt pose (closed, crossed eyes); the cartoon hurt frame is washed out by its flash.
        body = frames["hurt"][0] if pixel else frames["idle"][0]
        frames["die"] = motion.die_frames(body, anchor, pixel, flash_color, seed % 1000)
    table = {**anims, **{k: v for k, v in DERIVED.items() if k in frames and k not in anims}}
    return {a: v[1] for a, v in table.items()}, {a: v[2] for a, v in table.items()}


def generate(name: str, kind: str, color: str, features: list[str] | None = None, seed: int = 0,
             scale: int = 2, palette: str | None = None, fine: bool = False) -> SpriteSet:
    """`fine` draws the same art at twice the resolution (SNES-like) at the same on-screen size."""
    if kind not in KINDS:
        raise ValueError(f"unknown sprite kind '{kind}'")
    spec = KINDS[kind]
    feats = list(features) if features is not None else features_for(name)
    rng_seed = zlib.crc32(f"{name}:{kind}:{seed}".encode())
    extra = {"one_eye": random.Random(rng_seed).random() < 0.3}
    if kind == "slime" and random.Random(rng_seed + 1).random() < 0.5 and "spots" not in feats:
        feats.append("spots")
    pal = palettes.get(palette)
    r = ramp(body_color(color, feats) if kind == "hero" else color, pal)
    anims = {**spec.anims, **DRAWN_EXTRA.get(kind, {})}
    if kind in NATIVE:
        frames = creatures.frames(kind, name, color, feats, seed, pal, spec.size, anims, fine, NATIVE[kind])
        flash_color = tuple(int(x) for x in pal.rgb[pal.light]) if pal else motion.FLASH
        fps, loop = add_derived(kind, frames, anims, True, spec.anchor, flash_color, rng_seed)
        if pal:
            for name_ in ("attack", "die"):
                if name_ in frames:
                    frames[name_] = [pal.snap(f) for f in frames[name_]]
        sheet, anim_set = build_sheet(frames, fps, loop)
        size = (spec.size[0] * 2, spec.size[1] * 2) if fine else spec.size
        return finalize(name, sheet, size, anim_set, 1 if fine else scale, spec.anchor)
    if kind == "hero" and fine and chibi.is_human(feats):
        # People get the detailed front-facing chibi, drawn natively at the fine size.
        frames = chibi.frames(name, color, feats, seed, pal, held_weapon(feats))
        flash_color = tuple(int(x) for x in pal.rgb[pal.light]) if pal else motion.FLASH
        fps, loop = add_derived(kind, frames, anims, True, spec.anchor, flash_color, rng_seed)
        if pal and "die" in frames:
            frames["die"] = [pal.snap(f) for f in frames["die"]]
        sheet, anim_set = build_sheet(frames, fps, loop)
        return finalize(name, sheet, (chibi.W, chibi.H), anim_set, 1, spec.anchor)
    frames: dict[str, list[np.ndarray]] = {}
    for anim, (n, _fps, _loop) in anims.items():
        frames[anim] = []
        for i in range(n):
            cv = Canvas(*spec.size)
            cv.skip_outline = fine
            spec.paint(Ctx(cv, r, feats, anim, i, random.Random(rng_seed), extra))
            frame = refine(cv.copy(), r.outline) if fine else cv.copy()
            frames[anim].append(pal.snap(frame) if pal else frame)  # hard-coded colours join the palette
    flash_color = tuple(int(x) for x in pal.rgb[pal.light]) if pal else motion.FLASH
    fps, loop = add_derived(kind, frames, anims, True, spec.anchor, flash_color, rng_seed)
    if pal:
        for name_ in ("attack", "die"):  # derived frames may hold blended colours
            if name_ in frames:
                frames[name_] = [pal.snap(f) for f in frames[name_]]
    sheet, anim_set = build_sheet(frames, fps, loop)
    size = (spec.size[0] * 2, spec.size[1] * 2) if fine else spec.size
    return finalize(name, sheet, size, anim_set, 1 if fine else scale, spec.anchor)
