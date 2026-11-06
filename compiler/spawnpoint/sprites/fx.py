"""Skill effects for card battles: short pixel animations played over a fighter (slash, fire vortex, ice shards,
lightning, poison cloud, healing sparkles, shield shimmer, strength aura, curse sigil, hit spark). Each is one
horizontal strip of square frames at FPS frames a second, drawn from code with the vfx toolkit: lines and light
rather than fills, simulated sparks, flame, smoke and embers, a charge, a release, a spread and a long decay.

The hit spark follows pixelfx's hit-spark (https://github.com/patch-gg/pixelfx, MIT, Copyright (c) 2026 Patch), whose
spark spray and light pop adapt Sprite Fusion's open-source impact (https://www.spritefusion.com/pixel-art-vfx/impact,
MIT, Copyright (c) 2026 Hugo Duprez).

World effects (WORLD) play in every pixel-art game through the FX autoload: an enemy popping, landing dust, a pickup
sparkle, a harvest, a splash, and two loops, petals falling from a blossom tree and fireflies at night.

    strip(name) -> RGBA array (size, size * frames, 4); EFFECTS and WORLD list names, sizes and frame counts
"""

from __future__ import annotations

import math
import random

import numpy as np

from .vfx import (BACK, DUST, EMBER, FIRE, FLAKE, GRIT, MOTE, PAL, SMOKE, SMOKES, SPARK, STAR, STREAK, VAPOUR, WHITE, Frame,
                  Lights, Particles, bolt, dim, render, sparkle)

FPS = 20  # the card battle plays every strip at this rate


def _cols(ramp, idx: np.ndarray) -> np.ndarray:
    return np.asarray(ramp, np.float32)[np.clip(idx, 0, len(ramp) - 1)]


class _Slash:
    """A crescent swept from top left to bottom right: white leading edge, steel body, a tail that burns away, sparks
    thrown off the end of the swing and a flare of light where it bites."""

    def __init__(self, R: random.Random) -> None:
        self.C = PAL["metal"]
        self.ps = Particles(R, ground=24, sparks=[WHITE, self.C[6], self.C[5], self.C[3]])
        self.lights, self.R, self.t, self.bit = Lights(), R, 0.0, False

    def update(self, dt: float) -> None:
        self.t += dt
        if not self.bit and self.t >= 0.1:
            self.bit = True
            hx, hy = 24 * math.cos(0.75), 24 * math.sin(0.75)
            self.lights.add(hx, hy, 30, self.C[6], 0.55, 0.22)
            for _ in range(9):
                a = 0.75 + math.pi / 2 + self.R.uniform(-0.7, 0.5)
                v = self.R.uniform(120, 260)
                self.ps.spawn(SPARK, hx, hy, math.cos(a) * v, math.sin(a) * v - 30, self.R.uniform(0.2, 0.4))
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        grow = min(1.0, (t + 0.03) / 0.12)
        head = -2.5 + (1 - (1 - grow) ** 2) * 3.25          # fast attack, easing into the end of the swing
        tail = head - 2.1 * grow if t < 0.16 else head - 2.1 * max(0.0, 1 - (t - 0.16) / 0.22)
        fade = 1.0 if t < 0.24 else max(0.0, 1 - (t - 0.24) / 0.16)
        if head - tail > 0.05 and fade > 0:
            def colour(u, v):
                idx = np.where(u > 0.86, 7, np.where(u > 0.6, 6, np.where(u > 0.32, 5, 4)))
                idx = np.where(v > 0.72, np.minimum(7, idx + 1), idx)
                return _cols(C, idx)
            f.arc(0, 0, 27, lambda u: 6 + 6 * np.sin(np.pi * u) ** 0.8 * fade, tail - 0.5, head - 0.2,
                  lambda u, v: _cols(C, np.where(v > 0.8, 4, 3)), a=0.5 * fade)   # the smear left behind
            f.arc(0, 0, 26, lambda u: 11 * np.sin(np.pi * u) ** 0.7 * fade, tail, head, colour,
                  a=lambda_alpha(fade))
            for k in range(6):
                ang = tail + (head - tail) * (k + 0.5) / 6
                f.glow(21 * math.cos(ang), 21 * math.sin(ang), 12, C[6], 0.22 * fade * (k + 1) / 6)
        self.ps.draw(f)
        self.lights.draw(f)


def lambda_alpha(fade: float) -> float:
    """Arcs fade out by dither: the last of the swing thins pixel by pixel instead of turning see-through."""
    return 1.0 if fade >= 1 else fade


class _Fire:
    """A fire vortex: a white flash, then balls of flame spiral up off the target and cool into smoke, embers drift,
    a warm pool of light breathes underneath."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.acc = R, 0.0, 0.0
        self.ps = Particles(R, ground=20, sparks=[PAL["fire"][7], PAL["fire"][6], PAL["fire"][5], PAL["fire"][3]])
        self.lights = Lights()
        self.lights.add(0, 6, 34, PAL["fire"][5], 0.6, 0.35)

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if self.t < 0.5:
            self.acc += dt * 150
            while self.acc > 1:
                self.acc -= 1
                a = R.uniform(0, math.tau)  # round the feet, swirling as it rises
                r = R.uniform(2, 13) * (1 - self.t * 0.5)
                self.ps.spawn(FIRE, math.cos(a) * r, 16 + math.sin(a) * r * 0.3, -math.sin(a) * 22,
                              R.uniform(-120, -60), R.uniform(0.3, 0.55), None, R.uniform(3, 6) * (1.2 - r / 20), 0,
                              SMOKES if R.random() < 0.3 else 0)
                if R.random() < 0.12:
                    self.ps.spawn(EMBER, R.uniform(-8, 8), 10, R.uniform(-20, 20), R.uniform(-80, -40), R.uniform(0.5, 0.9))
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        F = PAL["fire"]
        if t < 0.06:
            f.circle(0, 10, 7 * (1 - t / 0.06) + 2, F[7])
            f.ring(0, 10, 12 + t * 120, 1.5, F[6], sy=0.4)
        heat = max(0.0, 1 - t / 0.75)
        f.glow(0, 12, 26, F[4], 0.35 * heat)
        f.glow(0, 12, 10, F[6], 0.25 * heat)
        self.ps.draw(f, "back")
        self.ps.draw(f, "front")
        self.lights.draw(f)


def _spike(f: Frame, ang: float, L: float, w: float, C, a: float = 1.0) -> None:
    """A faceted ice spike from the centre outward: a lit left face, a darker right face, a white tip, a dark rim."""
    ca, sa = math.cos(ang), math.sin(ang)
    d = 2.0
    while d <= L:
        u = d / L
        hw = w * (1 - u) + 0.4
        o = -hw
        while o <= hw:
            col = WHITE if u > 0.84 else C[1] if abs(o) > hw - 0.6 else C[6] if o < -0.3 else C[7] if o < 0.3 else C[4]
            f.put(ca * d - sa * o, sa * d + ca * o, col, a)
            o += 0.5
        d += 0.5


class _Ice:
    """Ice spikes burst out of the target, hold with a glint running up them, then shatter: shards and flakes fly,
    a frost ring spreads, cold light fades."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.broke = R, 0.0, False
        self.C = PAL["ice"]
        self.spikes = [(i * math.tau / 7 + R.uniform(-0.25, 0.25) - 0.4, R.uniform(15, 24), R.uniform(2.2, 3.4)) for i in range(7)]
        self.ps = Particles(R, ground=26, sparks=[WHITE, self.C[6], self.C[5], self.C[3]])
        self.lights = Lights()
        self.lights.add(0, 0, 30, self.C[5], 0.55, 0.3)

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if not self.broke and self.t >= 0.32:
            self.broke = True
            self.lights.add(0, 0, 34, self.C[6], 0.6, 0.2)
            for ang, L, _w in self.spikes:
                for _ in range(3):
                    v = R.uniform(80, 200)
                    a = ang + R.uniform(-0.3, 0.3)
                    self.ps.spawn(SPARK, math.cos(ang) * L * 0.6, math.sin(ang) * L * 0.6, math.cos(a) * v, math.sin(a) * v - 40,
                                  R.uniform(0.25, 0.45))
                for _ in range(2):
                    self.ps.spawn(FLAKE, math.cos(ang) * L * 0.5, math.sin(ang) * L * 0.5, R.uniform(-40, 40), R.uniform(-50, 10),
                                  R.uniform(0.4, 0.8), self.C[6], R.uniform(1, 2))
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        if t < 0.32:
            grow = min(1.0, t / 0.08)
            for ang, L, w in self.spikes:
                _spike(f, ang, L * (1 - (1 - grow) ** 3), w, C, 1.0)
            if 0.12 < t < 0.3:  # a glint running out along the spikes
                g = (t - 0.12) / 0.18
                for ang, L, _w in self.spikes:
                    f.put(math.cos(ang) * L * g, math.sin(ang) * L * g, WHITE)
                    f.glow(math.cos(ang) * L * g, math.sin(ang) * L * g, 4, C[6], 0.3)
        elif t < 0.4:
            for ang, L, w in self.spikes:  # the white break frame, thinning
                _spike(f, ang, L, w * 0.6, [WHITE] * 8, 1 - (t - 0.32) / 0.08)
        ring = t - 0.3
        if 0 < ring < 0.4:
            f.ring(0, 6, 8 + ring * 70, 1.5, C[6], a=1 - ring / 0.4, sy=0.45)
            f.glow_ring(0, 6, 8 + ring * 70, 4, C[5], 0.3 * (1 - ring / 0.4), sy=0.45)
        f.glow(0, 0, 22, C[4], 0.3 * max(0.0, 1 - t / 0.7))
        self.ps.draw(f)
        self.lights.draw(f)


class _Bolt:
    """Lightning: a white-hot jagged bolt with forks strikes from above three times, each a new path, with a flash,
    sparks and a ring where it lands, then it flickers out."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.n = R, 0.0, 0
        self.C = PAL["volt"]
        self.ps = Particles(R, ground=22, sparks=[WHITE, self.C[5], self.C[4], self.C[3]])
        self.lights = Lights()
        self.paths: list = []

    def _strike(self) -> None:
        R = self.R
        main = bolt(R, R.uniform(-10, 10), -31, R.uniform(-2, 2), 4, 6, 9)
        forks = []
        for _ in range(2):
            i = R.randint(2, 6)
            x, y = main[i]
            forks.append(bolt(R, x, y, x + R.choice((-1, 1)) * R.uniform(8, 14), y + R.uniform(6, 12), 3, 4))
        self.paths = [main] + forks
        self.lights.add(0, 4, 40, self.C[5], 0.7, 0.14)
        for _ in range(7):
            a = R.uniform(-math.pi, 0)
            v = R.uniform(120, 260)
            self.ps.spawn(SPARK, 0, 4, math.cos(a) * v, math.sin(a) * v, R.uniform(0.2, 0.4))

    def update(self, dt: float) -> None:
        self.t += dt
        if self.n < 3 and self.t >= self.n * 0.1:
            self.n += 1
            self._strike()
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        since = t - (self.n - 1) * 0.1
        if self.paths and since < 0.07:
            for k, pts in enumerate(self.paths):
                for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                    if k == 0:
                        f.line(xa - 1, ya, xb - 1, yb, C[4])
                        f.line(xa + 1, ya, xb + 1, yb, C[3])
                    f.line(xa, ya, xb, yb, WHITE if k == 0 else C[5])
                    f.glow_line(xa, ya, xb, yb, 5 if k == 0 else 3, C[4], 0.3 if k == 0 else 0.15)
            f.circle(0, 4, 3, WHITE)
            f.ring(0, 6, 6 + since * 140, 1.2, C[5], sy=0.45)
        if t < 0.04 or 0.1 <= t < 0.13:
            f.glow(0, 0, 30, C[5], 0.35)
        self.ps.draw(f)
        self.lights.draw(f)


class _Poison:
    """A poison cloud: green vapour puffs swell and thin round the target with a sickly haze, bubbles rise, wobble
    and pop into specks, drops of venom drip."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.acc = R, 0.0, 0.0
        self.C = PAL["poison"]
        self.ps = Particles(R, ground=22, sparks=[self.C[6], self.C[5], self.C[4], self.C[2]], haze=self.C[4])
        self.bubbles = [(R.uniform(-14, 14), R.uniform(0.0, 0.45), R.uniform(1.6, 3.2), R.uniform(0, 6)) for _ in range(9)]

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if self.t < 0.45:
            self.acc += dt * 60
            while self.acc > 1:
                self.acc -= 1
                a = R.uniform(0, math.tau)
                r = R.uniform(2, 16)
                self.ps.spawn(VAPOUR, math.cos(a) * r, math.sin(a) * r * 0.6 + 4, math.cos(a) * 24, R.uniform(-26, -4),
                              R.uniform(0.5, 0.9), R.choice((self.C[3], self.C[4], self.C[5])), R.uniform(6, 11))
                if R.random() < 0.2:
                    self.ps.spawn(GRIT, R.uniform(-8, 8), R.uniform(-4, 6), R.uniform(-20, 20), R.uniform(-20, 10),
                                  R.uniform(0.4, 0.6), self.C[5])
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        self.ps.draw(f, "back")
        for x, born, r, ph in self.bubbles:  # bubbles rising, wobbling, then popping
            age = t - born
            if age < 0:
                continue
            life = 0.42
            if age < life:
                bx, by = x + math.sin(age * 9 + ph) * 1.5, 12 - age * 46
                f.circle(bx, by, r, C[3])
                f.ring(bx, by, r + 0.6, 1, C[5])
                f.put(bx - r * 0.4, by - r * 0.4, C[6])
                f.glow(bx, by, r * 2.5, C[4], 0.12)
            elif age < life + 0.08:
                bx, by = x + math.sin(life * 9 + ph) * 1.5, 12 - life * 46
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    f.put(bx + dx * (r + 1), by + dy * (r + 1), C[6])
        f.glow(0, 4, 28, C[4], 0.3 * max(0.0, 1 - t / 0.8))
        self.ps.draw(f, "front")


class _Heal:
    """Healing: a ring of light opens on the floor, motes and little crosses rise and twinkle, a soft green glow
    swells and fades."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.acc = R, 0.0, 0.0
        self.C = PAL["heal"]
        self.ps = Particles(R, ground=99, sparks=[WHITE, self.C[6], self.C[5], self.C[4]])

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if self.t < 0.5:
            self.acc += dt * 64
            while self.acc > 1:
                self.acc -= 1
                x = R.uniform(-16, 16)
                if R.random() < 0.7:
                    self.ps.spawn(MOTE, x, R.uniform(8, 20), R.uniform(-6, 6), R.uniform(-110, -60), R.uniform(0.35, 0.6),
                                  R.choice((self.C[5], self.C[6], WHITE)), R.uniform(0.8, 1.2))
                else:
                    self.ps.spawn(STAR, x, R.uniform(-14, 14), 0, R.uniform(-30, -10), R.uniform(0.35, 0.6), self.C[6],
                                  R.uniform(1.5, 3))
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        open_ = min(1.0, t / 0.15)
        fade = max(0.0, 1 - max(0.0, t - 0.45) / 0.3)
        if fade > 0:
            r = 6 + 14 * (1 - (1 - open_) ** 2)
            f.ring(0, 18, r, 1.5, C[6], a=fade, sy=0.32, keep=lambda g: np.sin(g) < 0)
            f.ring(0, 18, r, 1.5, C[7], a=fade, sy=0.32, keep=lambda g: np.sin(g) >= 0)
            f.glow_ring(0, 18, r, 4, C[5], 0.35 * fade, sy=0.32)
            f.glow(0, 4, 28, C[4], 0.42 * fade * open_)
            f.glow(0, 6, 12, C[6], 0.2 * fade * open_)
        self.ps.draw(f)


def _hex_inside(xs: np.ndarray, ys: np.ndarray, R: float) -> np.ndarray:
    s = math.sin(math.pi / 3)
    return (np.abs(ys) <= R * s) & (np.abs(xs) * s + np.abs(ys) * 0.5 <= R * s)


class _Shield:
    """A shield: a hexagon of light draws itself round the fighter, flashes white, a shimmer sweeps across its face,
    the corners glint, then it thins away."""

    def __init__(self, R: random.Random) -> None:
        self.C = PAL["ice"]
        self.lights = Lights()
        self.lights.add(0, 0, 32, self.C[5], 0.45, 0.5)
        self.t = 0.0

    def update(self, dt: float) -> None:
        self.t += dt
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C, R = self.C, 24.0
        corners = [(R * math.cos(math.pi / 3 * i), R * math.sin(math.pi / 3 * i)) for i in range(7)]
        draw = min(1.0, t / 0.12)
        fade = 1.0 if t < 0.4 else max(0.0, 1 - (t - 0.4) / 0.2)
        if fade <= 0:
            return
        white = 0.12 <= t < 0.17
        # the face: a faint dithered fill and a shimmer band sweeping across it
        if t >= 0.12:
            sweep = -R + (t - 0.12) / 0.3 * 2.4 * R

            def face(xs, ys):
                m = _hex_inside(xs, ys, R - 1.5)
                band = np.abs(xs + ys * 0.5 - sweep) < 3
                col = np.where(band[..., None], np.asarray(C[6], np.float32), np.asarray(C[3], np.float32))
                col = np.where(band[..., None], np.asarray(C[6], np.float32), np.asarray(C[2], np.float32))
                return m & (band | ((xs.astype(int) + ys.astype(int)) % 4 == 0)), np.broadcast_to(col, xs.shape + (4,)), \
                    np.where(band, 0.85, 0.5) * fade
            f.shade(-R, -R, R, R, face)
            f.glow_line(sweep - 10, -12, sweep + 4, 14, 5, C[6], 0.25 * fade)
        # the rim draws itself edge by edge, white on the flash frame
        total = draw * 6
        for i in range(6):
            share = min(1.0, max(0.0, total - i))
            if share <= 0:
                break
            (xa, ya), (xb, yb) = corners[i], corners[i + 1]
            xe, ye = xa + (xb - xa) * share, ya + (yb - ya) * share
            f.line(xa, ya, xe, ye, WHITE if white else C[6], fade)
            f.line(xa * 0.93, ya * 0.93, xe * 0.93, ye * 0.93, C[4], fade)
            f.glow_line(xa, ya, xe, ye, 4, C[5], 0.22 * fade)
        if 0.17 <= t < 0.45:
            for i, (x, y) in enumerate(corners[:6]):
                if (int(t * 20) + i) % 3 == 0:
                    sparkle(f, x, y, 2, C[6], C[5], 0.4 * fade)
        self.lights.draw(f)


class _Buff:
    """Strength: an ember-red ring flares at the feet, hot streaks shoot up the body, two bright chevrons rise, the
    air shimmers with embers and a warm glow."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.acc = R, 0.0, 0.0
        self.C = PAL["ember"]
        self.ps = Particles(R, ground=99, sparks=[PAL["fire"][7], self.C[6], self.C[5], self.C[3]])

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if self.t < 0.45:
            self.acc += dt * 45
            while self.acc > 1:
                self.acc -= 1
                x = R.uniform(-15, 15)
                if R.random() < 0.6:
                    self.ps.spawn(STREAK, x, R.uniform(12, 20), 0, R.uniform(-40, -20), R.uniform(0.3, 0.5), self.C[5])
                else:
                    self.ps.spawn(EMBER, x, R.uniform(4, 18), R.uniform(-10, 10), R.uniform(-60, -30), R.uniform(0.4, 0.7))
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        fade = max(0.0, 1 - max(0.0, t - 0.4) / 0.3)
        r = 8 + 12 * min(1.0, t / 0.12)
        f.ring(0, 19, r, 1.5, C[6], a=fade, sy=0.32)
        f.glow_ring(0, 19, r, 4, C[5], 0.3 * fade, sy=0.32)
        for k, (x, born) in enumerate(((-7, 0.05), (7, 0.15))):  # chevrons rising
            age = t - born
            if 0 <= age < 0.45:
                y, a = 10 - age * 60, (1 if age < 0.3 else 1 - (age - 0.3) / 0.15)
                for o, col in ((0, PAL["fire"][7]), (1, C[5]), (2, C[3])):
                    f.polyline([(x - 4, y + 3 + o), (x, y - 1 + o), (x + 4, y + 3 + o)], col, a)
                f.glow(x, y, 7, C[5], 0.3 * a)
        f.glow(0, 6, 24, C[4], 0.25 * fade)
        self.ps.draw(f)


class _Curse:
    """A curse: a violet sigil opens and turns round the target, dark motes spiral into it, shadow smoke curls off,
    and it snaps shut with a dark flash."""

    def __init__(self, R: random.Random) -> None:
        self.R, self.t, self.acc = R, 0.0, 0.0
        self.C = PAL["arcane"]
        self.ps = Particles(R, ground=99, sparks=[self.C[6], self.C[5], self.C[4], self.C[2]])
        self.motes = [(R.uniform(0, math.tau), R.uniform(16, 26), R.uniform(0.0, 0.3)) for _ in range(16)]

    def update(self, dt: float) -> None:
        self.t, R = self.t + dt, self.R
        if 0.1 < self.t < 0.5:
            self.acc += dt * 14
            while self.acc > 1:
                self.acc -= 1
                self.ps.spawn(SMOKE, R.uniform(-12, 12), R.uniform(-4, 12), R.uniform(-8, 8), R.uniform(-20, -6),
                              R.uniform(0.5, 0.8), PAL["shadow"][4], R.uniform(3, 5))
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C, S = self.C, PAL["shadow"]
        self.ps.draw(f, "back")
        open_ = min(1.0, t / 0.15)
        shut = 0.55
        fade = 1.0 if t < shut else max(0.0, 1 - (t - shut) / 0.15)
        if fade > 0:
            r = 22 * (1 - (1 - open_) ** 2)
            spin = t * 4
            f.ring(0, 2, r, 1.2, C[5], a=fade)
            f.ring(0, 2, r * 0.7, 1, C[4], a=fade)
            for i in range(6):  # runes on the ring
                a = spin + i * math.tau / 6
                x, y = math.cos(a) * r * 0.85, 2 + math.sin(a) * r * 0.85
                f.line(x - 1.5, y, x + 1.5, y, C[6], fade)
                f.line(x, y - 1.5, x, y + 1.5, C[6], fade)
            f.glow_ring(0, 2, r, 4, C[4], 0.3 * fade)
        for a0, r0, born in self.motes:  # motes spiralling in
            age = t - born
            if 0 <= age < 0.45:
                k = age / 0.45
                a, r = a0 + k * 4, r0 * (1 - k)
                x, y = math.cos(a) * r, 2 + math.sin(a) * r
                f.put(x, y, S[6] if k < 0.7 else C[6])
                f.put(x - math.cos(a + 1.2), y - math.sin(a + 1.2), S[4])
                f.glow(x, y, 3, C[4], 0.25)
        if shut <= t < shut + 0.1:
            k = (t - shut) / 0.1
            f.circle(0, 2, 6 * (1 - k) + 1, S[2])
            f.ring(0, 2, 4 + k * 20, 1.5, C[5], a=1 - k)
            f.glow(0, 2, 22, C[5], 0.4 * (1 - k))
        self.ps.draw(f, "front")


def _ray(f: Frame, x: float, y: float, a: float, L: float, w: float, C, start: float = 0.0) -> None:
    """One ray of the hit cross: fat at the root, a hair at the tip, white cooling outward."""
    c, s = math.cos(a), math.sin(a)
    d = start * L
    while d <= L:
        u = d / L
        hw = w * (1 - u) ** 1.6
        col = WHITE if u < 0.3 else C[5] if u < 0.62 else C[4] if u < 0.88 else C[3]
        f.put(x + c * d, y + s * d, col)
        o = 0.5
        while o <= hw:
            for e in (-o, o):
                f.put(x + c * d - s * e, y + s * d + c * e, C[5] if u < 0.3 and o < 1 else C[4])
            o += 0.5
        d += 0.5


class _Hit:
    """The everyday hit: a lopsided cross flare round a white diamond, a cone of sparks and hot chips that fall and
    bounce, a pop of light (after pixelfx's hit-spark)."""

    def __init__(self, R: random.Random) -> None:
        self.C = [(74, 23, 18, 255), (201, 40, 31, 255), (242, 86, 29, 255), (255, 138, 42, 255), (255, 226, 107, 255),
                  (255, 243, 166, 255), WHITE]
        C, self.t, A = self.C, 0.0, -0.3
        self.ps = Particles(R, ground=14, sparks=[C[6], C[5], C[4], C[2]])
        self.lights = Lights()
        tilt = R.uniform(-0.08, 0.08)
        self.rays = [(A + tilt, R.uniform(13, 15), 1.6), (A + math.pi + tilt, R.uniform(4, 5), 1.6),
                     (A - math.pi / 2 + tilt, R.uniform(8, 10), 1.8), (A + math.pi / 2 + tilt, R.uniform(6, 7), 1.6),
                     (A - math.pi / 4 + tilt, R.uniform(3, 4), 0.8)]
        self.lights.add(0, 0, 20, C[4], 0.4, 0.18)
        for i in range(9):
            a, v = A + R.uniform(-0.6, 0.6) - 0.15, R.uniform(110, 220)
            self.ps.spawn(SPARK, 1, 0, math.cos(a) * v, math.sin(a) * v - 40, R.uniform(0.2, 0.35), WHITE, 1,
                          R.uniform(0.01, 0.03) if i > 6 else 0)
        for _ in range(5):
            a, v = A + R.uniform(-1.1, 0.5) - 0.3, R.uniform(50, 120)
            self.ps.spawn(GRIT, 1, 0, math.cos(a) * v, math.sin(a) * v - R.uniform(30, 70), R.uniform(0.3, 0.4),
                          R.choice((C[5], C[4], C[4], C[3])))

    def update(self, dt: float) -> None:
        self.t += dt
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        self.ps.draw(f)
        if t < 0.05:
            for a, L, w in self.rays:
                _ray(f, 0, 0, a, L, w, C)
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    m = abs(dx) + abs(dy)
                    if m <= 3:
                        f.put(dx, dy, WHITE)
                    elif m == 4:
                        f.put(dx, dy, C[3])
        elif t < 0.1:
            for a, L, w in self.rays:
                _ray(f, 0, 0, a, L * 1.2, w * 0.55, C, 0.12)
        elif t < 0.15:
            a, L, _w = self.rays[0]
            _ray(f, 0, 0, a, L * 1.3, 0.6, [C[0], C[1], C[2], C[3], C[3], C[4]], 0.4)
        pop = math.exp(-t / 0.05)
        if pop > 0.02:
            f.glow(0, 0, 14, C[4], 0.35 * pop)
            f.glow(0, 0, 5, WHITE, 0.2 * pop)
        self.lights.draw(f)


# name -> (frame size, frames at FPS, effect class)
EFFECTS = {"slash": (64, 9, _Slash), "fire": (64, 16, _Fire), "ice": (64, 14, _Ice), "bolt": (64, 9, _Bolt),
           "poison": (64, 16, _Poison), "heal": (64, 16, _Heal), "shield": (64, 12, _Shield), "buff": (64, 15, _Buff),
           "curse": (64, 15, _Curse), "hit": (40, 7, _Hit)}


# --- world effects (any pixel-art game) ------------------------------------------------------------

class _Pop:
    """An enemy defeated: a white flash and ring, a spray of sparks and grit, then soft smoke that swells and clears.
    Neutral colours, so the FX autoload can add a burst in the enemy's own colour."""

    def __init__(self, R: random.Random) -> None:
        self.t = 0.0
        self.ps = Particles(R, ground=14, sparks=[WHITE, (255, 243, 166, 255), (255, 200, 120, 255), (200, 120, 90, 255)])
        self.lights = Lights()
        self.lights.add(0, 0, 26, (255, 240, 200, 255), 0.55, 0.2)
        for _ in range(10):
            a, v = R.uniform(0, math.tau), R.uniform(90, 200)
            self.ps.spawn(SPARK, 0, 0, math.cos(a) * v, math.sin(a) * v - 50, R.uniform(0.2, 0.4))
        for _ in range(6):
            a, v = R.uniform(-math.pi, 0), R.uniform(40, 110)
            self.ps.spawn(GRIT, 0, 0, math.cos(a) * v, math.sin(a) * v, R.uniform(0.35, 0.5), (230, 222, 210, 255), 2)
        for k in range(7):
            a = k * math.tau / 7 + R.uniform(-0.3, 0.3)
            self.ps.spawn(SMOKE, math.cos(a) * 4, math.sin(a) * 3, math.cos(a) * 30, math.sin(a) * 20 - 8,
                          R.uniform(0.45, 0.7), (220, 214, 230, 255), R.uniform(4, 6), 0.03)

    def update(self, dt: float) -> None:
        self.t += dt
        self.ps.update(dt)
        self.lights.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        self.ps.draw(f, "back")
        if t < 0.05:
            f.circle(0, 0, 7 - t * 60, WHITE)
        if t < 0.16:
            k = t / 0.16
            f.ring(0, 0, 5 + k * 16, 1.5, (255, 243, 166, 255), a=1 - k)
        self.ps.draw(f, "front")
        self.lights.draw(f)


class _Dust:
    """Landing dust: two soft puffs skid out along the ground and thin away, a few specks kick up."""

    def __init__(self, R: random.Random) -> None:
        self.ps = Particles(R, ground=10)
        col = (236, 226, 204, 255)
        for side in (-1, 1):
            for k in range(4):
                self.ps.spawn(DUST, side * (2 + k * 2), 8 - k * 0.6, side * R.uniform(40, 90), R.uniform(-14, -4),
                              R.uniform(0.3, 0.45), col, R.uniform(2.5, 4.2))
            for _ in range(2):
                self.ps.spawn(GRIT, side * 2, 8, side * R.uniform(30, 70), R.uniform(-90, -50), R.uniform(0.3, 0.4),
                              (200, 188, 160, 255))

    def update(self, dt: float) -> None:
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        self.ps.draw(f, "back")
        self.ps.draw(f, "front")


class _Collect:
    """A pickup: a four-point star flashes, a ring opens, little stars scatter and twinkle out."""

    def __init__(self, R: random.Random) -> None:
        self.C = PAL["gold"]
        self.ps = Particles(R)
        for k in range(6):
            a = k * math.tau / 6 + R.uniform(-0.2, 0.2)
            self.ps.spawn(STAR, 0, 0, math.cos(a) * 70, math.sin(a) * 70, R.uniform(0.25, 0.4), self.C[6], R.uniform(1, 2))

    def update(self, dt: float) -> None:
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        if t < 0.12:
            sparkle(f, 0, 0, 6 * (1 - t / 0.12) + 1, C[6], C[5], 0.6)
        if t < 0.2:
            k = t / 0.2
            f.ring(0, 0, 3 + k * 11, 1, C[6], a=1 - k)
            f.glow(0, 0, 12, C[5], 0.4 * (1 - k))
        self.ps.draw(f)


class _Harvest:
    """A harvest: leaves and soil crumbs pop up and fall, a golden glint and twinkles over the crop."""

    def __init__(self, R: random.Random) -> None:
        self.C = PAL["gold"]
        self.ps = Particles(R, ground=12, sparks=[WHITE, self.C[6], self.C[5], self.C[3]])
        for _ in range(8):
            a, v = R.uniform(-math.pi * 0.9, -math.pi * 0.1), R.uniform(60, 130)
            self.ps.spawn(GRIT, 0, 6, math.cos(a) * v, math.sin(a) * v - 40, R.uniform(0.35, 0.5),
                          R.choice(((92, 184, 74, 255), (138, 216, 96, 255), (154, 98, 56, 255))), 2)
        for _ in range(4):
            self.ps.spawn(STAR, R.uniform(-8, 8), R.uniform(-10, 2), 0, -20, R.uniform(0.3, 0.45), self.C[6], R.uniform(1.4, 2.4),
                          R.uniform(0.0, 0.12))

    def update(self, dt: float) -> None:
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        if t < 0.15:
            sparkle(f, 0, -2, 5 * (1 - t / 0.15) + 1, C[6], C[5], 0.55)
            f.glow(0, 0, 16, C[5], 0.3 * (1 - t / 0.15))
        self.ps.draw(f)


class _Splash:
    """Water: droplets leap and fall back, a ripple spreads on a flat ring, a glint of light."""

    def __init__(self, R: random.Random) -> None:
        self.C = PAL["ice"]
        self.ps = Particles(R, ground=8, sparks=[WHITE, self.C[6], self.C[5], self.C[4]])
        for _ in range(10):
            a, v = R.uniform(-math.pi * 0.85, -math.pi * 0.15), R.uniform(80, 170)
            self.ps.spawn(SPARK, 0, 6, math.cos(a) * v, math.sin(a) * v, R.uniform(0.25, 0.4))

    def update(self, dt: float) -> None:
        self.ps.update(dt)

    def draw(self, f: Frame, t: float) -> None:
        C = self.C
        k = min(1.0, t / 0.4)
        f.ring(0, 7, 3 + k * 12, 1, C[6], a=1 - k, sy=0.4)
        if t > 0.1:
            f.ring(0, 7, 2 + (k - 0.25) * 8, 1, C[5], a=1 - k, sy=0.4)
        self.ps.draw(f)


class _Petals:
    """A loop under a blossom tree: pink petals drift down, sway and spin, and land; seamless."""
    PERIOD = 2.4

    def __init__(self, R: random.Random) -> None:
        self.p = [(R.uniform(-18, 18), R.uniform(0, self.PERIOD), R.uniform(1.6, 2.4), R.uniform(0, math.tau))
                  for _ in range(10)]

    def update(self, dt: float) -> None:
        pass

    def draw(self, f: Frame, t: float) -> None:
        pink, light, deep = (255, 176, 204, 255), (255, 224, 236, 255), (232, 120, 160, 255)
        for x0, born, life, ph in self.p:
            age = (t - born) % self.PERIOD
            if age > life:
                continue
            k = age / life
            x = x0 + math.sin(age * 3 + ph) * 4
            y = -20 + k * 40
            spin = math.sin(age * 6 + ph)
            a = 1.0 if k < 0.85 else 1 - (k - 0.85) / 0.15  # it settles and fades on the ground
            f.put(x, y, light if spin > 0 else pink, a)  # a petal turning: wide, then edge-on
            f.put(x + (1 if spin > 0 else -1), y, pink if spin > 0 else deep, a)
            if abs(spin) < 0.5:
                f.put(x, y + 1, deep, a)


class _Fireflies:
    """A night loop: fireflies wander in slow loops and blink, each a warm pixel with a soft glow; seamless."""
    PERIOD = 3.0

    def __init__(self, R: random.Random) -> None:
        self.flies = [(R.uniform(-22, 22), R.uniform(-22, 18), R.randint(1, 2), R.randint(1, 2), R.uniform(0, math.tau),
                       R.uniform(5, 10)) for _ in range(6)]

    def update(self, dt: float) -> None:
        pass

    def draw(self, f: Frame, t: float) -> None:
        u = t / self.PERIOD * math.tau  # whole turns in a period, so the loop closes
        for x0, y0, a, b, ph, r in self.flies:
            x, y = x0 + math.sin(u * a + ph) * r, y0 + math.sin(u * b + ph * 1.7) * r * 0.6
            blink = 0.5 + 0.5 * math.sin(u * 2 + ph * 3)
            if blink < 0.15:
                continue
            f.put(x, y, (255, 246, 160, 255) if blink > 0.6 else (214, 232, 110, 255))
            f.glow(x, y, 6, (230, 240, 120, 255), 0.45 * blink)


# name -> (frame size, frames at FPS, effect class); loops have whole periods of frames
WORLD = {"pop": (48, 12, _Pop), "dust": (32, 8, _Dust), "collect": (32, 7, _Collect), "harvest": (40, 10, _Harvest),
         "splash": (32, 8, _Splash), "petals": (48, int(_Petals.PERIOD * FPS), _Petals),
         "fireflies": (64, int(_Fireflies.PERIOD * FPS), _Fireflies)}
LOOPS = {"petals", "fireflies"}


def strip(name: str) -> np.ndarray:
    size, n, make = EFFECTS[name] if name in EFFECTS else WORLD[name]
    return render(make, size, n, FPS, (size / 2, size / 2), seed=sum(map(ord, name)))
