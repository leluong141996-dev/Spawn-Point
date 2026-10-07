"""Collision outlines from pixels: alpha mask -> outer contour -> simplified polygon (numpy only)."""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

Point = tuple[float, float]


def alpha_mask(rgba: np.ndarray, threshold: int = 32) -> np.ndarray:
    return rgba[..., 3] >= threshold


def bounds(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Opaque bounding box (x, y, w, h), or None for an empty mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def close_gaps(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Morphological closing so detached details (eyes, antennae) join the body outline."""
    if radius <= 0:
        return mask
    padded = np.pad(mask, radius + 1)
    grown = padded.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            grown |= np.roll(np.roll(padded, dy, 0), dx, 1)
    shrunk = grown.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shrunk &= np.roll(np.roll(grown, dy, 0), dx, 1)
    r = radius + 1
    return shrunk[r:-r, r:-r] | mask


def largest_component(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        comp = []
        q = deque([(sy, sx)])
        seen[sy, sx] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if len(comp) > len(best):
            best = comp
    out = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        out[y, x] = True
    return out


def outer_contour(mask: np.ndarray) -> list[tuple[int, int]]:
    """Outer boundary of a component along pixel edges (grid corners), clockwise in image space."""
    h, w = mask.shape
    m = np.pad(mask, 1)
    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for y, x in zip(*np.nonzero(mask)):
        py, px = y + 1, x + 1
        if not m[py - 1, px]:
            edges[(x, y)].append((x + 1, y))
        if not m[py, px + 1]:
            edges[(x + 1, y)].append((x + 1, y + 1))
        if not m[py + 1, px]:
            edges[(x + 1, y + 1)].append((x, y + 1))
        if not m[py, px - 1]:
            edges[(x, y + 1)].append((x, y))
    loops: list[list[tuple[int, int]]] = []
    while edges:
        start = next(iter(edges))
        loop = [start]
        cur = start
        while True:
            nxt_list = edges.get(cur)
            if not nxt_list:
                break
            nxt = nxt_list.pop()
            if not nxt_list:
                del edges[cur]
            if nxt == start:
                break
            loop.append(nxt)
            cur = nxt
        if len(loop) >= 3:
            loops.append(loop)
    if not loops:
        return []
    return max(loops, key=lambda lp: abs(polygon_area(lp)))


def polygon_area(pts) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2


def simplify(points: list[Point], epsilon: float) -> list[Point]:
    """Douglas–Peucker on a closed polygon."""
    if len(points) < 4:
        return list(points)
    # Split at the two mutually farthest-ish points so the closed loop simplifies symmetrically.
    first = points[0]
    far = max(range(len(points)), key=lambda i: (points[i][0] - first[0]) ** 2 + (points[i][1] - first[1]) ** 2)
    a = _dp(points[: far + 1], epsilon)
    b = _dp(points[far:] + [first], epsilon)
    return a[:-1] + b[:-1]


def _dp(pts: list[Point], eps: float) -> list[Point]:
    if len(pts) < 3:
        return list(pts)
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-9
    best_i, best_d = 0, -1.0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if d > best_d:
            best_i, best_d = i, d
    if best_d <= eps:
        return [pts[0], pts[-1]]
    return _dp(pts[: best_i + 1], eps)[:-1] + _dp(pts[best_i:], eps)


def outline(rgba: np.ndarray, epsilon: float = 0.75, close_radius: int = 1) -> list[Point]:
    """Simplified outer outline of the opaque pixels, in pixel coordinates."""
    mask = alpha_mask(rgba)
    if not mask.any():
        return []
    comp = largest_component(close_gaps(mask, close_radius))
    poly = simplify([(float(x), float(y)) for x, y in outer_contour(comp)], epsilon)
    return poly if len(poly) >= 3 else []
