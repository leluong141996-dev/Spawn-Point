"""Pixel-art scenery: a banded sky and parallax layers (clouds, mountains, hills, trees, skylines...) per theme.

Colours are derived from the game's background colour so the scenery always matches it, then snapped to the
game's palette. Every layer tiles horizontally (all curves are periodic), is drawn on a small pixel grid and
scaled up with nearest-neighbour like the sprites, so the pixel size matches.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image

from . import palettes
from .generate import _hex

THEMES = ("night", "forest", "desert", "neon", "candy", "ocean", "lava", "snow")
WIDTH = 640  # art pixels per repeat (1280 world px at 2 px per art pixel)
SKY_W, SKY_H = 320, 180
RGB = tuple[int, int, int]


# --- colour helpers ---------------------------------------------------------------------------

def _rgb(c: str) -> RGB:
    r, g, b = _hex(c)
    return round(r * 255), round(g * 255), round(b * 255)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def shade(c: RGB, k: float, hue: float = 0.0) -> RGB:
    """k < 1 darker, k > 1 lighter; `hue` rotates (shadows lean cool, lights lean warm)."""
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
    if k >= 1:
        v, s = min(1.0, v * k + (k - 1) * 0.1), s * max(0.0, 1 - (k - 1) * 0.5)
    else:
        v, s = v * k, min(1.0, s * (1 + (1 - k) * 0.3))
    r, g, b = colorsys.hsv_to_rgb((h + hue) % 1, s, v)
    return round(r * 255), round(g * 255), round(b * 255)


def luminance(c: RGB) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


# --- drawing ----------------------------------------------------------------------------------

def canvas(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 4), np.uint8)


def _put(img: np.ndarray, x: int, y: int, c: RGB) -> None:
    if 0 <= y < img.shape[0]:
        img[y, x % img.shape[1]] = (*c, 255)  # x wraps: every layer tiles


def _fill_below(img: np.ndarray, ys: list[int], c: RGB, rim: RGB | None = None) -> None:
    h = img.shape[0]
    for x, y in enumerate(ys):
        y = max(0, min(h, y))
        img[y:, x] = (*c, 255)
        if rim is not None and y < h:
            img[y, x] = (*rim, 255)


def _rect(img: np.ndarray, x0: int, y0: int, x1: int, y1: int, c: RGB) -> None:
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            _put(img, x, y, c)


def _disc(img: np.ndarray, cx: float, cy: float, r: float, c: RGB) -> None:
    for y in range(int(cy - r) - 1, int(cy + r) + 2):
        for x in range(int(cx - r) - 1, int(cx + r) + 2):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                _put(img, x, y, c)


def _ridge(w: int, base: float, amp: float, rng: random.Random, sharp: bool = False) -> list[int]:
    """A periodic skyline: y per column (bigger = lower). `sharp` makes pointed peaks (mountains)."""
    parts = [(rng.choice((2, 3)), rng.random() * 6.28, 0.55), (rng.choice((5, 6, 7)), rng.random() * 6.28, 0.3),
             (rng.choice((11, 13)), rng.random() * 6.28, 0.15)]
    ys = []
    for x in range(w):
        t = x / w
        if sharp:
            v = sum(wt * (1 - abs(math.sin(math.pi * f * t + p))) for f, p, wt in parts)
        else:
            v = sum(wt * (0.5 + 0.5 * math.sin(2 * math.pi * f * t + p)) for f, p, wt in parts)
        ys.append(round(base - amp * v))
    return ys


# --- sky --------------------------------------------------------------------------------------

def _bands(top: RGB, bottom: RGB, n: int) -> list[RGB]:
    return [mix(top, bottom, i / (n - 1)) for i in range(n)]


def sky(theme: str, bg: RGB, rng: random.Random) -> np.ndarray:
    """A screen-sized gradient in hard bands with a dithered seam between them; stars / sun / moon on top."""
    dark = luminance(bg) < 0.3
    warm = {"desert": (255, 190, 120), "lava": (170, 50, 20), "candy": (255, 235, 245)}.get(theme)
    top = shade(bg, 0.72 if not dark else 0.6, -0.02)
    bottom = mix(bg, warm or (255, 255, 255), 0.35 if warm else (0.18 if dark else 0.3))
    if theme == "neon":
        top, bottom = shade(bg, 0.6), mix(bg, (190, 40, 150), 0.35)
    if theme == "desert":
        top = mix(bg, (110, 60, 130), 0.45)
    n = 6
    bands = _bands(top, bottom, n)
    img = canvas(SKY_W, SKY_H)
    edges = [round(SKY_H * 0.78 * i / n) for i in range(n + 1)]
    for y in range(SKY_H):
        k = next((i for i in range(n) if y < edges[i + 1]), n - 1)
        img[y, :] = (*bands[k], 255)
        # dither the last two rows of a band into the next one
        if k < n - 1 and y >= edges[k + 1] - 2:
            for x in range(SKY_W):
                if (x + y) % 2 == 0:
                    img[y, x] = (*bands[k + 1], 255)
    if theme in ("night", "lava", "neon") or dark and theme not in ("ocean",):
        light = (255, 244, 214)
        for _ in range(55):  # stars
            x, y = rng.randrange(SKY_W), rng.randrange(int(SKY_H * 0.6))
            img[y, x] = (*mix(bands[min(y * n // SKY_H, n - 1)], light, rng.choice((0.5, 0.75, 1.0))), 255)
    if theme in ("night", "lava", "neon", "forest") and dark:
        _disc(img, SKY_W * 0.78, SKY_H * 0.2, 11, (236, 232, 210))
        _disc(img, SKY_W * 0.78 + 3, SKY_H * 0.2 - 2, 9, mix(top, (236, 232, 210), 0.12))  # a crescent
    elif theme not in ("ocean", "lava", "neon"):
        sun = (255, 222, 120) if theme != "snow" else (250, 250, 235)
        _disc(img, SKY_W * 0.8, SKY_H * 0.22, 14, mix(sun, bands[1], 0.35))
        _disc(img, SKY_W * 0.8, SKY_H * 0.22, 10, sun)
    return img


# --- layers -----------------------------------------------------------------------------------

def clouds(theme: str, bg: RGB, rng: random.Random) -> np.ndarray:
    h = 90
    img = canvas(WIDTH, h)
    dark = luminance(bg) < 0.3
    base = mix(bg, (255, 255, 255), 0.18 if dark else 0.7)
    under = shade(base, 0.82, 0.04)
    if theme == "lava":
        base, under = (70, 40, 40), (45, 25, 28)
    if theme == "ocean":  # light rays and drifting bubbles instead of clouds
        for _ in range(7):
            x = rng.randrange(WIDTH)
            for y in range(h):
                for dx in range(-2 - y // 12, 3 + y // 12):
                    if (x + dx + y) % 3:
                        continue
                    _put(img, x + dx + y // 3, y, mix(bg, (255, 255, 255), 0.1))
        return img
    for k in range(7):
        cx = (k * WIDTH // 7 + rng.randrange(-20, 20)) % WIDTH
        cy = rng.randrange(14, h - 28)
        w = rng.randrange(26, 48)
        for i in range(rng.randrange(3, 5)):  # a cloud is a few overlapping puffs on a flat base
            r = rng.randrange(6, 11)
            _disc(img, cx + (i - 1.5) * w / 4, cy - rng.randrange(0, 5), r, base)
        _rect(img, int(cx - w / 2), cy, int(cx + w / 2), cy + 3, base)
        _rect(img, int(cx - w / 2), cy + 3, int(cx + w / 2), cy + 4, under)
    return img


def _pine(img: np.ndarray, x: int, base: int, h: int, c: RGB, light: RGB) -> None:
    for i in range(h):
        half = max(0, (i * 3) // (h * 2) + (i % 5 == 4))
        half = 1 + i * 4 // h
        for dx in range(-half, half + 1):
            _put(img, x + dx, base - h + i, c if dx > -half or i % 2 else light)
    _rect(img, x, base, x, base + 1, shade(c, 0.6))


def _round_tree(img: np.ndarray, x: int, base: int, h: int, c: RGB, light: RGB) -> None:
    r = max(3, h // 2)
    _rect(img, x, base - h // 3, x, base + 1, shade(c, 0.55))
    _disc(img, x, base - h // 3 - r + 1, r, c)
    _disc(img, x - r // 3, base - h // 3 - r, r // 2, light)


def _cactus(img: np.ndarray, x: int, base: int, h: int, c: RGB, light: RGB) -> None:
    _rect(img, x, base - h, x + 1, base, c)
    _rect(img, x, base - h, x, base, light)
    a = h // 2
    _rect(img, x - 3, base - a - 4, x - 3, base - a, c)
    _rect(img, x - 3, base - a, x - 1, base - a, c)
    _rect(img, x + 4, base - a - 6, x + 4, base - a - 2, c)
    _rect(img, x + 2, base - a - 2, x + 4, base - a - 2, c)


def _lollipop(img: np.ndarray, x: int, base: int, h: int, c: RGB, light: RGB) -> None:
    _rect(img, x, base - h // 2, x, base + 1, (240, 240, 240))
    r = max(3, h // 3)
    _disc(img, x, base - h // 2 - r, r, c)
    for t in range(r * 2):  # a swirl
        a = t / 2
        _put(img, round(x + math.cos(a) * a * r / (r * 2)), round(base - h // 2 - r + math.sin(a) * a * r / (r * 2)), light)


def _kelp(img: np.ndarray, x: int, base: int, h: int, c: RGB, light: RGB) -> None:
    for i in range(h):
        _put(img, x + round(math.sin(i / 3 + x) * 2), base - i, c if i % 3 else light)
        _put(img, x + round(math.sin(i / 3 + x) * 2) + 1, base - i, c)


TREES = {"forest": _pine, "snow": _pine, "night": _pine, "lava": None, "desert": _cactus, "candy": _lollipop,
         "ocean": _kelp, "neon": None}


def mountains(theme: str, color: RGB, light: RGB, rng: random.Random, h: int = 150) -> np.ndarray:
    img = canvas(WIDTH, h)
    ys = _ridge(WIDTH, h * 0.75, h * 0.62, rng, sharp=theme not in ("candy", "desert", "ocean"))
    _fill_below(img, ys, color, rim=light)
    if theme in ("snow", "night") or theme == "forest" and rng.random() < 0.0:
        cap = (240, 244, 250) if theme == "snow" else mix(color, (255, 255, 255), 0.25)
        top = min(ys)
        for x, y in enumerate(ys):
            if y < top + 10:  # snow caps on the highest peaks
                for dy in range(0, 3 + (top + 10 - y) // 4):
                    if y + dy < h and img[y + dy, x, 3]:
                        img[y + dy, x] = (*cap, 255)
    if theme == "lava":  # glowing cracks / a lit crater
        for _ in range(40):
            x = rng.randrange(WIDTH)
            y = ys[x] + rng.randrange(2, 28)
            if y < h:
                _put(img, x, y, (255, 120, 40))
    return img


def hills(theme: str, color: RGB, light: RGB, detail: RGB, rng: random.Random, h: int = 110, trees: bool = True,
          density: float = 0.07) -> np.ndarray:
    img = canvas(WIDTH, h)
    ys = _ridge(WIDTH, h * 0.7, h * 0.5, rng)
    _fill_below(img, ys, color, rim=light)
    draw = TREES.get(theme)
    if trees and draw is not None:
        for _ in range(int(WIDTH * density)):
            x = rng.randrange(WIDTH)
            th = rng.randrange(10, 22) if theme != "ocean" else rng.randrange(14, 34)
            c = detail if rng.random() < 0.7 else shade(detail, 1.15)
            for dx in (0, -WIDTH, WIDTH):  # wrap-around copies keep the tile seamless
                draw(img, x + dx, ys[x] + 1, th, c, shade(c, 1.3, -0.02))
    return img


def skyline(bg: RGB, far: RGB, window: RGB, rng: random.Random, h: int = 150, lit: bool = True) -> np.ndarray:
    img = canvas(WIDTH, h)
    x = 0
    while x < WIDTH:
        w = rng.randrange(10, 26)
        bh = rng.randrange(30, h - 20)
        w = min(w, WIDTH - x)
        c = far
        _rect(img, x, h - bh, x + w - 1, h, c)
        _rect(img, x, h - bh, x + w - 1, h - bh, shade(c, 1.35))
        if rng.random() < 0.3:
            _rect(img, x + w // 2, h - bh - 8, x + w // 2, h - bh, shade(c, 0.8))  # antenna
        if lit:
            for wy in range(h - bh + 4, h - 4, 5):
                for wx in range(x + 2, x + w - 2, 4):
                    if rng.random() < 0.45:
                        _put(img, wx, wy, window if rng.random() < 0.75 else (255, 255, 255))
        x += w + rng.randrange(0, 3)
    return img


def dunes(color: RGB, light: RGB, rng: random.Random, h: int = 100) -> np.ndarray:
    img = canvas(WIDTH, h)
    ys = _ridge(WIDTH, h * 0.7, h * 0.45, rng)
    _fill_below(img, ys, color, rim=light)
    return img


# --- recipes ----------------------------------------------------------------------------------

@dataclass
class Layer:
    name: str
    image: np.ndarray
    scroll: float
    anchor: str  # "ground": bottom on the ground line; "top": near the top of the level
    lift: int = 0  # art pixels the bottom edge sits above the ground line


def theme_for(bg: RGB) -> str:
    """A scenery theme for a plain background colour (used when none is named)."""
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in bg))
    if v < 0.35:
        return "night" if s < 0.5 or 0.55 < h < 0.75 else "forest"
    if s < 0.2:
        return "snow"
    return {0: "desert"}.get(0, "forest") if 0.04 < h < 0.14 else "snow"


def build(theme: str, background: str, palette: str | None, seed: int) -> tuple[np.ndarray, list[Layer]]:
    """The sky image and the parallax layers (back to front) for `theme`, in `palette` when there is one."""
    if theme not in THEMES:
        theme = theme_for(_rgb(background))
    rng = random.Random(f"scenery:{theme}:{seed}")
    bg = _rgb(background)
    pal = palettes.get(palette)

    def pick(c: RGB, *avoid: RGB) -> RGB:
        """`c` as a palette colour that is none of `avoid` (so layers stay apart after snapping)."""
        if pal is None:
            return c
        gone = {i for i in (pal.index_of(a) for a in avoid) if i is not None}
        return pal.nearest(c, exclude=gone)

    sky_img = sky(theme, bg, rng)
    if pal:
        sky_img = pal.snap(sky_img)
    horizon = tuple(int(x) for x in sky_img[int(SKY_H * 0.7), 0, :3])
    dark = luminance(bg) < 0.3
    tint = shade(bg, 0.3, 0.03) if not dark else shade(bg, 0.35)
    if theme in ("candy", "snow"):
        tint = mix(bg, (90, 60, 120) if theme == "candy" else (60, 80, 120), 0.6)
    accent = {"forest": (38, 92, 66), "night": (22, 34, 60), "snow": (70, 100, 140), "desert": (70, 130, 70),
              "candy": (240, 90, 160), "ocean": (30, 140, 110), "lava": (50, 30, 30), "neon": (60, 20, 90)}[theme]
    tint = mix(tint, accent, 0.3)  # shadows lean toward the theme's colour, or dark tones all collapse to one grey
    far = pick(mix(horizon, tint, 0.38), horizon)
    mid = pick(mix(horizon, tint, 0.6), horizon, far)
    near = pick(mix(horizon, tint, 0.8), horizon, far, mid)
    lit = lambda c: pick(shade(c, 1.3, -0.02), c)  # noqa: E731
    detail_mid = pick(mix(mid, accent, 0.6), mid, near)
    detail_near = pick(mix(near, accent, 0.6), near, mid)
    layers: list[Layer] = []
    if theme != "neon":
        layers.append(Layer("clouds", clouds(theme, bg, rng), 0.08, "ground", 85))
    if theme == "neon":
        layers.append(Layer("far", skyline(bg, far, (255, 90, 170), rng, 150, lit=False), 0.18, "ground", 0))
        layers.append(Layer("mid", skyline(bg, mid, (120, 235, 245), rng, 120), 0.35, "ground", -10))
        layers.append(Layer("near", hills(theme, near, lit(near), detail_near, rng, 70, False), 0.6, "ground", -10))
    elif theme == "desert":
        layers.append(Layer("far", mountains(theme, far, lit(far), rng, 130), 0.18, "ground", 0))
        layers.append(Layer("mid", dunes(mid, lit(mid), rng, 110), 0.35, "ground", -5))
        layers.append(Layer("near", hills(theme, near, lit(near), detail_near, rng, 90, True, 0.03), 0.6, "ground", -10))
    elif theme == "ocean":
        layers.append(Layer("far", mountains(theme, far, lit(far), rng, 130), 0.18, "ground", 0))
        layers.append(Layer("mid", hills(theme, mid, lit(mid), detail_mid, rng, 130, True, 0.05), 0.4, "ground", -8))
        layers.append(Layer("near", hills(theme, near, lit(near), detail_near, rng, 80, False), 0.6, "ground", -12))
    else:
        layers.append(Layer("far", mountains(theme, far, lit(far), rng), 0.18, "ground", 0))
        layers.append(Layer("mid", hills(theme, mid, lit(mid), detail_mid, rng, 120, True, 0.05), 0.35, "ground", -6))
        layers.append(Layer("near", hills(theme, near, lit(near), detail_near, rng, 90, True, 0.045), 0.6, "ground", -12))
    if pal:
        for layer in layers:
            layer.image = pal.snap(layer.image)
    return sky_img, layers


# --- space (side-scrolling shooters) ------------------------------------------------------------

SPACE_H = 272  # art pixels: the height of the shooter field (17 tiles)
STAR_LAYERS = (("far", 14.0), ("mid", 34.0), ("near", 80.0))  # name, world px/s the layer scrolls left


def space(background: str, palette: str | None, seed: int) -> tuple[np.ndarray, list[tuple[str, np.ndarray, float]]]:
    """A dark gradient sky and three layers of stars that scroll past at different speeds (plus a distant planet)."""
    rng = random.Random(f"space:{seed}")
    bg = _rgb(background)
    pal = palettes.get(palette)
    top = shade(bg, 0.5)
    bottom = mix(bg, (60, 30, 110), 0.28) if luminance(bg) < 0.3 else mix(shade(bg, 0.3), (60, 30, 110), 0.3)
    # Space is one flat dark colour: a gradient reads as a horizon, and a small palette turns it into stripes.
    sky_img = canvas(SKY_W, SKY_H)
    sky_img[:, :] = (*top, 255)
    bands = [top, top]
    layers = []
    tints = [(255, 255, 255), (255, 244, 200), (190, 215, 255)]
    for li, (name, speed) in enumerate(STAR_LAYERS):
        img = canvas(WIDTH, SPACE_H)
        n = (170, 80, 26)[li]
        for _ in range(n):
            x, y = rng.randrange(WIDTH), rng.randrange(SPACE_H)
            c = mix(bands[min(y * 2 // SPACE_H, 1)], rng.choice(tints), (0.4, 0.7, 1.0)[li] * rng.choice((0.6, 1.0)))
            _put(img, x, y, c)
            if li == 2:  # the near stars are little streaks: they move fast
                _put(img, x + 1, y, c)
                _put(img, x + 2, y, mix(c, bands[0], 0.5))
            elif li == 1 and rng.random() < 0.25:
                _put(img, x + 1, y, c)
        if li == 0:  # a planet on the slowest layer, with a shaded edge and a ring
            cx, cy, r = rng.randrange(120, WIDTH - 120), rng.randrange(60, SPACE_H - 60), 26
            sky_colors = [tuple(int(v) for v in sky_img[y, 0, :3]) for y in range(0, SKY_H, 8)]

            def pick(c: RGB, *avoid: RGB) -> RGB:  # a palette colour apart from the sky and the other parts
                if pal is None:
                    return c
                gone = {i for i in (pal.index_of(a) for a in (*avoid, *sky_colors)) if i is not None}
                return pal.nearest(c, exclude=gone)
            planet = pick(mix(bg, (210, 120, 80), 0.7))
            dark = pick(shade(planet, 0.6), planet)
            light = pick(shade(planet, 1.3), planet, dark)
            _disc(img, cx, cy, r, dark)
            _disc(img, cx - 3, cy - 3, r - 4, planet)
            _disc(img, cx - 8, cy - 8, r - 14, light)
            for t in range(-r - 10, r + 11):  # a thin ring across it
                _put(img, cx + t, cy + t // 5 + 4, light)
        layers.append((name, img, speed))
    if pal:
        sky_img = pal.snap(sky_img)
        layers = [(n, pal.snap(i), sp) for n, i, sp in layers]
    return sky_img, layers


FLOOR = 32  # art pixels per side of the repeating top-down floor tile (64 world px)


def floor_tile(theme: str, background: str, palette: str | None, seed: int) -> np.ndarray:
    """A seamless floor texture for top-down games: the background colour with soft speckle and the theme's
    small details (grass tufts, sand ripples, frost, cracks, circuit lines)."""
    if theme not in THEMES:
        theme = theme_for(_rgb(background))
    rng = random.Random(f"floor:{theme}:{seed}")
    pal = palettes.get(palette)
    bg = _rgb(background)
    dark = luminance(bg) < 0.4

    def pick(c: RGB, *avoid: RGB) -> RGB:
        if pal is None:
            return c
        gone = {i for i in (pal.index_of(a) for a in avoid) if i is not None}
        return pal.nearest(c, exclude=gone)
    base = pick(bg)
    hi = pick(shade(base, 1.14 if dark else 1.06, -0.01), base)
    lo = pick(shade(base, 0.88), base, hi)
    img = canvas(FLOOR, FLOOR)
    img[:, :] = (*base, 255)
    for _ in range(FLOOR * FLOOR // 22):  # soft speckle
        img[rng.randrange(FLOOR), rng.randrange(FLOOR)] = (*(hi if rng.random() < 0.5 else lo), 255)
    accent = {"forest": (70, 150, 80), "night": (60, 80, 140), "desert": (230, 190, 120), "neon": (60, 220, 235),
              "candy": (255, 255, 255), "ocean": (90, 170, 230), "lava": (255, 120, 40), "snow": (255, 255, 255)}[theme]
    # Themes with a signature colour use it; the rest use a lighter tone of the floor itself (a palette often has no
    # other near colour to pick, and a stray one would show up as a regular pattern of odd dots).
    detail = pick(mix(base, accent, 0.45), base, hi, lo) if theme in ("neon", "lava", "ocean") else hi
    for _ in range(5):
        x, y = rng.randrange(2, FLOOR - 3), rng.randrange(3, FLOOR - 3)
        if theme in ("forest", "night", "candy"):  # tufts
            for dx, h in ((-1, 2), (0, 3), (1, 2)):
                _rect(img, x + dx, y - h, x + dx, y, detail)
        elif theme in ("desert", "snow"):  # ripples / drifts
            _rect(img, x - 2, y, x + 2, y, detail)
            _rect(img, x - 1, y + 1, x + 1, y + 1, lo)
        elif theme == "lava":  # glowing cracks
            for k in range(4):
                _put(img, x + k, y + (k % 2), detail)
        elif theme == "neon":  # circuit traces
            _rect(img, x, y, x + 4, y, lo)
            _put(img, x + 4, y, detail)
        else:  # ocean: ripples
            _rect(img, x - 2, y, x + 2, y, detail)
            _put(img, x, y - 1, detail)
    if pal:
        img = pal.snap(img)
    return img


def to_image(a: np.ndarray) -> Image.Image:
    return Image.fromarray(a, "RGBA")
