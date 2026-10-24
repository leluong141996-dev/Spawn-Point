# Development

[← back to the README](../README.md)

## Development

```bash
git clone https://github.com/leluong141996-dev/Spawn-Point && cd Spawn-Point
pip install -e ".[dev]"
pytest                      # everything: compiler, studio, end-to-end builds, web + browser, GDScript suite
pytest -m "not llm"         # without the live-LLM tests
spawnpoint manifest         # regenerate manifest.json after changing a component
godot4 --headless --path godot --fixed-fps 60 res://tests/run_tests.tscn   # GDScript suite only
```

`spawnpoint demo -o site` builds the browser demo site: the showcase graphs in `examples/`, one shared Godot
engine, each game checked in headless Chrome. The Pages workflow publishes it on every push.

Adding a component: create `godot/addons/spawn_point/components/<name>_component.gd` following the
contract (typed `@export`s with ranges, `SP_NAME` / `SP_HOSTS` / `SP_REQUIRES` / `SP_CATEGORY`
constants, `##` docs on everything public), add tests in `godot/tests/`, then run `spawnpoint manifest`.

Contributions are welcome: open an issue to discuss a bigger change first, keep `pytest -m "not llm"`
green, and add a test with every fix. CI runs the full suite (with Godot) on every push and pull request.

## Roadmap

1. ✅ Component library with juice
2. ✅ Graph compiler (validation, rules, levels, SFX, smoke test)
3. ✅ Studio orchestrator — prompt → brief → layered builds, web export with live reload, tweaks, creative pass
4. ✅ Asset pipeline — procedural pixel-art sprites and tiles, sheet/folder import with auto-slicing, outline → `CollisionPolygon2D`, automatic animation, AI-art provider plug-in
5. ✅ Playtester — skill-profiled bots with a jump-aware planner, telemetry, death heatmaps, bounded auto-tuning
6. ✅ Web cockpit — `spawnpoint studio`: live arcade, right-click-to-edit with the LLM, parameter desk, sprite gallery, playtest desk
7. ✅ **[SpawnPoint-Coder-7B](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ)** — a fine-tuned 7B model (QLoRA, trainable and servable on a
   single 12 GB consumer GPU such as an RTX 3060) specialised in briefs, tweaks and graph patches, so
   the whole studio runs well offline for free. The compiler acts as the data filter and the judge:
   every training example must compile, and evaluation measures first-try validity, how often the
   normalizer has to repair output, and whether tweaks change only what was asked.
   Hosted providers (Claude, OpenAI, any OpenAI-compatible API) stay supported via `SPAWNPOINT_LLM_*`.
