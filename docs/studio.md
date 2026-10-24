# Spawn Point Studio

[← back to the README](../README.md)

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
