"""Card battle backdrops: one painted pixel scene per theme, 480x272 art pixels shown at 2x behind the fight.

Layers back to front: a banded sky (sun, moon, stars or aurora), two ranges of mountains fading into the sky, the
theme's scenery (willow trees, pines, dunes and ruins, a volcano, palms, lollipop trees, a neon skyline), then
the ground the fighters stand on, with tufts, flowers and stones and a lighter clearing in the middle.

    backdrop(theme, seed) -> RGBA array (272, 480, 4)
"""

from __future__ import annotations

import math
import random

import numpy as np

W, H = 480, 272
GROUND = 150  # art row where the ground starts; the fighters stand around row 168

RGB = tuple[int, int, int]


def _c(h: str) -> RGB:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


# theme -> sky top, sky bottom, far hills, near hills, ground, ground dark, ground light, accent
THEMES: dict[str, dict] = {
    "forest": dict(sky=("#5ab0e8", "#c8ecf8"), far="#8ab8d8", near="#5a9a8a", ground=("#5aa84a", "#3f8a3a", "#7cc85a"),
                   accent=("#ffd84a", "#ff8fb4", "#f8f4ea"), sun=True, caps=True),
    "night": dict(sky=("#141a3a", "#3a3a6a"), far="#2a2f58", near="#1f2a48", ground=("#2f5a4a", "#1f4038", "#3f7058"),
                  accent=("#9ad4ff", "#c8a8ff", "#fff8c8"), moon=True, stars=True),
    "desert": dict(sky=("#f0a860", "#fce0a8"), far="#e8a878", near="#d08a58", ground=("#e8c47a", "#c89a58", "#f8dc98"),
                   accent=("#c84a3a", "#5aa048", "#f8f0d8"), sun=True),
    "snow": dict(sky=("#6a8ac8", "#d8e8f8"), far="#a8c0e0", near="#7a98c0", ground=("#e8f0f8", "#b8c8e0", "#ffffff"),
                 accent=("#9ad4ff", "#c8e0ff", "#ffffff"), aurora=True, stars=True, caps=True),
    "lava": dict(sky=("#2a0a0a", "#a83a1a"), far="#5a1f1a", near="#3a1414", ground=("#4a2a2a", "#2a1414", "#6a3a30"),
                 accent=("#ff8a2a", "#ffd04a", "#ff4a1a"), glow=True),
    "ocean": dict(sky=("#3aa0e8", "#bfeaff"), far="#7ab8e0", near="#2a7ac0", ground=("#f0d79a", "#d9b878", "#fff0c0"),
                  accent=("#ff8fb4", "#ffd84a", "#ffffff"), sun=True, sea=True),
    "candy": dict(sky=("#ff9ec8", "#ffe0f0"), far="#f8b8e0", near="#e890d0", ground=("#a8e8a0", "#78c890", "#d0f8c0"),
                  accent=("#ff5a9a", "#5ad8ff", "#ffffff"), sun=True),
    "neon": dict(sky=("#0d0221", "#3a0a5a"), far="#2a0a4a", near="#1a0838", ground=("#1a1030", "#0d0820", "#2a1a50"),
                 accent=("#2de2e6", "#f6019d", "#f9c80e"), stars=True, grid=True),
}


class _Img:
    def __init__(self) -> None:
        self.px = np.zeros((H, W, 3), np.uint8)

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: RGB) -> None:
        x0, x1 = max(0, int(x0)), min(W - 1, int(x1))
        y0, y1 = max(0, int(y0)), min(H - 1, int(y1))
        if x0 <= x1 and y0 <= y1:
            self.px[y0:y1 + 1, x0:x1 + 1] = c

    def set(self, x: float, y: float, c: RGB) -> None:
        x, y = int(round(x)), int(round(y))
        if 0 <= x < W and 0 <= y < H:
            self.px[y, x] = c

    def disc(self, cx: float, cy: float, rx: float, ry: float, c: RGB) -> None:
        ys, xs = np.ogrid[0:H, 0:W]
        m = ((xs + 0.5 - cx) / max(rx, 0.1)) ** 2 + ((ys + 0.5 - cy) / max(ry, 0.1)) ** 2 <= 1
        self.px[m] = c

    def poly(self, pts: list[tuple[float, float]], c: RGB) -> None:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        for y in range(max(0, int(min(ys))), min(H, int(max(ys)) + 1)):
            hits = []
            n = len(pts)
            for i in range(n):
                (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
                if (ay <= y + 0.5 < by) or (by <= y + 0.5 < ay):
                    hits.append(ax + (y + 0.5 - ay) / (by - ay) * (bx - ax))
            hits.sort()
            for a, b in zip(hits[::2], hits[1::2]):
                self.rect(int(math.ceil(a - 0.5)), y, int(math.floor(b - 0.5)), y, c)
        del xs


def _ridge(rng: random.Random, base: float, amp: float, rough: float) -> np.ndarray:
    """A mountain or hill line: heights per column (sum of a few sines, then sharpened into peaks)."""
    x = np.arange(W, dtype=np.float64)
    y = np.zeros(W)
    for k in range(4):
        f = (0.006 + 0.01 * k) * (1 + rough * k)
        y += math.pow(0.55, k) * np.sin(x * f + rng.uniform(0, 6.28))
    y = np.abs(y) if rough > 0.5 else y
    return base - amp * (y - y.min()) / max(1e-6, y.max() - y.min())


def _sky(img: _Img, t: dict, rng: random.Random) -> None:
    top, bottom = _c(t["sky"][0]), _c(t["sky"][1])
    bands = 10
    for y in range(GROUND + 10):
        f = min(1.0, y / (GROUND + 10))
        band = f * bands
        k = int(band)
        frac = band - k
        c0 = _mix(top, bottom, k / bands)
        c1 = _mix(top, bottom, min(1.0, (k + 1) / bands))
        for x in range(W):  # dither the band edges
            img.px[y, x] = c1 if frac > 0.75 and (x + y) % 2 == 0 else c0
    if t.get("stars"):
        for _ in range(140):
            x, y = rng.randrange(W), rng.randrange(GROUND - 20)
            img.set(x, y, _c("#fff8e8") if rng.random() < 0.3 else _mix(bottom, (255, 255, 255), 0.5))
    if t.get("aurora"):
        for band, col in ((40, "#7af0c8"), (52, "#9ad4ff")):
            for x in range(W):
                yy = band + 10 * math.sin(x * 0.02 + band) + 4 * math.sin(x * 0.07)
                for d in range(8):
                    if (x + d) % 2 == 0 or d < 4:
                        img.set(x, yy + d, _mix(img.px[min(H - 1, max(0, int(yy + d))), x].tolist(), _c(col), 0.5 - d * 0.05))
    if t.get("sun"):
        cx, cy = 380, 46
        img.disc(cx, cy, 26, 26, _mix(bottom, (255, 255, 230), 0.4))
        img.disc(cx, cy, 18, 18, (255, 246, 200))
        img.disc(cx - 4, cy - 4, 8, 8, (255, 255, 240))
    if t.get("moon"):
        img.disc(372, 44, 20, 20, _mix(bottom, (255, 255, 255), 0.2))
        img.disc(372, 44, 15, 15, (240, 236, 210))
        img.disc(380, 40, 13, 13, _mix(top, bottom, 0.3))
    if t.get("glow"):
        for y in range(GROUND - 60, GROUND + 10):
            f = (y - (GROUND - 60)) / 70
            for x in range(0, W, 1):
                if (x + y) % 3 != 0:
                    img.px[y, x] = _mix(img.px[y, x].tolist(), _c("#ff6a2a"), f * 0.35)
    # a few clouds
    if not t.get("stars") and not t.get("glow"):
        for _ in range(4):
            cx, cy = rng.randrange(W), rng.randrange(20, 80)
            col = _mix(bottom, (255, 255, 255), 0.75)
            shade = _mix(bottom, (255, 255, 255), 0.45)
            for k in range(5):
                rx = rng.randint(10, 18)
                img.disc(cx + k * 12 - 24, cy - (k % 2) * 5 + 2, rx, rx * 0.55, shade)
                img.disc(cx + k * 12 - 25, cy - (k % 2) * 5, rx, rx * 0.5, col)


def _mountains(img: _Img, t: dict, rng: random.Random) -> None:
    sky_bottom = _c(t["sky"][1])
    for col, base, amp, rough in ((_mix(_c(t["far"]), sky_bottom, 0.25), GROUND - 22, 70, 1.0),
                                  (_c(t["near"]), GROUND + 2, 45, 0.3)):
        ridge = _ridge(rng, base, amp, rough)
        light = _mix(col, (255, 255, 255), 0.12)
        for x in range(W):
            top = int(ridge[x])
            img.rect(x, top, x, GROUND + 20, col)
            if x > 0 and ridge[x] < ridge[x - 1]:  # lit slopes facing the light (left)
                img.rect(x, top, x, top + 3, light)
        if rough > 0.5 and t.get("caps"):  # snowy caps on the far range's peaks
            line = base - amp * 0.62
            for x in range(W):
                top = int(ridge[x])
                if top < line:
                    img.rect(x, top, x, top + int((line - top) * 0.5) + 1, (248, 250, 255))


def _tree(img: _Img, x: float, y: float, s: float, leaf: RGB, rng: random.Random, willow: bool = False,
          trunk: RGB = (110, 70, 44)) -> None:
    dark = _mix(leaf, (20, 30, 40), 0.35)
    light = _mix(leaf, (255, 255, 220), 0.3)
    tw = max(3, int(5 * s))
    img.rect(x - tw // 2, y - 40 * s, x + tw // 2, y, trunk)
    img.rect(x - tw // 2, y - 40 * s, x - tw // 2, y, _mix(trunk, (255, 230, 200), 0.25))
    img.poly([(x - tw * 1.5, y), (x + tw * 1.5, y), (x + tw // 2, y - 6 * s), (x - tw // 2, y - 6 * s)], trunk)
    cy = y - 48 * s
    for k in range(7):
        a = k / 7 * math.tau
        img.disc(x + math.cos(a) * 14 * s, cy + math.sin(a) * 9 * s + 3 * s, 12 * s, 10 * s, dark)
    for k in range(6):
        a = k / 6 * math.tau + 0.3
        img.disc(x + math.cos(a) * 11 * s - 2 * s, cy + math.sin(a) * 7 * s - 2 * s, 11 * s, 9 * s, leaf)
    img.disc(x - 6 * s, cy - 6 * s, 7 * s, 5 * s, light)
    if willow:  # hanging strands, like the willows in the reference art
        for k in range(14):
            sx = x + rng.uniform(-24, 24) * s
            length = rng.uniform(18, 40) * s
            sway = rng.uniform(-3, 3)
            for d in range(int(length)):
                img.set(sx + sway * d / length, cy + 6 * s + d, leaf if d % 5 else light)


def _pine(img: _Img, x: float, y: float, s: float, leaf: RGB, snow: bool = False) -> None:
    dark = _mix(leaf, (10, 20, 30), 0.35)
    img.rect(x - 1, y - 8 * s, x + 1, y, (90, 60, 40))
    for k in range(4):
        w = (16 - k * 3.2) * s
        top = y - (10 + k * 10) * s - 12 * s
        img.poly([(x - w, y - (8 + k * 10) * s), (x + w, y - (8 + k * 10) * s), (x, top)], dark)
        img.poly([(x - w + 2, y - (9 + k * 10) * s), (x + w * 0.3, y - (9 + k * 10) * s), (x, top + 2)], leaf)
        if snow:
            img.poly([(x - w * 0.6, y - (13 + k * 10) * s), (x + w * 0.6, y - (13 + k * 10) * s), (x, top)], (240, 246, 255))


def _scenery(img: _Img, theme: str, t: dict, rng: random.Random) -> None:
    g = _c(t["ground"][0])
    if theme == "forest":
        for x in (90, 200, 290, 390):  # small trees in the distance, big willows framing the scene
            _tree(img, x + rng.randint(-10, 10), GROUND - 2, 0.6, _c("#3f8a5a"), rng)
        for x, sc in ((10, 2.3), (150, 1.3), (350, 1.4), (470, 2.2)):
            _tree(img, x, GROUND + 8, sc, _c("#4a9a4a"), rng, willow=True)
    elif theme == "candy":
        for x in (30, 140, 330, 450):
            s = rng.uniform(1.0, 1.4)
            img.rect(x - 2, GROUND - 40 * s, x + 2, GROUND + 4, (250, 240, 240))
            img.disc(x, GROUND - 46 * s, 16 * s, 16 * s, _c(rng.choice(("#ff5a9a", "#5ad8ff", "#ffd84a"))))
            for k in range(3):
                img.disc(x - 3 + k * 2, GROUND - 46 * s - 3, 12 * s - k * 4 * s, 12 * s - k * 4 * s,
                         (255, 255, 255) if k % 2 else _c("#ff8fc8"))
    elif theme == "night":
        for x in range(0, W + 30, 34):
            _pine(img, x + rng.randint(-8, 8), GROUND + 4, rng.uniform(1.0, 1.6), _c("#1f4a48"))
        for _ in range(26):  # fireflies
            img.set(rng.randrange(W), rng.randrange(GROUND - 60, GROUND + 30), _c("#e8ff8a"))
    elif theme == "snow":
        for x in range(10, W + 30, 44):
            _pine(img, x + rng.randint(-10, 10), GROUND + 4, rng.uniform(1.0, 1.5), _c("#2f6a6a"), snow=True)
    elif theme == "desert":
        for x0, w, h in ((40, 120, 22), (250, 160, 28), (390, 120, 18)):
            img.disc(x0 + w / 2, GROUND + 6, w / 2, h, _mix(g, _c("#c88a50"), 0.4))
        for x in (90, 110, 130):  # ruined pillars
            hgt = rng.randint(30, 60)
            img.rect(x - 5, GROUND - hgt, x + 5, GROUND + 4, _c("#d8b888"))
            img.rect(x - 5, GROUND - hgt, x - 3, GROUND + 4, _c("#f0d8a8"))
            img.rect(x - 7, GROUND - hgt - 4, x + 7, GROUND - hgt, _c("#c8a070"))
        for x in (320, 430):
            img.rect(x - 3, GROUND - 34, x + 3, GROUND + 4, _c("#5aa048"))
            img.rect(x - 12, GROUND - 24, x - 3, GROUND - 20, _c("#5aa048"))
            img.rect(x - 12, GROUND - 32, x - 9, GROUND - 20, _c("#5aa048"))
            img.rect(x + 3, GROUND - 18, x + 10, GROUND - 14, _c("#5aa048"))
            img.rect(x + 7, GROUND - 28, x + 10, GROUND - 14, _c("#5aa048"))
    elif theme == "lava":
        img.poly([(250, GROUND + 4), (330, GROUND - 90), (350, GROUND - 90), (440, GROUND + 4)], _c("#3a1a1a"))
        img.poly([(330, GROUND - 90), (350, GROUND - 90), (346, GROUND - 60), (334, GROUND - 70)], _c("#ff6a1a"))
        for d in range(60):
            img.set(340 + 12 * math.sin(d * 0.2), GROUND - 88 + d * 1.5, _c("#ffb03a"))
        for x in (40, 140, 450):  # dead trees
            img.rect(x - 2, GROUND - 50, x + 2, GROUND + 4, _c("#2a1414"))
            img.rect(x - 14, GROUND - 40, x, GROUND - 38, _c("#2a1414"))
            img.rect(x, GROUND - 30, x + 12, GROUND - 28, _c("#2a1414"))
    elif theme == "ocean":
        sea = _c("#2a82d0")
        img.rect(0, GROUND - 24, W, GROUND + 6, sea)
        for y in range(GROUND - 24, GROUND + 6, 4):
            for x in range(rng.randrange(8), W, 16):
                img.rect(x, y, x + 5, y, _c("#7fd0ff"))
        for x in (40, 430):
            for d in range(60):
                img.rect(x + d * 0.3 - 2, GROUND + 4 - d, x + d * 0.3 + 2, GROUND + 4 - d, _c("#9a6238"))
            for a in range(6):
                ang = a / 6 * math.tau
                for d in range(26):
                    img.rect(x + 18 + math.cos(ang) * d, GROUND - 56 + math.sin(ang) * d * 0.5 + d * d * 0.02,
                             x + 19 + math.cos(ang) * d, GROUND - 55 + math.sin(ang) * d * 0.5 + d * d * 0.02, _c("#3f9a4a"))
    elif theme == "neon":
        for x in range(0, W, 26):
            h = rng.randint(30, 100)
            w = rng.randint(16, 24)
            img.rect(x, GROUND - h, x + w, GROUND + 4, _c("#1a0a30"))
            img.rect(x, GROUND - h, x + w, GROUND - h, _c(rng.choice(t["accent"])))
            for wy in range(GROUND - h + 6, GROUND, 6):
                for wx in range(x + 3, x + w - 2, 5):
                    if rng.random() < 0.45:
                        img.rect(wx, wy, wx + 1, wy + 1, _c(rng.choice(t["accent"])))


def _ground(img: _Img, theme: str, t: dict, rng: random.Random) -> None:
    base, dark, light = (_c(c) for c in t["ground"])
    edge = [GROUND + int(3 * math.sin(x * 0.05) + 2 * math.sin(x * 0.13)) for x in range(W)]
    for x in range(W):
        img.rect(x, edge[x], x, H - 1, base)
        img.rect(x, edge[x], x, edge[x] + 1, light)
    # a lighter clearing where the fight happens, and depth: darker toward the bottom (dithered bands)
    noise = np.random.default_rng(rng.randrange(1 << 30)).random((H, W))
    for y in range(GROUND, H):
        depth = max(0.0, (y - 190) / (H - 190))
        for x in range(W):
            if y < edge[x]:
                continue
            cx = ((x - 240) / 250) ** 2 + ((y - 172) / 26) ** 2
            if cx < 0.7 or (cx < 1 and noise[y, x] < 0.5):
                img.px[y, x] = _mix(base, light, 0.35)
            elif depth > 0 and noise[y, x] < depth * 0.9:
                img.px[y, x] = _mix(base, dark, 0.5 + 0.5 * min(1.0, depth * 1.3))
    # tufts, flowers and stones
    for _ in range(220):
        x, y = rng.randrange(W), rng.randrange(GROUND + 6, H)
        if theme in ("desert", "ocean"):
            img.set(x, y, dark if rng.random() < 0.7 else light)
            continue
        img.set(x, y, dark)
        img.set(x - 1, y - 1, dark)
        img.set(x + 1, y - 2, _mix(dark, light, 0.5))
    for _ in range(40):
        x, y = rng.randrange(W), rng.randrange(GROUND + 8, H)
        col = _c(rng.choice(t["accent"]))
        img.set(x, y, col)
        img.set(x + 1, y, col)
        img.set(x, y - 1, (255, 255, 240) if theme != "neon" else col)
    for _ in range(10):
        x, y = rng.randrange(W), rng.randrange(GROUND + 10, H)
        s = rng.uniform(2, 5)
        img.disc(x, y, s * 1.4, s, _mix(dark, (90, 90, 100), 0.5))
        img.disc(x - 1, y - 1, s * 0.8, s * 0.5, _mix(light, (200, 200, 210), 0.5))
    if t.get("grid"):
        for y in range(GROUND + 8, H, 10):
            img.rect(0, y, W - 1, y, _mix(base, _c("#f6019d"), 0.5))
        for x in range(-400, W + 400, 40):
            for y in range(GROUND, H):
                xx = 240 + (x - 240) * (y - GROUND + 20) / 60
                img.set(xx, y, _mix(base, _c("#2de2e6"), 0.6))


def backdrop(theme: str, seed: int = 0) -> np.ndarray:
    t = THEMES.get(theme, THEMES["forest"])
    rng = random.Random(f"battle:{theme}:{seed}")
    img = _Img()
    _sky(img, t, rng)
    _mountains(img, t, rng)
    _scenery(img, theme, t, rng)
    _ground(img, theme, t, rng)
    out = np.full((H, W, 4), 255, np.uint8)
    out[..., :3] = img.px
    return out
