import wave

from spawnpoint import sfx


def test_presets_are_deterministic():
    a = sfx.synthesize(sfx.preset("coin", 3), seed=3)
    b = sfx.synthesize(sfx.preset("coin", 3), seed=3)
    assert a == b
    assert sfx.preset("coin", 3) != sfx.preset("coin", 4)


def test_all_presets_render_audible_short_sounds(tmp_path):
    files = sfx.write_all(tmp_path, seed=1)
    assert {f.stem for f in files} == set(sfx.PRESETS)
    for f in files:
        with wave.open(str(f)) as w:
            assert w.getframerate() == sfx.SAMPLE_RATE and w.getsampwidth() == 2
            seconds = w.getnframes() / w.getframerate()
            assert 0.02 < seconds <= 2.0, f.name
            frames = w.readframes(w.getnframes())
        peak = max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True)) for i in range(0, len(frames), 2))
        assert peak > 8000, f"{f.name} is too quiet"


def test_write_all_skips_unchanged(tmp_path):
    sfx.write_all(tmp_path, seed=1, names=["jump"])
    mtime = (tmp_path / "jump.wav").stat().st_mtime_ns
    sfx.write_all(tmp_path, seed=1, names=["jump"])
    assert (tmp_path / "jump.wav").stat().st_mtime_ns == mtime
