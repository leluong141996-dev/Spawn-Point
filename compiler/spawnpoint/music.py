"""Background music: a short chiptune loop per farming season, composed from a seed (no audio files are read).

Eight bars over a four-chord progression: a square-wave melody that walks the chord tones, a triangle bass on the
roots, and a quiet arpeggio (bells in winter). The loop is written as res://sfx/music.wav and played on repeat.
"""

from __future__ import annotations

import io
import random
import wave
from pathlib import Path

import numpy as np

RATE = 22050  # music is fine at half rate, and half the size on the web

# season -> (tempo, root note (MIDI), scale steps, progression of chord roots as scale degrees, lead wave)
STYLES = {
    "spring": (112, 60, (0, 2, 4, 5, 7, 9, 11), (0, 4, 5, 3), "square"),     # C major, I-V-vi-IV
    "autumn": (96, 57, (0, 2, 3, 5, 7, 8, 10), (0, 5, 2, 6), "square"),      # A minor, i-VI-III-VII
    "winter": (84, 62, (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 0), "sine"),        # D major, slow bells, I-iii-IV-I
    "desert": (100, 64, (0, 1, 4, 5, 7, 8, 10), (0, 1, 0, 4), "square"),     # E phrygian dominant, i-bII-i-V
}
SEASONS = tuple(STYLES)


def _freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _osc(kind: str, phase: np.ndarray) -> np.ndarray:
    p = phase % 1.0
    if kind == "square":
        return np.where(p < 0.25, 1.0, -1.0)  # a 25% pulse: the classic chiptune lead
    if kind == "triangle":
        return 4 * np.abs(p - 0.5) - 1
    return np.sin(2 * np.pi * p)


def _note(buf: np.ndarray, start: float, length: float, midi: float, kind: str, volume: float,
          decay: float = 0.0) -> None:
    """Adds one note to `buf` (seconds), with a short attack and release (and an optional exponential decay)."""
    s0, n = int(start * RATE), int(length * RATE)
    n = min(n, len(buf) - s0)
    if n <= 0:
        return
    i = np.arange(n)
    attack, release = max(int(0.006 * RATE), 1), max(int(0.04 * RATE), 1)
    env = np.minimum(np.minimum(1.0, i / attack), (n - i) / release)
    if decay:
        env = env * np.exp(-decay * i / RATE)
    buf[s0:s0 + n] += volume * env * _osc(kind, _freq(midi) * i / RATE)


def compose(season: str = "spring", seed: int = 0) -> list[float]:
    """Eight bars of music as samples in -1..1."""
    tempo, root, scale, progression, lead = STYLES.get(season, STYLES["spring"])
    rng = random.Random(f"music:{season}:{seed}")
    beat = 60.0 / tempo
    bars = 8
    buf = np.zeros(int(bars * 4 * beat * RATE) + RATE // 4)

    def degree(d: int, octave: int = 0) -> int:
        return root + scale[d % len(scale)] + 12 * (d // len(scale) + octave)

    melody_degree = 2
    for bar in range(bars):
        chord = progression[bar % len(progression)]
        tones = [chord, chord + 2, chord + 4]
        t0 = bar * 4 * beat
        for b in range(4):  # bass on the beat (root, and the fifth on beat three)
            d = chord if b != 2 else chord + 4
            _note(buf, t0 + b * beat, beat * 0.9, degree(d, -2), "triangle", 0.30)
        for step in range(8):  # an arpeggio on the eighths (bells in winter)
            d = tones[step % 3]
            if season == "winter":
                if step % 2 == 0:
                    _note(buf, t0 + step * beat / 2, beat * 1.5, degree(d, 1), "sine", 0.10, decay=3.0)
            else:
                _note(buf, t0 + step * beat / 2, beat * 0.35, degree(d), "square", 0.05)
        step = 0
        while step < 8:  # the melody: a walk that leans toward the chord's notes
            length = rng.choice((1, 1, 2, 2, 3)) if season != "winter" else rng.choice((2, 2, 3, 4))
            length = min(length, 8 - step)
            if rng.random() < 0.22 and step > 0:
                step += length
                continue
            target = rng.choice(tones) + 7
            melody_degree += max(-2, min(2, target - melody_degree)) if rng.random() < 0.7 else rng.choice((-1, 1))
            melody_degree = max(5, min(14, melody_degree))
            _note(buf, t0 + step * beat / 2, length * beat / 2 * 0.92, degree(melody_degree), lead,
                  0.16 if lead == "square" else 0.22, decay=1.5 if season == "winter" else 0.0)
            step += length
    peak = max(1e-6, float(np.abs(buf).max()))
    return list(buf / peak * 0.6)


def to_wav_bytes(samples: list[float]) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(np.asarray(samples), -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return out.getvalue()


def write(out_dir: Path, season: str, seed: int = 0) -> Path:
    """Writes music.wav for `season` (skipped when it is already there for the same season and seed)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target, stamp = out_dir / "music.wav", out_dir / ".music.params"
    key = f"{season}:{seed}"
    if not (target.exists() and stamp.exists() and stamp.read_text() == key):
        target.write_bytes(to_wav_bytes(compose(season, seed)))
        stamp.write_text(key)
    return target
