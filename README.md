# Spawn Point

**Compile a small JSON "game graph" into a juicy, runnable Godot 4 game — in seconds.**

Spawn Point is the foundation of an autonomous game-studio agent. Instead of asking an LLM to type
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

## Quick start

Requirements: Python ≥ 3.10 and [Godot 4.6](https://godotengine.org/download) on your `PATH`
(`godot4` or `godot`, or set `GODOT_BIN`).

```bash
pip install -e ".[dev]"
spawnpoint build examples/coin_hopper.json --run     # platformer
spawnpoint build examples/neon_arena.json --run      # top-down shooter
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

See the full reference in the [design spec](docs/superpowers/specs/2026-10-07-component-library-and-graph-compiler-design.md),
and list every component with its parameters, signals and methods:

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
| Combat | `Health`, `Hitbox`, `Hurtbox`, `Stomp`, `Weapon`, `Projectile` |
| World | `Collectible`, `TriggerZone`, `Spawner`, `Gate` |
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
compiler/tests/            pytest (includes end-to-end builds and the GDScript suite)
examples/                  example graphs
docs/                      design specs
```

## Development

```bash
pytest                      # everything: compiler, end-to-end builds, GDScript component suite
spawnpoint manifest         # regenerate manifest.json after changing a component
godot4 --headless --path godot --fixed-fps 60 res://tests/run_tests.tscn   # GDScript suite only
```

Adding a component: create `godot/addons/spawn_point/components/<name>_component.gd` following the
contract (typed `@export`s with ranges, `SP_NAME` / `SP_HOSTS` / `SP_REQUIRES` / `SP_CATEGORY`
constants, `##` docs on everything public), add tests in `godot/tests/`, then run `spawnpoint manifest`.

## Roadmap

1. ✅ Component library with juice
2. ✅ Graph compiler (validation, rules, levels, SFX, smoke test)
3. LLM orchestrator — prompt → graph in layers (core loop → win/lose → art & audio), web export, targeted re-patching from feedback
4. Asset pipeline — sprite-sheet auto-slicing, contour → `CollisionPolygon2D`, `AnimationPlayer` generation
5. Playtester agent — headless play with scripted/learned input, tunes parameters (e.g. coyote time) from telemetry
6. Web cockpit — live WebGL arcade, click an entity and describe the change

## License

MIT
