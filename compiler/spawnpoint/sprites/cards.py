"""Card game art: the card frames (one per card type) and the 16 px icons on cards, intents and map rooms, drawn
from code like the rest of the pixel art. Cards are shown at 2 or 3 screen pixels per art pixel.

    card_frame(kind)  -> 56x78 RGBA card: coloured border, name banner, art window, text panel
    icon(name)        -> 16x16 RGBA icon with a dark outline and a light rim (ICONS lists the names)
"""

from __future__ import annotations

import math

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
FRAME_COLORS = {"attack": ("#6a2420", "#b8503a", "#e88a5a"), "skill": ("#1a4a44", "#3a8a7a", "#7ac8b0"),
                "power": ("#3a1a5a", "#8a4ab8", "#c890f0")}
PARCHMENT, PARCHMENT_DARK, PARCHMENT_LIGHT = _c("#f2e2bc"), _c("#d8c090"), _c("#fff4d8")
GEM, GEM_DARK, GEM_LIGHT = _c("#f0a030"), _c("#a85a18"), _c("#ffe08a")
# Where things go on the 56x78 card (the game lays the cost, icon, name and text over these).
LAYOUT = {"cost": (8, 8), "medallion": (28, 26, 14), "banner": (3, 43, 52, 52), "text": (5, 54, 50, 73)}


def card_frame(kind: str) -> np.ndarray:
    """A blank card of one type: parchment, a round medallion for the icon, a name ribbon and a cost socket."""
    dark, mid, light = (_c(x) for x in FRAME_COLORS.get(kind, FRAME_COLORS["attack"]))
    g = Fig(FRAME_W, FRAME_H)
    w, h = FRAME_W, FRAME_H
    g.rect(0, 0, w - 1, h - 1, INK)
    g.rect(1, 1, w - 2, h - 2, mid)
    g.rect(1, 1, w - 2, 1, light)
    g.rect(1, 1, 1, h - 2, light)
    g.rect(1, h - 2, w - 2, h - 2, dark)
    g.rect(w - 2, 1, w - 2, h - 2, dark)
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        g.px[y, x] = (0, 0, 0, 0)
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
        g.px[y, x] = INK
    # the parchment body with a soft grain
    g.rect(3, 3, w - 4, h - 4, PARCHMENT)
    rng = np.random.default_rng(5)
    grain = rng.random((h, w)) < 0.06
    body = np.zeros((h, w), bool)
    body[4:h - 4, 4:w - 4] = True
    g.px[grain & body] = PARCHMENT_DARK
    g.rect(3, 3, w - 4, 3, PARCHMENT_LIGHT)
    g.rect(3, h - 4, w - 4, h - 4, PARCHMENT_DARK)
    # the medallion: a type-coloured ring, a gold rim and a darker disc
    cx, cy, r = LAYOUT["medallion"]
    g.ellipse(cx, cy, r + 1.5, r + 1.5, INK)
    g.ellipse(cx, cy, r + 0.5, r + 0.5, mid)
    g.ellipse(cx - 0.6, cy - 0.6, r - 1, r - 1, light)
    g.ellipse(cx, cy, r - 1.5, r - 1.5, dark)
    g.ellipse(cx, cy, r - 2.5, r - 2.5, GEM_DARK)
    g.ellipse(cx, cy, r - 3.5, r - 3.5, _c("#e8d4a4"))
    g.ellipse(cx + 1, cy + 1, r - 5, r - 5, _c("#dcc494"))
    g.ellipse(cx - 2, cy - 2, r - 8, r - 8, _c("#f4e4bc"))
    # the name ribbon, with folded tails
    x0, y0, x1, y1 = LAYOUT["banner"]
    g.rect(x0 - 1, y0 + 2, x0 + 3, y1 + 2, dark)
    g.rect(x1 - 3, y0 + 2, x1 + 1, y1 + 2, dark)
    g.rect(x0 + 2, y0, x1 - 2, y1, INK)
    g.rect(x0 + 3, y0 + 1, x1 - 3, y1 - 1, mid)
    g.rect(x0 + 3, y0 + 1, x1 - 3, y0 + 1, light)
    g.rect(x0 + 3, y1 - 1, x1 - 3, y1 - 1, dark)
    # the text panel
    tx0, ty0, tx1, ty1 = LAYOUT["text"]
    g.rect(tx0, ty0, tx1, ty1, _c("#ead6a8"))
    g.rect(tx0, ty0, tx1, ty0, PARCHMENT_DARK)
    # the cost socket
    gx, gy = LAYOUT["cost"]
    g.ellipse(gx, gy, 7.5, 7.5, INK)
    g.ellipse(gx, gy, 6.5, 6.5, GEM_DARK)
    g.ellipse(gx - 0.5, gy - 0.5, 5.5, 5.5, GEM)
    g.ellipse(gx - 2, gy - 2, 2, 2, GEM_LIGHT)
    return g.px


def card_back() -> np.ndarray:
    """The back of a card (draw and discard piles): a dark teal field with a gold diamond."""
    w, h = 40, 56
    g = Fig(w, h)
    g.rect(0, 0, w - 1, h - 1, INK)
    g.rect(1, 1, w - 2, h - 2, _c("#2a5a5a"))
    g.rect(3, 3, w - 4, h - 4, _c("#1a3a40"))
    for y in range(4, h - 4):
        for x in range(4, w - 4):
            if (x + y) % 6 == 0:
                g.px[y, x] = _c("#24484e")
    g.poly([(w / 2, 10), (w - 9, h / 2), (w / 2, h - 10), (9, h / 2)], GOLD_DARK)
    g.poly([(w / 2, 13), (w - 12, h / 2), (w / 2, h - 13), (12, h / 2)], GOLD)
    g.ellipse(w / 2, h / 2, 4, 4, _c("#1a3a40"))
    g.ellipse(w / 2 - 1, h / 2 - 1, 1.5, 1.5, GOLD_LIGHT)
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        g.px[y, x] = (0, 0, 0, 0)
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


def _coin(g: Fig) -> None:
    g.ellipse(8, 8, 6.5, 6.5, GOLD_DARK)
    g.ellipse(7.5, 7.5, 5.5, 5.5, GOLD)
    g.rect(7, 4, 8, 11, GOLD_DARK)
    g.ellipse(6, 5, 1.4, 1.4, GOLD_LIGHT)


def _crack(g: Fig) -> None:
    """Vulnerable: a cracked shield."""
    _shield(g)
    g.line(9, 2, 6, 7, INK)
    g.line(6, 7, 10, 10, INK)
    g.line(10, 10, 7, 15, INK)


def _crown(g: Fig) -> None:
    g.poly([(2, 5), (5, 9), (8, 3), (11, 9), (14, 5), (13, 13), (3, 13)], GOLD)
    g.rect(3, 11, 13, 13, GOLD_DARK)
    for x in (5, 8, 11):
        g.set(x, 12, RED)
    g.set(8, 3, GOLD_LIGHT)


def _question(g: Fig) -> None:
    g.ellipse(8, 8, 7, 7, PURPLE)
    g.ellipse(7, 7, 5.5, 5.5, _c("#b070e0"))
    for x, y in ((6, 4), (7, 3), (8, 3), (9, 3), (10, 4), (10, 5), (9, 6), (8, 7), (8, 8)):
        g.rect(x, y, x, y, WHITE)
    g.rect(8, 10, 8, 11, WHITE)


def _bag(g: Fig) -> None:
    g.ellipse(8, 10, 6, 5, _c("#b47a48"))
    g.rect(6, 3, 10, 6, _c("#b47a48"))
    g.rect(5, 5, 11, 6, WOOD_DARK)
    g.ellipse(6, 9, 1.6, 1.6, _c("#d8a070"))
    g.ellipse(9, 11, 2.2, 2.2, GOLD)
    g.set(9, 11, GOLD_DARK)


def _hammer(g: Fig) -> None:
    g.line(4, 14, 10, 7, WOOD, 2)
    g.rect(7, 2, 14, 6, STEEL_DARK)
    g.rect(7, 2, 14, 3, STEEL)
    g.rect(13, 2, 14, 6, STEEL_LIGHT)


def _potion(g: Fig) -> None:
    """A white-liquid bottle: the game tints it with the potion's colour."""
    g.rect(6, 1, 9, 3, _c("#b07a48"))
    g.rect(6, 4, 9, 6, _c("#d8eef8"))
    g.ellipse(8, 11, 5.5, 4.8, _c("#d8eef8"))
    g.ellipse(8, 12, 4.4, 3.6, _c("#f8f8f8"))
    g.rect(5, 9, 5, 10, WHITE)


def _blood(g: Fig) -> None:
    g.poly([(8, 1), (13, 9), (3, 9)], RED)
    g.ellipse(8, 10, 5, 5, RED)
    g.ellipse(8, 11, 3, 3, RED_DARK)
    g.ellipse(6.5, 8.5, 1.2, 1.6, RED_LIGHT)


def _lantern(g: Fig) -> None:
    g.rect(7, 1, 8, 2, STEEL_DARK)
    g.rect(4, 3, 11, 4, STEEL_DARK)
    g.rect(5, 5, 10, 12, _c("#ffe080"))
    g.rect(7, 6, 8, 10, _c("#fff8c0"))
    g.rect(4, 13, 11, 14, STEEL_DARK)
    g.rect(4, 5, 4, 12, STEEL_DARK)
    g.rect(11, 5, 11, 12, STEEL_DARK)


def _ring_icon(g: Fig) -> None:
    g.ellipse(8, 9, 6, 6, GOLD)
    g.ellipse(8, 9, 3.6, 3.6, (0, 0, 0, 0))
    g.ellipse(8, 3.5, 2.6, 2.4, GREEN)
    g.set(7, 3, GREEN_LIGHT)


def _anchor(g: Fig) -> None:
    g.ellipse(8, 3, 2.2, 2.2, STEEL)
    g.ellipse(8, 3, 1, 1, (0, 0, 0, 0))
    g.rect(7, 5, 8, 13, STEEL)
    g.rect(4, 6, 11, 7, STEEL)
    g.line(2, 10, 7, 14, STEEL, 2)
    g.line(13, 10, 8, 14, STEEL, 2)


def _vajra(g: Fig) -> None:
    g.rect(7, 4, 8, 12, GOLD)
    g.ellipse(7.5, 8, 2.5, 2, GOLD_DARK)
    for y in (2, 14):
        g.line(4, y, 7, y + (2 if y == 2 else -2), GOLD)
        g.line(11, y, 8, y + (2 if y == 2 else -2), GOLD)
        g.set(7, y, GOLD_LIGHT)


def _marbles(g: Fig) -> None:
    g.ellipse(8, 10, 6, 5, _c("#7a5a9a"))
    g.rect(6, 4, 10, 6, _c("#7a5a9a"))
    for (x, y, c) in ((5, 2, BLUE), (9, 1, RED), (11, 3, GREEN)):
        g.ellipse(x, y + 1, 1.8, 1.8, c)


def _stone(g: Fig) -> None:
    g.ellipse(8, 9, 6.5, 5, _c("#9aa0b0"))
    g.ellipse(6.5, 7.5, 3, 1.8, _c("#c8ccd8"))
    g.set(11, 11, _c("#6a7080"))


def _idol(g: Fig) -> None:
    g.ellipse(8, 5, 3.6, 3.6, GOLD)
    g.rect(5, 8, 11, 14, GOLD)
    g.rect(4, 13, 12, 14, GOLD_DARK)
    g.set(7, 5, INK)
    g.set(9, 5, INK)
    g.ellipse(6, 4, 1, 1, GOLD_LIGHT)


def _flower(g: Fig) -> None:
    g.rect(7, 9, 8, 15, GREEN_DARK)
    g.ellipse(5, 12, 2.4, 1.4, GREEN)
    for a in range(5):
        g.ellipse(8 + 3.4 * math.cos(a * 1.257), 6 + 3.4 * math.sin(a * 1.257), 2.4, 2.4, _c("#ff8fc8"))
    g.ellipse(8, 6, 2, 2, YELLOW)


def _vial(g: Fig) -> None:
    g.rect(6, 1, 9, 2, _c("#b07a48"))
    g.rect(6, 3, 9, 13, _c("#d8eef8"))
    g.rect(6, 7, 9, 13, RED)
    g.rect(6, 7, 6, 13, RED_LIGHT)
    g.ellipse(7.5, 13, 2, 1.5, RED_DARK)


ICONS = {"sword": _sword, "axe": _axe, "dagger": _dagger, "shield": _shield, "bow": _bow, "staff": _staff,
         "fire": _fire, "ice": _ice, "bolt": _bolt, "drop": _drop, "skull": _skull, "heart": _heart, "flex": _flex,
         "book": _book, "wind": _wind, "star": _star, "campfire": _campfire, "chest": _chest, "crown": _crown, "crack": _crack, "coin": _coin,
         "question": _question, "bag": _bag, "hammer": _hammer, "potion": _potion, "blood": _blood, "lantern": _lantern,
         "ring": _ring_icon, "anchor": _anchor, "vajra": _vajra, "marbles": _marbles, "stone": _stone, "idol": _idol,
         "flower": _flower, "vial": _vial}


def icon(name: str) -> np.ndarray:
    g = Fig(16, 16)
    ICONS.get(name, _star)(g)
    _ring(g)
    return g.px
