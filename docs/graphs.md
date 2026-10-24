# Game graphs and components

[← back to the README](../README.md)

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
| Farming | `FarmPlot` (soil that grows a crop only while watered, drawn from its growth stages), `Farmer` (till / plant / water / harvest, buy seeds, feed, collect, fish, chop, sleep, a basket and a tappable hotbar), `FarmAnimal` (wanders, needs feeding, gives eggs or milk, chicks grow up), `FarmDays` (a season of days with day and night), `SleepSpot` (a bed), `ToolBench` (tool upgrades), `FarmSave` (keeps the farm between plays), `Shop` and `Sprinkler` (buy animals, seeds and sprinklers), `GameMenu` (title screen, pause menu, music), `Gatherable` (trees and rocks that break into wood and stone), `FishingSpot` (cast, bite, reel in), `Warp` (doorways, e.g. into the farmhouse), `Market` (a stall or a shipping bin that buys the basket), `CropPest` (crows that eat crops) |
| Card games | `CardBattle` (a whole deckbuilding run on its hero: the branching map, fights with energy, block, statuses and foe intents, rewards, rest sites, shops, events, relics, potions, upgrades and the card UI; foes are ordinary entities spawned per fight) |
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
