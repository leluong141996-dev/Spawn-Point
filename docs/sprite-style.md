# Procedural sprites: style guide and roadmap

How Spawn Point's generated sprites look, so every new kind and feature matches the existing ones,
and the order in which missing kinds/features are added.

## Style guide (derived from `sprites/generate.py`)

**Grid and size.** Each kind is painted at its native pixel size (`KINDS[kind].size`, hero 12×16) and shown
at scale 2. `fine` (pixel_size 1) upscales the painted frame ×2 with EPX (`refine`) and re-outlines it, so new
art must read at native size first. Sizes are relative to the hero: a new creature is about as tall as the
hero unless it is meant to be big (bosses use `size`, not bigger art).

**Colour.** One base colour per entity → 4-tone ramp (`ramp()`): outline (darkest, hue +0.06), shadow
(v×0.68, hue +0.04), base, light (hue −0.03), plus `eye` (29,27,42) and `white`. Fixed accent colours are
module constants (`BLADE`, `GRIP`, hair brown, helmet steel) and are snapped to the theme palette like
everything else. New accents follow the same rule: few, named, palette-snapped.

**Shape language.** Chibi proportions (hero head ≈ half the height), chunky silhouettes, 1px outline around
the whole silhouette (`cv.outline`), light from the top-left (ellipse shading, light pixels on top-left edges),
shadow tone on lower/back parts (legs, far arm). Sprites face right; Godot mirrors them.

**Faces.** Two dark eye pixels toward the facing side (`_eyes`), blinking on idle; hurt pose closes/crosses them.

**Animation.** idle 6 frames (1px breathing bob), run 4 frames, jump/fall 1, hurt 1; `attack` and `die` are
derived (`add_derived`). Every feature must follow the bob offsets in every animation.

**Cartoon twin.** `cartoon.py` draws every kind smooth at 4× detail; new kinds/features get a cartoon version
in the same change.

**Determinism.** Same name/kind/colour/seed → same pixels. Existing sprites must not change unless a name now
maps to a new kind/feature on purpose.

## People in the fine style (`sprites/chibi.py`)

People (hero sprites without creature features such as a tail, wings or a beak) are drawn natively at
24×32 when `pixel_size` is 1, which the studio now uses for every pixel-art game. The look follows classic
chibi pixel characters:

- **Front-facing**, head about half the height (12×13 px), two 1×2 dot eyes, blush; no nose or mouth.
- **Flat colour blocks per part** (skin, hair, shirt, trousers, shoes), each with one shadow tone and a
  touch of light at the top-left; a dark neutral outline (30,24,42) around the figure, with the outline also
  showing between the legs.
- **The entity colour is the clothing colour.** Skin tone, hair colour and hair style are chosen from the
  name and seed (`chibi.choose`), so characters differ but stay stable. Goblins, orcs and trolls use the
  entity colour as skin and wear leather; skeletons are bone; zombies are pallid green.
- **Silhouette from hair, hats and props**: helmet (horned for vikings), pointed wizard hat, straw hat, hood,
  crown, ninja wrap; robe/dress outfits; one held weapon (sword > axe > spear > bow > staff), shield, cape.
- **Animation**: idle breath and blink, run with swinging arms and lifted feet, jump (arms up), fall (arms
  out), hurt (`> <` eyes, flinch), a 3-frame attack per weapon; `die` is derived.

The cartoon style draws the same people (`cartoon.draw_human`) from the same choices. The coarse style
(`pixel_size` 2) keeps the original 12×16 hero.

## Creatures (`sprites/creatures.py`)

`beast`, `spider`, `dragon`, `ghost` and `snake` use the same language (big head and eyes with a glint,
flat colour blocks, a dark neutral outline) and are painted natively at the fine size. The coarse style
shrinks the painting 2:1 (majority colour per 2×2 block, eye pixels always kept) and outlines it again.
Beast variants come from feature words: `bushy_tail` (fox), `thin_tail` (cats), `round_ears` (bear),
`floppy_ears` (dogs), `tusks` + `snout` (boar), `mane` (lion), `stripes` (tiger). Ghosts are tinted
toward white so they stay pale in any theme palette. Names route to these kinds in `studio/assemble.py`
(`BEAST_WORDS`, `SPIDER_WORDS`, `DRAGON_WORDS`, `GHOST_WORDS`, `SNAKE_WORDS`); every kind has a cartoon twin.

## What is missing (inventory of names in examples, prompts, genre defaults and routing word sets)

| Name seen | Drawn today as | Problem |
|---|---|---|
| Archer, Hunter | plain hero | no bow |
| Mage, Wizard, Witch | hero + hat | no staff |
| Zombie | plain hero | looks like any hero |
| Skeleton | plain hero | no skull/bones |
| Orc, Ogre, Troll | hero + horns / plain | no tusks, not bulky |
| Knight, Guard, Soldier | hero + helmet | no shield/spear |
| King, Queen, Princess | hero (+hair) | no crown/cape |
| Wolf, Fox, Puppy, Dog | hopper (a frog) | needs a four-legged beast |
| Spider | bug (top-down beetle) / slime in platformers | needs a side-view spider |
| Dragon | flyer (bat-like) | needs a dragon |
| Ghost | flyer | needs a floating ghost |
| Dino | plain hero | beast or own body |
| Key, CageKey | gem | needs a key |
| Arrow | bullet (dot) | needs an arrow |
| HealthPack | heart | potion fits fantasy themes |

## Roadmap

1. **Hero features** (player, NPCs and every humanoid enemy): `bow`, `staff`, `shield`, `spear`, `axe`, `cape`,
   `crown`, `hood`, `beard`, `tusks`, `skull` (skeleton face + rib/bone body), `zombie` (pallid skin, torn
   clothes), `bulky` (ogre/troll body). Word routing in `FEATURE_WORDS`.
2. **New kinds**: `beast` (wolf, fox, dog, bear, boar, cat), `spider`, `dragon`, `ghost`, `snake`; later
   `golem`, `eye`, `plant` if prompts need them. Routing in `studio/assemble.py` (`sprite_kind`).
3. **Items/props**: `key`, `potion`, `arrow`, `chest`, `bomb`, `scroll`, weapon pickups; decorative
   `tree`/`bush`/`rock` (entity or scenery layer, decided then).
4. **LLM hookup**: none needed at first (names route to kinds/features). Later: parse the player's
   character description for features; optionally let the brief list features.
5. **Tests and review** throughout: snapshot tests per kind/feature in pixel, fine, cartoon and palette
   modes; determinism; collision sanity; contact sheets old vs new for review.
