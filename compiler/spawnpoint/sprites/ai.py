"""AI-drawn sprites (plug-in providers) turned into game-ready SpriteSets.

The image model only supplies the *look*: one picture on a flat magenta background. Everything else is
deterministic — background removal, cropping, downscaling to the kind's pixel size, a 16-color
palette, and animations synthesized from the single frame (diffusion models cannot keep a character
consistent across frames). Results are cached by prompt, so rebuilds cost nothing.

Providers (environment):
  SPAWNPOINT_IMAGE_PROVIDER = a1111 | openai
  SPAWNPOINT_IMAGE_URL      = http://localhost:7860 (a1111) | https://api.openai.com/v1 (openai-compatible)
  SPAWNPOINT_IMAGE_API_KEY, SPAWNPOINT_IMAGE_MODEL (openai)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from .generate import KINDS
from .spriteset import SpriteError, SpriteSet, build_sheet, finalize

CACHE = Path(os.environ.get("SPAWNPOINT_CACHE", Path.home() / ".cache" / "spawnpoint")) / "ai_sprites"
KEY_COLOR = (255, 0, 255)

KIND_HINT = {
    "hero": "a small game hero character, full body, side view facing right",
    "slime": "a small blob monster, side view", "hopper": "a small hopping creature, side view",
    "flyer": "a small flying creature with wings, side view", "robot": "a small boxy robot enemy, side view",
    "turret": "a small cannon turret", "bug": "a small bug creature seen from above",
    "coin": "a single gold coin", "star": "a single star pickup", "gem": "a single gemstone",
    "heart": "a single heart pickup", "orb": "a single glowing orb", "door": "a tall wooden door",
    "exit": "a glowing exit doorway", "portal": "a swirling magic portal", "spikes": "a row of metal spikes",
    "bullet": "a small glowing projectile",
    "beast": "a small four-legged animal, side view", "spider": "a small spider, side view",
    "dragon": "a small winged dragon, side view", "ghost": "a small floating ghost", "snake": "a small snake, side view",
    "key": "a single golden key", "potion": "a single potion bottle with a cork", "scroll": "a single rolled paper scroll",
    "bomb": "a single round black bomb with a lit fuse", "chest": "a single wooden treasure chest",
    "arrow": "a single arrow pointing right", "tree": "a single tree", "bush": "a single round bush",
    "rock": "a single boulder",
}


class ImageProvider(Protocol):
    id: str

    def generate(self, prompt: str, size: int, seed: int) -> Image.Image: ...


def _post(url: str, payload: dict, headers: dict | None = None, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SpriteError(f"image provider returned {e.code}: {e.read()[:200]!r}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SpriteError(f"cannot reach the image provider at {url}: {e}") from e


@dataclass
class A1111Provider:
    """Stable Diffusion WebUI (AUTOMATIC1111 / Forge) txt2img API."""

    url: str = "http://localhost:7860"
    steps: int = 25

    @property
    def id(self) -> str:
        return f"a1111:{self.url}"

    def generate(self, prompt: str, size: int, seed: int) -> Image.Image:
        data = _post(self.url.rstrip("/") + "/sdapi/v1/txt2img", {
            "prompt": prompt, "negative_prompt": "text, watermark, frame, border, multiple characters, shadow, gradient",
            "width": size, "height": size, "steps": self.steps, "seed": seed, "cfg_scale": 7})
        return Image.open(io.BytesIO(base64.b64decode(data["images"][0])))


@dataclass
class OpenAIImagesProvider:
    """OpenAI-compatible /images/generations (OpenAI or a local server speaking the same API)."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    model: str = "gpt-image-1"

    @property
    def id(self) -> str:
        return f"openai:{self.base_url}:{self.model}"

    def generate(self, prompt: str, size: int, seed: int) -> Image.Image:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post(self.base_url.rstrip("/") + "/images/generations",
                     {"model": self.model, "prompt": prompt, "size": f"{size}x{size}", "n": 1,
                      "response_format": "b64_json"}, headers)
        return Image.open(io.BytesIO(base64.b64decode(data["data"][0]["b64_json"])))


def provider_from_env() -> ImageProvider | None:
    kind = os.environ.get("SPAWNPOINT_IMAGE_PROVIDER", "").lower()
    url = os.environ.get("SPAWNPOINT_IMAGE_URL")
    if kind == "a1111":
        return A1111Provider(url or "http://localhost:7860")
    if kind == "openai":
        return OpenAIImagesProvider(url or "https://api.openai.com/v1", os.environ.get("SPAWNPOINT_IMAGE_API_KEY"),
                                    os.environ.get("SPAWNPOINT_IMAGE_MODEL", "gpt-image-1"))
    return None


def build_prompt(description: str, kind: str) -> str:
    return (f"pixel art sprite of {description}, {KIND_HINT.get(kind, 'a small game object')}, centered, "
            f"16-bit retro game asset, crisp pixels, bold outline, on a solid flat magenta (#ff00ff) background")


# --- image -> sprite --------------------------------------------------------------------------

def remove_background(img: Image.Image, tolerance: int = 60) -> np.ndarray:
    """RGBA array with the flat background made transparent (chroma key + corner flood fill)."""
    rgba = np.asarray(img.convert("RGBA")).copy()
    rgb = rgba[..., :3].astype(int)
    h, w = rgb.shape[:2]
    corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
    bg = np.median(corners, axis=0)
    near_bg = np.abs(rgb - bg).sum(axis=2) < tolerance
    near_key = np.abs(rgb - np.array(KEY_COLOR)).sum(axis=2) < tolerance * 1.5
    # Flood fill from the border through background-coloured pixels, so the same colour inside the
    # character (e.g. a white eye on a white background) survives.
    mask = np.zeros((h, w), dtype=bool)
    stack = [(y, x) for y in (0, h - 1) for x in range(w)] + [(y, x) for x in (0, w - 1) for y in range(h)]
    while stack:
        y, x = stack.pop()
        if mask[y, x] or not near_bg[y, x]:
            continue
        mask[y, x] = True
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx]:
                stack.append((ny, nx))
    rgba[mask | near_key, 3] = 0
    return rgba


def to_pixel_frame(rgba: np.ndarray, size: tuple[int, int], colors: int = 16) -> np.ndarray:
    """Crop to the opaque box and fit into `size` (w, h), bottom-centered, with a small palette."""
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(xs) == 0:
        raise SpriteError("the generated image is empty after background removal")
    crop = Image.fromarray(rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1], "RGBA")
    w, h = size
    pad = 1  # room for squash/stretch animation
    scale = min((w - 2 * pad) / crop.width, (h - pad) / crop.height)
    nw, nh = max(1, round(crop.width * scale)), max(1, round(crop.height * scale))
    small = crop.resize((nw, nh), Image.BOX)
    alpha = (np.asarray(small)[..., 3] > 110)
    rgb = small.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    out = np.zeros((h, w, 4), dtype=np.uint8)
    x0, y0 = (w - nw) // 2, h - nh
    out[y0:y0 + nh, x0:x0 + nw, :3] = np.asarray(rgb)
    out[y0:y0 + nh, x0:x0 + nw, 3] = np.where(alpha, 255, 0)
    return out


def _resize_anchor(frame: np.ndarray, sx: float, sy: float, dy: int = 0) -> np.ndarray:
    """Scale the opaque part around its bottom-center (squash & stretch), then shift by dy."""
    h, w = frame.shape[:2]
    ys, xs = np.nonzero(frame[..., 3] > 0)
    crop = Image.fromarray(frame[ys.min():ys.max() + 1, xs.min():xs.max() + 1], "RGBA")
    nw, nh = max(1, round(crop.width * sx)), max(1, round(crop.height * sy))
    nw, nh = min(nw, w), min(nh, h)
    scaled = np.asarray(crop.resize((nw, nh), Image.NEAREST))
    out = np.zeros_like(frame)
    x0 = (w - nw) // 2
    y0 = max(0, min(h - nh, h - nh + dy))
    out[y0:y0 + nh, x0:x0 + nw] = scaled
    return out


def _tint(frame: np.ndarray, color=(255, 255, 255), k: float = 0.6) -> np.ndarray:
    out = frame.copy()
    m = out[..., 3] > 0
    out[m, :3] = (out[m, :3] * (1 - k) + np.array(color) * k).astype(np.uint8)
    return out


def animate(base: np.ndarray, kind: str) -> dict[str, list[np.ndarray]]:
    anims = KINDS[kind].anims if kind in KINDS else {"idle": (2, 3, True)}
    frames: dict[str, list[np.ndarray]] = {}
    for name in anims:
        if name == "idle":
            frames[name] = [base, _resize_anchor(base, 1.06, 0.94)]
        elif name == "run":
            frames[name] = [base, _resize_anchor(base, 0.95, 1.04, -1), base, _resize_anchor(base, 1.05, 0.96)]
        elif name == "jump":
            frames[name] = [_resize_anchor(base, 0.88, 1.1, -1)]
        elif name == "fall":
            frames[name] = [_resize_anchor(base, 1.06, 0.97)]
        elif name == "hurt":
            frames[name] = [_tint(base, (255, 255, 255), 0.55)]
    return frames


def ai_sprite(name: str, kind: str, description: str, provider: ImageProvider, seed: int = 0,
              size: int = 512) -> SpriteSet:
    if kind not in KINDS:
        raise SpriteError(f"unknown sprite kind '{kind}'")
    prompt = build_prompt(description, kind)
    key = hashlib.sha256(f"{provider.id}|{prompt}|{size}|{seed}".encode()).hexdigest()[:24]
    cached = CACHE / f"{key}.png"
    if cached.exists():
        img = Image.open(cached)
    else:
        img = provider.generate(prompt, size, seed)
        CACHE.mkdir(parents=True, exist_ok=True)
        img.save(cached)
    spec = KINDS[kind]
    base = to_pixel_frame(remove_background(img), spec.size)
    frames = animate(base, kind)
    sheet, anims = build_sheet(frames, {a: v[1] for a, v in spec.anims.items()}, {a: v[2] for a, v in spec.anims.items()})
    return finalize(name, sheet, spec.size, anims, 2, spec.anchor)
