class_name CardBattleComponent
extends Node
## A whole deckbuilding run (Slay the Spire style), played by its entity, the hero. The run is a path of floors:
## pick the next room (fight, elite, rest, treasure), and the last floor is the boss. In a fight you get
## [member energy] energy and draw [member hand_size] cards each turn; foes show their next move above their heads.
## Click or tap a card to play it on the selected foe (click a foe to select it), or press 1-9; Tab switches the
## target, E or Space ends the turn. After a fight you earn gold (the score) and pick one of three new cards.
## The hero's [HealthComponent] holds its HP. Emits [signal won] when the boss falls (wire it to win()).
##
## Cards: "Name|cost|type|effects|rarity|icon;..." where type is attack, skill or power, rarity is starter, common,
## uncommon or rare, and effects are comma-separated: dmg:N (the target), hits:N (dmg that many times), all:N (every
## foe), blk:N, draw:N, nrg:N, heal:N, poison:N, weak:N, vuln:N, str:N, exhaust.
## Foes: "Type|hp|tier|intent,intent,..." (tier normal, elite or boss); each intent is atk:N, atk:NxK, blk:N, str:N,
## weak:N, vuln:N, poison:N or heal:N, joined with + to do several at once ("blk:6+atk:4"). Foes repeat their list.

const SP_NAME := "CardBattle"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Health"]
const SP_INTERNAL: Array[String] = ["play_index", "end_turn", "choose", "skip_reward", "autopilot_step", "card",
	"card_text", "foes_alive", "hand", "phase", "intent_of", "deal", "begin_fight", "set_target", "use_potion", "view_deck"]
const SP_CATEGORY := "core"

## Emitted when a fight begins; [param kind] is "fight", "elite" or "boss".
signal fight_started(kind: String)
## Emitted when every foe of a fight is down.
signal fight_won(floor_number: int)
## Emitted when the boss is defeated.
signal won()
## Emitted when the hero falls.
signal died()
## Emitted for every card played.
signal card_played(card_name: String)

## The card library (see the class description).
@export_multiline var cards: String = "Strike|1|attack|dmg:6|starter|sword;Defend|1|skill|blk:5|starter|shield"
## The starting deck: card names, "Name*N" for copies.
@export var starter: String = "Strike*5,Defend*5"
## The foes (see the class description).
@export_multiline var foes: String = "Slime|14|normal|atk:6,blk:4+atk:3;Ogre|60|boss|atk:10,str:2,atk:6x2"
## Floors in the run, the boss's included.
@export_range(2, 20) var floors: int = 7
## Energy each turn.
@export_range(1, 10) var energy: int = 3
## Cards drawn each turn.
@export_range(1, 10) var hand_size: int = 5
## Gold for winning a fight (elites give double).
@export_range(0, 1000) var gold_per_fight: int = 12
## Share of max HP a rest heals.
@export_range(0.0, 1.0, 0.01) var rest_heal: float = 0.3
## Where the first foe stands, relative to the hero.
@export var foe_offset: Vector2 = Vector2(330, 0)
## Space between foes in px.
@export_range(40.0, 400.0, 1.0) var foe_gap: float = 130.0
## The relic the hero starts with (see SPCardContent.RELICS; empty for none).
@export var starter_relic: String = ""
## The backdrop's theme, for drifting leaves, snow, embers... (a palette name; empty for none).
@export var theme: String = ""
## The hero's name on its panel.
@export var hero_name: String = "Hero"
## Seconds between foe moves (0 = instant, for tests).
@export_range(0.0, 2.0, 0.01) var pace: float = 0.45
## Map and draw seed (0 = a new run every time).
@export_range(0, 1000000) var run_seed: int = 0

const STATUS_KEYS := ["block", "poison", "weak", "vuln", "str"]
const NODE_ICON := {"fight": "sword", "elite": "skull", "rest": "campfire", "treasure": "chest", "boss": "crown",
	"event": "question", "shop": "bag"}
const NODE_NAME := {"fight": "Fight", "elite": "Elite", "rest": "Rest", "treasure": "Treasure", "boss": "Boss",
	"event": "Unknown", "shop": "Shop"}
const TYPE_COLOR := {"attack": Color("#b8503a"), "skill": Color("#3a8a7a"), "power": Color("#8a4ab8")}
const ICON_FX := {"sword": "slash", "axe": "slash", "dagger": "slash", "bow": "slash", "wind": "slash", "fire": "fire",
	"ice": "ice", "bolt": "bolt", "star": "bolt", "drop": "poison", "staff": "curse", "skull": "curse", "crack": "curse",
	"flex": "buff", "book": "buff", "heart": "heal", "shield": "shield"}
const STATUS_ICON := {"str": "flex", "poison": "drop", "weak": "skull", "vuln": "crack"}
const STATUS_COLOR := {"str": Color("#ffb03a"), "poison": Color("#7cf05a"), "weak": Color("#c8a2ff"), "vuln": Color("#ff8fb4")}
const INK := Color("#1d1a33")
const GOLD := Color("#ffec27")

var phase := "map"  # map, fight, foe_turn, won_fight, reward, rest, shop, event, notice, pick, done
var floor_index := -1
var run_map: Array = []  # per floor: an Array of rooms {kind, lane, next: [room indices on the next floor]}
var room := -1  # the room taken on the current floor
var options: Array = []  # what the open panel offers (rooms, cards, choices, shop items)
var relics: Array[String] = []
var potions: Array[String] = []
var deck: Array[String] = []
var draw_pile: Array[String] = []
var hand: Array[String] = []
var discard: Array[String] = []
var energy_left := 0
var target := 0
var hero_st := {}
var foe_list: Array[Dictionary] = []  # {node, type, hp, tier, intents, step, st}
var spawner: Callable  # (type, position) -> Node2D; World.spawn when unset (tests build foes themselves)

var _entity: Node2D
var _health: HealthComponent
var _library := {}  # name -> {name, cost, type, fx, rarity, icon}
var _foe_types: Array[Dictionary] = []
var _rng := RandomNumberGenerator.new()
var _fight_kind := "fight"
var _turn := 0
var _shop_cards: Array = []
var _shop_relic := ""
var _shop_potion := ""
var _shop_removed := false
var _event := {}
var _pick_from := ""
var _pick_mode := ""
var _pick_cost := 0
var _busy := false
var _view: Node2D
var _ui: CanvasLayer
var _hand_root: Control
var _energy_label: Label
var _pile_label: Label
var _discard_label: Label
var _draw_back: TextureRect
var _discard_back: TextureRect
var _end_button: Button
var _portrait: TextureRect
var _hero_bar: Control
var _gold_label: Label
var _floor_label: Label
var _panel_body: VBoxContainer
var _belt: HBoxContainer
var _path: Array[int] = []  # the room taken on each floor so far
var _font: Font
var _font_plain: Font
var _deal_next := false
var _vignette: Control
var _vignette_tween: Tween
var _panel: Control
var _panel_title: Label
var _panel_hint: Label
var _tex := {}


func _ready() -> void:
	_entity = get_parent() as Node2D
	_health = SP.component(_entity, &"Health") as HealthComponent
	if run_seed != 0:
		_rng.seed = run_seed
	else:
		_rng.randomize()
	_parse_cards()
	_parse_foes()
	for entry in starter.split(",", false):
		var parts := entry.strip_edges().split("*")
		var n := int(parts[1]) if parts.size() > 1 else 1
		for i in n:
			if _library.has(parts[0]):
				deck.append(parts[0])
	_make_map()
	if SPCardContent.RELICS.has(starter_relic):
		relics.append(starter_relic)
	for k in STATUS_KEYS:
		hero_st[k] = 0
	if _health:
		_health.invincibility_time = 0.0
		_health.died.connect(func() -> void:
			phase = "done"
			died.emit())
	_view = Node2D.new()
	_view.name = "CardView"
	_view.z_index = 30
	_view.draw.connect(_draw_world)
	_entity.get_parent().add_child.call_deferred(_view)
	_start_ambient.call_deferred()
	_build_ui()
	_open_map.call_deferred()


# --- data -----------------------------------------------------------------------------------

func _parse_cards() -> void:
	for entry in cards.split(";", false):
		var f := entry.strip_edges().split("|")
		if f.size() < 4:
			continue
		var fx: Array = []
		for e in f[3].split(",", false):
			var kv := e.strip_edges().split(":")
			fx.append([kv[0], int(kv[1]) if kv.size() > 1 else 1])
		_library[f[0]] = {"name": f[0], "cost": int(f[1]), "type": f[2], "fx": fx,
			"rarity": f[4] if f.size() > 4 else "common", "icon": f[5] if f.size() > 5 else "sword"}


func _parse_foes() -> void:
	for entry in foes.split(";", false):
		var f := entry.strip_edges().split("|")
		if f.size() < 4:
			continue
		var intents: Array = []
		for step in f[3].split(",", false):
			var moves: Array = []
			for m in step.split("+", false):
				var kv := m.strip_edges().split(":")
				var val := kv[1] if kv.size() > 1 else "1"
				var hits := 1
				if "x" in val:
					hits = int(val.split("x")[1])
					val = val.split("x")[0]
				moves.append([kv[0], int(val), hits])
			intents.append(moves)
		_foe_types.append({"type": f[0], "hp": int(f[1]), "tier": f[2], "intents": intents})


func card(card_name: String) -> Dictionary:
	return _library.get(card_name, {})


func _fx(c: Dictionary, key: String) -> int:
	for e: Array in c.get("fx", []):
		if e[0] == key:
			return e[1]
	return 0


## What a card does, in words.
func card_text(card_name: String) -> String:
	var c := card(card_name)
	var out: PackedStringArray = []
	var hits := maxi(1, _fx(c, "hits"))
	for e: Array in c.get("fx", []):
		var v: int = e[1]
		match e[0]:
			"dmg":
				out.append("Deal %d damage%s." % [v, " %d times" % hits if hits > 1 else ""])
			"all":
				out.append("Deal %d damage to ALL foes." % v)
			"blk":
				out.append("Gain %d Block." % v)
			"draw":
				out.append("Draw %d card%s." % [v, "s" if v > 1 else ""])
			"nrg":
				out.append("Gain %d energy." % v)
			"heal":
				out.append("Heal %d HP." % v)
			"poison":
				out.append("Apply %d Poison." % v)
			"weak":
				out.append("Apply %d Weak." % v)
			"vuln":
				out.append("Apply %d Vulnerable." % v)
			"str":
				out.append("Gain %d Strength." % v)
			"exhaust":
				out.append("Exhaust.")
	return " ".join(out)


func _targeted(c: Dictionary) -> bool:
	for k in ["dmg", "poison", "weak", "vuln"]:
		if _fx(c, k) > 0:
			return true
	return false


# --- the run --------------------------------------------------------------------------------
# The map is a graph of rooms: floors left to right, each room on one of LANES lanes, linked to the rooms on
# the next floor one lane up, level or down. You walk one link per floor; the boss waits on the last floor.

const LANES := 4

func _make_map() -> void:
	run_map.clear()
	for f in floors:
		var nodes: Array = []
		if f == floors - 1:
			nodes.append({"kind": "boss", "lane": 1.5, "next": []})
		else:
			var lanes := [0, 1, 2, 3]
			lanes.shuffle()
			var count := 3 if _rng.randf() < 0.5 else 2
			var picked := lanes.slice(0, count)
			picked.sort()
			for lane: int in picked:
				nodes.append({"kind": _room_kind(f), "lane": float(lane), "next": []})
		run_map.append(nodes)
	for f in floors - 1:
		var here: Array = run_map[f]
		var there: Array = run_map[f + 1]
		for i in here.size():
			for j in there.size():
				if absf(float(here[i]["lane"]) - float(there[j]["lane"])) <= 1.01 or there.size() == 1:
					here[i]["next"].append(j)
			if here[i]["next"].is_empty():  # no neighbour: link the closest room
				here[i]["next"].append(_closest(there, float(here[i]["lane"])))
		for j in there.size():  # every room can be reached
			var reached := false
			for n: Dictionary in here:
				if j in n["next"]:
					reached = true
			if not reached:
				here[_closest(here, float(there[j]["lane"]))]["next"].append(j)
	room = -1


func _closest(nodes: Array, lane: float) -> int:
	var best := 0
	for k in nodes.size():
		if absf(float(nodes[k]["lane"]) - lane) < absf(float(nodes[best]["lane"]) - lane):
			best = k
	return best


func _room_kind(f: int) -> String:
	if f == 0:
		return "fight"
	if f == floors - 2:
		return "rest"
	if f == floors / 2 and f < floors - 2:
		return "treasure"
	var r := _rng.randf()
	if f >= 2 and r < 0.14:
		return "elite"
	if f >= 2 and r < 0.24:
		return "shop"
	if f >= 3 and r < 0.32:
		return "rest"
	if r < 0.52:
		return "event"
	return "fight"


func _open_map() -> void:
	if phase == "done":
		return
	floor_index += 1
	if floor_index >= run_map.size():
		return
	phase = "map"
	options = []
	if floor_index == 0:
		for j in run_map[0].size():
			options.append(j)
	else:
		options = run_map[floor_index - 1][room]["next"].duplicate()
		options.sort()
	_show_map()


## Picks option [param i] of what is open: a room on the map, a reward card, a choice at a rest site, in a shop
## or an event, or a card of the deck.
func choose(i: int) -> void:
	if i < 0 or i >= options.size() or _busy:
		return
	match phase:
		"map":
			room = options[i]
			_path.append(room)
			var kind: String = run_map[floor_index][room]["kind"]
			_hide_panel()
			match kind:
				"rest":
					_open_rest()
				"treasure":
					var relic := _random_relic()
					_gain_relic(relic)
					_add_gold(1.5)
					_show_choices("Treasure!", "You found %s: %s" % [SPCardContent.RELICS[relic]["name"],
						SPCardContent.RELICS[relic]["text"]], ["Go on"])
					phase = "notice"
				"shop":
					_open_shop()
				"event":
					_open_event()
				_:
					begin_fight(kind)
		"reward":
			var picked: String = options[i]
			deck.append(picked)
			GameState.message("%s joins your deck" % picked)
			Sfx.play("pickup")
			_hide_panel()
			_open_map.call_deferred()
		"rest":
			if i == 0:
				var amount := int(round(_health.max_health * rest_heal))
				_health.heal(amount)
				_pop(_entity, "+%d" % amount, Color("#7cf07c"))
				_play_fx("heal", _entity)
				Sfx.play("pickup")
				_hide_panel()
				_open_map.call_deferred()
			else:
				_open_pick("upgrade", "Smith: choose a card to upgrade")
		"shop":
			_buy(i)
		"event":
			_resolve_event(i)
		"notice":
			_hide_panel()
			_open_map.call_deferred()
		"pick":
			_picked(i)


func skip_reward() -> void:
	match phase:
		"reward", "notice":
			_hide_panel()
			_open_map.call_deferred()
		"shop":
			_hide_panel()
			_open_map.call_deferred()
		"pick":
			_cancel_pick()


func _add_gold(times: float) -> int:
	var amount := int(round(gold_per_fight * times * _rng.randf_range(0.85, 1.15) * (1.25 if "idol" in relics else 1.0)))
	GameState.add_score(amount)
	return amount


func _card_pool(rare_only := false) -> Array[String]:
	var pool: Array[String] = []
	for n: String in _library:
		var c: Dictionary = _library[n]
		if c["rarity"] != "starter" and not c.get("upgraded", false) and (not rare_only or c["rarity"] == "rare"):
			pool.append(n)
	return pool


func _roll_cards(count: int, better: bool) -> Array:
	var pool := _card_pool()
	var out: Array = []
	var tries := 0
	while out.size() < mini(count, pool.size()) and tries < 80:
		tries += 1
		var n: String = pool[_rng.randi() % pool.size()]
		var rarity: String = _library[n]["rarity"]
		var keep := 1.0 if rarity == "common" else (0.55 if rarity == "uncommon" else 0.25)
		if better:
			keep = minf(1.0, keep * 1.8)
		if n not in out and _rng.randf() < keep:
			out.append(n)
	return out


func _offer_cards(title: String, better: bool, lines := "") -> void:
	phase = "reward"
	options = _roll_cards(3, better)
	if options.is_empty():
		_open_map.call_deferred()
		return
	_show_cards(title, (lines + "\n" if lines != "" else "") + "Take a card (click or 1-%d), or skip (S)" % options.size(),
		options, true)


# --- rest, shop, events, deck picks ----------------------------------------------------------

func _open_rest() -> void:
	phase = "rest"
	options = ["rest", "smith"]
	var amount := int(round(_health.max_health * rest_heal))
	_show_choices("Rest Site", "The fire crackles. Rest, or improve a card.",
		["Rest (+%d HP)" % amount, "Smith (upgrade a card)"], ["campfire", "hammer"])


func _upgradable() -> Array[String]:
	var out: Array[String] = []
	for n in deck:
		if not card(n).get("upgraded", false) and n not in out:
			out.append(n)
	return out


## The upgraded card's name; its library entry is made on first use.
func _upgraded(card_name: String) -> String:
	var up_name := card_name + "+"
	if not _library.has(up_name):
		_library[up_name] = SPCardContent.upgrade(_library[card_name])
	return up_name


func _price(what: String) -> int:
	return int(round(gold_per_fight * float(SPCardContent.PRICE[what])))


func _open_shop() -> void:
	phase = "shop"
	_shop_cards = _roll_cards(5, true)
	var owned := relics
	var free := SPCardContent.RELICS.keys().filter(func(r: String) -> bool: return r not in owned)
	_shop_relic = free[_rng.randi() % free.size()] if not free.is_empty() else ""
	_shop_potion = SPCardContent.POTIONS.keys()[_rng.randi() % SPCardContent.POTIONS.size()]
	_shop_removed = false
	_refresh_shop()


func _shop_items() -> Array:
	var items: Array = []
	for n: String in _shop_cards:
		items.append(["card", n, _price(card(n)["rarity"])])
	if _shop_relic != "":
		items.append(["relic", _shop_relic, _price("relic")])
	if _shop_potion != "":
		items.append(["potion", _shop_potion, _price("potion")])
	if not _shop_removed:
		items.append(["remove", "", _price("remove")])
	return items


func _refresh_shop() -> void:
	options = _shop_items()
	_show_shop()


func _buy(i: int) -> void:
	var item: Array = options[i]
	if GameState.score < item[2]:
		GameState.message("Not enough gold")
		return
	match item[0]:
		"card":
			GameState.add_score(-item[2])
			deck.append(item[1])
			_shop_cards.erase(item[1])
		"relic":
			GameState.add_score(-item[2])
			_gain_relic(item[1])
			_shop_relic = ""
		"potion":
			if potions.size() >= SPCardContent.MAX_POTIONS:
				GameState.message("Your potion belt is full")
				return
			GameState.add_score(-item[2])
			potions.append(item[1])
			_shop_potion = ""
		"remove":
			_open_pick("remove", "Choose a card to remove (%d gold)" % item[2], item[2])
			return
	Sfx.play("pickup")
	_refresh_shop()


func _open_event() -> void:
	phase = "event"
	_event = SPCardContent.EVENTS[_rng.randi() % SPCardContent.EVENTS.size()]
	options = _event["choices"]
	var labels: Array = []
	for c: Dictionary in options:
		labels.append(c["label"])
	_show_choices(_event["title"], _event["text"], labels)


func _resolve_event(i: int) -> void:
	var pick_after := ""
	var lines: PackedStringArray = []
	for o: Array in options[i]["outcome"]:
		match o[0]:
			"gold":
				lines.append("+%d gold" % _add_gold(o[1]))
			"hp":
				if o[1] < 0:
					_health.damage(-o[1])
					lines.append("%d HP" % o[1])
				else:
					_health.heal(o[1])
			"heal_pct":
				var amount := int(round(_health.max_health * o[1] / 100.0))
				_health.heal(amount)
				_play_fx("heal", _entity)
				lines.append("+%d HP" % amount)
			"max_hp":
				_health.max_health += o[1]
				_health.heal(o[1])
				lines.append("+%d max HP" % o[1])
			"relic":
				var r := _random_relic()
				_gain_relic(r)
				lines.append("Relic: %s" % SPCardContent.RELICS[r]["name"])
			"potion":
				if potions.size() < SPCardContent.MAX_POTIONS:
					var p: String = SPCardContent.POTIONS.keys()[_rng.randi() % SPCardContent.POTIONS.size()]
					potions.append(p)
					lines.append("Potion: %s" % SPCardContent.POTIONS[p]["name"])
			"rare_card":
				var pool := _card_pool(true)
				if pool.is_empty():
					pool = _card_pool()
				if not pool.is_empty():
					var n: String = pool[_rng.randi() % pool.size()]
					deck.append(n)
					lines.append("New card: %s" % n)
			"remove", "upgrade":
				pick_after = o[0]
	if phase == "done":
		return
	_refresh_ui()
	if pick_after == "remove":
		_open_pick("remove", "Choose a card to remove")
	elif pick_after == "upgrade":
		_open_pick("upgrade", "Choose a card to upgrade")
	else:
		phase = "notice"
		options = ["go"]
		_show_choices(_event["title"], " ".join(lines) if not lines.is_empty() else "Nothing happens.", ["Go on"])


## Shows the deck to pick a card from: "upgrade", "remove" or "view".
func _open_pick(mode: String, title: String, cost := 0) -> void:
	_pick_from = phase
	_pick_mode = mode
	_pick_cost = cost
	phase = "pick"
	options = (_upgradable() if mode == "upgrade" else deck.duplicate()) as Array
	if mode != "view" and options.is_empty():
		_cancel_pick()
		return
	_show_cards(title, "Click a card%s" % ("" if mode == "view" else ", or S to cancel"), options, false, true)


func _picked(i: int) -> void:
	var n: String = options[i]
	match _pick_mode:
		"upgrade":
			var at := deck.find(n)
			deck[at] = _upgraded(n)
			_play_fx("buff", _entity)
			GameState.message("%s upgraded" % n)
		"remove":
			deck.erase(n)
			if _pick_cost > 0:
				GameState.add_score(-_pick_cost)
				_shop_removed = true
			GameState.message("%s removed" % n)
		"view":
			_cancel_pick()
			return
	Sfx.play("pickup")
	if _pick_from == "shop":
		phase = "shop"
		_refresh_shop()
	else:
		_hide_panel()
		_open_map.call_deferred()


func _cancel_pick() -> void:
	phase = _pick_from
	match _pick_from:
		"shop":
			_refresh_shop()
		"rest":
			_open_rest()
		"map":
			_show_map()
		"fight", "foe_turn":
			_hide_panel()
			_refresh_ui()
		_:
			_hide_panel()
			_open_map.call_deferred()


## Opens the deck to look at (the Deck button).
func view_deck() -> void:
	if phase in ["pick", "done"] or _busy:
		return
	_open_pick("view", "Your deck (%d cards)" % deck.size())


# --- relics and potions ----------------------------------------------------------------------

func _random_relic() -> String:
	var free: Array = SPCardContent.RELICS.keys().filter(func(r: String) -> bool: return r not in relics)
	if free.is_empty():
		return relics[0] if not relics.is_empty() else "anchor"
	return free[_rng.randi() % free.size()]


func _gain_relic(r: String) -> void:
	if r not in relics:
		relics.append(r)
		GameState.message("Relic: %s" % SPCardContent.RELICS[r]["name"])
	_refresh_ui()


## Drinks the potion in slot [param i] (in a fight; aimed ones hit the selected foe).
func use_potion(i: int) -> bool:
	if phase != "fight" or _busy or i < 0 or i >= potions.size():
		return false
	var p: String = potions[i]
	var alive := foes_alive()
	if SPCardContent.POTIONS[p]["target"] and alive.is_empty():
		return false
	potions.remove_at(i)
	var foe: Dictionary = alive[clampi(target, 0, alive.size() - 1)] if not alive.is_empty() else {}
	match p:
		"fire":
			_play_fx("fire", foe["node"])
			deal({}, foe["node"], foe["st"], 20)
		"poison":
			foe["st"]["poison"] += 6
			_play_fx("poison", foe["node"])
		"block":
			hero_st["block"] += 12
			_play_fx("shield", _entity)
		"energy":
			energy_left += 2
		"strength":
			hero_st["str"] += 2
			_play_fx("buff", _entity)
		"heal":
			_health.heal(15)
			_play_fx("heal", _entity)
		"swift":
			_draw_cards(3)
	Sfx.play("pickup", 0.05, -4.0, 1.3)
	_after_action()
	return true


# --- fights ---------------------------------------------------------------------------------

func begin_fight(kind: String) -> void:
	_fight_kind = kind
	for f in foe_list:
		if is_instance_valid(f["node"]):
			f["node"].queue_free()
	foe_list.clear()
	var picks: Array[Dictionary] = []
	var normals := _foe_types.filter(func(t: Dictionary) -> bool: return t["tier"] == "normal")
	var elites := _foe_types.filter(func(t: Dictionary) -> bool: return t["tier"] == "elite")
	var bosses := _foe_types.filter(func(t: Dictionary) -> bool: return t["tier"] == "boss")
	if normals.is_empty():
		normals = _foe_types.duplicate()
	var grow := 1.0 + 0.08 * maxi(0, floor_index)
	if kind == "boss" and not bosses.is_empty():
		picks.append(_scaled(bosses[0], 1.0))
	elif kind == "elite":
		if not elites.is_empty():
			picks.append(_scaled(elites[_rng.randi() % elites.size()], grow))
		else:
			var t: Dictionary = normals[_rng.randi() % normals.size()]
			picks.append(_scaled(t, grow * 2.2))
	else:
		var count := 1 if floor_index < 2 else 1 + int(_rng.randf() < 0.6)
		for i in count:
			picks.append(_scaled(normals[_rng.randi() % normals.size()], grow))
	var x := 0.0
	for p in picks:
		var at := _entity.global_position + foe_offset + Vector2(x, 0)
		var node: Node2D = spawner.call(p["type"], at) if spawner.is_valid() else World.spawn(p["type"], at, {"sp_team": "enemy"})
		x += foe_gap * (1.4 if p["tier"] == "boss" else 1.0)
		if node == null:
			continue
		var h := SP.component(node, &"Health") as HealthComponent
		if h:
			h.max_health = p["hp"]
			h.current = p["hp"]
			h.invincibility_time = 0.0
		SP.face(node, Vector2.LEFT, false)
		var st := {}
		for k in STATUS_KEYS:
			st[k] = 0
		foe_list.append({"node": node, "type": p["type"], "tier": p["tier"], "intents": p["intents"],
			"step": 0, "st": st})
	target = 0
	draw_pile = deck.duplicate()
	_shuffle(draw_pile)
	hand.clear()
	discard.clear()
	for k in STATUS_KEYS:
		hero_st[k] = 0
	_turn = 0
	if "anchor" in relics:
		hero_st["block"] = 10
	if "vajra" in relics:
		hero_st["str"] = 1
	if "marbles" in relics:
		for f in foe_list:
			f["st"]["vuln"] = 1
	if "vial" in relics:
		_health.heal(2)
	fight_started.emit(kind)
	if kind == "boss":
		_boss_intro(picks[0]["type"])
	_start_turn()


func _scaled(t: Dictionary, k: float) -> Dictionary:
	var d := t.duplicate()
	d["hp"] = maxi(1, int(round(t["hp"] * k)))
	return d


func _shuffle(a: Array[String]) -> void:
	for i in range(a.size() - 1, 0, -1):
		var j := _rng.randi() % (i + 1)
		var tmp := a[i]
		a[i] = a[j]
		a[j] = tmp


func foes_alive() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for f in foe_list:
		if not is_instance_valid(f["node"]):
			continue
		var n: Node = f["node"]
		if not n.is_queued_for_deletion():
			var c := SP.core(n)
			if c == null or not c.dead:
				out.append(f)
	return out


func set_target(i: int) -> void:
	var alive := foes_alive()
	if alive.is_empty():
		return
	target = clampi(i, 0, alive.size() - 1)


func _start_turn() -> void:
	phase = "fight"
	_turn += 1
	if _turn > 1 or "anchor" not in relics:
		hero_st["block"] = 0
	if hero_st["poison"] > 0:
		_lose_hp(_entity, hero_st, hero_st["poison"], Color("#7cf07c"))
		hero_st["poison"] -= 1
		if phase == "done":
			return
	energy_left = energy + (1 if _turn == 1 and "lantern" in relics else 0) + (1 if _turn % 3 == 0 and "flower" in relics else 0)
	_draw_cards(hand_size + (2 if _turn == 1 and "snake_ring" in relics else 0))
	_banner("Your Turn", GOLD, 0.35)
	_deal_next = true
	_refresh_ui()


func _draw_cards(n: int) -> void:
	for i in n:
		if draw_pile.is_empty():
			if discard.is_empty():
				return
			draw_pile = discard.duplicate()
			discard.clear()
			_shuffle(draw_pile)
		if hand.size() >= 10:
			return
		hand.append(draw_pile.pop_back())


## Plays the card at [param i] in the hand on the selected foe. Returns false when it cannot be played.
func play_index(i: int) -> bool:
	if phase != "fight" or _busy or i < 0 or i >= hand.size():
		return false
	var c := card(hand[i])
	if c.is_empty() or c["cost"] > energy_left:
		if not c.is_empty():
			GameState.message("Not enough energy")
		return false
	var alive := foes_alive()
	if alive.is_empty():
		return false
	target = clampi(target, 0, alive.size() - 1)
	var foe: Dictionary = alive[target]
	energy_left -= c["cost"]
	var card_name: String = hand[i]
	hand.remove_at(i)
	var hits := maxi(1, _fx(c, "hits"))
	var hit_fx: String = ICON_FX.get(c["icon"], "slash")
	if c["type"] == "attack":
		_lunge(_entity, 1.0)
	_fly_card(i, card_name)
	for e: Array in c["fx"]:
		var v: int = e[1]
		match e[0]:
			"dmg":
				for h in hits:
					if is_instance_valid(foe["node"]):
						_play_fx(hit_fx, foe["node"], h * 0.12)
						deal(hero_st, foe["node"], foe["st"], v)
			"all":
				for f in alive:
					_play_fx(hit_fx if hit_fx != "slash" else "hit", f["node"])
					deal(hero_st, f["node"], f["st"], v)
			"blk":
				v += 1 if "stone" in relics else 0
				hero_st["block"] += v
				_pop(_entity, "+%d" % v, Color("#9ee8ff"), "shield")
				_play_fx("shield", _entity)
				Sfx.play("pickup", 0.05, -6.0, 0.8)
			"draw":
				_draw_cards(v)
			"nrg":
				energy_left += v
			"heal":
				_health.heal(v)
				_pop(_entity, "+%d" % v, Color("#7cf07c"))
				_play_fx("heal", _entity)
			"poison", "weak", "vuln":
				foe["st"][e[0]] += v
				_play_fx("poison" if e[0] == "poison" else "curse", foe["node"], 0.1)
				_pop(foe["node"], "+%d" % v, STATUS_COLOR[e[0]], STATUS_ICON[e[0]])
			"str":
				hero_st["str"] += v
				_pop(_entity, "+%d" % v, STATUS_COLOR["str"], "flex")
				_play_fx("buff", _entity)
	if _fx(c, "exhaust") == 0 and c["type"] != "power":
		discard.append(card_name)
	card_played.emit(card_name)
	_after_action()
	return true


## Deals [param base] damage from someone with statuses [param from_st] to [param node]. Returns the HP lost.
func deal(from_st: Dictionary, node: Node, to_st: Dictionary, base: int) -> int:
	if node == null or not is_instance_valid(node):
		return 0
	var amount := base + int(from_st.get("str", 0))
	if from_st.get("weak", 0) > 0:
		amount = int(floor(amount * 0.75))
	if to_st.get("vuln", 0) > 0:
		amount = int(floor(amount * 1.5))
	amount = maxi(0, amount)
	var blocked := mini(int(to_st.get("block", 0)), amount)
	to_st["block"] = int(to_st.get("block", 0)) - blocked
	amount -= blocked
	if blocked > 0:
		_pop(node, "-%d" % blocked, Color("#9ee8ff"), "shield", 0.0, -1.0)
	if amount > 0:
		_lose_hp(node, to_st, amount, Color.WHITE)
	elif blocked > 0:
		Sfx.play("hit", 0.08, -4.0, 1.4)
	return amount


func _lose_hp(node: Node, _st: Dictionary, amount: int, color: Color) -> void:
	var h := SP.component(node, &"Health") as HealthComponent
	if h == null:
		return
	h.damage(amount)
	_pop(node, str(amount) + ("!" if amount >= 10 else ""), color, "", 0.05, 1.0, amount >= 10)
	if amount >= 15 and pace > 0.0:  # a big hit: a flash and a moment's freeze
		_flash(0.35)
		FX.hitstop(0.06)
	FX.shake(0.12 + minf(amount, 20) * 0.012)
	Sfx.play("hit")


func _after_action() -> void:
	if phase == "done":
		return
	if foes_alive().is_empty():
		_fight_over.call_deferred()
		return
	set_target(target)
	_refresh_ui()


func _fight_over() -> void:
	if phase != "fight" and phase != "foe_turn":
		return
	phase = "won_fight"
	hand.clear()
	_refresh_ui()
	if pace > 0.0:
		await get_tree().create_timer(pace * 2.0).timeout
	fight_won.emit(floor_index + 1)
	_banner("Victory!", GOLD, 0.6)
	if "burning_blood" in relics:
		_health.heal(6)
		_play_fx("heal", _entity)
	if _fight_kind == "boss":
		phase = "done"
		_add_gold(3)
		won.emit()
		return
	var lines: PackedStringArray = ["+%d gold" % _add_gold(2.0 if _fight_kind == "elite" else 1.0)]
	if potions.size() < SPCardContent.MAX_POTIONS and _rng.randf() < 0.4:
		var p: String = SPCardContent.POTIONS.keys()[_rng.randi() % SPCardContent.POTIONS.size()]
		potions.append(p)
		lines.append("Potion: %s" % SPCardContent.POTIONS[p]["name"])
	if _fight_kind == "elite":
		var r := _random_relic()
		_gain_relic(r)
		lines.append("Relic: %s" % SPCardContent.RELICS[r]["name"])
	_offer_cards("Victory!", _fight_kind == "elite", "   ".join(lines))


func end_turn() -> void:
	if phase != "fight" or _busy:
		return
	phase = "foe_turn"
	_banner("Enemy Turn", Color("#ff7a6a"), 0.25)
	discard.append_array(hand)
	hand.clear()
	_tick_down(hero_st)
	_refresh_ui()
	_busy = true
	for f in foes_alive():
		if pace > 0.0:
			await get_tree().create_timer(pace).timeout
		if phase == "done" or not is_inside_tree():
			_busy = false
			return
		if not is_instance_valid(f["node"]):
			continue
		var st: Dictionary = f["st"]
		st["block"] = 0
		if st["poison"] > 0:
			_lose_hp(f["node"], st, st["poison"], Color("#7cf07c"))
			st["poison"] -= 1
			if f not in foes_alive():
				continue
		_foe_act(f)
		_tick_down(st)
		f["step"] = (f["step"] + 1) % maxi(1, f["intents"].size())
	_busy = false
	if phase == "done":
		return
	if foes_alive().is_empty():
		phase = "fight"
		_fight_over()
		return
	if pace > 0.0:
		await get_tree().create_timer(pace).timeout
	if phase != "done":
		_start_turn()


func _tick_down(st: Dictionary) -> void:
	for k in ["weak", "vuln"]:
		if st[k] > 0:
			st[k] -= 1


## The foe's next move: an Array of [kind, value, hits].
func intent_of(f: Dictionary) -> Array:
	var list: Array = f["intents"]
	return list[f["step"] % list.size()] if not list.is_empty() else []


func _foe_act(f: Dictionary) -> void:
	var node: Node2D = f["node"]
	var st: Dictionary = f["st"]
	for m: Array in intent_of(f):
		match m[0]:
			"atk":
				_lunge(node, -1.0)
				for h in m[2]:
					if phase != "done":
						_play_fx("slash", _entity, h * 0.12)
						deal(st, _entity, hero_st, m[1])
			"blk":
				st["block"] += m[1]
				_pop(node, "+%d" % m[1], Color("#9ee8ff"), "shield")
				_play_fx("shield", node)
			"str":
				st["str"] += m[1]
				_pop(node, "+%d" % m[1], STATUS_COLOR["str"], "flex")
				_play_fx("buff", node)
			"heal":
				var h := SP.component(node, &"Health") as HealthComponent
				if h:
					h.heal(m[1])
					_play_fx("heal", node)
			"weak", "vuln", "poison":
				hero_st[m[0]] += m[1]
				_play_fx("poison" if m[0] == "poison" else "curse", _entity)
				_pop(_entity, "+%d" % m[1], STATUS_COLOR[m[0]], STATUS_ICON[m[0]])


func _lunge(node: Node2D, dir: float) -> void:
	var anim := SP.component(node, &"Animator") as AnimatorComponent
	if anim:
		anim.play_attack()
	var shape := node.get_node_or_null(^"Visual") as Node2D
	if shape == null or pace <= 0.0:
		return
	var t := shape.create_tween()
	t.tween_property(shape, ^"position:x", 26.0 * dir, 0.08).set_ease(Tween.EASE_OUT)
	t.tween_property(shape, ^"position:x", 0.0, 0.16).set_ease(Tween.EASE_IN_OUT)


## One sensible move for bots and recordings: pick a room or card, play a card, or end the turn.
func autopilot_step() -> void:
	if _busy:
		return
	match phase:
		"map":  # rest when hurt, take on elites when healthy, otherwise rooms that pay
			var hp := float(_health.current) / _health.max_health
			var want := {"rest": 6.0 if hp < 0.55 else 0.5, "elite": 4.0 if hp > 0.75 else -2.0, "treasure": 5.0,
				"shop": 3.0 if GameState.score >= _price("common") else 0.0, "event": 2.0, "fight": 2.5, "boss": 1.0}
			var best := 0
			for i in options.size():
				var k: String = run_map[floor_index][options[i]]["kind"]
				var kb: String = run_map[floor_index][options[best]]["kind"]
				if want.get(k, 0.0) > want.get(kb, 0.0):
					best = i
			choose(best)
		"reward":
			if deck.size() > 22:
				skip_reward()
			else:
				choose(0)
		"rest":
			choose(0 if _health.current < _health.max_health * 0.7 or _upgradable().is_empty() else 1)
		"shop":
			for i in options.size():
				var item: Array = options[i]
				if item[0] in ["card", "relic"] and GameState.score >= item[2]:
					choose(i)
					return
			skip_reward()
		"event":
			choose(0)
		"notice":
			choose(0)
		"pick":
			var best := 0
			for i in options.size():  # upgrade an attack, remove a basic card
				var c := card(options[i])
				if (_pick_mode == "remove" and c["rarity"] == "starter") or (_pick_mode == "upgrade" and c["type"] == "attack"):
					best = i
					break
			choose(best)
		"fight":
			var incoming := 0
			for f in foes_alive():
				for m: Array in intent_of(f):
					if m[0] == "atk":
						incoming += (m[1] + int(f["st"]["str"])) * m[2]
			var pick := -1
			for i in hand.size():
				var c := card(hand[i])
				if c["cost"] > energy_left:
					continue
				var defensive := _fx(c, "blk") > 0
				if pick < 0:
					pick = i
				elif defensive and incoming > hero_st["block"]:
					pick = i
					break
				elif not defensive and _fx(card(hand[pick]), "blk") > 0 and incoming <= hero_st["block"]:
					pick = i
			if not potions.is_empty() and (_health.current < _health.max_health * 0.4 or _fight_kind == "boss"):
				use_potion(0)
				return
			if pick < 0:
				end_turn()
				return
			var alive := foes_alive()
			var low := 0
			for i in alive.size():
				var h := SP.component(alive[i]["node"], &"Health") as HealthComponent
				var hl := SP.component(alive[low]["node"], &"Health") as HealthComponent
				if h and hl and h.current < hl.current:
					low = i
			set_target(low)
			play_index(pick)


# --- input ----------------------------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var k := (event as InputEventKey).keycode
		if k >= KEY_1 and k <= KEY_9:
			if phase == "fight":
				play_index(k - KEY_1)
			else:
				choose(k - KEY_1)
		elif k == KEY_TAB and phase == "fight":
			set_target((target + 1) % maxi(1, foes_alive().size()))
			_refresh_ui()
		elif k in [KEY_E, KEY_SPACE] and phase == "fight":
			end_turn()
		elif k == KEY_S and phase in ["reward", "shop", "pick", "notice"]:
			skip_reward()
		elif k == KEY_D:
			view_deck()
	elif event is InputEventMouseButton and event.pressed and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		if phase != "fight":
			return
		var world := _entity.get_global_mouse_position()
		var alive := foes_alive()
		for i in alive.size():
			if _body_rect(alive[i]["node"]).grow(16).has_point(world):
				set_target(i)
				_refresh_ui()
				return


# --- drawing --------------------------------------------------------------------------------

## Where an entity's picture is on screen (global): its sprite frame, or its collision shape.
func _body_rect(n: Node2D) -> Rect2:
	var s := n.get_node_or_null(^"Visual/Shape/Sprite") as AnimatedSprite2D
	if s and s.sprite_frames and s.sprite_frames.has_animation(s.animation):
		var tex := s.sprite_frames.get_frame_texture(s.animation, 0)
		if tex:
			var sz := tex.get_size()
			var local := s.offset - (sz / 2.0 if s.centered else Vector2.ZERO)
			var a := s.global_transform * local
			var b := s.global_transform * (local + sz)
			return Rect2(Vector2(minf(a.x, b.x), minf(a.y, b.y)), (b - a).abs())
	var half := SP.half_size(n)
	return Rect2(n.global_position - half, half * 2.0)


func _art(file: String) -> Texture2D:
	if not _tex.has(file):
		var path := "res://sprites/art_%s.png" % file
		_tex[file] = load(path) if ResourceLoader.exists(path) else null
	return _tex[file]


func _icon(icon_name: String) -> Texture2D:
	return _art("ci_" + icon_name)


func _frame(kind: String) -> Texture2D:
	return _art("frame_" + kind)


func _load_fonts() -> void:
	for pair in [["res://sprites/pixel_font.fnt", "_font"], ["res://sprites/pixel_font_plain.fnt", "_font_plain"]]:
		if ResourceLoader.exists(pair[0]):
			var f := load(pair[0]) as FontFile
			if f:
				f.fixed_size_scale_mode = TextServer.FIXED_SIZE_SCALE_INTEGER_ONLY
				set(pair[1], f)
	if _font == null:
		_font = ThemeDB.fallback_font
	if _font_plain == null:
		_font_plain = _font


func _process(_delta: float) -> void:
	if _view and is_instance_valid(_view):
		_view.queue_redraw()
	_update_vignette()
	if _hero_bar:
		_hero_bar.queue_redraw()
		_gold_label.text = str(GameState.score)


func _text(c: CanvasItem, at: Vector2, text: String, size: int, color := Color.WHITE, width := -1.0,
		align := HORIZONTAL_ALIGNMENT_LEFT) -> void:
	c.draw_string(_font, at, text, align, width, size, color)


func _draw_world() -> void:
	if _health and _health.current > 0:
		_draw_bars(_entity, _health.current, _health.max_health, hero_st)
	if phase not in ["fight", "foe_turn", "won_fight"]:
		return
	var alive := foes_alive()
	for i in alive.size():
		var f: Dictionary = alive[i]
		var n: Node2D = f["node"]
		var h := SP.component(n, &"Health") as HealthComponent
		if h == null:
			continue
		_draw_bars(n, h.current, h.max_health, f["st"])
		var r := _body_rect(n)
		var top := Vector2(r.get_center().x, r.position.y + 6)
		_draw_intent(f, top)
		if i == target and phase == "fight":
			var p := top + Vector2(0, -34 + sin(Time.get_ticks_msec() / 160.0) * 3.0)
			for k in 6:  # a pixel arrow
				_view.draw_rect(Rect2(p.x - 6 + k, p.y - 6 + k, 12 - k * 2, 1), GOLD)
			_view.draw_rect(Rect2(p.x - 7, p.y - 7, 14, 1), INK)


func _draw_bars(n: Node2D, cur: int, top: int, st: Dictionary) -> void:
	var w := 96.0
	var r := _body_rect(n)
	var p := Vector2(round(r.get_center().x - w / 2.0), round(maxf(r.end.y, n.global_position.y) + 6))
	_bar(_view, p, w, cur, top, Color("#e8383a"))
	if st.get("block", 0) > 0:  # the block badge: a shield with the number on it
		var tex := _icon("shield")
		var b := p + Vector2(-20, -5)
		if tex:
			_view.draw_texture_rect(tex, Rect2(b, Vector2(22, 22)), false)
		_text(_view, b + Vector2(0, 15), str(st["block"]), 9, Color.WHITE, 22, HORIZONTAL_ALIGNMENT_CENTER)
	var x := p.x
	for k in ["str", "poison", "weak", "vuln"]:
		if st.get(k, 0) > 0:
			var tex := _icon(STATUS_ICON[k])
			if tex:
				_view.draw_texture_rect(tex, Rect2(Vector2(x, p.y + 16), Vector2(16, 16)), false)
			_text(_view, Vector2(x + 12, p.y + 33), str(st[k]), 9, STATUS_COLOR[k])
			x += 26


## A framed health bar with the numbers inside it.
func _bar(c: CanvasItem, p: Vector2, w: float, cur: int, top: int, color: Color) -> void:
	c.draw_rect(Rect2(p - Vector2(3, 3), Vector2(w + 6, 18)), INK)
	c.draw_rect(Rect2(p - Vector2(1, 1), Vector2(w + 2, 14)), Color("#4a3040"))
	c.draw_rect(Rect2(p, Vector2(w, 12)), Color("#3a1420"))
	var fill := w * clampf(float(cur) / maxf(1, top), 0, 1)
	c.draw_rect(Rect2(p, Vector2(fill, 12)), color)
	c.draw_rect(Rect2(p, Vector2(fill, 3)), color.lightened(0.35))
	c.draw_rect(Rect2(p + Vector2(0, 10), Vector2(fill, 2)), color.darkened(0.3))
	_text(c, p + Vector2(0, 10), "%d/%d" % [cur, top], 9, Color.WHITE, w, HORIZONTAL_ALIGNMENT_CENTER)


## The foe's next move in a dark badge above its head (icon and number, like the reference games).
func _draw_intent(f: Dictionary, at: Vector2) -> void:
	var items := []
	for m: Array in intent_of(f):
		var icon_name: String = {"atk": "sword", "blk": "shield", "str": "flex", "heal": "heart", "poison": "drop",
			"weak": "skull", "vuln": "crack"}.get(m[0], "skull")
		var text := ""
		if m[0] == "atk":
			var amount: int = m[1] + int(f["st"]["str"])
			if f["st"]["weak"] > 0:
				amount = int(floor(amount * 0.75))
			if hero_st["vuln"] > 0:
				amount = int(floor(amount * 1.5))
			text = str(amount) + ("x%d" % m[2] if m[2] > 1 else "")
		elif m[0] in ["blk", "heal"]:
			text = str(m[1])
		items.append([icon_name, text])
	var widths := []
	var total := 6.0
	for it: Array in items:
		var tw: float = _font.get_string_size(it[1], HORIZONTAL_ALIGNMENT_LEFT, -1, 18).x if it[1] != "" else 0.0
		widths.append(24.0 + tw)
		total += 24.0 + tw + 4.0
	var box := Rect2(Vector2(round(at.x - total / 2.0), at.y - 30), Vector2(round(total), 26))
	_view.draw_rect(box.grow(2), INK)
	_view.draw_rect(box, Color("#2a2438"))
	_view.draw_rect(Rect2(box.position, Vector2(box.size.x, 2)), Color("#4a4060"))
	var x := box.position.x + 4
	for k in items.size():
		var it: Array = items[k]
		var tex := _icon(it[0])
		if tex:
			_view.draw_texture_rect(tex, Rect2(Vector2(x, box.position.y + 1), Vector2(24, 24)), false)
		if it[1] != "":
			_text(_view, Vector2(x + 24, box.position.y + 20), it[1], 18, Color.WHITE)
		x += widths[k] + 4


## Plays a skill effect (a strip from sprites/fx.py) over a fighter.
func _play_fx(effect: String, node: Node, delay := 0.0) -> void:
	var tex := _art("fx_" + effect)
	if tex == null or node == null or not is_instance_valid(node) or not is_inside_tree():
		return
	var at := _body_rect(node as Node2D).get_center()
	var s := Sprite2D.new()
	s.texture = tex
	s.hframes = maxi(1, int(tex.get_width() / tex.get_height()))
	s.scale = Vector2(2, 2)
	s.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	s.z_index = 40
	s.global_position = at
	s.visible = delay <= 0.0
	_view.get_parent().add_child(s)
	var t := s.create_tween()
	if delay > 0.0:
		t.tween_interval(delay)
		t.tween_callback(func() -> void: s.visible = true)
	t.tween_property(s, ^"frame", s.hframes - 1, maxf(0.05, 0.07 * s.hframes)).from(0)
	t.tween_callback(s.queue_free)


## A number popping out of a fighter (damage, block, statuses), with an icon when given.
func _pop(node: Node, text: String, color: Color, icon_name := "", delay := 0.0, side := 1.0, big := false) -> void:
	if node == null or not is_instance_valid(node) or not is_inside_tree() or _view == null:
		return
	var r := _body_rect(node as Node2D)
	var holder := Node2D.new()
	holder.z_index = 60
	holder.global_position = Vector2(r.get_center().x + side * randf_range(-6, 14), r.position.y + r.size.y * 0.3)
	var l := Label.new()
	l.text = text
	l.add_theme_font_override(&"font", _font)
	l.add_theme_font_size_override(&"font_size", 36 if big else 27)
	l.add_theme_color_override(&"font_color", color)
	l.position = Vector2(0, -20)
	holder.add_child(l)
	var tex := _icon(icon_name) if icon_name != "" else null
	if tex:
		var ic := Sprite2D.new()
		ic.texture = tex
		ic.scale = Vector2(2, 2)
		ic.position = Vector2(-18, -2)
		holder.add_child(ic)
	holder.visible = delay <= 0.0
	_view.get_parent().add_child(holder)
	holder.scale = Vector2(1.6, 1.6)
	var t := holder.create_tween()
	if delay > 0.0:
		t.tween_interval(delay)
		t.tween_callback(func() -> void: holder.visible = true)
	t.tween_property(holder, ^"scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	t.parallel().tween_property(holder, ^"position:y", holder.position.y - 36, 0.8).set_ease(Tween.EASE_OUT)
	t.tween_property(holder, ^"modulate:a", 0.0, 0.3)
	t.tween_callback(holder.queue_free)


# --- screen UI ------------------------------------------------------------------------------

func _label(size: int, color := Color.WHITE, plain := false) -> Label:
	var l := Label.new()
	l.add_theme_font_override(&"font", _font_plain if plain else _font)
	l.add_theme_font_size_override(&"font_size", size)
	l.add_theme_color_override(&"font_color", color)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _box_style(bg: Color, border: Color, width := 3) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(width)
	s.set_content_margin_all(8)
	s.anti_aliasing = false
	return s


func _button(text: String, color := Color("#e8902a")) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	b.add_theme_font_override(&"font", _font_plain)
	b.add_theme_font_size_override(&"font_size", 18)
	for st in [["normal", color], ["hover", color.lightened(0.18)], ["pressed", color.darkened(0.2)],
			["disabled", Color("#5a5468")]]:
		var sb := _box_style(st[1], INK, 3)
		sb.shadow_color = Color(0, 0, 0, 0.35)
		sb.shadow_offset = Vector2(0, 4)
		sb.shadow_size = 1
		b.add_theme_stylebox_override(StringName(st[0]), sb)
	for c in [&"font_color", &"font_hover_color", &"font_pressed_color"]:
		b.add_theme_color_override(c, INK)
	b.add_theme_color_override(&"font_disabled_color", Color("#2a2438"))
	return b


func _panel_box(at: Vector2, size: Vector2) -> Panel:
	var p := Panel.new()
	var sb := _box_style(Color("#1c2833"), Color("#0b1016"), 3)
	sb.border_blend = false
	p.add_theme_stylebox_override(&"panel", sb)
	p.position = at
	p.size = size
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return p


func _build_ui() -> void:
	_load_fonts()
	GameState.set_var("hud_hidden", true)
	_ui = CanvasLayer.new()
	_ui.layer = 20
	add_child(_ui)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(root)
	# the hero's panel: portrait, name, HP and gold
	var hero := _panel_box(Vector2(10, 10), Vector2(258, 74))
	root.add_child(hero)
	var frame := _panel_box(Vector2(6, 6), Vector2(62, 62))
	(frame.get_theme_stylebox(&"panel") as StyleBoxFlat).bg_color = Color("#2c3e4c")
	hero.add_child(frame)
	_portrait = TextureRect.new()
	_portrait.position = Vector2(9, 9)
	_portrait.size = Vector2(56, 56)
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	hero.add_child(_portrait)
	var name_label := _label(18)
	name_label.text = hero_name
	name_label.position = Vector2(78, 6)
	hero.add_child(name_label)
	_hero_bar = Control.new()
	_hero_bar.position = Vector2(80, 32)
	_hero_bar.size = Vector2(168, 18)
	_hero_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hero_bar.draw.connect(func() -> void:
		if _health:
			_bar(_hero_bar, Vector2(3, 3), 162, _health.current, _health.max_health, Color("#e8383a")))
	hero.add_child(_hero_bar)
	var coin := TextureRect.new()
	coin.texture = _icon("coin")
	coin.position = Vector2(78, 52)
	coin.size = Vector2(16, 16)
	coin.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	hero.add_child(coin)
	_gold_label = _label(18, GOLD)
	_gold_label.position = Vector2(98, 50)
	hero.add_child(_gold_label)
	_floor_label = _label(18, Color("#d8d0e8"))
	_floor_label.position = Vector2(160, 50)
	hero.add_child(_floor_label)
	_belt = HBoxContainer.new()
	_belt.position = Vector2(12, 90)
	_belt.add_theme_constant_override(&"separation", 4)
	root.add_child(_belt)
	# the hand, the energy orb, the piles and the end turn button
	_hand_root = Control.new()
	_hand_root.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_hand_root.offset_top = -178
	_hand_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_hand_root)
	var bottom_left := Control.new()
	bottom_left.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	bottom_left.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(bottom_left)
	_draw_back = _pile(bottom_left, Vector2(18, -66))
	var orb := Panel.new()
	var orb_style := _box_style(Color("#e8902a"), INK, 4)
	orb_style.set_corner_radius_all(32)
	orb_style.border_color = INK
	orb.add_theme_stylebox_override(&"panel", orb_style)
	orb.position = Vector2(26, -170)
	orb.size = Vector2(64, 64)
	orb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bottom_left.add_child(orb)
	var shine := Panel.new()
	var shine_style := _box_style(Color("#ffd88a"), Color("#ffd88a"), 0)
	shine_style.set_corner_radius_all(6)
	shine.add_theme_stylebox_override(&"panel", shine_style)
	shine.position = Vector2(14, 10)
	shine.size = Vector2(12, 8)
	shine.mouse_filter = Control.MOUSE_FILTER_IGNORE
	orb.add_child(shine)
	_energy_label = _label(27, Color.WHITE)
	_energy_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_energy_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_energy_label.size = Vector2(64, 64)
	orb.add_child(_energy_label)
	_pile_label = _label(18, Color("#e8e0f0"))
	_pile_label.position = Vector2(14, -92)
	bottom_left.add_child(_pile_label)
	var bottom_right := Control.new()
	bottom_right.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	bottom_right.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(bottom_right)
	_discard_back = _pile(bottom_right, Vector2(-100, -66))
	_discard_label = _label(18, Color("#e8e0f0"))
	_discard_label.position = Vector2(-128, -92)
	bottom_right.add_child(_discard_label)
	_end_button = _button("End Turn", Color("#e8502a"))
	_end_button.position = Vector2(-164, -158)
	_end_button.size = Vector2(150, 50)
	_end_button.pressed.connect(end_turn)
	bottom_right.add_child(_end_button)
	# the panel: the map and rewards
	_panel = ColorRect.new()
	(_panel as ColorRect).color = Color(0.05, 0.06, 0.1, 0.84)
	_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	_panel.visible = false
	root.add_child(_panel)
	var col := VBoxContainer.new()
	col.set_anchors_preset(Control.PRESET_CENTER)
	col.grow_horizontal = Control.GROW_DIRECTION_BOTH
	col.grow_vertical = Control.GROW_DIRECTION_BOTH
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_theme_constant_override(&"separation", 20)
	_panel.add_child(col)
	_panel_title = _label(36, GOLD)
	_panel_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(_panel_title)
	_panel_body = VBoxContainer.new()
	_panel_body.alignment = BoxContainer.ALIGNMENT_CENTER
	_panel_body.add_theme_constant_override(&"separation", 16)
	col.add_child(_panel_body)
	_panel_hint = _label(18, Color("#d8d0e8"))
	_panel_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(_panel_hint)
	_build_vignette(root)
	_set_portrait.call_deferred()


func _pile(parent: Control, at: Vector2) -> TextureRect:
	var t := TextureRect.new()
	t.texture = _art("card_back")
	t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	t.position = at
	t.size = Vector2(80, 112)
	t.stretch_mode = TextureRect.STRETCH_SCALE
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(t)
	return t


func _set_portrait() -> void:
	var s := _entity.get_node_or_null(^"Visual/Shape/Sprite") as AnimatedSprite2D
	if s == null or s.sprite_frames == null or not s.sprite_frames.has_animation(&"idle"):
		return
	var tex := s.sprite_frames.get_frame_texture(&"idle", 0)
	if tex == null:
		return
	var a := AtlasTexture.new()
	a.atlas = tex
	var w := float(tex.get_width())
	var side := minf(w, tex.get_height() * 0.62)
	a.region = Rect2(round((w - side) / 2.0), 0, round(side), round(side))  # the head and shoulders
	_portrait.texture = a


func _panel_open(title: String, hint: String) -> void:
	_refresh_ui()
	_panel_title.text = title
	_panel_hint.text = hint
	for c in _panel_body.get_children():
		c.queue_free()
	_panel.visible = true


func _row(sep := 24) -> HBoxContainer:
	var r := HBoxContainer.new()
	r.alignment = BoxContainer.ALIGNMENT_CENTER
	r.add_theme_constant_override(&"separation", sep)
	_panel_body.add_child(r)
	return r


## The map: a parchment with the floors left to right, the links as dotted lines, the path walked in gold and
## the rooms that can be entered now as pulsing buttons.
func _show_map() -> void:
	_panel_open("Floor %d of %d: choose a room" % [floor_index + 1, floors],
		"Click a glowing room, or press 1-%d" % options.size())
	var map := Control.new()
	map.custom_minimum_size = Vector2(840, 330)
	map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel_body.add_child(map)
	var pos := func(f: int, lane: float) -> Vector2:
		return Vector2(60 + f * 720.0 / maxf(1, floors - 1), 50 + lane * 76)
	map.draw.connect(func() -> void:
		map.draw_rect(Rect2(Vector2.ZERO, map.custom_minimum_size), Color("#1d1a33"))
		map.draw_rect(Rect2(Vector2(4, 4), map.custom_minimum_size - Vector2(8, 8)), Color("#e8d4a4"))
		map.draw_rect(Rect2(Vector2(10, 10), map.custom_minimum_size - Vector2(20, 20)), Color("#f2e2bc"))
		for f in floors - 1:
			for i in run_map[f].size():
				var a: Vector2 = pos.call(f, run_map[f][i]["lane"])
				for j: int in run_map[f][i]["next"]:
					var b: Vector2 = pos.call(f + 1, run_map[f + 1][j]["lane"])
					var walked: bool = _path.size() > f + 1 and _path[f] == i and _path[f + 1] == j
					var d := a.distance_to(b)
					for k in range(10, int(d) - 10, 7):  # dotted line
						var p := a.lerp(b, k / d)
						map.draw_rect(Rect2(p - Vector2(1.5, 1.5), Vector2(3, 3)),
							Color("#e8902a") if walked else Color("#8a7a5a")))
	for f in floors:
		for i in run_map[f].size():
			var node: Dictionary = run_map[f][i]
			var at: Vector2 = pos.call(f, node["lane"])
			var b := TextureButton.new()
			b.texture_normal = _icon(NODE_ICON.get(node["kind"], "sword"))
			b.ignore_texture_size = true
			b.stretch_mode = TextureButton.STRETCH_SCALE
			b.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			var big := 48.0 if node["kind"] == "boss" else 32.0
			b.size = Vector2(big, big)
			b.position = at - b.size / 2.0
			b.tooltip_text = NODE_NAME.get(node["kind"], node["kind"])
			var idx := options.find(i) if f == floor_index else -1
			if idx >= 0:
				b.pressed.connect(func() -> void: choose(idx))
				b.pivot_offset = b.size / 2.0
				var t := b.create_tween().set_loops()
				t.tween_property(b, ^"scale", Vector2(1.25, 1.25), 0.45)
				t.tween_property(b, ^"scale", Vector2.ONE, 0.45)
			else:
				b.disabled = true
				var done: bool = f < floor_index and _path.size() > f and _path[f] == i
				b.modulate = Color.WHITE if done else Color(0.55, 0.5, 0.45, 0.8 if f > floor_index else 0.45)
			map.add_child(b)
	var legend := _row(14)
	for k in ["fight", "elite", "event", "shop", "rest", "treasure", "boss"]:
		var ic := TextureRect.new()
		ic.texture = _icon(NODE_ICON[k])
		ic.custom_minimum_size = Vector2(16, 16)
		ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		ic.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		legend.add_child(ic)
		var l := _label(9, Color("#d8d0e8"))
		l.text = NODE_NAME[k]
		legend.add_child(l)


## Cards to pick from (rewards, the deck); `picking` lays the deck out in a scrollable grid.
func _show_cards(title: String, hint: String, names: Array, with_skip: bool, picking := false) -> void:
	_panel_open(title, hint)
	var holder: Container
	if picking:
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size = Vector2(860, 340)
		scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		_panel_body.add_child(scroll)
		var grid := GridContainer.new()
		grid.columns = 7
		grid.add_theme_constant_override(&"h_separation", 10)
		grid.add_theme_constant_override(&"v_separation", 10)
		scroll.add_child(grid)
		holder = grid
	else:
		holder = _row()
	for i in names.size():
		var idx := i
		var cv := _card_view(names[i], not picking)
		var glow := _glow(cv.size)
		cv.add_child(glow)
		cv.move_child(glow, 0)
		cv.mouse_entered.connect(func() -> void: glow.visible = true)
		cv.mouse_exited.connect(func() -> void: glow.visible = false)
		cv.gui_input.connect(func(e: InputEvent) -> void:
			if _pressed(e):
				choose(idx))
		holder.add_child(cv)
	if with_skip or picking:
		var s := _button("Skip" if with_skip else ("Close" if _pick_mode == "view" else "Cancel"))
		s.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		s.pressed.connect(skip_reward)
		_panel_body.add_child(s)


## A scene with buttons (rest sites, events, notices); optional icons above the labels.
func _show_choices(title: String, text: String, labels: Array, icons: Array = []) -> void:
	_panel_open(title, "")
	var body := _label(18, Color("#f2e2bc"))
	body.text = text
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.custom_minimum_size = Vector2(620, 0)
	_panel_body.add_child(body)
	var row := _row()
	for i in labels.size():
		var idx := i
		var b := _button(labels[i], Color("#e8d4a4"))
		if i < icons.size():
			b.icon = _icon(icons[i])
			b.expand_icon = true
			b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			b.add_theme_constant_override(&"icon_max_width", 64)
			b.custom_minimum_size = Vector2(220, 150)
		else:
			b.custom_minimum_size = Vector2(0, 50)
		b.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		b.pressed.connect(func() -> void: choose(idx))
		row.add_child(b)


func _show_shop() -> void:
	_panel_open("Shop", "Gold: %d   (click to buy, Leave when done)" % GameState.score)
	var cards_row := _row(14)
	var other_row := _row(18)
	for i in options.size():
		var item: Array = options[i]
		var idx := i
		var can := GameState.score >= int(item[2])
		var box := VBoxContainer.new()
		box.alignment = BoxContainer.ALIGNMENT_CENTER
		var price := _label(18, GOLD if can else Color("#a09080"))
		price.text = "%d g" % item[2]
		price.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		if item[0] == "card":
			var cv := _card_view(item[1])
			cv.gui_input.connect(func(e: InputEvent) -> void:
				if _pressed(e):
					choose(idx))
			if not can:
				cv.modulate = Color(0.65, 0.65, 0.7)
			box.add_child(cv)
			box.add_child(price)
			cards_row.add_child(box)
			continue
		var label: String = {"relic": "", "potion": "", "remove": "Remove a card"}[item[0]]
		var b := _button(label if item[0] == "remove" else (SPCardContent.RELICS[item[1]]["name"] if item[0] == "relic"
			else SPCardContent.POTIONS[item[1]]["name"]), Color("#e8d4a4"))
		if item[0] == "relic":
			b.icon = _icon(SPCardContent.RELICS[item[1]]["icon"])
			b.tooltip_text = SPCardContent.RELICS[item[1]]["text"]
		elif item[0] == "potion":
			b.icon = _icon("potion")
			b.tooltip_text = SPCardContent.POTIONS[item[1]]["text"]
			b.add_theme_color_override(&"icon_normal_color", Color(SPCardContent.POTIONS[item[1]]["color"]))
		b.expand_icon = item[0] != "remove"
		b.add_theme_constant_override(&"icon_max_width", 32)
		b.disabled = not can
		b.pressed.connect(func() -> void: choose(idx))
		box.add_child(b)
		box.add_child(price)
		other_row.add_child(box)
	var leave := _button("Leave", Color("#e8502a"))
	leave.pressed.connect(skip_reward)
	other_row.add_child(leave)


## Relics and potions under the hero's panel; the Deck button.
func _refresh_belt() -> void:
	if _belt == null:
		return
	for c in _belt.get_children():
		c.queue_free()
	for r in relics:
		var ic := TextureRect.new()
		ic.texture = _icon(SPCardContent.RELICS[r]["icon"])
		ic.custom_minimum_size = Vector2(32, 32)
		ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		ic.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		ic.tooltip_text = "%s: %s" % [SPCardContent.RELICS[r]["name"], SPCardContent.RELICS[r]["text"]]
		ic.mouse_filter = Control.MOUSE_FILTER_STOP
		_belt.add_child(ic)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(8, 8)
	_belt.add_child(gap)
	for i in SPCardContent.MAX_POTIONS:
		var slot := TextureButton.new()
		slot.custom_minimum_size = Vector2(32, 32)
		slot.ignore_texture_size = true
		slot.stretch_mode = TextureButton.STRETCH_SCALE
		slot.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		if i < potions.size():
			var pd: Dictionary = SPCardContent.POTIONS[potions[i]]
			slot.texture_normal = _icon("potion")
			slot.modulate = Color(pd["color"]).lightened(0.15)
			slot.tooltip_text = "%s: %s (click in a fight)" % [pd["name"], pd["text"]]
			var idx := i
			slot.pressed.connect(func() -> void: use_potion(idx))
		else:
			slot.texture_normal = _icon("potion")
			slot.modulate = Color(0.2, 0.2, 0.25, 0.6)
			slot.disabled = true
		_belt.add_child(slot)
	var deck_button := _button("Deck %d" % deck.size(), Color("#e8d4a4"))
	deck_button.add_theme_font_size_override(&"font_size", 9)
	deck_button.custom_minimum_size = Vector2(0, 30)
	deck_button.pressed.connect(view_deck)
	_belt.add_child(deck_button)


func _hide_panel() -> void:
	_panel.visible = false


func _pressed(e: InputEvent) -> bool:
	return (e is InputEventMouseButton and e.pressed and (e as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT) \
		or (e is InputEventScreenTouch and e.pressed)


func _card_view(card_name: String, big := false) -> Control:
	var c := card(card_name)
	var k := 3.0 if big else 2.0  # screen px per art px of the 56x78 card (sprites/cards.py)
	var size := Vector2(56, 78) * k
	var root := Control.new()
	root.custom_minimum_size = size
	root.size = size
	root.pivot_offset = Vector2(size.x / 2.0, size.y)
	root.mouse_filter = Control.MOUSE_FILTER_STOP
	var frame := _frame(c.get("type", "attack"))
	if frame:
		var fr := TextureRect.new()
		fr.texture = frame
		fr.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		fr.stretch_mode = TextureRect.STRETCH_SCALE
		fr.size = size
		fr.mouse_filter = Control.MOUSE_FILTER_IGNORE
		root.add_child(fr)
	else:
		var bg := Panel.new()
		bg.add_theme_stylebox_override(&"panel", _box_style(TYPE_COLOR.get(c.get("type", "attack"), Color.GRAY), INK, 4))
		bg.size = size
		bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
		root.add_child(bg)
	var icon := TextureRect.new()
	icon.texture = _icon(c.get("icon", "sword"))
	icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	icon.stretch_mode = TextureRect.STRETCH_SCALE
	icon.position = Vector2(20, 18) * k
	icon.size = Vector2(16, 16) * k
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(icon)
	var title := _label(18 if big else 9, Color("#8af07a") if c.get("upgraded", false) else Color.WHITE)
	title.text = card_name
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	title.position = Vector2(5, 43) * k
	title.size = Vector2(46, 10) * k
	title.clip_text = true
	root.add_child(title)
	var text := _label(9, INK, true)
	text.text = card_text(card_name)
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	text.position = Vector2(5, 54) * k
	text.size = Vector2(46, 20) * k
	if big:
		text.add_theme_font_size_override(&"font_size", 18)
	root.add_child(text)
	if c.get("rarity", "common") in ["uncommon", "rare"]:  # a silver or gold star on the ribbon's end
		var star := TextureRect.new()
		star.texture = _icon("star")
		star.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		star.stretch_mode = TextureRect.STRETCH_SCALE
		star.size = Vector2(8, 8) * k
		star.position = Vector2(46, 39) * k
		star.modulate = Color.WHITE if c["rarity"] == "rare" else Color(0.75, 0.8, 0.95)
		if c["rarity"] == "uncommon":
			star.self_modulate = Color(0.85, 0.85, 1.0)
		star.mouse_filter = Control.MOUSE_FILTER_IGNORE
		root.add_child(star)
	var cost := _label(18 if not big else 27, Color.WHITE)
	cost.text = str(c.get("cost", 0))
	cost.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cost.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	cost.position = Vector2(1, 1) * k
	cost.size = Vector2(14, 14) * k
	root.add_child(cost)
	return root


## A pulsing gold outline behind a card (the card under the mouse, ready to play).
func _glow(size: Vector2) -> Control:
	var g := Panel.new()
	var sb := _box_style(Color(0, 0, 0, 0), Color("#ffd84a"), 4)
	sb.expand_margin_left = 5
	sb.expand_margin_right = 5
	sb.expand_margin_top = 5
	sb.expand_margin_bottom = 5
	g.add_theme_stylebox_override(&"panel", sb)
	g.size = size
	g.mouse_filter = Control.MOUSE_FILTER_IGNORE
	g.visible = false
	g.show_behind_parent = true
	var t := g.create_tween().set_loops()
	t.tween_property(g, ^"modulate:a", 0.45, 0.4)
	t.tween_property(g, ^"modulate:a", 1.0, 0.4)
	return g


## The played card flies up toward the fight and fades.
func _fly_card(index: int, card_name: String) -> void:
	if _hand_root == null or not _hand_root.is_inside_tree() or pace <= 0.0:
		return
	var views := _hand_root.get_children()
	if index >= views.size():
		return
	var from := (views[index] as Control).global_position
	var cv := _card_view(card_name)
	cv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cv.position = from
	_ui.add_child(cv)
	var t := cv.create_tween().set_parallel(true)
	t.tween_property(cv, ^"position", Vector2(from.x * 0.5 + 300, 150), 0.28).set_ease(Tween.EASE_OUT)
	t.tween_property(cv, ^"scale", Vector2(0.6, 0.6), 0.28)
	t.tween_property(cv, ^"modulate:a", 0.0, 0.28).set_delay(0.08)
	t.chain().tween_callback(cv.queue_free)


func _refresh_ui() -> void:
	if _hand_root == null:
		return
	for c in _hand_root.get_children():
		c.queue_free()
	var fighting := phase == "fight"
	var in_fight := phase in ["fight", "foe_turn", "won_fight"]
	_end_button.visible = in_fight
	_end_button.disabled = not fighting
	_energy_label.get_parent().visible = in_fight
	_energy_label.text = "%d/%d" % [energy_left, energy]
	for n: CanvasItem in [_pile_label, _discard_label, _draw_back, _discard_back]:
		n.visible = in_fight
	_pile_label.text = "Draw %d" % draw_pile.size()
	_discard_label.text = "Discard %d" % discard.size()
	_floor_label.text = "Floor %d/%d" % [maxi(1, floor_index + 1), floors]
	_refresh_belt()
	if not fighting:
		return
	var n := hand.size()
	var view_w := _hand_root.size.x if _hand_root.size.x > 0 else 960.0
	var room := view_w - 330.0
	var step := minf(118.0, room / maxf(1, n))
	var x0 := view_w / 2.0 - 20.0 - (step * (n - 1) + 112.0) / 2.0
	var deal := _deal_next
	_deal_next = false
	for i in n:
		var cv := _card_view(hand[i])
		var idx := i
		var mid := i - (n - 1) / 2.0
		var home := Vector2(x0 + i * step, 12 + absf(mid) * absf(mid) * 1.5)
		cv.position = home
		cv.rotation = deg_to_rad(mid * 2.5)
		if card(hand[i]).get("cost", 0) > energy_left:
			cv.modulate = Color(0.62, 0.62, 0.68)
		cv.gui_input.connect(func(e: InputEvent) -> void:
			if _pressed(e):
				play_index(idx))
		var glow := _glow(cv.size)
		cv.add_child(glow)
		cv.move_child(glow, 0)
		cv.mouse_entered.connect(func() -> void:
			glow.visible = card(hand[idx]).get("cost", 0) <= energy_left
			Sfx.play("pickup", 0.05, -14.0, 1.6)
			cv.z_index = 10
			var t := cv.create_tween().set_parallel(true)
			t.tween_property(cv, ^"position:y", home.y - 34, 0.08)
			t.tween_property(cv, ^"scale", Vector2(1.14, 1.14), 0.08)
			t.tween_property(cv, ^"rotation", 0.0, 0.08))
		cv.mouse_exited.connect(func() -> void:
			glow.visible = false
			cv.z_index = 0
			var t := cv.create_tween().set_parallel(true)
			t.tween_property(cv, ^"position:y", home.y, 0.08)
			t.tween_property(cv, ^"scale", Vector2.ONE, 0.08)
			t.tween_property(cv, ^"rotation", deg_to_rad(mid * 2.5), 0.08))
		_hand_root.add_child(cv)
		if deal and pace > 0.0:  # a new turn: the cards fly in from the draw pile
			cv.position = Vector2(20, 120)
			cv.scale = Vector2(0.5, 0.5)
			var t := cv.create_tween().set_parallel(true)
			t.tween_property(cv, ^"position", home, 0.22).set_delay(i * 0.07).set_ease(Tween.EASE_OUT)
			t.tween_property(cv, ^"scale", Vector2.ONE, 0.22).set_delay(i * 0.07)


# --- atmosphere and juice --------------------------------------------------------------------

## theme -> (particle colours, falling speed, sideways drift, count, size)
const AMBIENT := {
	"forest": [["#7cc85a", "#ffd84a", "#4a9a4a"], 30.0, 40.0, 24, 3.0],
	"night": [["#e8ff8a", "#c8ff70"], -6.0, 14.0, 28, 2.0],
	"snow": [["#ffffff", "#e8f4ff"], 40.0, 18.0, 70, 2.0],
	"lava": [["#ffb03a", "#ff6a2a", "#ffd04a"], -45.0, 12.0, 40, 2.0],
	"desert": [["#f0d8a0", "#e8c080"], 6.0, 90.0, 30, 2.0],
	"ocean": [["#bfeaff", "#ffffff"], -20.0, 8.0, 22, 2.0],
	"candy": [["#ff8fc8", "#ffffff", "#5ad8ff"], 22.0, 20.0, 30, 2.0],
	"neon": [["#2de2e6", "#f6019d"], 260.0, 0.0, 50, 1.0],
}


## Drifting pixels over the backdrop: leaves, fireflies, snow, embers, sand, bubbles, sparkles or neon rain.
func _start_ambient() -> void:
	var a: Array = AMBIENT.get(theme, [])
	if a.is_empty() or _view == null:
		return
	var view := Vector2(960, 540)
	for k in a[0].size():
		var p := CPUParticles2D.new()
		p.amount = maxi(1, int(a[3] / a[0].size()))
		p.lifetime = 12.0
		p.preprocess = 12.0
		p.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
		p.emission_rect_extents = view / 2.0
		p.position = view / 2.0
		p.direction = Vector2(a[2], a[1]).normalized() if Vector2(a[2], a[1]).length() > 0.1 else Vector2.DOWN
		p.spread = 25.0
		p.gravity = Vector2.ZERO
		p.initial_velocity_min = Vector2(a[2], a[1]).length() * 0.6
		p.initial_velocity_max = Vector2(a[2], a[1]).length() * 1.2
		p.scale_amount_min = a[4]
		p.scale_amount_max = a[4] * (1.0 if theme == "neon" else 1.5)
		p.color = Color(a[0][k])
		if theme == "neon":
			p.scale_amount_max = 1.0
			p.scale_amount_min = 1.0
			p.texture = _rain_texture()
		if theme in ["night", "ocean"]:  # fireflies and bubbles fade in and out
			var g := Gradient.new()
			g.set_color(0, Color(1, 1, 1, 0))
			g.add_point(0.5, Color(1, 1, 1, 1))
			g.set_color(g.get_point_count() - 1, Color(1, 1, 1, 0))
			p.color_ramp = g
		p.z_index = 5
		p.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_view.get_parent().add_child(p)


func _rain_texture() -> Texture2D:
	var img := Image.create(1, 6, false, Image.FORMAT_RGBA8)
	img.fill(Color.WHITE)
	return ImageTexture.create_from_image(img)


## A banner sliding across the middle of the screen ("Your turn", "Victory!").
func _banner(text: String, color: Color, hold := 0.5) -> void:
	if _ui == null or pace <= 0.0:
		return
	var band := ColorRect.new()
	band.color = Color(0.05, 0.04, 0.1, 0.72)
	band.size = Vector2(2000, 64)
	band.position = Vector2(-2000, 200)
	band.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var l := _label(36, color)
	l.text = text
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	l.size = Vector2(960, 64)
	l.position = Vector2(2000 - 960, 0)
	band.add_child(l)
	_ui.add_child(band)
	var view_w := _hand_root.size.x if _hand_root and _hand_root.size.x > 0 else 960.0
	l.position.x = 2000 - view_w + (view_w - 960) / 2.0
	var t := band.create_tween()
	t.tween_property(band, ^"position:x", -2000 + view_w, 0.22).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	t.tween_interval(hold)
	t.tween_property(band, ^"modulate:a", 0.0, 0.25)
	t.tween_callback(band.queue_free)


## A white flash over everything (big hits).
func _flash(strength := 0.5) -> void:
	if _ui == null or pace <= 0.0:
		return
	var r := ColorRect.new()
	r.color = Color(1, 1, 1, strength)
	r.set_anchors_preset(Control.PRESET_FULL_RECT)
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(r)
	var t := r.create_tween()
	t.tween_property(r, ^"color:a", 0.0, 0.18)
	t.tween_callback(r.queue_free)


## The boss arrives: the screen darkens and its name grows in the middle.
func _boss_intro(boss_name: String) -> void:
	if _ui == null or pace <= 0.0:
		return
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.0)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(shade)
	var l := _label(54, Color("#ff5a4a"))
	l.text = boss_name.to_upper()
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.set_anchors_preset(Control.PRESET_CENTER)
	l.grow_horizontal = Control.GROW_DIRECTION_BOTH
	l.grow_vertical = Control.GROW_DIRECTION_BOTH
	shade.add_child(l)
	l.pivot_offset = l.size / 2.0
	l.scale = Vector2(2.2, 2.2)
	l.modulate.a = 0.0
	var t := shade.create_tween()
	t.tween_property(shade, ^"color:a", 0.6, 0.3)
	t.parallel().tween_property(l, ^"scale", Vector2.ONE, 0.4).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	t.parallel().tween_property(l, ^"modulate:a", 1.0, 0.3)
	t.tween_interval(0.9)
	t.tween_property(shade, ^"modulate:a", 0.0, 0.4)
	t.tween_callback(shade.queue_free)
	FX.shake(0.5)


## A red border that pulses while the hero is low on health.
func _update_vignette() -> void:
	if _vignette == null or _health == null:
		return
	var low := _health.current > 0 and _health.current <= _health.max_health * 0.3 and phase in ["fight", "foe_turn"]
	if low and not _vignette.visible:
		_vignette.visible = true
		_vignette_tween = _vignette.create_tween().set_loops()
		_vignette_tween.tween_property(_vignette, ^"modulate:a", 0.35, 0.6)
		_vignette_tween.tween_property(_vignette, ^"modulate:a", 1.0, 0.6)
	elif not low and _vignette.visible:
		_vignette.visible = false
		if _vignette_tween:
			_vignette_tween.kill()


func _build_vignette(root: Control) -> void:
	_vignette = Control.new()
	_vignette.set_anchors_preset(Control.PRESET_FULL_RECT)
	_vignette.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_vignette.visible = false
	_vignette.draw.connect(func() -> void:
		var s := _vignette.size
		for k in 6:
			var c := Color(0.9, 0.1, 0.15, 0.32 - k * 0.05)
			_vignette.draw_rect(Rect2(k * 4, k * 4, s.x - k * 8, s.y - k * 8), c, false, 4.0))
	root.add_child(_vignette)
