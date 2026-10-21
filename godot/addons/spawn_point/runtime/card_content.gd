class_name SPCardContent
extends RefCounted
## The fixed content of a card-game run (used by [CardBattleComponent]): relics, potions, map events and card
## upgrades. Gold amounts are multiples of the run's gold per fight, so prices follow the game's economy.

## id -> name, icon (res://sprites/art_ci_<icon>.png), what it does.
const RELICS := {
	"burning_blood": {"name": "Burning Blood", "icon": "blood", "text": "Heal 6 HP after each fight."},
	"lantern": {"name": "Lantern", "icon": "lantern", "text": "+1 energy on the first turn of each fight."},
	"snake_ring": {"name": "Ring of the Snake", "icon": "ring", "text": "Draw 2 more cards on the first turn."},
	"anchor": {"name": "Anchor", "icon": "anchor", "text": "Start each fight with 10 Block."},
	"vajra": {"name": "Vajra", "icon": "vajra", "text": "Start each fight with 1 Strength."},
	"marbles": {"name": "Bag of Marbles", "icon": "marbles", "text": "Foes start each fight Vulnerable."},
	"stone": {"name": "Smooth Stone", "icon": "stone", "text": "Cards that give Block give 1 more."},
	"idol": {"name": "Golden Idol", "icon": "idol", "text": "Earn 25% more gold."},
	"flower": {"name": "Happy Flower", "icon": "flower", "text": "Every 3 turns, gain 1 energy."},
	"vial": {"name": "Blood Vial", "icon": "vial", "text": "Heal 2 HP at the start of each fight."},
}
## The relic each class starts with.
const STARTER_RELIC := {"warrior": "burning_blood", "mage": "lantern", "rogue": "snake_ring"}

## id -> name, bottle colour, what it does, whether it needs a target.
const POTIONS := {
	"fire": {"name": "Fire Potion", "color": "#ff6a2a", "text": "Deal 20 damage.", "target": true},
	"block": {"name": "Block Potion", "color": "#5ab0ff", "text": "Gain 12 Block.", "target": false},
	"energy": {"name": "Energy Potion", "color": "#ffd84a", "text": "Gain 2 energy.", "target": false},
	"strength": {"name": "Strength Potion", "color": "#ff4a6a", "text": "Gain 2 Strength.", "target": false},
	"heal": {"name": "Healing Potion", "color": "#7cf07c", "text": "Heal 15 HP.", "target": false},
	"poison": {"name": "Poison Potion", "color": "#5cd84a", "text": "Apply 6 Poison.", "target": true},
	"swift": {"name": "Swift Potion", "color": "#c8a2ff", "text": "Draw 3 cards.", "target": false},
}
const MAX_POTIONS := 3

## A "?" room: a short scene and two or three choices. Each outcome is a list of [what, amount]:
## gold (times the gold per fight), hp (lose or gain), heal_pct, max_hp, relic, potion, rare_card, remove, upgrade.
const EVENTS := [
	{"title": "Golden Shrine", "text": "A small shrine glitters with old coins.",
		"choices": [{"label": "Pray", "outcome": [["gold", 3]]},
			{"label": "Take everything (lose 8 HP)", "outcome": [["gold", 6], ["hp", -8]]}]},
	{"title": "Healing Spring", "text": "Warm water bubbles up between the stones.",
		"choices": [{"label": "Drink (heal 30%)", "outcome": [["heal_pct", 30]]},
			{"label": "Bathe (remove a card)", "outcome": [["remove", 1]]}]},
	{"title": "Whispering Tome", "text": "An open book whispers your name.",
		"choices": [{"label": "Read it (a rare card, lose 6 HP)", "outcome": [["rare_card", 1], ["hp", -6]]},
			{"label": "Close it", "outcome": []}]},
	{"title": "Wandering Smith", "text": "An old smith sets down her anvil and smiles.",
		"choices": [{"label": "Upgrade a card", "outcome": [["upgrade", 1]]},
			{"label": "Buy her a drink (+5 max HP)", "outcome": [["max_hp", 5]]}]},
	{"title": "Lost Adventurer", "text": "Their pack still lies by the road.",
		"choices": [{"label": "Take the trinket (lose 10 HP)", "outcome": [["relic", 1], ["hp", -10]]},
			{"label": "Take the potion", "outcome": [["potion", 1]]}]},
	{"title": "Cursed Altar", "text": "Dark power hums under your fingers.",
		"choices": [{"label": "Offer blood (lose 5 HP, gain a relic)", "outcome": [["hp", -5], ["relic", 1]]},
			{"label": "Walk away", "outcome": []}]},
]

## Shop prices, in gold-per-fight units.
const PRICE := {"common": 3.5, "uncommon": 5.0, "rare": 7.5, "remove": 5.0, "relic": 10.0, "potion": 3.5}


## The upgraded version of a card: bigger numbers, the same cost ("Strike" -> "Strike+").
static func upgrade(c: Dictionary) -> Dictionary:
	var up := c.duplicate(true)
	up["name"] = String(c["name"]) + "+"
	var fx: Array = []
	for e: Array in c["fx"]:
		var v: int = e[1]
		match e[0]:
			"dmg", "all", "blk", "heal", "poison":
				v += maxi(3, int(round(v * 0.5)))
			"weak", "vuln", "str", "draw", "nrg":
				v += 1
		fx.append([e[0], v])
	up["fx"] = fx
	up["upgraded"] = true
	return up
