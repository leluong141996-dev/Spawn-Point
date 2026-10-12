"""Record a gameplay GIF of a built project (autopilot + screenshots -> optimized GIF).

Needs a display (the game renders in a real window for a few seconds).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from . import godot
from .manifest import ADDON_DIR

RECORD_SCENE = "res://addons/spawn_point/tools/record.tscn"


def record_frames(project: Path, out_dir: Path, seconds: float, fps: int, skip: float = 0.0) -> list[Path]:
    # Projects built before the recorder existed get the current tool copied in.
    tools = project / "addons" / "spawn_point" / "tools"
    for name in ("record.gd", "record.tscn"):
        shutil.copy2(ADDON_DIR / "tools" / name, tools / name)
    step = max(1, round(60 / fps))
    total = int(seconds * 60)
    cmd = [godot.find_binary(), "--path", str(project), "--fixed-fps", "60", RECORD_SCENE,
           "--", str(out_dir), str(total), str(step), str(int(skip * 60))]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=(seconds + skip) * 20 + 60)
    frames = sorted(out_dir.glob("frame_*.png"))
    if not frames:
        raise godot.GodotError("recording produced no frames (is a display available?)", proc.stdout + proc.stderr)
    return frames


def make_gif(frames: list[Path], out: Path, fps: int, width: int, colors: int = 256) -> Path:
    images = [Image.open(f).convert("RGB") for f in frames]
    w, h = images[0].size
    size = (width, round(h * width / w))
    resample = Image.NEAREST if w % width == 0 else Image.LANCZOS  # exact halves keep pixel art crisp
    images = [im.resize(size, resample) for im in images]
    # One shared palette (sampled across the clip) so colors don't flicker between frames.
    sample = Image.new("RGB", (size[0], size[1] * min(6, len(images))))
    for i, im in enumerate(images[:: max(1, len(images) // 6)][:6]):
        sample.paste(im, (0, i * size[1]))
    # Octree keeps small saturated sprites; median cut spends the palette on big gradients (cartoon skies).
    palette = sample.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    quantized = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    out.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(out, save_all=True, append_images=quantized[1:], duration=round(1000 / fps), loop=0,
                      optimize=True, disposal=1)
    return out


def record_gif(project: Path, out: Path, seconds: float = 8.0, fps: int = 20, width: int = 640,
               skip: float = 0.0) -> Path:
    """`skip`: seconds of autopilot play before the clip starts (survivor games get busy later)."""
    with tempfile.TemporaryDirectory() as tmp:
        frames = record_frames(project, Path(tmp), seconds, fps, skip)
        return make_gif(frames, out, fps, width)
