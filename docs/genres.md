# Genres in depth

[← back to the README](../README.md)

## A card game from one sentence

Ask for a deckbuilder (`spawnpoint create "a deckbuilder where a wizard climbs a frozen tower full of ice spirits"`,
or `"game thẻ bài kiểu Slay the Spire, hiệp sĩ đánh lũ xương khô"`) and Spawn Point builds a whole run: a branching map
of fights, elites, unknown events, shops, rest sites and treasure, with the boss at the top. Each turn you get 3 energy
and 5 cards; foes show their next move above their heads. Block, poison, weak, vulnerable and strength work the way
deckbuilder players expect, and after a fight you earn gold and pick one of three cards.

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/cards-map.png" width="70%" alt="The run's map on a parchment: rooms linked by dotted paths, the boss at the end"></p>

The model picks the hero and its class (a warrior, mage or rogue starting deck), the game's own cards ("Fireball",
"Ice Shield": named, and what each does), the foes and how they fight (brutes hit hard, guards block, casters curse
and poison, swarms come in packs) and the boss; the assembler sets the numbers and balances the run with the autopilot.
Rest sites heal or upgrade a card (Strike becomes Strike+), shops sell cards, relics and potions and remove cards, ten
relics change the rules (one to start with per class) and potions are drunk in a fight. The art is pixel art drawn
from code: a painted backdrop per theme (a willow forest, a haunted night, desert ruins, a frozen peak, a volcano, a
beach, a candy land, a neon city) with drifting leaves, snow or embers, parchment cards, skill effects (slashes, fire,
ice, lightning, poison), a pixel font, and the same chibi heroes and monsters as the other games, drawn big.

## A cozy farm from one sentence

<p align="center">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-field.gif" width="48%" alt="Tilling, planting, watering and harvesting in the fenced field">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-animals.gif" width="48%" alt="Collecting eggs and milk from the chickens and the cow in the pen">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-fishing.gif" width="48%" alt="Fishing from the pond's shore: cast, wait for the bite, reel in">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-house.gif" width="48%" alt="Walking into the farmhouse: bed, fireplace, table and rug">
</p>
<p align="center"><sub>A cozy farm made from one sentence: the field, the animals, fishing and the farmhouse inside.
Every tile, building, animal and crop is drawn by plain Python. Recorded with <code>spawnpoint gif --focus field|animals|fish|house</code> (autopilot).</sub></p>

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-overview.png" width="92%" alt="A generated island farm: farmhouse, fenced crop field, animal pen with a coop, pond and woods"><br><sub>One generated farm, the whole map: everything here is drawn by plain Python, no image files.</sub></p>

Ask for a farming game (`spawnpoint create "a cozy farming game with strawberries and pumpkins"`) and
Spawn Point lays out a whole farm: a farmhouse with a dirt path to its door, a fenced crop field, an animal pen with a
coop, a pond, a shipping bin, and woods around the edge, on an island (water all round, cliffs to the south; an
ocean-themed farm always is one) or in a meadow in the woods. The art is a 16-pixel tile set drawn from code: grass with tufts, flowers and mushrooms, paths with soft edges,
water with lily pads and reeds, buildings, fences, four kinds of tree, chickens and cows, a farmer who walks in four
directions, and crops with five growth stages (strawberries, carrots, potatoes, pumpkins, corn, wheat, cabbages...,
picked from the crop's name).

A farm is a season of a few days, each running from 6:00 to 22:00 with the light turning gold in the evening and dark
at night; sleep in the farmhouse bed (or drop off in the fields at midnight) and watered crops grow overnight. Earn the
target before the season ends. What you do there: buy seeds (they cost money), till the grass with the hoe, plant,
water and harvest; feed the hens and the cow, then collect eggs and milk (chicks grow into hens); fish from the pond's
shore (cast, wait for the bite, reel in on the "!"); chop trees and break rocks for wood and stone; carry it all to the
shipping bin, while crows, foxes, rabbits or mice go for your crops. Step through the farmhouse door for a cozy room
inside (bed, fireplace, table, rug). Maps vary: the house on either side, the field and the pen swapping places, the
pond moving around. The workbench by the house sells tool upgrades (a watering can and a hoe that work a
3x3 patch, a bigger basket, a sharper axe, a better rod), and the farm saves itself: close the game and it carries on
where you left it (a won or lost season, or R, starts a fresh one). Some days it rains and the crops water themselves
(snow on a winter farm); a shop stall sells hens, cows, golden melon seeds and sprinklers that water their patch every
morning. A farm opens on a title screen (carry on, or N for a new farm), P pauses, and each season has its own little
chiptune, composed at build time. On a phone, ACT does all of it, a tap on a seed in the bar picks it, and II pauses. The
hotbar shows your seeds and basket. You walk behind trees and the house (the scene is depth-sorted), and only an
object's footprint blocks you. `spawnpoint overview <project>` saves a picture of the whole map after a short autopilot
run, like the one above.

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/sunny-farm.gif" width="52%" alt="Sunny Farm: the farmer harvests, sells at the shipping bin and works the field"> <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-night.gif" width="40%" alt="Evening turns to night on the farm; the farmer milks the cow before bed"></p>

The theme sets the season, and the model picks it from the prompt ("a winter farm", "nông trại trên sa mạc"): a snowy
farm is winter (snow, a frozen pond, snowy pines and bare trees, and crops grow slower), a desert farm has sand, palms
and cacti (and the soil dries faster), an autumn farm is orange with maples, the rest is spring.

<p align="center"><img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-seasons.png" width="92%" alt="The same kind of farm in spring, autumn, winter and the desert"></p>
<p align="center">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-winter.gif" width="32%" alt="A winter farm: snow, snowy pines, bare trees">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-autumn.gif" width="32%" alt="An autumn farm: orange ground, maples">
  <img src="https://raw.githubusercontent.com/leluong141996-dev/Spawn-Point/main/docs/media/farm-desert.gif" width="32%" alt="A desert farm: sand, palms and cacti">
</p>
