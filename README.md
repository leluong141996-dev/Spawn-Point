# Spawn Point

**Describe a 2D game in one sentence — get a playable, juicy Godot 4 game in seconds.**

[![CI](https://github.com/leluong141996-dev/Spawn-Point/actions/workflows/ci.yml/badge.svg)](https://github.com/leluong141996-dev/Spawn-Point/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/spawnpoint-studio)](https://pypi.org/project/spawnpoint-studio/)
[![Model](https://img.shields.io/badge/%F0%9F%A4%97%20model-SpawnPoint--Coder--7B-yellow)](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ)
[![Play the demos](https://img.shields.io/badge/%E2%96%B6%20play-demos%20in%20your%20browser-ff004d)](https://leluong141996-dev.github.io/Spawn-Point/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/leluong141996-dev/Spawn-Point?style=social)](https://github.com/leluong141996-dev/Spawn-Point/stargazers)

⭐ **If Spawn Point drew something fun or useful, a star helps other people find it. If it drew something wrong, [open an issue](https://github.com/leluong141996-dev/Spawn-Point/issues/new) with your prompt: the model's tests grow from prompts that broke.**

<p align="center">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/knight-quest.gif" width="48%" alt="Knight's Quest: a sword platformer">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/castle-defense.gif" width="48%" alt="Castle Defense: a tower defense game">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/ninja-rescue.gif" width="48%" alt="Ninja Rescue: a platformer where a ninja frees his mother">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/dino-eggs.gif" width="48%" alt="Dino Eggs: a bubble shooter with dinosaur eggs">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/night-survivor.gif" width="48%" alt="Night Survivor: auto-fire, gems, level-ups">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/pixel-hopper.gif" width="48%" alt="Pixel Hopper: a Mario-style platformer">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/star-run.gif" width="48%" alt="Star Run: a side-scrolling shooter with power-ups and a boss">
</p>
<p align="center"><sub>Seven of the demo games, each one a small JSON graph in <code>examples/</code> built from the
same component library: generated pixel art, collision traced from the sprites, juice on by default.
Recorded with <code>spawnpoint gif</code> (autopilot).</sub></p>

<p align="center"><b><a href="https://leluong141996-dev.github.io/Spawn-Point/">▶ Play the demos in your browser</a></b>: a Mario-style platformer, a
knight with a sword, tower defense, a ninja rescue, a dinosaur-egg bubble shooter, a survivor with level-ups, a cozy
island farm, an arena shooter and a side-scrolling space shooter. No install needed, and
they work on phones too (touch controls).</p>

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

## Install

Requirements: Python ≥ 3.10, [Godot 4.6](https://godotengine.org/download) on your `PATH` (`godot4` or
`godot`, or set `GODOT_BIN`), and for the LLM features one of: a 12 GB NVIDIA GPU with Docker (vLLM, fastest),
[Ollama](https://ollama.com/download) on any machine (Mac, AMD, or CPU), or any OpenAI-compatible API.

```bash
pip install spawnpoint-studio
spawnpoint llm up                      # SpawnPoint-Coder-7B: vLLM on NVIDIA, otherwise Ollama (or set SPAWNPOINT_LLM_*)
spawnpoint create "a ninja platformer where you collect stars"
```

No GPU? [Play the demos in your browser](https://leluong141996-dev.github.io/Spawn-Point/), or build the hand-written examples locally, no LLM needed:

```bash
spawnpoint examples copy pixel_hopper && spawnpoint build pixel_hopper.json --run
```

## Spawn Point Studio (web cockpit)

```bash
spawnpoint studio          # opens http://localhost:8070 — games live in ./out
```

A local "studio floor" around the running game — no terminal needed:

- **Projects**: every game in the workspace; **New game** from a prompt (optionally with the
  playtester and the creative pass). Progress streams live while the layers land.
- **Arcade**: the web build in the middle, reloading by itself after every change.
  **Right-click an enemy or item in the game** to select it, then just say what to change:
  *"double its health and make it shoot fireballs"* — the LLM returns a patch scoped to that entity,
  the compiler checks it (with repair rounds), missing projectiles are created, and the game reloads.
- **Designer**: the brief, rules, tweak history, studio edits and tuning.
  **Artist**: every sprite sheet. **Developer**: every entity → component → parameter as a typed
  input with the manifest's ranges; editing one rebuilds the game (no LLM needed).
  **QA**: run the playtester or run + tune, with the stats table and the death heatmap.

Edits are stored as overrides in `studio.json` and survive later tweaks; they win over the tuner.
Standard library only on the server, one HTML/JS page on the client, Server-Sent Events for progress.

## Make a game from a sentence

```bash
spawnpoint llm up                     # SpawnPoint-Coder-7B: vLLM (~11 GB VRAM) or Ollama — or any OpenAI-compatible API
spawnpoint create "a ninja platformer where you collect stars"
```

```
Design:
  “Ninja Star Dash” — platformer, palette candy, goal collect_all, short, difficulty 2
  player: double_jump, stomp; jump 4.0 tiles; speed fast; feel floaty; juice subtle
  enemies: 4x Goblin (walker), 2x Spider (hopper); pickups: 10x Star; hazards: spikes
  [L0 core loop] ok in 5.5s (build 3.1s, web 2.4s)
  ▶ playing at http://localhost:8060/  (the page reloads as layers land)
  [L1 goals & enemies] ok in 5.1s
  [L2 feel & polish] ok in 5.1s
Done in 25.7s (design 10.0s; LLM 2 call(s), 977 prompt + 256 completion tokens).
```

The browser opens on the first playable layer and reloads as the next ones land. Then iterate:

```bash
spawnpoint tweak out/ninja-star-dash "jump 20% higher and add a dash, night colors"
#   palette: "candy" -> "night"
#   player.abilities: ["double_jump", "stomp"] -> ["double_jump", "stomp", "dash"]
#   player.jump_tiles: 4.0 -> 4.8
```

Only what you asked for changes, and the level layout is kept. Prompts can be in any language
(non-English prompts are translated first). How it works:

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
GPU (AWQ 4-bit). v5 added **side-scrolling shooters** (flight patterns, power-ups, a boss), **Vietnamese prompts read directly** and a small per-genre format instead of one big form; v5.1 fixes prompts that name the hero only indirectly ("a tank shooting monsters"). The downloadable AWQ build gets 88% of a sealed set of 16 human-written prompts for shooters and the v4 fixes fully right, and 80% of 30 human-written game ideas in English and Vietnamese (v4: 87% on those 30; the model card lists every number and where v5.1 is behind). The GGUF Q4_K_M build scores 83% on those 30. Older models still work with `SPAWNPOINT_BRIEF_FORMAT=v4`. It is tuned for the 2D game kinds Spawn Point builds; other genres are no better than a general 7B coder. `spawnpoint llm up` downloads and serves it: the AWQ build on vLLM when
Docker and an NVIDIA GPU are present, otherwise the [GGUF build](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-GGUF)
(Q4_K_M, ~4.7 GB) in Ollama. Force one with `--backend vllm|ollama`.

LLM settings: `SPAWNPOINT_LLM_BASE_URL` (default: vLLM at `http://localhost:8000/v1`, or Ollama at
`http://localhost:11434/v1` when only Ollama answers), `SPAWNPOINT_LLM_MODEL` (default: SpawnPoint-Coder if the
server has it, else its first model), `SPAWNPOINT_LLM_API_KEY`.
Web builds need the Godot **web export templates** (Editor → Manage Export Templates, or unpack
`web_*.zip` from the official `.tpz` into `~/.local/share/godot/export_templates/<version>/`);
use `--no-web` to skip and play natively with `spawnpoint run`.

## A cozy farm from one sentence

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-overview.png" width="92%" alt="A generated island farm: farmhouse, fenced crop field, animal pen with a coop, pond and woods"><br><sub>One generated farm, the whole map: everything here is drawn by plain Python, no image files.</sub></p>

Ask for a farming game (`spawnpoint create "a cozy farming game with strawberries and pumpkins"`) and
Spawn Point lays out a whole farm: a farmhouse with a dirt path to its door, a fenced crop field, an animal pen with a
coop, a pond, a shipping bin, and woods around the edge, on an island (water all round, cliffs to the south; an
ocean-themed farm always is one) or in a meadow in the woods. The art is a 16-pixel tile set drawn from code: grass with tufts, flowers and mushrooms, paths with soft edges,
water with lily pads and reeds, buildings, fences, four kinds of tree, chickens and cows, a farmer who walks in four
directions, and crops with five growth stages (strawberries, carrots, potatoes, pumpkins, corn, wheat, cabbages...,
picked from the crop's name).

What you do there: plant, water and harvest; collect eggs and milk when an animal has something to give; chop trees and
break rocks for wood and stone; carry it all to the shipping bin before sunset, while crows go for your crops. The
hotbar shows your seeds and basket. You walk behind trees and the house (the scene is depth-sorted), and only an
object's footprint blocks you. `spawnpoint overview <project>` saves a picture of the whole map after a short autopilot
run, like the one above.

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/sunny-farm.gif" width="70%" alt="Sunny Farm: the farmer harvests, sells at the shipping bin and works the field"></p>

## Sprites: generated or your own

Layer 2 replaces placeholder shapes with **procedural pixel art** — no assets, no GPU: chibi people with big heads, monsters with faces (a biting plant, a mushroom, a snail, a flame spirit, a reaper, an alien, a dragon, a ghost...), items, props, themed tiles and a parallax sky. Spawn Point makes pixel art games only. (A graph can still ask for the smooth `"art_style": "cartoon"` look by hand, but games made from a prompt are always pixel art.)

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/parade-heroes.gif" width="48%" alt="Animated heroes: knight, wizard, ranger, viking, king, princess, ninja..."> <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/parade-monsters.gif" width="48%" alt="Animated monsters: slime, frog, biting plant, mushroom, snail, flame..."></p>
<p align="center"><sub>Every character and monster is drawn by plain Python from its name (<code>spawnpoint sprites parade --set heroes|monsters|items</code>).</sub></p>

The
kind follows the entity (`Goblin` → humanoid, `FireBat` → flyer, `LaserBot` → robot, `Crystal` → gem…)
and details follow the name (`Ninja` → mask, `Fox` → ears and tail, `Spider` → legs, a sword-wielder holds a sword).
Every sprite has idle / run / jump / fall / hurt animations driven automatically by an `Animator` component, plus
`attack` (played each time its weapon fires) and `die` (a death sequence that plays on after the entity is gone) for
anything that fights or can be hurt; heroes breathe and blink while they stand.

**Pixel-art settings** (`settings` in the graph; the assembler sets the first two from the game's theme):

| Setting | Values | What it does |
|---|---|---|
| `pixel_palette` | `none`, `pico8`, `sweetie16`, `endesga32` | Limits every sprite, tile and backdrop colour to a classic palette, so the whole game shares one set of colours. |
| `scenery` | `auto`, `flat`, or a theme (`night`, `forest`, `desert`, `neon`, `candy`, `ocean`, `lava`, `snow`) | A banded sky with sun or moon and stars, parallax clouds, mountains, hills and themed trees, cacti, skylines or kelp (a themed floor for top-down games). `auto` picks one that fits the background colour, `flat` keeps the plain hills. |
| `pixel_size` | `2` (default), `1` | `2` is chunky (NES-like); `1` draws the same art at twice the resolution (SNES-like) at the same on-screen size. |

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/pixel-size.png" width="92%" alt="The same game with pixel_size 2 (chunky) and pixel_size 1 (fine)"><br><sub>The same game, same moment: <code>pixel_size: 2</code> (left) and <code>pixel_size: 1</code> (right).</sub></p>

Ground tiles are drawn for their neighbours (grass on top, outlined exposed edges, rounded and notched corners,
varied interiors, capped one-way planks), and pixel-art levels get pixel effects: skidding dust, hit sparks and a
screen shake in whole pixels.

**Collision comes from the pixels.** Hitboxes, hurtboxes, pickups, hazards and static bodies use the
sprite's traced outline (`CollisionPolygon2D`); moving bodies keep a smooth capsule/circle fitted to
the sprite's opaque bounds, so characters never snag on tile seams.

```bash
spawnpoint sprites kinds                                          # hero, slime, hopper, flyer, robot, ...
spawnpoint sprites generate hero --name Knight --color "#c2c3c7"  # assets/sprites/Knight.sprite.json
spawnpoint sprites import hero.png --grid 32x32 --anim idle=0-3 --anim run=4-9
spawnpoint sprites import sheet.png --rows idle,run,jump           # auto-sliced by transparent gutters
spawnpoint sprites import kenney_frames/                           # idle_0.png, walk_1.png, ...
spawnpoint sprites preview assets/sprites/Knight.sprite.json       # contact sheet + collision outline
spawnpoint sprites gallery --style fine -o gallery.png             # every kind on one sheet, for review
spawnpoint sprites parade --set monsters -o monsters.gif           # an animated sheet of characters, monsters or items
```

Names pick the art: `Knight` gets a helmet and shield, `SkeletonArcher` a skull and a bow (and shoots
arrows), `HealthPotion` is a potion, `GoldKey` a key. Layer 2 scatters trees, bushes and rocks that
match the palette, drawn behind everything and without collision.

Record a clip of any built game to share it (a window opens for a few seconds; autopilot plays):

```bash
spawnpoint gif out/pixel-hopper -o demo.gif --seconds 8 --fps 20 --width 640
```

**AI art (optional plug-in).** Point Spawn Point at an image model and layer 2 asks it for the look of
each entity, then makes it game-ready: flat background removed, cropped and fitted to the kind's pixel
size, a 16-color palette, animations synthesized from the single frame, collision traced from the
pixels. Results are cached by prompt; if the provider is down, a generated sprite is used instead.

```bash
export SPAWNPOINT_IMAGE_PROVIDER=a1111  SPAWNPOINT_IMAGE_URL=http://localhost:7860   # Stable Diffusion WebUI
# or: SPAWNPOINT_IMAGE_PROVIDER=openai SPAWNPOINT_IMAGE_URL=https://api.openai.com/v1 SPAWNPOINT_IMAGE_API_KEY=...
spawnpoint create "a knight platformer in a haunted castle" --ai-art
```

In a graph: `"sprite": {"ai": {"prompt": "a tiny knight in silver armor", "kind": "hero"}}`.

Use one in a graph with `"sprite": "assets/sprites/Knight.sprite.json"` (relative to the graph file)
or `"sprite": {"generate": {"kind": "slime", "color": "#ff004d"}}` — see `examples/pixel_hopper.json`.
When an entity has a sprite and no explicit `shape`, its collision size comes from the drawing.

## Playtesting: bots find what's unfair, then fix it

```bash
spawnpoint playtest out/pixel-hopper --tune
```

```
  before:
    novice   won 1/3  deaths 5   (Spikes 4, Frog 1)  missed jumps 3/100  pickups 69%
    average  won 1/3  deaths 2   (Spikes 2)          missed jumps 3/92   pickups 92%
    expert   won 3/3  deaths 3   (fall 3)            missed jumps 0/43   pickups 100%
  round 1 (kept, score 0.8083 -> 0.475):
    Player.Hurtbox.size_scale = 0.75 — Spikes caused 6/7 deaths
    Player.Health.max_health = 4 — novice bots won only 1/3
  after:
    average  won 2/3  deaths 2   (Spikes 1, Slime 1)
```

Three bot skill levels (novice: slow reactions and late jumps; average; expert) press the same keys
a person would, so coyote time, jump buffering and knockback are tested for real. They navigate with
a jump-aware path planner over the tile map, so a failure means the level is hard — not that the bot
is lost. Runs are headless and seeded: 9 runs of up to a minute each take a few seconds.

- **Telemetry**: deaths with cause (`fall`, `Spikes`, `Slime`, `EnemyBullet`…) and position, missed
  jumps (pressed after coyote time ran out), stuck spots, pickups, targets the bots gave up on.
- **Report**: `playtest/report.md`, `report.json` and `heatmap.png` (deaths colored by cause).
- **Tuning** (`--tune`): bounded rules (late jumps → more coyote time; one enemy dominates → it slows
  down; spikes dominate → a more forgiving hurtbox; still too hard → more health…), targets set by the
  game's difficulty. Each round is rebuilt and re-tested and kept only if it gets closer to the targets.
  Studio games store the result in `studio.json`, so later tweaks keep it;
  `spawnpoint create "..." --playtest` does all of this automatically after layer 2.

### Collecting fine-tuning data (opt-in, local only)

```bash
spawnpoint create "..." --record        # or export SPAWNPOINT_RECORD=1 for every create/tweak
spawnpoint dataset stats                # records per task, accepted, corrected by the pipeline
```

Each LLM call is appended to `~/.local/share/spawnpoint/dataset/<date>.jsonl` (override with
`SPAWNPOINT_DATASET_DIR`) with the exact `messages`, the model's `raw` answer, and the `target` the
pipeline actually used — the normalized brief, or the patch the compiler accepted — plus `notes`,
compiler `errors`, `accepted` and `corrected`. Training on `messages → target` teaches the model to
stop making the mistakes the normalizer and compiler had to fix (roadmap item 7). Nothing is uploaded.

## Quick start (hand-written graphs)

```bash
spawnpoint examples list
spawnpoint examples copy coin_hopper && spawnpoint build coin_hopper.json --run   # platformer
spawnpoint examples copy neon_arena && spawnpoint build neon_arena.json --run     # top-down shooter
```

Controls: move **WASD / arrows**, jump **Space / Z / W**, dash **Shift / C**, shoot **X / J / left mouse**,
restart **R**.

The output in `out/<game>/` is a normal Godot project. Open `project.godot` in the editor and keep
developing; the component library is copied into `addons/spawn_point/`.

## A game graph

```json
{
  "name": "Coin Hopper",
  "genre": "platformer",
  "entities": {
    "Player": {
      "shape": { "type": "capsule", "size": [22, 34] },
      "components": { "PlatformerMovement": { "air_jumps": 1 }, "PlayerInput": {},
                      "Health": { "max_health": 3 }, "Hurtbox": {}, "Stomp": {} }
    },
    "Slime": {
      "components": { "PlatformerMovement": { "max_speed": 60 }, "PatrolAI": {},
                      "Health": { "max_health": 1 }, "Hurtbox": {}, "Hitbox": {} }
    },
    "Coin": { "body": "area", "shape": { "type": "circle", "size": [14, 14] },
              "components": { "Collectible": { "score": 1 } } },
    "Exit": { "body": "area", "components": { "TriggerZone": {} } }
  },
  "level": {
    "map": ["...........C......",
            "......=====.......",
            ".P.......C....S..E",
            "##################"],
    "legend": { "#": "solid", "=": "oneway", "P": "Player", "S": "Slime", "C": "Coin", "E": "Exit" }
  },
  "rules": [
    { "on": "Exit.triggered", "if": "count('Coin') == 0", "do": ["win()"] },
    { "on": "Slime.died", "do": ["add_score(5)"] }
  ]
}
```

- **Entities** are a body (`character` / `static` / `area`), a placeholder `shape`
  (`rect`, `circle`, `capsule`, `triangle`, `spikes`, `none`) and components with parameters.
  Colors default from the entity's role; collision shapes always match the visual.
- **Level** is an ASCII map. `solid` and `oneway` are tiles; any other legend value is an entity.
- **Rules**: `on` an event (`Entity.signal`, `Entity.Component.signal`, `GameState.score_changed`,
  `Game.ready`…), optional `if` expression, `do` actions (`win()`, `add_score(n)`, `Door.open()`,
  `spawn("Slime")`, `shake(0.5)`, `message("Hi")`…). They compile to a readable `rules.gd`.

List every component with its parameters, signals and methods:

```bash
spawnpoint components          # human-readable
spawnpoint components --json   # the manifest an LLM can consume
```

## Diagnostics built for self-correction

```bash
$ spawnpoint validate broken.json
  ✗ error[E_UNKNOWN_PARAM] entities.Player.components.Health.max_hp: Health has no parameter 'max_hp' (hint: Did you mean 'max_health'?)
  ✗ error[E_RULE_DO] rules[0].do[1]: Door has no method 'opne' (hint: Did you mean 'open'?)
  ! warning[W_UNREACHABLE] level.map: Coin at (44,2) looks unreachable (jump ≈ 3 tiles up, 4 across)
```

`--json` prints the same as `{severity, code, path, message, hint}` objects. Builds also run a
headless smoke test (spawn, scripted input, crash detection) and report `E_RUNTIME` errors.

## Components

| Category | Components |
|---|---|
| Movement | `PlatformerMovement` (coyote time, jump buffer, variable jump, apex hang, dash, double jump), `TopDownMovement` (accel/friction, dash) |
| Controllers | `PlayerInput`, `PatrolAI`, `ChaseAI`, `Aim` |
| Combat | `Health`, `Hitbox`, `Hurtbox`, `Stomp`, `Weapon`, `Projectile` (a sword is a `Weapon` whose projectile is a short, piercing slash) |
| World | `Collectible`, `TriggerZone`, `Spawner` (ramping waves, spawns around the player), `Gate` |
| Progression | `Experience` (XP and levels), `XpOrb` (gems that fly to the player), `LevelUpMenu` (pause and pick one of three upgrades) |
| Game modes | `BubbleBoard` (a complete bubble shooter: bank shots, colour pops, falling clusters, a descending ceiling) |
| Shooters | `FlightPath` (straight, wave, dive and hover patterns across the screen), `ShmupShip` (auto-fire, power-ups that add shots and spread), `HealthBar` (boss bars), and `WaveSpawner` gates (`autostart`, `endless`, random spread) |
| Tower defense | `PathFollower` (walks the road to the base), `Base` (loses a life per invader that gets in), `WaveSpawner` ("8 x Goblin every 1.2; ..."), `TowerSlot`, `TowerBuilder` (click a pad, pay in gold), `TowerBrain` (targets the invader furthest along), `GroundPatch` (roads and paths) |
| Farming | `FarmPlot` (soil that grows a crop only while watered, drawn from its growth stages), `Farmer` (plant / water / harvest, collect, chop, a basket and a hotbar), `FarmAnimal` (wanders, gives eggs or milk), `Gatherable` (trees and rocks that break into wood and stone), `Market` (a stall or a shipping bin that buys the basket), `CropPest` (crows that eat crops) |
| Feel | `Juice` — attached to every entity unless `"juice": "none"` |

Runtime autoloads: `GameState` (score, lives, variables, win/lose), `World` (spawning, rule
bindings), `FX` (hit-stop, shake, particles, floating text), `Sfx` (pooled sounds with pitch
variation). Sounds are synthesized at build time by a built-in sfxr port — no assets needed.

## Repository layout

```
godot/                     Godot project hosting the component library and its tests
  addons/spawn_point/      components/, runtime/, tools/ (build, smoke, capture), manifest.json
  tests/                   headless GDScript tests
compiler/spawnpoint/       Python compiler: graph schema, analysis, rules codegen, sfx, CLI
compiler/spawnpoint/studio LLM orchestrator: brief, assembler, level generators, web export, browser check
compiler/spawnpoint/sprites SpriteSet format, pixel-art generator and tiles, importer, contour → collision, AI-art providers
compiler/spawnpoint/playtest bots, jump-aware planner, telemetry, heatmaps, tuner
compiler/spawnpoint/cockpit web studio: HTTP + SSE server and the single-page UI
compiler/tests/            pytest (includes end-to-end builds and the GDScript suite)
examples/                  example graphs
scripts/                   helper scripts (local LLM)
docs/media/                README GIFs
```

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

## License

MIT
