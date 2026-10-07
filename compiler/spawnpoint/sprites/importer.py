"""Import existing art into a SpriteSet: grid sheets, auto-sliced sheets, or folders of frames."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from .spriteset import ANIM_ORDER, SpriteError, SpriteSet, build_sheet, finalize

DEFAULT_FPS = {"idle": 4.0, "run": 10.0, "jump": 8.0, "fall": 8.0, "hurt": 8.0}
ANIM_SYNONYMS = {
    "idle": "idle", "stand": "idle", "rest": "idle", "breath": "idle",
    "run": "run", "walk": "run", "move": "run",
    "jump": "jump", "up": "jump", "fall": "fall", "down": "fall",
    "hurt": "hurt", "hit": "hurt", "damage": "hurt", "pain": "hurt",
}


def parse_ranges(spec: str) -> list[int]:
    """'0-3,7,9-10' -> [0, 1, 2, 3, 7, 9, 10]."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _runs(occupied: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) runs of True values."""
    runs, start = [], None
    for i, v in enumerate(occupied):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(occupied)))
    return runs


def _pad_to(frame: np.ndarray, w: int, h: int, anchor: str) -> np.ndarray:
    out = np.zeros((h, w, 4), dtype=np.uint8)
    fh, fw = frame.shape[:2]
    x = (w - fw) // 2
    y = h - fh if anchor == "bottom" else (h - fh) // 2
    out[y:y + fh, x:x + fw] = frame
    return out


def _trim(frame: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(frame[..., 3] > 0)
    if len(xs) == 0:
        return frame[:1, :1]
    return frame[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def slice_grid(img: np.ndarray, cell: tuple[int, int], spacing: int = 0, margin: int = 0) -> list[list[np.ndarray]]:
    """Rows of cells (empty cells included, so indices match what the artist sees)."""
    cw, ch = cell
    h, w = img.shape[:2]
    rows = []
    y = margin
    while y + ch <= h:
        row = []
        x = margin
        while x + cw <= w:
            row.append(img[y:y + ch, x:x + cw])
            x += cw + spacing
        rows.append(row)
        y += ch + spacing
    if not rows or not rows[0]:
        raise SpriteError(f"a {cw}x{ch} grid does not fit a {w}x{h} sheet")
    return rows


def slice_auto(img: np.ndarray) -> list[list[np.ndarray]]:
    """Frames separated by fully transparent gutters. Returns rows of trimmed frames."""
    alpha = img[..., 3] > 0
    row_runs = _runs(alpha.any(axis=1))
    if not row_runs:
        raise SpriteError("the image is fully transparent")
    rows = []
    for y0, y1 in row_runs:
        band = img[y0:y1]
        cols = _runs((band[..., 3] > 0).any(axis=0))
        rows.append([_trim(band[:, x0:x1]) for x0, x1 in cols])
    return rows


def _empty(frame: np.ndarray) -> bool:
    return not (frame[..., 3] > 0).any()


def from_rows(name: str, rows: list[list[np.ndarray]], *, anims: dict[str, list[int]] | None = None,
              row_names: list[str] | None = None, fps: dict[str, float] | None = None, scale: int = 2,
              anchor: str = "bottom", trim: bool = False) -> SpriteSet:
    fps = {**DEFAULT_FPS, **(fps or {})}
    flat = [f for row in rows for f in row]
    if anims:
        chosen = {}
        for anim, idx in anims.items():
            bad = [i for i in idx if not 0 <= i < len(flat)]
            if bad:
                raise SpriteError(f"animation '{anim}' uses frame {bad[0]}, but the sheet has {len(flat)} frames (0-{len(flat) - 1})")
            empty = [i for i in idx if _empty(flat[i])]
            if empty:
                raise SpriteError(f"animation '{anim}' uses empty frame(s) {empty}; non-empty frames are "
                                  f"{[i for i, f in enumerate(flat) if not _empty(f)]}")
            chosen[anim] = [flat[i] for i in idx]
    else:
        nonempty_rows = [[f for f in row if not _empty(f)] for row in rows]
        nonempty_rows = [r for r in nonempty_rows if r]
        if not nonempty_rows:
            raise SpriteError("no non-empty frames found")
        if row_names:
            if len(row_names) > len(nonempty_rows):
                raise SpriteError(f"{len(row_names)} row names given but the sheet has {len(nonempty_rows)} rows")
            chosen = {n: nonempty_rows[i] for i, n in enumerate(row_names)}
        elif len(nonempty_rows) > 1:
            chosen = {(ANIM_ORDER[i] if i < len(ANIM_ORDER) else f"row{i}"): r for i, r in enumerate(nonempty_rows)}
        else:
            chosen = {"idle": nonempty_rows[0]}
    if trim:
        chosen = {k: [_trim(f) for f in v] for k, v in chosen.items()}
    w = max(f.shape[1] for fs in chosen.values() for f in fs)
    h = max(f.shape[0] for fs in chosen.values() for f in fs)
    frames = {k: [_pad_to(f, w, h, anchor) for f in v] for k, v in chosen.items()}
    sheet, animations = build_sheet(frames, {k: fps.get(k, 8.0) for k in frames}, {k: k not in ("jump", "fall", "hurt") for k in frames})
    return finalize(name, sheet, (w, h), animations, scale, anchor)


def import_sheet(path: Path, name: str | None = None, *, grid: tuple[int, int] | None = None, spacing: int = 0,
                 margin: int = 0, anims: dict[str, list[int]] | None = None, row_names: list[str] | None = None,
                 fps: dict[str, float] | None = None, scale: int = 2, anchor: str = "bottom") -> SpriteSet:
    img = np.asarray(Image.open(path).convert("RGBA"))
    name = name or _clean_name(Path(path).stem)
    if grid:
        rows = slice_grid(img, grid, spacing, margin)
        return from_rows(name, rows, anims=anims, row_names=row_names, fps=fps, scale=scale, anchor=anchor)
    rows = slice_auto(img)
    return from_rows(name, rows, anims=anims, row_names=row_names, fps=fps, scale=scale, anchor=anchor)


_FRAME_FILE = re.compile(r"^(?P<stem>.*?)[\s_\-.]*(?P<num>\d+)$")


def import_folder(directory: Path, name: str | None = None, *, fps: dict[str, float] | None = None,
                  scale: int = 2, anchor: str = "bottom") -> SpriteSet:
    """Frames named like idle_0.png, hero-walk-03.png, run1.png; files without a number are idle."""
    files = sorted(p for p in Path(directory).iterdir() if p.suffix.lower() == ".png")
    if not files:
        raise SpriteError(f"no PNG files in {directory}")
    groups: dict[str, list[tuple[int, np.ndarray]]] = {}
    for p in files:
        m = _FRAME_FILE.match(p.stem)
        stem, num = (m.group("stem"), int(m.group("num"))) if m else (p.stem, 0)
        anim = _anim_name(stem)
        groups.setdefault(anim, []).append((num, np.asarray(Image.open(p).convert("RGBA"))))
    rows_by_anim = {k: [f for _, f in sorted(v, key=lambda t: t[0])] for k, v in groups.items()}
    if "idle" not in rows_by_anim:
        first = next(iter(rows_by_anim))
        rows_by_anim["idle"] = rows_by_anim.pop(first)
    names = list(rows_by_anim)
    return from_rows(name or _clean_name(Path(directory).name), [rows_by_anim[n] for n in names],
                     row_names=names, fps=fps, scale=scale, anchor=anchor, trim=True)


def _anim_name(stem: str) -> str:
    tokens = [t.lower() for t in re.split(r"[\s_\-.]+", stem) if t]
    for t in reversed(tokens):
        if t in ANIM_SYNONYMS:
            return ANIM_SYNONYMS[t]
    return tokens[-1] if tokens else "idle"


def _clean_name(raw: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", raw)
    return "".join(w[:1].upper() + w[1:] for w in words) or "Sprite"


def preview(s: SpriteSet, zoom: int = 6, show_polygon: bool = True) -> Image.Image:
    """Contact sheet: one row per animation, plus the collision outline on the first idle frame."""
    from PIL import ImageDraw

    w, h = s.frame_size
    cols = max(len(a.frames) for a in s.animations.values())
    out = Image.new("RGBA", ((cols + 1) * (w * zoom + 8) + 120, len(s.animations) * (h * zoom + 8) + 8), (40, 44, 60, 255))
    d = ImageDraw.Draw(out)
    for r, (anim, a) in enumerate(s.animations.items()):
        y = 4 + r * (h * zoom + 8)
        d.text((4, y + 4), f"{anim} ({len(a.frames)}f @{a.fps:g})", fill=(255, 241, 232, 255))
        for c, (col, row) in enumerate(a.frames):
            f = Image.fromarray(s.frame(col, row)).resize((w * zoom, h * zoom), Image.NEAREST)
            out.alpha_composite(f, (120 + c * (w * zoom + 8), y))
    if show_polygon and s.polygon:
        idle = s.animations.get("idle") or next(iter(s.animations.values()))
        x0 = 120 + cols * (w * zoom + 8)
        f = Image.fromarray(s.frame(*idle.frames[0])).resize((w * zoom, h * zoom), Image.NEAREST)
        out.alpha_composite(f, (x0, 4))
        pts = [(x0 + px * zoom, 4 + py * zoom) for px, py in s.polygon]
        d.line(pts + pts[:1], fill=(0, 228, 54, 255), width=2)
    return out
