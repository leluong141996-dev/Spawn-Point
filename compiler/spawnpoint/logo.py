"""The Spawn Point logo, drawn as pixel art from code: a glowing spawn pad with a sprout growing out of it, and a
chunky pixel wordmark. `spawnpoint logo -o <dir>` writes the icon (several sizes), the wordmark and a favicon."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

RGBA = tuple[int, int, int, int]


def _c(h: str, a: int = 255) -> RGBA:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


BG, BG_LIGHT, BG_EDGE = _c("#1d1a33"), _c("#2b2650"), _c("#0e0c1c")
PAD, PAD_LIGHT, PAD_DARK, GLOW = _c("#29adff"), _c("#9ee8ff"), _c("#1a6ab0"), _c("#29adff", 70)
LEAF, LEAF_LIGHT, LEAF_DARK, STEM = _c("#5cd84a"), _c("#a8f070"), _c("#2c8a3c"), _c("#3fa83a")
GOLD, GOLD_DARK, GOLD_LIGHT, INK = _c("#ffec27"), _c("#e8902a"), _c("#fff7a8"), _c("#2a1e2e")
SPARK = _c("#fffaf0")


def _blend(dst: np.ndarray, y: int, x: int, c: RGBA) -> None:
    if 0 <= y < dst.shape[0] and 0 <= x < dst.shape[1]:
        a = c[3] / 255.0
        dst[y, x, :3] = (dst[y, x, :3] * (1 - a) + np.array(c[:3]) * a).astype(np.uint8)
        dst[y, x, 3] = max(dst[y, x, 3], c[3])


def icon(size: int = 32) -> np.ndarray:
    """The square app icon at its art size (32x32 art pixels; scale it up by whole numbers)."""
    n = 32
    img = np.zeros((n, n, 4), dtype=np.uint8)
    # a rounded dark tile with a soft top light
    for y in range(n):
        for x in range(n):
            corner = min(x, n - 1 - x) + min(y, n - 1 - y)
            if corner < 3 and (min(x, n - 1 - x) < 2 and min(y, n - 1 - y) < 2):
                if (min(x, n - 1 - x), min(y, n - 1 - y)) in ((0, 0), (0, 1), (1, 0)):
                    continue
            img[y, x] = _c("#3a3366") if y < 6 else BG_LIGHT if y < 11 else _c("#24204a") if y < 16 else BG
    edge = img[..., 3] > 0
    p = np.pad(edge, 1)
    ring = edge & ~(p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
    img[ring] = BG_EDGE
    # the beam of light rising from the pad
    for y in range(6, 25):
        for x in range(12, 20):
            a = int(60 * (1 - abs(x - 15.5) / 4.5) * (y - 5) / 19)
            if a > 0:
                _blend(img, y, x, (158, 232, 255, a))
    # the spawn pad: a glowing ellipse
    for y in range(22, 29):
        for x in range(5, 27):
            d = ((x - 15.5) / 10.5) ** 2 + ((y - 25) / 3.2) ** 2
            if d <= 1.0:
                img[y, x] = PAD_DARK if d > 0.62 else PAD
            elif d <= 1.35:
                _blend(img, y, x, GLOW)
    for x in range(9, 23):  # the lit inner rim
        _blend(img, 23, x, PAD_LIGHT)
    for x in range(11, 21):
        img[25, x] = PAD_LIGHT if (x % 3) else PAD
    # the sprout: a stem and two round leaves, a bud on top
    for y in range(12, 25):
        img[y, 15] = STEM
        img[y, 16] = LEAF_DARK
    for cx, cy, rx, ry in ((11.5, 15.5, 4.2, 2.4), (20.5, 12.5, 4.2, 2.4)):
        for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
                d = ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2
                if d <= 1.0:
                    img[y, x] = LEAF_DARK if y + 0.5 > cy + ry * 0.35 else LEAF
                    if d < 0.35 and y + 0.5 < cy:
                        img[y, x] = LEAF_LIGHT
    for (y, x, col) in ((9, 15, LEAF), (9, 16, LEAF), (8, 15, LEAF_LIGHT), (10, 15, LEAF), (10, 16, LEAF_DARK),
                        (11, 15, STEM), (11, 16, LEAF_DARK)):
        img[y, x] = col
    sprout = (img[..., 1] > 150) & (img[..., 0] < 200) & (img[..., 2] < 140)  # an outline round the green
    q = np.pad(sprout, 1)
    rim = (q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]) & ~sprout & (np.arange(n)[:, None] < 22)
    img[rim] = _c("#143a24")
    # sparkles
    for (y, x) in ((5, 7), (8, 25), (4, 21), (19, 6)):
        img[y, x] = SPARK
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            _blend(img, y + dy, x + dx, (255, 250, 240, 140))
    return img


# A 5x7 pixel font for the wordmark (only the letters it needs, and a few spares).
GLYPHS = {
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    " ": ["00"] * 7,
}


def wordmark(text: str = "SPAWN POINT", scale: int = 3) -> np.ndarray:
    """The name in chunky gold pixel letters with a dark outline and a drop shadow (art pixels)."""
    glyphs = [GLYPHS.get(ch, GLYPHS[" "]) for ch in text.upper()]
    w = sum((len(g[0]) + 1) * scale + 1 for g in glyphs) + 8
    h = 7 * scale + 8
    mask = np.zeros((h, w), dtype=bool)
    shade = np.zeros((h, w), dtype=np.uint8)  # 0 body, 1 top light, 2 bottom shadow
    x_at = 3
    for rows in glyphs:
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == "1":  # one pixel wider than the grid: bold strokes
                    y0, x0 = 3 + gy * scale, x_at + gx * scale
                    mask[y0:y0 + scale, x0:x0 + scale + 1] = True
                    shade[y0:y0 + scale, x0:x0 + scale + 1] = 1 if gy < 2 else (2 if gy > 4 else 0)
        x_at += (len(rows[0]) + 1) * scale + 1
    img = np.zeros((h, w, 4), dtype=np.uint8)
    shadow = np.zeros_like(mask)
    shadow[2:, 2:] = mask[:-2, :-2]
    p = np.pad(mask, 1)
    outline = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~mask
    img[shadow & ~mask] = BG_EDGE
    img[outline] = INK
    img[mask] = GOLD
    img[mask & (shade == 1)] = GOLD_LIGHT
    img[mask & (shade == 2)] = GOLD_DARK
    return img


def banner(scale: int = 3) -> np.ndarray:
    """The icon and the wordmark side by side (art pixels, transparent background)."""
    ic, wm = icon(), wordmark(scale=scale)
    h = max(ic.shape[0], wm.shape[0])
    out = np.zeros((h, ic.shape[1] + 6 + wm.shape[1], 4), dtype=np.uint8)
    out[(h - ic.shape[0]) // 2:(h - ic.shape[0]) // 2 + ic.shape[0], :ic.shape[1]] = ic
    y = (h - wm.shape[0]) // 2
    out[y:y + wm.shape[0], ic.shape[1] + 6:] = wm
    return out


def _up(a: np.ndarray, k: int) -> Image.Image:
    return Image.fromarray(a).resize((a.shape[1] * k, a.shape[0] * k), Image.NEAREST)


def write(out_dir: Path) -> list[Path]:
    """logo-icon-<size>.png (32..512), logo.png (icon + name), favicon.ico."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    ic = icon()
    for k in (1, 2, 4, 8, 16):
        path = out_dir / f"logo-icon-{32 * k}.png"
        _up(ic, k).save(path)
        written.append(path)
    path = out_dir / "logo.png"
    _up(banner(), 4).save(path)
    written.append(path)
    fav = out_dir / "favicon.ico"
    _up(ic, 2).save(fav, sizes=[(16, 16), (32, 32), (64, 64)])
    written.append(fav)
    return written
