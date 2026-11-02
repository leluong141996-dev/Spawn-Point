# Use SpawnPoint-Coder-7B on its own

[SpawnPoint-Coder-7B](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-GGUF) turns a game idea into the game's
design as JSON. Spawn Point compiles that design into a Godot 4 game, but you can call the model from your own code.
This folder holds what Spawn Point sends:

| file | what it is |
|---|---|
| `prompts.json` | the system prompts: `design_system` for a new game, `tweak_system` for a change; add `farm_line` or `card_line` when the idea matches `farm_words` or `card_words` |
| `design.schema.json` | the JSON schema of a design (one shape per genre, picked by `genre`) |
| `tweak.schema.json` | the schema of a change: `{"brief": the updated design, "new_level": bool}` |
| `design.py` | a 70-line example, standard library only |

## Try it

```bash
ollama pull hf.co/smoky1496/SpawnPoint-Coder-7B-GGUF:Q4_K_M
python design.py "a ninja platformer where you collect stars" > design.json
python design.py "make it night and add bats" --change design.json
```

On vLLM: `BASE_URL=http://localhost:8000/v1 MODEL=SpawnPoint-Coder-7B python design.py "..."`.

Send the schema as `response_format: {"type": "json_schema", ...}` (Ollama, vLLM and llama.cpp's server support it). The
model was trained with it, and without it a 7B model can drift out of the format. Temperature 0.4 for a new design, 0.1
for a change.

## Turn the design into a game

```bash
pip install spawnpoint-studio
spawnpoint setup
spawnpoint create "my game" --brief design.json
```

## Tell me what you're building

If you use the model for something else, or need a genre or a field it doesn't have, [open a
discussion](https://github.com/leluong141996-dev/Spawn-Point/discussions). That's what decides what I work on next.
