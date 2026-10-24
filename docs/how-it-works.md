# How Spawn Point works

[← back to the README](../README.md)

## How it works

Spawn Point is an open-source, autonomous game studio that runs on your own machine. Instead of asking an LLM to type
hundreds of lines of GDScript (slow, expensive, and easy to break with Godot 3/4 mix-ups), the LLM
assembles **pre-tested components** like LEGO, places them on an **ASCII map**, and wires gameplay
with **declarative rules**. A deterministic compiler validates everything and lets Godot itself write
the scenes.

```
graph.json ──► validate (Python) ──► build scenes (Godot headless) ──► smoke-run ──► playable project
               ~1 ms, LLM-friendly       ~2 s                            ~0.3 s
               error messages
```

| | Typical LLM-writes-code agents | Spawn Point |
|---|---|---|
| How code is produced | GDScript generated from scratch | Components + JSON graph |
| Time to a playable build | minutes to hours | ~3 seconds |
| Game feel | none by default | coyote time, jump buffer, squash & stretch, hit-stop, screen shake, particles, SFX — on by default |
| Hitboxes | drift from visuals | derived from the same shape as the visual |
| Failure mode | crashes, syntax errors | structured diagnostics *before* Godot runs |

## Under the hood: from a sentence to a game

`spawnpoint create` runs four steps:

1. **Design** — the LLM fills a small, enumerated **GameBrief** (genre, palette, abilities, enemy
   archetypes, pickups, goal, feel…) using guided JSON decoding, so even a 7B model cannot produce
   malformed output. A normalizer repairs typical small-model mistakes (plural names, archetypes that
   don't exist in the genre, impossible goals).
2. **Assemble** — deterministic: archetypes become tuned component bundles, goals become rules,
   levels are generated (platformer chunks tagged with the jump they need; top-down arenas whose
   floor is always connected) and re-seeded until the compiler finds everything reachable.
3. **Layers** — L0 core movement → L1 enemies, pickups, goal → L2 feel & juice; each one is compiled,
   exported to the web and live-reloaded.
4. **Creative pass** (`--creative`) — the LLM proposes a small graph patch (parameters, rules); the
   compiler's diagnostics drive up to two repair rounds; if it still fails, it is dropped.

**The model.** [SpawnPoint-Coder-7B](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ) is a 7B model
fine-tuned to generate Godot 4 games through this pipeline: it writes the game design, tweaks and entity
edits as strict JSON, and the compiler turns that into Godot scenes and GDScript. It runs on a single 12 GB
GPU (AWQ 4-bit). **v6 designs card games** (Slay the Spire style deckbuilders): 94% of a sealed set of 16 card-game prompts fully right (v5.2: 56%), 90% of 30 human-written game ideas in English and Vietnamese; the downloadable AWQ build gets 94% and 87% on those, the GGUF Q4_K_M build 88% and 83% (the model card lists every number). Earlier: v5 added **side-scrolling shooters** (flight patterns, power-ups, a boss), **Vietnamese prompts read directly** and a small per-genre format instead of one big form; v5.1 fixes prompts that name the hero only indirectly ("a tank shooting monsters"); v5.2 catches farm pests mentioned only in passing ("có cáo", "with a fox around") and leaves peaceful farms without any. The downloadable AWQ build gets 94% of a sealed set of 16 human-written prompts for shooters and the v4 fixes fully right, 100% of a sealed set of 16 farm prompts with pests named in passing, and 83% of 30 human-written game ideas in English and Vietnamese (v4: 87% on those 30; the model card lists every number and where v5.2 is behind). The GGUF Q4_K_M build scores 87% on those 30. Older models still work with `SPAWNPOINT_BRIEF_FORMAT=v4`. It is tuned for the 2D game kinds Spawn Point builds; other genres are no better than a general 7B coder. `spawnpoint llm up` downloads and serves it: the AWQ build on vLLM when
Docker and an NVIDIA GPU are present, otherwise the [GGUF build](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-GGUF)
(Q4_K_M, ~4.7 GB) in Ollama. Force one with `--backend vllm|ollama`.

LLM settings: `SPAWNPOINT_LLM_BASE_URL` (default: vLLM at `http://localhost:8000/v1`, or Ollama at
`http://localhost:11434/v1` when only Ollama answers), `SPAWNPOINT_LLM_MODEL` (default: SpawnPoint-Coder if the
server has it, else its first model), `SPAWNPOINT_LLM_API_KEY`.
Web builds need the Godot **web export templates**: `spawnpoint setup` fetches them (or Editor → Manage Export
Templates); use `--no-web` to skip and play natively with `spawnpoint run`.

## Diagnostics built for self-correction

```bash
$ spawnpoint validate broken.json
  ✗ error[E_UNKNOWN_PARAM] entities.Player.components.Health.max_hp: Health has no parameter 'max_hp' (hint: Did you mean 'max_health'?)
  ✗ error[E_RULE_DO] rules[0].do[1]: Door has no method 'opne' (hint: Did you mean 'open'?)
  ! warning[W_UNREACHABLE] level.map: Coin at (44,2) looks unreachable (jump ≈ 3 tiles up, 4 across)
```

`--json` prints the same as `{severity, code, path, message, hint}` objects. Builds also run a
headless smoke test (spawn, scripted input, crash detection) and report `E_RUNTIME` errors.
