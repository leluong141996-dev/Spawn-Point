# Sprites

[← back to the README](../README.md)

## Sprites: generated or your own

Layer 2 replaces placeholder shapes with **procedural pixel art** — no assets, no GPU: chibi people with big heads, monsters with faces (a biting plant, a mushroom, a snail, a flame spirit, a reaper, an alien, a dragon, a ghost...), items, props, themed tiles and a parallax sky. Spawn Point makes pixel art games only. (A graph can still ask for the smooth `"art_style": "cartoon"` look by hand, but games made from a prompt are always pixel art.)

Every character and monster is drawn by plain Python from its name; `spawnpoint sprites parade --set heroes|monsters|items` renders them as an animated sheet.

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
spawnpoint gif out/sunny-farm -o demo.gif --seconds 10 --fps 10 --focus fish
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
