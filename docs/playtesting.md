# Playtesting

[← back to the README](../README.md)

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
