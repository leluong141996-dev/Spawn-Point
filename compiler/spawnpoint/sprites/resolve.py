"""Connects sprites to the compiler: resolve an entity's sprite, derive its collision, plan entries."""

from __future__ import annotations

from pathlib import Path

from ..graph import Entity, Shape
from .generate import KINDS, generate
from .spriteset import SpriteError, SpriteSet, load

SPRITE_DIR = "res://sprites"


def resolve(name: str, ent: Entity, base_dir: Path | None, default_color: str,
            warn=lambda msg: None, style: str = "pixel") -> SpriteSet:
    """`warn(message)` reports a non-fatal problem (an AI sprite falling back to a generated one).
    `style` picks the generator for generated sprites: "pixel" art or smooth "cartoon"."""
    ref = ent.sprite
    if isinstance(ref, str):
        path = Path(ref)
        if not path.is_absolute():
            if base_dir is None:
                raise SpriteError(f"relative sprite path '{ref}' needs the graph's folder (build from a file)")
            path = base_dir / path
        if not path.exists():
            raise SpriteError(f"sprite file '{ref}' not found")
        return load(path)
    if ref.ai is not None:
        from .ai import ai_sprite, provider_from_env

        spec = ref.ai
        if spec.kind not in KINDS:
            raise SpriteError(f"unknown sprite kind '{spec.kind}'")
        provider = provider_from_env()
        if provider is None:
            warn("no image provider configured (SPAWNPOINT_IMAGE_PROVIDER); using a generated sprite")
        else:
            try:
                return ai_sprite(name, spec.kind, spec.prompt, provider, spec.seed)
            except SpriteError as e:
                warn(f"AI sprite failed ({e}); using a generated sprite")
        return _generate(style, name, spec.kind, spec.color or default_color, None, spec.seed)
    gen = ref.generate
    if gen.kind not in KINDS:
        raise SpriteError(f"unknown sprite kind '{gen.kind}'")
    return _generate(style, name, gen.kind, gen.color or default_color, gen.features, gen.seed)


def _generate(style: str, name: str, kind: str, color: str, features, seed: int) -> SpriteSet:
    if style == "cartoon":
        from .cartoon import generate_cartoon
        return generate_cartoon(name, kind, color, features, seed)
    return generate(name, kind, color, features, seed)


def derived_shape(ent: Entity, s: SpriteSet, genre: str) -> Shape:
    """Body collision fitted to the sprite's opaque bounds (smooth shapes for moving bodies)."""
    _, _, bw, bh = s.bounds
    w, h = bw * s.scale, bh * s.scale
    color = ent.shape.color
    if ent.body == "character":
        if genre == "topdown":
            d = min(w, h) * 0.9
            return Shape(type="circle", size=(d, d), color=color)
        return Shape(type="capsule", size=(max(w * 0.8, 4), h), color=color)
    return Shape(type="rect", size=(w, h), color=color)


def plan_entry(entity: str, s: SpriteSet) -> dict:
    fw, fh = s.frame_size
    bx, by, bw, bh = s.bounds
    cx, cy = bx + bw / 2, by + bh / 2  # the entity origin sits at the center of the opaque box
    k = s.scale
    return {
        "texture": f"{SPRITE_DIR}/{entity}.png",
        "frame_size": [fw, fh],
        "scale": k,
        "offset": [round((fw / 2 - cx) * k, 3), round((fh / 2 - cy) * k, 3)],
        "animations": {n: {"frames": [list(f) for f in a.frames], "fps": a.fps, "loop": a.loop}
                       for n, a in s.animations.items()},
        "polygon": [[round((x - cx) * k, 2), round((y - cy) * k, 2)] for x, y in safe_polygon(s.polygon)],
        "color": s.color,
        "smooth": s.smooth,
    }


def safe_polygon(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """A simple (non self-intersecting) polygon Godot can decompose; falls back to the convex hull."""
    if len(poly) >= 3 and _is_simple(poly) and abs(_area(poly)) > 0.5:
        return poly
    return convex_hull(poly)


def convex_hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    p = sorted(set(pts))
    if len(p) < 3:
        return p

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list = []
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def _area(pts) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])) / 2


def _is_simple(pts: list[tuple[float, float]]) -> bool:
    n = len(pts)
    if len(set(pts)) != n:
        return False
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _intersect(*segs[i], *segs[j]):
                return False
    return True


def _intersect(a, b, c, d) -> bool:
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True

    def on(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    return (o1 == 0 and on(a, c, b)) or (o2 == 0 and on(a, d, b)) or (o3 == 0 and on(c, a, d)) or (o4 == 0 and on(c, b, d))


__all__ = ["resolve", "derived_shape", "plan_entry", "safe_polygon", "SpriteError", "SPRITE_DIR"]
