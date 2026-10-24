<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/logo.png" width="520" alt="Spawn Point: a sprout growing out of a glowing spawn pad, and the name in gold pixel letters"></p>

# Spawn Point

**Make a 2D game from one sentence in about 20 seconds. Change it by saying what you want. Share it as a web game.**

For beginners and game jams: free, runs on your own computer, and every sprite, tile, effect and sound is drawn by code,
so there are no assets to find and no licenses to worry about. The result is a real Godot 4 project you can keep building.

[![CI](https://github.com/leluong141996-dev/Spawn-Point/actions/workflows/ci.yml/badge.svg)](https://github.com/leluong141996-dev/Spawn-Point/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/spawnpoint-studio)](https://pypi.org/project/spawnpoint-studio/)
[![Model](https://img.shields.io/badge/%F0%9F%A4%97%20model-SpawnPoint--Coder--7B-yellow)](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ)
[![Play the demos](https://img.shields.io/badge/%E2%96%B6%20play-demos%20in%20your%20browser-ff004d)](https://leluong141996-dev.github.io/Spawn-Point/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/leluong141996-dev/Spawn-Point?style=social)](https://github.com/leluong141996-dev/Spawn-Point/stargazers)

⭐ **If Spawn Point drew something fun or useful, a star helps other people find it. If it drew something wrong, [open an issue](https://github.com/leluong141996-dev/Spawn-Point/issues/new) with your prompt: the model's tests grow from prompts that broke.**

<p align="center">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/cards-fight.gif" width="48%" alt="A card battle in a willow forest: a ranger plays cards against a piranha plant and a wolf">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/cards-run.gif" width="48%" alt="A card game run at night: the map, an event, a knight fighting skeletons and bats">
</p>
<p align="center"><sub>New in 0.4: a Slay the Spire style card game from one sentence ("game thẻ bài, hiệp sĩ đánh lũ xương khô, trùm là Lich").</sub></p>

<p align="center"><b><a href="https://leluong141996-dev.github.io/Spawn-Point/">▶ Play the demos in your browser</a></b>: a Slay the Spire style card game, a Mario-style platformer, a
knight with a sword, tower defense, a ninja rescue, a dinosaur-egg bubble shooter, a survivor with level-ups, a cozy
island farm, an arena shooter and a side-scrolling space shooter. No install needed, and
they work on phones too (touch controls).</p>

## Make your first game

```bash
pip install spawnpoint-studio
spawnpoint setup          # installs Godot 4.6 and the web templates if missing, checks how the model can run
spawnpoint llm up         # downloads and serves the SpawnPoint-Coder-7B model (NVIDIA GPU, or Ollama anywhere)
spawnpoint create "a ninja platformer where you collect stars"
```

```
Design:
  “Star Quest” — platformer, palette night, goal collect_all, medium, difficulty 2
  player: Ninja (stomp); jump 3.5 tiles; speed normal; feel snappy; juice normal
  ▶ meet the cast at http://localhost:8060/  (the game opens there when it is built)
  [L0 core loop] ok in 3.0s
  [L1 goals & enemies] ok in 2.8s
  [L2 feel & polish] ok in 5.6s
Done in 17.9s

Change it with words, e.g. "make the jump higher", "add more enemies", "make it harder", "cho nhảy cao hơn".
change> cho nhảy cao hơn
  player.jump_tiles: 3.5 -> 4.2
  the browser tab reloads with the new version
change>
Share it:   spawnpoint share out/star-quest   (a zip for itch.io or your friends)
```

While it builds, your browser shows the game's cast (the hero, the enemies, the boss, the pickups) and then switches
to the game. Prompts can be in English or Vietnamese.

## Change it with words

After `create`, type what you want at the `change>` prompt (or later: `spawnpoint tweak <game> "..."`). Only what
you asked for changes, and the level layout is kept.

| say | what changes |
|---|---|
| "make the jump 20% higher", "cho nhảy cao hơn" | the jump height |
| "add a dash", "give him a sword" | the hero's abilities |
| "more enemies", "add bats that chase you" | the enemies |
| "make it harder", "dễ hơn" | the difficulty: enemy health, numbers, the level |
| "night colors", "a winter farm" | the theme and its art |
| "make the boss a dragon", "add a card called Meteor" | card games: the boss, the cards |
| "new look", "đổi hình" (and "old look") | other colours and details for every character; the same game |

For finer control, `spawnpoint studio` opens a web cockpit where you right-click anything in the game to edit it.

## Share it

```bash
spawnpoint share out/star-quest                          # -> out/star-quest-web.zip
spawnpoint share out/star-quest --itch your-name/star-quest   # and upload it to your itch.io page
```

With `--itch`, Spawn Point fetches butler (itch.io's uploader), logs you in through the browser the first time (or
uses `BUTLER_API_KEY`) and uploads the game; create the page on itch.io first (kind of project: HTML).

The zip is a web build with `index.html` at the top: on [itch.io](https://itch.io) make a new HTML project, upload
it and tick "This file will be played in the browser" (960 x 540, fullscreen button on). It also works on any static
host (GitHub Pages, Netlify) and on phones, with touch controls.

## What can it make?

| kind | try |
|---|---|
| Card game (deckbuilder) | `"a deckbuilder where a wizard climbs a frozen tower full of ice spirits"` |
| Farming game | `"a cozy island farm with strawberries and pumpkins, watch out for crows"` |
| Platformer | `"a ninja platformer where you collect stars, with spikes and bats"` |
| Rescue platformer | `"a fox must save her puppy from a cage guarded by goblins"` |
| Sword platformer | `"a knight with a sword fights slimes and skeletons"` |
| Top-down shooter | `"a space game where I blast alien bugs in an arena"` |
| Survivor with level-ups | `"survive 3 minutes of zombies, pick an upgrade every level"` |
| Tower defense | `"defend the castle from goblins and orcs with archer and cannon towers"` |
| Side-scrolling shooter | `"a falcon ship fights drones and saucers, the boss is a mothership"` |
| Bubble shooter | `"a dinosaur egg shooter, pop three of a colour"` |

## Good for game jams

- **A playable start in under a minute**, then change it with words while you think about the idea.
- **It is a real Godot 4 project**: open `out/<game>/project.godot` in Godot and keep going by hand; the scenes and
  components are plain GDScript.
- **No art or sound needed**: everything is generated (pixel art, backdrops, effects, chiptune music, sound effects),
  and you can swap in your own sprites later (`spawnpoint sprites import`).
- **Free and offline**: the model runs on your machine, no API keys, nothing leaves your computer.
- **It looks finished**: a title screen with the game's name and keys, a pause menu, music, and a Play again button.
- **Ready to submit**: `spawnpoint share --itch you/game` uploads it to itch.io in one step.

## How it works

The AI never writes game code. A small fine-tuned model,
[SpawnPoint-Coder-7B](https://huggingface.co/smoky1496/SpawnPoint-Coder-7B-AWQ), fills in a short design (genre,
hero, enemy behaviours, theme, goal) as JSON, and a deterministic compiler builds the game from **hand-written,
tested Godot components**: Godot itself writes the scenes, a smoke test runs every build, and all art and sound are
generated by code. It runs on your own machine: a 12 GB NVIDIA GPU, or Ollama on anything.

```
your sentence ──► small model: a design (JSON) ──► compiler + tested components ──► Godot 4 project ──► web build
```

## Learn more

- [How it works](docs/how-it-works.md): the design, the assembler, the layers, the model, diagnostics
- [Install details](docs/install.md): requirements, GPUs, Ollama, other APIs
- [Genres in depth](docs/genres.md): the card game and the cozy farm
- [Spawn Point Studio](docs/studio.md): a web cockpit to create, right-click to edit, playtest
- [Sprites](docs/sprites.md): how the pixel art is drawn, or bring your own
- [Playtesting](docs/playtesting.md): bots that play your game and tune it
- [Game graphs and components](docs/graphs.md): write a game by hand in JSON, every component, the repository layout
- [Development](docs/development.md): tests, CI, roadmap

## License

MIT
