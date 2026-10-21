"""Card game art: the card frames (one per card type) and the 16 px icons on cards, intents and map rooms, drawn
from code like the rest of the pixel art. Cards are shown at 2 or 3 screen pixels per art pixel.

    card_frame(kind)  -> 56x78 RGBA card: coloured border, name banner, art window, text panel
    icon(name)        -> 16x16 RGBA icon with a dark outline and a light rim (ICONS lists the names)
"""

from __future__ import annotations

import numpy as np

from .chibi import Fig

RGBA = tuple[int, int, int, int]
FRAME_W, FRAME_H = 56, 78


def _c(h: str, a: int = 255) -> RGBA:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


INK = _c("#1d1a33")
WHITE = _c("#fff8ec")
# card type -> (border dark, border, border light)
FRAME_COLORS = {"attack": ("#7a2430", "#c8463a", "#ee7a5a"), "skill": ("#1f3f7a", "#3a78c8", "#7ab8f0"),
                "power": ("#4a1f7a", "#9a4ac8", "#c890f0")}
PARCHMENT, PARCHMENT_DARK = _c("#f0dcb0"), _c("#d0b080")
WINDOW, WINDOW_LIGHT = _c("#2b2650"), _c("#3a3366")


def card_frame(kind: str) -> np.ndarray:
    """A blank card of one type; the name, icon, cost and text are laid over it in the game."""
    dark, mid, light = (_c(x) for x in FRAME_COLORS.get(kind, FRAME_COLORS["attack"]))
    g = Fig(FRAME_W, FRAME_H)
    w, h = FRAME_W, FRAME_H
    g.rect(0, 0, w - 1, h - 1, INK)
    g.rect(1, 1, w - 2, h - 2, mid)
    g.rect(1, 1, w - 2, 1, light)          # bevel: lit top and left, dark bottom and right
    g.rect(1, 1, 1, h - 2, light)
    g.rect(1, h - 2, w - 2, h - 2, dark)
    g.rect(w - 2, 1, w - 2, h - 2, dark)
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):  # rounded corners
        g.px[y, x] = (0, 0, 0, 0)
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
        g.px[y, x] = INK
    # the name banner
    g.rect(4, 4, w - 5, 13, INK)
    g.rect(5, 5, w - 6, 12, dark)
    g.rect(5, 5, w - 6, 5, mid)
    # the art window, with a soft light at the top
    g.rect(5, 15, w - 6, 42, INK)
    g.rect(6, 16, w - 7, 41, WINDOW)
    for y in range(16, 26):
        for x in range(6, w - 6):
            if (x + y) % 2 == 0 and y < 22:
                g.px[y, x] = WINDOW_LIGHT
    # the text panel
    g.rect(4, 45, w - 5, h - 5, INK)
    g.rect(5, 46, w - 6, h - 6, PARCHMENT)
    g.rect(5, h - 6, w - 6, h - 6, PARCHMENT_DARK)
    g.rect(w - 6, 46, w - 6, h - 6, PARCHMENT_DARK)
    # rivets
    for x, y in ((3, 43), (w - 4, 43)):
        g.px[y, x] = light
    return g.px


def _ring(g: Fig) -> None:
    """A dark outline round the drawing, then a light rim (reads on dark and light backgrounds)."""
    for col in (INK, WHITE):
        a = g.px[..., 3] > 0
        p = np.pad(a, 1)
        ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
        g.px[ring] = col


STEEL, STEEL_LIGHT, STEEL_DARK = _c("#c8d0e0"), _c("#f0f4ff"), _c("#7a849a")
WOOD, WOOD_DARK = _c("#9a6238"), _c("#6a3e24")
GOLD, GOLD_DARK, GOLD_LIGHT = _c("#ffcc40"), _c("#c88a20"), _c("#fff0a0")
RED, RED_DARK, RED_LIGHT = _c("#e83a3a"), _c("#a01e2a"), _c("#ff8a7a")
GREEN, GREEN_DARK, GREEN_LIGHT = _c("#5cd84a"), _c("#2c8a3c"), _c("#b4f08a")
BLUE, BLUE_DARK, BLUE_LIGHT = _c("#3a8ae8"), _c("#1f4f9a"), _c("#9ad4ff")
PURPLE, PURPLE_LIGHT = _c("#9a4ac8"), _c("#d8a8ff")
ORANGE, YELLOW = _c("#ff8a2a"), _c("#ffe040")
BONE, BONE_DARK = _c("#f0ead8"), _c("#b8b0a0")


def _sword(g: Fig) -> None:
    g.line(3, 12, 11, 4, STEEL, 2)
    g.line(4, 12, 12, 4, STEEL_DARK)
    g.line(3, 11, 10, 4, STEEL_LIGHT)
    g.rect(12, 2, 13, 3, STEEL_LIGHT)
    g.line(2, 9, 6, 13, GOLD, 1)         # cross guard
    g.line(2, 10, 5, 13, GOLD_DARK)
    g.rect(1, 13, 2, 14, WOOD)           # grip and pommel
    g.set(1, 15, GOLD)


def _axe(g: Fig) -> None:
    g.line(4, 14, 11, 3, WOOD, 2)
    g.ellipse(10, 5, 4.5, 3.6, STEEL)
    g.ellipse(9, 4, 2.6, 1.6, STEEL_LIGHT)
    g.rect(11, 6, 13, 7, STEEL_DARK)


def _dagger(g: Fig) -> None:
    g.poly([(7, 1), (9, 1), (9, 9), (8, 11), (7, 9)], STEEL)
    g.rect(7, 1, 7, 9, STEEL_LIGHT)
    g.rect(4, 10, 12, 11, GOLD)
    g.rect(7, 12, 9, 14, WOOD)
    g.rect(7, 15, 9, 15, GOLD_DARK)


def _shield(g: Fig) -> None:
    g.poly([(2, 2), (14, 2), (14, 8), (8, 15), (2, 8)], BLUE)
    g.poly([(4, 4), (12, 4), (12, 8), (8, 13), (4, 8)], BLUE_DARK)
    g.rect(7, 3, 9, 13, GOLD)
    g.rect(3, 6, 13, 7, GOLD)
    g.rect(3, 3, 5, 3, BLUE_LIGHT)


def _bow(g: Fig) -> None:
    for k in range(13):
        y = 2 + k
        x = 4 + round(4 * (1 - ((y - 8.5) / 6.5) ** 2))
        g.set(x, y, WOOD)
        g.set(x - 1, y, WOOD_DARK)
    g.line(4, 2, 4, 14, WHITE)
    g.line(3, 8, 14, 8, STEEL_DARK)
    g.poly([(12, 6), (15, 8), (12, 10)], STEEL)


def _staff(g: Fig) -> None:
    g.line(4, 15, 10, 5, WOOD, 2)
    g.ellipse(11.5, 3.5, 3, 3, PURPLE)
    g.ellipse(10.8, 2.8, 1.2, 1.2, PURPLE_LIGHT)
    for x, y in ((5, 3), (14, 8), (8, 1)):
        g.set(x, y, YELLOW)


def _fire(g: Fig) -> None:
    g.poly([(8, 1), (13, 8), (12, 13), (8, 15), (4, 13), (3, 8), (6, 5), (7, 8)], ORANGE)
    g.poly([(8, 6), (11, 10), (10, 13), (8, 14), (6, 13), (5, 10)], YELLOW)
    g.ellipse(8, 12, 1.6, 1.6, WHITE)


def _ice(g: Fig) -> None:
    for a, b in (((8, 1), (8, 15)), ((2, 4), (14, 12)), ((2, 12), (14, 4))):
        g.line(a[0], a[1], b[0], b[1], BLUE_LIGHT, 1)
    g.ellipse(8, 8, 2.4, 2.4, WHITE)
    for x, y in ((8, 1), (8, 15), (2, 4), (14, 12), (2, 12), (14, 4)):
        g.set(x, y, WHITE)


def _bolt(g: Fig) -> None:
    g.poly([(9, 1), (3, 9), (8, 9), (6, 15), (13, 6), (8, 6), (11, 1)], YELLOW)
    g.line(9, 2, 5, 8, WHITE)


def _drop(g: Fig) -> None:
    g.poly([(8, 1), (12, 8), (4, 8)], GREEN)
    g.ellipse(8, 10, 4.6, 4.6, GREEN)
    g.ellipse(8, 11, 3, 3, GREEN_DARK)
    g.ellipse(6.5, 8.5, 1.2, 1.6, GREEN_LIGHT)


def _skull(g: Fig) -> None:
    g.ellipse(8, 7, 6, 5.5, BONE)
    g.rect(5, 11, 11, 14, BONE)
    g.ellipse(5.5, 7.5, 1.8, 2, INK)
    g.ellipse(10.5, 7.5, 1.8, 2, INK)
    g.rect(8, 10, 8, 11, BONE_DARK)
    for x in (6, 8, 10):
        g.rect(x, 13, x, 14, BONE_DARK)


def _heart(g: Fig) -> None:
    g.ellipse(5.5, 6, 3.6, 3.6, RED)
    g.ellipse(10.5, 6, 3.6, 3.6, RED)
    g.poly([(2, 7), (14, 7), (8, 14)], RED)
    g.ellipse(5, 5, 1.4, 1.2, RED_LIGHT)
    g.rect(10, 9, 12, 9, RED_DARK)


def _flex(g: Fig) -> None:
    """Strength: a raised fist with a flame of power."""
    g.poly([(8, 1), (11, 5), (10, 7), (6, 7), (5, 5)], ORANGE)
    g.poly([(8, 3), (9, 6), (7, 6)], YELLOW)
    g.rect(4, 8, 12, 13, _c("#f0b080"))
    g.rect(4, 8, 12, 8, _c("#ffd0a0"))
    for x in (6, 8, 10):
        g.rect(x, 8, x, 10, _c("#c88050"))
    g.rect(6, 14, 10, 15, _c("#c88050"))


def _book(g: Fig) -> None:
    g.rect(2, 3, 13, 13, PURPLE)
    g.rect(4, 4, 13, 12, WHITE)
    g.rect(2, 3, 3, 13, _c("#5a2a7a"))
    for y in (6, 8, 10):
        g.rect(6, y, 11, y, BONE_DARK)
    g.rect(9, 12, 10, 15, RED)


def _wind(g: Fig) -> None:
    for y, x0, x1 in ((4, 2, 11), (8, 1, 13), (12, 3, 10)):
        g.rect(x0, y, x1, y, WHITE)
        g.rect(x1, y - 1, x1 + 1, y - 1, WHITE)
    g.set(13, 2, BLUE_LIGHT)


def _star(g: Fig) -> None:
    from .generate import _star_points
    g.poly(_star_points(8, 8.5, 7, 3), GOLD)
    g.poly(_star_points(8, 8.5, 4, 1.8), GOLD_LIGHT)


def _campfire(g: Fig) -> None:
    g.line(2, 14, 13, 11, WOOD, 2)
    g.line(2, 11, 13, 14, WOOD_DARK, 2)
    g.poly([(8, 1), (12, 8), (11, 11), (5, 11), (4, 8), (7, 6)], ORANGE)
    g.poly([(8, 5), (10, 9), (8, 11), (6, 9)], YELLOW)


def _chest(g: Fig) -> None:
    g.rect(2, 7, 13, 14, WOOD)
    g.ellipse(8, 7, 6, 3.4, _c("#b47a48"))
    g.rect(2, 7, 13, 8, WOOD_DARK)
    g.rect(2, 7, 2, 14, GOLD)
    g.rect(13, 7, 13, 14, GOLD)
    g.rect(7, 8, 9, 11, GOLD)
    g.set(8, 10, INK)


def _crown(g: Fig) -> None:
    g.poly([(2, 5), (5, 9), (8, 3), (11, 9), (14, 5), (13, 13), (3, 13)], GOLD)
    g.rect(3, 11, 13, 13, GOLD_DARK)
    for x in (5, 8, 11):
        g.set(x, 12, RED)
    g.set(8, 3, GOLD_LIGHT)


ICONS = {"sword": _sword, "axe": _axe, "dagger": _dagger, "shield": _shield, "bow": _bow, "staff": _staff,
         "fire": _fire, "ice": _ice, "bolt": _bolt, "drop": _drop, "skull": _skull, "heart": _heart, "flex": _flex,
         "book": _book, "wind": _wind, "star": _star, "campfire": _campfire, "chest": _chest, "crown": _crown}


def icon(name: str) -> np.ndarray:
    g = Fig(16, 16)
    ICONS.get(name, _star)(g)
    _ring(g)
    return g.px
