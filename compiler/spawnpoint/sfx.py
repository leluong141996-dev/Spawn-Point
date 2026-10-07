"""Procedural retro sound effects (a port of DrPetter's sfxr synth and its preset generators).

Every game gets jump / land / hurt / shoot / coin / explosion / powerup / dash / blip sounds,
deterministic for a given seed, so the first build already has audio feedback.
"""

from __future__ import annotations

import io
import math
import random
import struct
import wave
from dataclasses import dataclass, replace
from pathlib import Path

SAMPLE_RATE = 44100
SQUARE, SAW, SINE, NOISE = 0, 1, 2, 3


@dataclass
class SfxParams:
    wave_type: int = SQUARE
    base_freq: float = 0.3
    freq_limit: float = 0.0
    freq_ramp: float = 0.0
    freq_dramp: float = 0.0
    duty: float = 0.0
    duty_ramp: float = 0.0
    vib_strength: float = 0.0
    vib_speed: float = 0.0
    env_attack: float = 0.0
    env_sustain: float = 0.3
    env_decay: float = 0.4
    env_punch: float = 0.0
    lpf_resonance: float = 0.0
    lpf_freq: float = 1.0
    lpf_ramp: float = 0.0
    hpf_freq: float = 0.0
    hpf_ramp: float = 0.0
    pha_offset: float = 0.0
    pha_ramp: float = 0.0
    repeat_speed: float = 0.0
    arp_speed: float = 0.0
    arp_mod: float = 0.0
    volume: float = 0.6


# --- preset generators (after sfxr's "generator" buttons) -------------------------------------


def _pickup(r: random.Random) -> SfxParams:
    p = SfxParams(base_freq=0.4 + r.random() * 0.5, env_sustain=r.random() * 0.1,
                  env_decay=0.1 + r.random() * 0.4, env_punch=0.3 + r.random() * 0.3)
    p.arp_speed = 0.5 + r.random() * 0.2
    p.arp_mod = 0.2 + r.random() * 0.4
    return p


def _laser(r: random.Random) -> SfxParams:
    p = SfxParams(wave_type=r.choice([SQUARE, SAW, SINE]))
    p.base_freq = 0.5 + r.random() * 0.5
    p.freq_limit = max(0.2, p.base_freq - 0.2 - r.random() * 0.6)
    p.freq_ramp = -0.15 - r.random() * 0.2
    if r.random() < 0.5:
        p.duty, p.duty_ramp = r.random() * 0.5, r.random() * 0.2
    else:
        p.duty, p.duty_ramp = 0.4 + r.random() * 0.5, -r.random() * 0.7
    p.env_sustain = 0.1 + r.random() * 0.2
    p.env_decay = r.random() * 0.4
    if r.random() < 0.5:
        p.env_punch = r.random() * 0.3
    if r.random() < 0.33:
        p.pha_offset, p.pha_ramp = r.random() * 0.2, -r.random() * 0.2
    p.hpf_freq = r.random() * 0.3 if r.random() < 0.5 else 0.0
    p.volume = 0.45
    return p


def _explosion(r: random.Random) -> SfxParams:
    p = SfxParams(wave_type=NOISE)
    if r.random() < 0.5:
        p.base_freq, p.freq_ramp = 0.1 + r.random() * 0.4, -0.1 + r.random() * 0.4
    else:
        p.base_freq, p.freq_ramp = 0.2 + r.random() * 0.7, -0.2 - r.random() * 0.2
    p.base_freq *= p.base_freq
    if r.random() < 0.2:
        p.freq_ramp = 0.0
    if r.random() < 0.33:
        p.repeat_speed = 0.3 + r.random() * 0.5
    p.env_sustain = 0.1 + r.random() * 0.3
    p.env_decay = 0.2 + r.random() * 0.4
    if r.random() < 0.5:
        p.pha_offset, p.pha_ramp = -0.3 + r.random() * 0.9, -r.random() * 0.3
    p.env_punch = 0.2 + r.random() * 0.6
    if r.random() < 0.5:
        p.vib_strength, p.vib_speed = r.random() * 0.7, r.random() * 0.6
    return p


def _powerup(r: random.Random) -> SfxParams:
    p = SfxParams()
    if r.random() < 0.5:
        p.wave_type = SAW
    else:
        p.duty = r.random() * 0.6
    if r.random() < 0.5:
        p.base_freq, p.freq_ramp, p.repeat_speed = 0.2 + r.random() * 0.3, 0.1 + r.random() * 0.4, 0.4 + r.random() * 0.4
    else:
        p.base_freq, p.freq_ramp = 0.2 + r.random() * 0.3, 0.05 + r.random() * 0.2
        if r.random() < 0.5:
            p.vib_strength, p.vib_speed = r.random() * 0.7, r.random() * 0.6
    p.env_sustain = r.random() * 0.4
    p.env_decay = 0.1 + r.random() * 0.4
    return p


def _hurt(r: random.Random) -> SfxParams:
    p = SfxParams(wave_type=r.choice([SQUARE, SAW, NOISE]))
    if p.wave_type == SQUARE:
        p.duty = r.random() * 0.6
    p.base_freq = 0.2 + r.random() * 0.6
    p.freq_ramp = -0.3 - r.random() * 0.4
    p.env_sustain = r.random() * 0.1
    p.env_decay = 0.1 + r.random() * 0.2
    if r.random() < 0.5:
        p.hpf_freq = r.random() * 0.3
    return p


def _jump(r: random.Random) -> SfxParams:
    p = SfxParams(wave_type=SQUARE, duty=r.random() * 0.6)
    p.base_freq = 0.3 + r.random() * 0.3
    p.freq_ramp = 0.1 + r.random() * 0.2
    p.env_sustain = 0.1 + r.random() * 0.3
    p.env_decay = 0.1 + r.random() * 0.2
    if r.random() < 0.5:
        p.hpf_freq = r.random() * 0.3
    if r.random() < 0.5:
        p.lpf_freq = 1.0 - r.random() * 0.6
    p.volume = 0.45
    return p


def _blip(r: random.Random) -> SfxParams:
    p = SfxParams(wave_type=r.choice([SQUARE, SAW]))
    if p.wave_type == SQUARE:
        p.duty = r.random() * 0.6
    p.base_freq = 0.2 + r.random() * 0.4
    p.env_sustain = 0.1 + r.random() * 0.1
    p.env_decay = r.random() * 0.2
    p.hpf_freq = 0.1
    return p


def _land(r: random.Random) -> SfxParams:
    # A soft, low thud.
    return SfxParams(wave_type=NOISE, base_freq=0.08 + r.random() * 0.04, freq_ramp=-0.1,
                     env_sustain=0.02, env_decay=0.12 + r.random() * 0.05, env_punch=0.4,
                     lpf_freq=0.35, volume=0.5)


def _dash(r: random.Random) -> SfxParams:
    # A breathy whoosh.
    return SfxParams(wave_type=NOISE, base_freq=0.35 + r.random() * 0.1, freq_ramp=-0.25,
                     env_attack=0.05, env_sustain=0.08, env_decay=0.18, lpf_freq=0.5, lpf_ramp=-0.2,
                     hpf_freq=0.15, volume=0.45)


PRESETS = {
    "jump": _jump,
    "land": _land,
    "hurt": _hurt,
    "shoot": _laser,
    "coin": _pickup,
    "explosion": _explosion,
    "powerup": _powerup,
    "dash": _dash,
    "blip": _blip,
}


def preset(name: str, seed: int = 0) -> SfxParams:
    # Stable per-preset seed so changing one preset never changes the others.
    r = random.Random(f"{name}:{seed}")
    return PRESETS[name](r)


# --- synthesis --------------------------------------------------------------------------------


def synthesize(p: SfxParams, seed: int = 0, max_seconds: float = 2.0) -> list[float]:
    rnd = random.Random(seed)
    out: list[float] = []

    def reset(restart: bool) -> None:
        nonlocal fperiod, fmaxperiod, fslide, fdslide, period, square_duty, square_slide
        nonlocal arp_mod, arp_time, arp_limit
        fperiod = 100.0 / (p.base_freq * p.base_freq + 0.001)
        period = int(fperiod)
        fmaxperiod = 100.0 / (p.freq_limit * p.freq_limit + 0.001)
        fslide = 1.0 - p.freq_ramp**3 * 0.01
        fdslide = -(p.freq_dramp**3) * 0.000001
        square_duty = 0.5 - p.duty * 0.5
        square_slide = -p.duty_ramp * 0.00005
        arp_mod = 1.0 - p.arp_mod**2 * 0.9 if p.arp_mod >= 0 else 1.0 + p.arp_mod**2 * 10.0
        arp_time = 0
        arp_limit = int((1.0 - p.arp_speed) ** 2 * 20000 + 32)
        if p.arp_speed == 1.0:
            arp_limit = 0

    fperiod = fmaxperiod = fslide = fdslide = square_duty = square_slide = arp_mod = 0.0
    period = arp_time = arp_limit = 0
    reset(False)

    phase = 0
    fltp = fltdp = fltphp = 0.0
    fltw = p.lpf_freq**3 * 0.1
    fltw_d = 1.0 + p.lpf_ramp * 0.0001
    fltdmp = min(5.0 / (1.0 + p.lpf_resonance**2 * 20.0) * (0.01 + fltw), 0.8)
    flthp = p.hpf_freq**2 * 0.1
    flthp_d = 1.0 + p.hpf_ramp * 0.0003
    vib_phase = 0.0
    vib_speed = p.vib_speed**2 * 0.01
    vib_amp = p.vib_strength * 0.5
    env_vol = 0.0
    env_stage = 0
    env_time = 0
    env_length = [max(1, int(p.env_attack**2 * 100000)), max(1, int(p.env_sustain**2 * 100000)),
                  max(1, int(p.env_decay**2 * 100000))]
    fphase = p.pha_offset**2 * 1020.0 * (1 if p.pha_offset >= 0 else -1)
    fdphase = p.pha_ramp**2 * (1 if p.pha_ramp >= 0 else -1)
    iphase = abs(int(fphase))
    ipp = 0
    phaser = [0.0] * 1024
    noise = [rnd.uniform(-1, 1) for _ in range(32)]
    rep_time = 0
    rep_limit = int((1.0 - p.repeat_speed) ** 2 * 20000 + 32)
    if p.repeat_speed == 0.0:
        rep_limit = 0

    for _ in range(int(SAMPLE_RATE * max_seconds)):
        rep_time += 1
        if rep_limit and rep_time >= rep_limit:
            rep_time = 0
            reset(True)
        arp_time += 1
        if arp_limit and arp_time >= arp_limit:
            arp_limit = 0
            fperiod *= arp_mod
        fslide += fdslide
        fperiod *= fslide
        if fperiod > fmaxperiod:
            fperiod = fmaxperiod
            if p.freq_limit > 0.0:
                break
        rfperiod = fperiod
        if vib_amp > 0.0:
            vib_phase += vib_speed
            rfperiod = fperiod * (1.0 + math.sin(vib_phase) * vib_amp)
        period = max(int(rfperiod), 8)
        square_duty = min(max(square_duty + square_slide, 0.0), 0.5)

        env_time += 1
        if env_time > env_length[env_stage]:
            env_time = 0
            env_stage += 1
            if env_stage == 3:
                break
        if env_stage == 0:
            env_vol = env_time / env_length[0]
        elif env_stage == 1:
            env_vol = 1.0 + (1.0 - env_time / env_length[1]) * 2.0 * p.env_punch
        else:
            env_vol = 1.0 - env_time / env_length[2]

        fphase += fdphase
        iphase = min(abs(int(fphase)), 1023)
        if flthp_d != 1.0:
            flthp = min(max(flthp * flthp_d, 0.00001), 0.1)

        ssample = 0.0
        for _s in range(8):  # 8x supersampling
            phase += 1
            if phase >= period:
                phase %= period
                if p.wave_type == NOISE:
                    noise = [rnd.uniform(-1, 1) for _ in range(32)]
            fp = phase / period
            if p.wave_type == SQUARE:
                sample = 0.5 if fp < square_duty else -0.5
            elif p.wave_type == SAW:
                sample = 1.0 - fp * 2.0
            elif p.wave_type == SINE:
                sample = math.sin(fp * 2.0 * math.pi)
            else:
                sample = noise[phase * 32 // period]
            pp = fltp
            fltw = min(max(fltw * fltw_d, 0.0), 0.1)
            if p.lpf_freq != 1.0:
                fltdp += (sample - fltp) * fltw
                fltdp -= fltdp * fltdmp
            else:
                fltp = sample
                fltdp = 0.0
            fltp += fltdp
            fltphp += fltp - pp
            fltphp -= fltphp * flthp
            sample = fltphp
            phaser[ipp & 1023] = sample
            sample += phaser[(ipp - iphase + 1024) & 1023]
            ipp = (ipp + 1) & 1023
            ssample += sample * env_vol
        out.append(ssample / 8.0)

    # Normalize to the requested loudness and fade the last few ms to avoid clicks.
    peak = max((abs(s) for s in out), default=0.0)
    if peak > 0:
        k = p.volume / peak
        out = [s * k for s in out]
    fade = min(len(out), int(SAMPLE_RATE * 0.005))
    for i in range(fade):
        out[-1 - i] *= i / fade
    return out


def to_wav_bytes(samples: list[float]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))
    return buf.getvalue()


def write_all(out_dir: Path, seed: int = 0, names: list[str] | None = None) -> list[Path]:
    """Writes <name>.wav for each preset. Skips files whose params did not change."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in names or list(PRESETS):
        params = preset(name, seed)
        stamp = out_dir / f".{name}.params"
        target = out_dir / f"{name}.wav"
        key = repr(replace(params))
        if target.exists() and stamp.exists() and stamp.read_text() == key:
            written.append(target)
            continue
        target.write_bytes(to_wav_bytes(synthesize(params, seed)))
        stamp.write_text(key)
        written.append(target)
    return written
