# Spawn Point: a retrospective

[← back to the README](../README.md)

**Status: finished.** Spawn Point works and stays available (PyPI, the model on Hugging Face, the browser demos), but
I'm no longer developing it. This page is what I built in about two and a half weeks (October 7 to 24, 2026), what
worked, and why I stopped.

## What I set out to do

Turn one sentence into a small playable game, on your own computer, for free: "a platformer where a fox in a candy
land collects stars" → a Godot 4 project in about 20 seconds, then change it by typing ("make it night and add bats").

## What I built

- **A compiler from a JSON game graph to a Godot 4 project.** Entities are components plus parameters, levels are
  ASCII maps, gameplay rules are declarative and compile to GDScript. Godot itself builds the scenes headless
  (`PackedScene.pack()` + `ResourceSaver.save()`), and every build is smoke-tested.
- **48 hand-written, tested Godot components**: platformer and top-down movement with game feel (coyote time, jump
  buffer, hit-stop, screen shake), combat, enemy AI, tower defense, a shoot 'em up, a bubble shooter, a cozy farm
  with seasons and saving, and a Slay the Spire style deckbuilder.
- **Everything audiovisual drawn or composed by code**: pixel-art characters and monsters, tiles, backdrops, effects,
  a pixel font, sfxr-style sound effects and chiptune music. No image or sound files.
- **SpawnPoint-Coder-7B**, a fine-tuned 7B model that writes the game's design (not its code) as JSON, released in
  six versions. The last one designs card games: 94% of a sealed set of 16 card-game prompts fully right (the
  previous version: 56%), 90% of 30 human-written prompts in English and Vietnamese. It runs on a 12 GB GPU, or
  through Ollama on anything.
- **The rest of a product**: a terminal flow (`setup`, `create`, change it with words, `share --itch`), a web cockpit,
  playtest bots that tune difficulty, a cast preview while a game builds, install CI on Linux, macOS and Windows,
  15 releases on PyPI, about 18,000 lines of Python and 11,000 of GDScript, and 786 tests.

## What worked

- **Don't let the model write the code.** Model-written GDScript is where the usual failures live (Godot 3 APIs in a
  Godot 4 project, hitboxes that don't match the art, no game feel). A small model filling a schema-constrained form,
  plus a deterministic compiler over tested components that validates and smoke-tests every build, removed that whole
  class of failure.
- **A sealed test set written before the training data.** It caught two regressions I would otherwise have shipped,
  both caused by my own synthetic data (every farm had pests, so the model added pests to peaceful farms).
- **Measuring "change it with words" with real beginner requests.** 42 requests in two languages turned up silent
  failures: a sword that was asked for and quietly dropped, a model escaping a constrained value into whitespace.
- **Testing the install on machines I don't have.** CI on Windows found a crash a Linux-only developer never sees.

## Why I stopped

The engineering held up; the product question didn't.

- **The frontier models' free tiers already do most of this.** Ask a big model for a small Godot game and you get one,
  and they improve every month. A local 7B model is not a reason to switch.
- **Speed was never the pain.** Nobody minds waiting a few minutes for a better result; "20 seconds" was my metric,
  not a user's.
- **The audience was unclear.** People who are serious about making games want to make the decisions themselves, or
  build their own tools; people who aren't try it once. When I posted it, game developers told me so, bluntly and
  fairly: the barrier to *implementing* mechanics is gone, the hard part left is making something fun, and a tool that
  makes games *for* you doesn't help with that.

## What I'd do differently

- **Start from a game I want to make**, and build tools only when that game needs them. Good tools for game developers
  usually come out of a real game.
- **Ask people before building.** One honest conversation with game developers in week one would have saved the
  pivot in week three.
- **Build next to the big models, not against them**: tools they (and people) can call, such as a validator, a builder
  or an asset processor, rather than a smaller version of what they already do.

## What's still useful here

- The Godot component library (`godot/addons/spawn_point/components`), usable on its own.
- The procedural pixel art, effects, font, sound and music generators (`compiler/spawnpoint/sprites`, `sfx.py`,
  `music.py`).
- The approach to fine-tuning a small model for structured output and evaluating it honestly (sealed sets, replay
  data, measuring every older set before a release).

Thanks to everyone who tried it, and to the people who told me what they really thought.
