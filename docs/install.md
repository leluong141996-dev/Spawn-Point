# Install details

[← back to the README](../README.md)

## Install details

Requirements: Python ≥ 3.10; Godot 4.6 (`spawnpoint setup` downloads it into Spawn Point's own folder if none is on
your `PATH`; or set `GODOT_BIN`) with its web export templates (`setup` fetches only the two web files, about 80 MB);
and to run the model one of: a 12 GB NVIDIA GPU with Docker (vLLM, fastest), [Ollama](https://ollama.com/download) on
any machine (Mac, AMD, or CPU), or any OpenAI-compatible API (`SPAWNPOINT_LLM_*`). `spawnpoint setup --check` reports
what is missing without installing anything.

No GPU? [Play the demos in your browser](https://leluong141996-dev.github.io/Spawn-Point/), or build the hand-written examples locally, no LLM needed:

```bash
spawnpoint examples copy pixel_hopper && spawnpoint build pixel_hopper.json --run
```
