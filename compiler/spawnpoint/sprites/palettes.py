"""Classic pixel-art palettes and the helpers that keep generated art inside one.

A game that uses a single small palette looks "designed" instead of "generated": every sprite, tile and
backdrop shares the same colours. The palettes below are the community standards (PICO-8, Sweetie 16,
Endesga 32); `THEME_PALETTE` says which suits which game theme.
"""

from __future__ import annotations

import numpy as np

PALETTES: dict[str, tuple[str, ...]] = {
    "pico8": ("#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f", "#c2c3c7", "#fff1e8",
              "#ff004d", "#ffa300", "#ffec27", "#00e436", "#29adff", "#83769c", "#ff77a8", "#ffccaa"),
    "sweetie16": ("#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070", "#38b764", "#257179",
                  "#29366f", "#3b5dc9", "#41a6f6", "#73eff7", "#f4f4f4", "#94b0c2", "#566c86", "#333c57"),
    "endesga32": ("#be4a2f", "#d77643", "#ead4aa", "#e4a672", "#b86f50", "#733e39", "#3e2731", "#a22633",
                  "#e43b44", "#f77622", "#feae34", "#fee761", "#63c74d", "#3e8948", "#265c42", "#193c3e",
                  "#124e89", "#0099db", "#2ce8f5", "#ffffff", "#c0cbdc", "#8b9bb4", "#5a6988", "#3a4466",
                  "#262b44", "#181425", "#ff0044", "#68386c", "#b55088", "#f6757a", "#e8b796", "#c28569"),
}
NAMES = ("none", *PALETTES)

# Which palette suits which game theme (the brief's palette names).
THEME_PALETTE = {"night": "sweetie16", "forest": "endesga32", "desert": "endesga32", "neon": "sweetie16",
                 "candy": "endesga32", "ocean": "sweetie16", "lava": "endesga32", "snow": "endesga32"}


def rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def to_lab(colors: np.ndarray) -> np.ndarray:
    """(n, 3) uint8/float RGB -> (n, 3) CIE Lab (D65)."""
    c = np.asarray(colors, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


LIGHTNESS_WEIGHT = 0.55  # hue matters more than brightness: a shaded yellow should stay yellow-ish, not turn green


def _dist(labs: np.ndarray, lab: np.ndarray) -> np.ndarray:
    d = labs - lab
    return np.sqrt((LIGHTNESS_WEIGHT * d[..., 0]) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)


class Palette:
    def __init__(self, name: str):
        self.name = name
        self.hex = PALETTES[name]
        self.rgb = np.array([rgb(c) for c in self.hex], dtype=np.uint8)
        self.lab = to_lab(self.rgb)
        self.light = int(np.argmax(self.lab[:, 0]))
        self.dark = int(np.argmin(self.lab[:, 0]))

    def nearest_index(self, color: tuple[int, int, int], exclude: set[int] = frozenset(),
                      lightness: tuple[float, float] | None = None) -> int:
        """Palette entry closest to `color` (Lab distance), skipping `exclude`; `lightness` limits the Lab L range
        (relaxed step by step when nothing qualifies)."""
        lab = to_lab(np.array([color]))[0]
        d = _dist(self.lab, lab)
        for relax in (0.0, 8.0, 20.0, 1000.0):
            ok = np.ones(len(d), bool)
            if lightness:
                ok &= (self.lab[:, 0] >= lightness[0] - relax) & (self.lab[:, 0] <= lightness[1] + relax)
            for i in exclude:
                ok[i] = False
            if ok.any():
                return int(np.argmin(np.where(ok, d, np.inf)))
        return int(np.argmin(d))

    def index_of(self, color: tuple[int, int, int]) -> int | None:
        hits = np.nonzero((self.rgb == np.array(color, dtype=np.uint8)).all(axis=1))[0]
        return int(hits[0]) if len(hits) else None

    def nearest(self, color: tuple[int, int, int], **kw) -> tuple[int, int, int]:
        r, g, b = self.rgb[self.nearest_index(color, **kw)]
        return int(r), int(g), int(b)

    def snap(self, img: np.ndarray) -> np.ndarray:
        """RGBA array with every pixel's colour replaced by its nearest palette colour (alpha kept; pixels with
        partial alpha are made fully opaque or transparent, pixel art has no half-transparency)."""
        out = img.copy()
        flat = out.reshape(-1, 4)
        opaque = flat[:, 3] >= 128
        flat[~opaque] = 0
        if opaque.any():
            cols, inverse = np.unique(flat[opaque][:, :3], axis=0, return_inverse=True)
            nearest = np.argmin(_dist(to_lab(cols)[:, None, :], self.lab[None, :, :]), axis=1)
            flat[opaque, :3] = self.rgb[nearest][inverse.reshape(-1)]
            flat[opaque, 3] = 255
        return out


_CACHE: dict[str, Palette] = {}


def get(name: str | None) -> Palette | None:
    if not name or name == "none":
        return None
    if name not in PALETTES:
        raise ValueError(f"unknown palette '{name}' (choose from {', '.join(NAMES)})")
    if name not in _CACHE:
        _CACHE[name] = Palette(name)
    return _CACHE[name]
