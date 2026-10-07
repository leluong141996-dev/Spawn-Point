from PIL import Image

from spawnpoint.gif import make_gif


def test_make_gif_shared_palette_and_size(tmp_path):
    frames = []
    for i in range(6):
        im = Image.new("RGB", (960, 540), (29, 43, 83))
        im.paste((255, 0, 77), (100 + i * 40, 200, 160 + i * 40, 260))
        path = tmp_path / f"frame_{i:04d}.png"
        im.save(path)
        frames.append(path)
    out = make_gif(frames, tmp_path / "demo.gif", fps=20, width=480)
    gif = Image.open(out)
    assert gif.size == (480, 270)
    assert gif.n_frames == 6
    assert gif.info["duration"] == 50
    assert gif.info["loop"] == 0
