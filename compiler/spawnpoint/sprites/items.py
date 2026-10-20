"""Chibi items and props in the creatures.py language (flat colour blocks, one shadow tone, a touch of light,
a dark outline), painted natively at the fine size: key, potion, scroll, bomb, chest, arrow, the gate
(a door, or a barred cage) and the decorative tree, bush and rock. The entity colour is the item's "own" colour (key metal, potion liquid,
scroll seal, arrow fletching, foliage, stone); fixed materials (wood, glass, parchment, iron) stay fixed.
"""

from __future__ import annotations

from .chibi import EYE, WHITE, Fig, tone
from .creatures import Look

RGBA = tuple[int, int, int, int]
WOOD = "#96603a"
GLASS = "#d8eef8"
PARCHMENT = "#f0dca8"
IRON = "#3a3a4e"
STEEL = "#b4bccc"
GOLD = "#ffcc40"
CORK = "#b07a48"
SPARK = ("#fff4a0", "#ffb03a", "#ff6a3a")


def _sparkle(g: Fig, x: int, y: int, i: int) -> None:
    """A little four-point twinkle that grows and fades over four frames."""
    r = (0, 1, 2, 1)[i % 4]
    if r == 0:
        return
    g.set(x, y, WHITE)
    for d in range(1, r + 1):
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            g.set(x + dx, y + dy, WHITE)


def paint_key(g: Fig, L: Look, anim: str, i: int) -> None:
    b = L.body
    y = (0, 0, 1, 1)[i % 4]
    g.ellipse(5, 6 + y, 4.5, 4.5, b.base)          # the bow (ring)
    g.ellipse(4, 5 + y, 2, 2, b.light)
    g.ellipse(5, 6 + y, 1.6, 1.6, (0, 0, 0, 0))     # the hole
    g.rect(9, 6 + y, 15, 7 + y, b.base)            # shaft
    g.rect(9, 7 + y, 15, 7 + y, b.shadow)
    g.rect(12, 8 + y, 13, 10 + y, b.base)          # teeth
    g.rect(15, 8 + y, 15, 9 + y, b.base)
    g.rect(13, 9 + y, 13, 10 + y, b.shadow)
    _sparkle(g, 2, 2 + y, i)


def paint_potion(g: Fig, L: Look, anim: str, i: int) -> None:
    liquid, glass, cork = L.body, tone(GLASS, None), tone(CORK, None)
    g.ellipse(8, 13, 6.5, 6, glass.base)            # flask
    g.rect(6, 4, 9, 8, glass.base)                  # neck
    g.rect(5, 2, 10, 4, cork.base)                  # cork
    g.rect(5, 4, 10, 4, cork.shadow)
    g.ellipse(8, 14.5, 5.2, 4.2, liquid.base)       # liquid
    g.rect(4, 12, 12, 12, liquid.light)
    g.rect(10, 13, 12, 17, liquid.shadow)
    g.rect(4, 9, 5, 11, WHITE)                      # glint on the glass
    for k, (bx, by) in enumerate(((6, 16), (9, 15), (7, 13))):  # rising bubbles
        if (i + k) % 4 < 2:
            g.set(bx, by - (i + k) % 2, liquid.light)


def paint_scroll(g: Fig, L: Look, anim: str, i: int) -> None:
    pa = tone(PARCHMENT, None)
    y = (0, 1)[i % 2]
    g.rect(3, 4 + y, 14, 11 + y, pa.base)
    g.rect(3, 10 + y, 14, 11 + y, pa.shadow)
    for x0 in (1, 14):                               # the rolled ends
        g.rect(x0, 3 + y, x0 + 2, 12 + y, pa.shadow)
        g.rect(x0, 3 + y, x0 + 2, 3 + y, pa.light)
    for row in (6, 8):                               # writing
        g.rect(5, row + y, 12, row + y, tone("#8a6a48", None).base)
    g.ellipse(9, 11 + y, 2.2, 2.2, L.body.base)      # the wax seal
    g.set(8, 10 + y, L.body.light)


def paint_bomb(g: Fig, L: Look, anim: str, i: int) -> None:
    iron = tone(IRON, None)
    g.ellipse(8, 11, 6.5, 6.5, iron.base)
    g.ellipse(6, 8, 2.4, 2, iron.light)
    g.rect(11, 12, 13, 15, iron.shadow)
    g.rect(7, 3, 10, 5, tone(STEEL, None).base)      # cap
    g.line(10, 3, 12, 1, tone(CORK, None).base)       # fuse
    g.set(13, 1, tone(CORK, None).base)
    spark = tone(SPARK[i % 3], None).base             # a flickering spark
    g.rect(13, 0, 14, 1, spark)
    if i % 2 == 0:
        g.set(15, 0, WHITE)
        g.set(13, 2, tone(SPARK[1], None).base)


def paint_chest(g: Fig, L: Look, anim: str, i: int) -> None:
    w, gold = tone(WOOD, None), tone(GOLD, None)
    g.rect(2, 10, 21, 18, w.base)                     # box
    g.rect(2, 16, 21, 18, w.shadow)
    g.rect(3, 4, 20, 9, w.base)                       # lid
    g.rect(2, 5, 21, 9, w.base)
    g.rect(4, 4, 10, 5, w.light)
    g.rect(2, 9, 21, 9, w.shadow)
    for x in (5, 18):                                 # bands
        g.rect(x, 4, x, 18, gold.shadow)
    g.rect(10, 8, 13, 12, gold.base)                  # lock plate
    g.rect(11, 10, 12, 11, EYE)
    g.rect(10, 8, 13, 8, gold.light)
    _sparkle(g, 19, 2, i)


def paint_arrow(g: Fig, L: Look, anim: str, i: int) -> None:
    wd, st, fl = tone(WOOD, None), tone(STEEL, None), L.body
    g.rect(3, 3, 16, 4, wd.base)
    g.rect(3, 4, 16, 4, wd.shadow)
    g.poly([(15.5, 0.5), (19.8, 4), (15.5, 7.5)], st.base)  # head
    g.set(16, 2, st.light)
    g.poly([(0, 0.5), (5, 3), (0, 3.5)], fl.base)            # fletching
    g.poly([(0, 7.5), (5, 5), (0, 4.5)], fl.shadow)


def paint_door(g: Fig, L: Look, anim: str, i: int) -> None:
    """A tall gate filling its 18x126 column (collision follows the pixels): an arched wooden door with
    iron bands and a lock, or an iron portcullis when the name says cage/gate."""
    b, iron, gold = L.body, tone(IRON, None), tone(GOLD, None)
    w, h = g.w, g.h
    barred = "bars" in L.f
    g.ellipse(w / 2, 9, w / 2 - 1, 8, iron.base if barred else b.base)   # arched top
    g.rect(1, 9, w - 2, h - 1, iron.base if barred else b.base)
    if barred:
        g.ellipse(w / 2, 10, w / 2 - 3, 6, EYE)                          # the dark inside
        g.rect(3, 10, w - 4, h - 4, EYE)
        for x in range(4, w - 3, 4):                     # bars, lit on the left (on even pixels: the coarse 2:1 keeps them)
            g.rect(x, 4, x + 1, h - 2, b.base)
            g.rect(x, 4, x, h - 2, b.light)
        for y in (14, h // 2 + 6, h - 14):                                 # crossbars
            g.rect(1, y, w - 2, y + 3, b.shadow)
            g.rect(1, y, w - 2, y, b.light)
    else:
        for x in (6, 10):                                                  # plank seams
            g.rect(x, 3, x, h - 2, b.shadow)
        g.rect(2, 4, 2, h - 3, b.light)
        for y in (18, h - 22):                                             # iron bands with rivets
            g.rect(1, y, w - 2, y + 3, iron.base)
            g.rect(1, y, w - 2, y, iron.light)
            for x in (3, w - 4):
                g.set(x, y + 2, tone(STEEL, None).base)
        g.rect(1, h - 3, w - 2, h - 1, b.shadow)                           # threshold
    ly = h // 2 - 7                                                        # the lock and its keyhole
    g.rect(w - 10, ly, w - 3, ly + 11, gold.base)
    g.rect(w - 10, ly, w - 3, ly + 1, gold.light)
    g.rect(w - 4, ly + 1, w - 3, ly + 10, gold.shadow)
    g.rect(w - 7, ly + 4, w - 6, ly + 8, EYE)
    if barred:                                                             # a padlock shackle
        g.rect(w - 9, ly - 4, w - 4, ly - 3, iron.light)
        g.rect(w - 9, ly - 4, w - 8, ly - 1, iron.light)
        g.rect(w - 5, ly - 4, w - 4, ly - 1, iron.light)


def paint_tree(g: Fig, L: Look, anim: str, i: int) -> None:
    leaf, wd = L.body, tone(WOOD, None)
    sway = (0, 1, 0, -1)[i % 4]
    g.rect(13, 30, 18, 47, wd.base)                   # trunk
    g.rect(17, 30, 18, 47, wd.shadow)
    g.rect(14, 31, 14, 40, wd.light)
    g.rect(11, 45, 20, 47, wd.base)                   # roots
    if "pine" in L.f:                                 # stacked triangles
        for n, (top, half) in enumerate(((2, 6), (10, 9), (19, 12))):
            dx = sway if n == 0 else (sway // 2 if n == 1 else 0)
            g.poly([(16 + dx - half, top + 12), (16 + dx, top), (16 + dx + half, top + 12)], leaf.base)
            g.poly([(16 + dx, top), (16 + dx + half, top + 12), (16 + dx + 2, top + 12)], leaf.shadow)
            g.rect(16 + dx - half // 2, top + 6, 16 + dx - 2, top + 7, leaf.light)
        return
    g.ellipse(16, 24, 12, 8, leaf.base)               # round crown in three blobs
    g.ellipse(16 + sway, 15, 11, 8, leaf.base)
    g.ellipse(16 + sway, 7, 7, 6, leaf.base)
    g.ellipse(22, 24, 6, 6, leaf.shadow)
    g.ellipse(21 + sway, 15, 5, 5, leaf.shadow)
    g.ellipse(11 + sway, 11, 3.5, 2.6, leaf.light)
    g.ellipse(10, 20, 3, 2, leaf.light)


def paint_bush(g: Fig, L: Look, anim: str, i: int) -> None:
    leaf = L.body
    sway = (0, 1)[i % 2]
    g.ellipse(8, 10, 7, 6, leaf.base)
    g.ellipse(22, 10, 6, 5.5, leaf.shadow)
    g.ellipse(15 + sway, 8, 8, 7, leaf.base)
    g.rect(2, 13, 26, 15, leaf.shadow)
    g.ellipse(12 + sway, 5, 3, 2, leaf.light)
    g.ellipse(5, 8, 2, 1.6, leaf.light)
    if "berries" in L.f:
        for bx, by in ((9, 9), (17, 11), (21, 7)):
            g.rect(bx, by, bx + 1, by + 1, tone("#e04858", None).base)


def paint_rock(g: Fig, L: Look, anim: str, i: int) -> None:
    st = L.body
    g.ellipse(11, 10, 10, 6.5, st.base)
    g.ellipse(19, 12, 5, 4, st.shadow)
    g.rect(2, 14, 22, 15, st.shadow)
    g.ellipse(8, 7, 4, 2.2, st.light)
    g.line(12, 9, 14, 12, st.shadow)                  # a crack
    if "moss" in L.f:
        g.ellipse(9, 4.5, 5, 1.8, tone("#5aa040", None).base)


PAINTERS = {"door": paint_door, "key": paint_key, "potion": paint_potion, "scroll": paint_scroll, "bomb": paint_bomb,
            "chest": paint_chest, "arrow": paint_arrow, "tree": paint_tree, "bush": paint_bush, "rock": paint_rock}
