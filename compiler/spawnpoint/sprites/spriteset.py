"""SpriteSet: a uniform-grid sprite sheet + animations + bounds/outline, shared by generator and importer."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import contour

FORMAT = 1
ANIM_ORDER = ("idle", "run", "jump", "fall", "hurt")


class SpriteError(ValueError):
    pass


@dataclass
class Animation:
    frames: list[tuple[int, int]]  # (column, row) grid cells
    fps: float = 8.0
    loop: bool = True

    def to_dict(self) -> dict:
        return {"frames": [list(f) for f in self.frames], "fps": self.fps, "loop": self.loop}


@dataclass
class SpriteSet:
    name: str
    sheet: Image.Image
    frame_size: tuple[int, int]
    animations: dict[str, Animation]
    scale: float = 2  # world px per frame px (2 for pixel art, 0.5 for the 4x-detail cartoon style)
    anchor: str = "center"  # center | bottom
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)  # opaque box of the idle pose, frame pixels
    polygon: list[tuple[float, float]] = field(default_factory=list)  # outline of the idle pose
    color: str = "#ffffff"
    smooth: bool = False  # draw with linear filtering (cartoon art) instead of nearest (pixel art)

    @property
    def columns(self) -> int:
        return self.sheet.width // self.frame_size[0]

    @property
    def rows(self) -> int:
        return self.sheet.height // self.frame_size[1]

    def frame(self, col: int, row: int) -> np.ndarray:
        w, h = self.frame_size
        return np.asarray(self.sheet.crop((col * w, row * h, col * w + w, row * h + h)).convert("RGBA"))

    def to_dict(self, image_name: str) -> dict:
        return {
            "format": FORMAT, "name": self.name, "image": image_name, "frame_size": list(self.frame_size),
            "scale": self.scale, "anchor": self.anchor,
            "animations": {k: a.to_dict() for k, a in self.animations.items()},
            "bounds": list(self.bounds), "polygon": [list(p) for p in self.polygon], "color": self.color,
        }

    def save(self, directory: Path, name: str | None = None) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        base = name or self.name
        self.sheet.save(directory / f"{base}.png")
        path = directory / f"{base}.sprite.json"
        path.write_text(json.dumps(self.to_dict(f"{base}.png"), indent=1) + "\n")
        return path


def finalize(name: str, sheet: Image.Image, frame_size: tuple[int, int], animations: dict[str, Animation],
             scale: float = 2, anchor: str = "center") -> SpriteSet:
    """Validates the grid and derives bounds, outline and dominant color from the idle pose."""
    sheet = sheet.convert("RGBA")
    s = SpriteSet(name, sheet, tuple(frame_size), dict(animations), scale, anchor)
    _check(s)
    idle = s.animations.get("idle") or next(iter(s.animations.values()))
    union = np.zeros((frame_size[1], frame_size[0], 4), dtype=np.uint8)
    for col, row in idle.frames:
        f = s.frame(col, row)
        union = np.where(f[..., 3:4] > union[..., 3:4], f, union)
    mask = contour.alpha_mask(union)
    b = contour.bounds(mask)
    if b is None:
        raise SpriteError(f"sprite '{name}': the idle frames are fully transparent")
    s.bounds = b
    s.polygon = contour.outline(union)
    s.color = dominant_color(union)
    return s


def _check(s: SpriteSet) -> None:
    w, h = s.frame_size
    if w <= 0 or h <= 0:
        raise SpriteError(f"sprite '{s.name}': bad frame size {w}x{h}")
    if s.sheet.width % w or s.sheet.height % h:
        raise SpriteError(f"sprite '{s.name}': sheet {s.sheet.width}x{s.sheet.height} is not a multiple of {w}x{h}")
    if not s.animations:
        raise SpriteError(f"sprite '{s.name}': no animations")
    for anim_name, a in s.animations.items():
        if not a.frames:
            raise SpriteError(f"sprite '{s.name}': animation '{anim_name}' has no frames")
        for col, row in a.frames:
            if not (0 <= col < s.columns and 0 <= row < s.rows):
                raise SpriteError(f"sprite '{s.name}': animation '{anim_name}' uses frame ({col},{row}) "
                                  f"outside the {s.columns}x{s.rows} grid")


def dominant_color(rgba: np.ndarray) -> str:
    px = rgba[rgba[..., 3] >= 128][:, :3]
    if len(px) == 0:
        return "#ffffff"
    # Ignore near-black outline pixels, quantize, take the most common.
    lum = px.astype(int).sum(axis=1)
    px = px[lum > 120] if (lum > 120).any() else px
    q = (px // 16) * 16 + 8
    (r, g, b), _ = Counter(map(tuple, q.tolist())).most_common(1)[0]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def load(path: Path) -> SpriteSet:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SpriteError(f"cannot read sprite file {path}: {e}") from e
    try:
        image = Image.open(path.parent / data["image"]).convert("RGBA")
        anims = {k: Animation([tuple(f) for f in v["frames"]], float(v.get("fps", 8)), bool(v.get("loop", True)))
                 for k, v in data["animations"].items()}
        s = SpriteSet(data.get("name", path.stem), image, tuple(data["frame_size"]), anims,
                      int(data.get("scale", 2)), data.get("anchor", "center"))
    except (KeyError, OSError, TypeError, ValueError) as e:
        raise SpriteError(f"invalid sprite file {path}: {e}") from e
    _check(s)
    if data.get("bounds") and data.get("polygon"):
        s.bounds = tuple(data["bounds"])
        s.polygon = [tuple(p) for p in data["polygon"]]
        s.color = data.get("color", "#ffffff")
        return s
    return finalize(s.name, s.sheet, s.frame_size, s.animations, s.scale, s.anchor)


def build_sheet(frames: dict[str, list[np.ndarray]], fps: dict[str, float], loop: dict[str, bool]
                ) -> tuple[Image.Image, dict[str, Animation]]:
    """Lays out frames row-per-animation in ANIM_ORDER (then any others)."""
    names = [n for n in ANIM_ORDER if n in frames] + [n for n in frames if n not in ANIM_ORDER]
    h, w = next(iter(frames.values()))[0].shape[:2]
    cols = max(len(frames[n]) for n in names)
    sheet = np.zeros((h * len(names), w * cols, 4), dtype=np.uint8)
    anims = {}
    for row, n in enumerate(names):
        for col, f in enumerate(frames[n]):
            sheet[row * h:(row + 1) * h, col * w:(col + 1) * w] = f
        anims[n] = Animation([(c, row) for c in range(len(frames[n]))], fps.get(n, 8.0), loop.get(n, True))
    return Image.fromarray(sheet, "RGBA"), anims
