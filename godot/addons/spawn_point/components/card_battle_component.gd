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
	"card_text", "foes_alive", "hand", "phase", "intent_of", "deal", "begin_fight", "set_target"]
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
## The hero's name on its panel.
@export var hero_name: String = "Hero"
## Seconds between foe moves (0 = instant, for tests).
@export_range(0.0, 2.0, 0.01) var pace: float = 0.45
## Map and draw seed (0 = a new run every time).
@export_range(0, 1000000) var run_seed: int = 0

const STATUS_KEYS := ["block", "poison", "weak", "vuln", "str"]
const NODE_ICON := {"fight": "sword", "elite": "skull", "rest": "campfire", "treasure": "chest", "boss": "crown"}
const NODE_NAME := {"fight": "Fight", "elite": "Elite", "rest": "Rest", "treasure": "Treasure", "boss": "Boss"}
const TYPE_COLOR := {"attack": Color("#b8503a"), "skill": Color("#3a8a7a"), "power": Color("#8a4ab8")}
const ICON_FX := {"sword": "slash", "axe": "slash", "dagger": "slash", "bow": "slash", "wind": "slash", "fire": "fire",
	"ice": "ice", "bolt": "bolt", "star": "bolt", "drop": "poison", "staff": "curse", "skull": "curse", "crack": "curse",
	"flex": "buff", "book": "buff", "heart": "heal", "shield": "shield"}
const STATUS_ICON := {"str": "flex", "poison": "drop", "weak": "skull", "vuln": "crack"}
const STATUS_COLOR := {"str": Color("#ffb03a"), "poison": Color("#7cf05a"), "weak": Color("#c8a2ff"), "vuln": Color("#ff8fb4")}
const INK := Color("#1d1a33")
const GOLD := Color("#ffec27")

var phase := "map"  # map, fight, foe_turn, reward, rest, done
var floor_index := -1
var run_map: Array = []  # per floor: an Array of node kinds
var options: Array = []  # what the current panel offers (node kinds or card names)
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
var _panel_map: HBoxContainer
var _font: Font
var _font_plain: Font
var _deal_next := false
var _panel: Control
var _panel_title: Label
var _panel_row: HBoxContainer
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

func _make_map() -> void:
	run_map.clear()
	for i in floors:
		if i == floors - 1:
			run_map.append(["boss"])
		elif i == 0:
			run_map.append(["fight"])
		elif i == floors - 2:
			run_map.append(["rest", "treasure"] if _rng.randf() < 0.5 else ["rest", "elite"])
		else:
			var a := _pick_node(i)
			var b := _pick_node(i)
			var tries := 0
			while b == a and tries < 8:
				b = _pick_node(i)
				tries += 1
			run_map.append([a, b] if a != b else [a])


func _pick_node(i: int) -> String:
	var r := _rng.randf()
	if i >= 2 and r < 0.18:
		return "elite"
	if i >= 2 and r < 0.36:
		return "rest"
	if r < 0.5:
		return "treasure"
	return "fight"


func _open_map() -> void:
	if phase == "done":
		return
	floor_index += 1
	if floor_index >= run_map.size():
		return
	phase = "map"
	options = run_map[floor_index].duplicate()
	if options.size() == 1 and options[0] in ["fight", "boss"] and floor_index == 0:
		choose(0)
		return
	_show_panel("Floor %d of %d: where next?" % [floor_index + 1, floors],
		"Click a room, or press 1-%d" % options.size() if options.size() > 1 else "Click to go on, or press 1")


## Picks option [param i] of the open panel (a room on the map, or a reward card).
func choose(i: int) -> void:
	if i < 0 or i >= options.size() or _busy:
		return
	match phase:
		"map":
			var kind: String = options[i]
			_hide_panel()
			if kind == "rest":
				var amount := int(round(_health.max_health * rest_heal))
				_health.heal(amount)
				_pop(_entity, "+%d" % amount, Color("#7cf07c"))
				_play_fx("heal", _entity)
				GameState.message("You rest by the fire (+%d HP)" % amount)
				Sfx.play("pickup")
				_open_map.call_deferred()
			elif kind == "treasure":
				GameState.add_score(gold_per_fight)
				_offer_cards("Treasure! Take a card", true)
			else:
				begin_fight(kind)
		"reward":
			var picked: String = options[i]
			deck.append(picked)
			GameState.message("%s joins your deck" % picked)
			Sfx.play("pickup")
			_hide_panel()
			_open_map.call_deferred()


func skip_reward() -> void:
	if phase == "reward":
		_hide_panel()
		_open_map.call_deferred()


func _offer_cards(title: String, better: bool) -> void:
	phase = "reward"
	var pool: Array[String] = []
	for n: String in _library:
		if _library[n]["rarity"] != "starter":
			pool.append(n)
	options = []
	var tries := 0
	while options.size() < mini(3, pool.size()) and tries < 60:
		tries += 1
		var n: String = pool[_rng.randi() % pool.size()]
		var rarity: String = _library[n]["rarity"]
		var keep := 1.0 if rarity == "common" else (0.55 if rarity == "uncommon" else 0.25)
		if better:
			keep = minf(1.0, keep * 1.8)
		if n not in options and _rng.randf() < keep:
			options.append(n)
	if options.is_empty():
		_open_map.call_deferred()
		return
	_show_panel(title, "Click a card or press 1-%d; S skips" % options.size(), true)


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
	fight_started.emit(kind)
	if kind == "boss":
		GameState.message("The %s appears!" % picks[0]["type"])
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
	hero_st["block"] = 0
	if hero_st["poison"] > 0:
		_lose_hp(_entity, hero_st, hero_st["poison"], Color("#7cf07c"))
		hero_st["poison"] -= 1
		if phase == "done":
			return
	energy_left = energy
	_draw_cards(hand_size)
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
	if _fight_kind == "boss":
		phase = "done"
		GameState.add_score(gold_per_fight * 3)
		won.emit()
		return
	GameState.add_score(gold_per_fight * (2 if _fight_kind == "elite" else 1))
	_offer_cards("Victory! Take a card", _fight_kind == "elite")


func end_turn() -> void:
	if phase != "fight" or _busy:
		return
	phase = "foe_turn"
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
		"map":
			var best := 0
			for i in options.size():
				var k: String = options[i]
				if k == "rest" and _health.current < _health.max_health * 0.6:
					best = i
				elif k in ["fight", "treasure"] and options[best] == "elite":
					best = i
			choose(best)
		"reward":
			choose(0)
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
		elif k == KEY_S and phase == "reward":
			skip_reward()
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
	_panel_row = HBoxContainer.new()
	_panel_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_panel_row.add_theme_constant_override(&"separation", 24)
	col.add_child(_panel_row)
	_panel_map = HBoxContainer.new()
	_panel_map.alignment = BoxContainer.ALIGNMENT_CENTER
	_panel_map.add_theme_constant_override(&"separation", 6)
	col.add_child(_panel_map)
	_panel_hint = _label(18, Color("#d8d0e8"))
	_panel_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(_panel_hint)
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
	var w := tex.get_width()
	a.region = Rect2(w / 2.0 - 16, 0, 36, 36)  # the head and shoulders
	_portrait.texture = a


func _show_panel(title: String, hint: String, with_skip := false) -> void:
	_refresh_ui()
	_panel_title.text = title
	_panel_hint.text = hint
	for c in _panel_row.get_children():
		c.queue_free()
	for c in _panel_map.get_children():
		c.queue_free()
	for i in options.size():
		var o: String = options[i]
		var idx := i
		if phase == "reward":
			var cv := _card_view(o, true)
			cv.gui_input.connect(func(e: InputEvent) -> void:
				if _pressed(e):
					choose(idx))
			_panel_row.add_child(cv)
		else:
			var b := _button(NODE_NAME.get(o, o), Color("#e8d4a4"))
			b.custom_minimum_size = Vector2(150, 150)
			b.icon = _icon(NODE_ICON.get(o, "sword"))
			b.expand_icon = true
			b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			b.add_theme_constant_override(&"icon_max_width", 64)
			b.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			b.pressed.connect(func() -> void: choose(idx))
			_panel_row.add_child(b)
	if with_skip:
		var s := _button("Skip")
		s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		s.pressed.connect(skip_reward)
		_panel_row.add_child(s)
	if phase == "map":  # the road ahead: one small column of rooms per floor
		for f in run_map.size():
			var column := VBoxContainer.new()
			column.add_theme_constant_override(&"separation", 2)
			column.alignment = BoxContainer.ALIGNMENT_CENTER
			for k: String in run_map[f]:
				var ic := TextureRect.new()
				ic.texture = _icon(NODE_ICON[k])
				ic.custom_minimum_size = Vector2(32, 32)
				ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
				ic.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
				ic.modulate = Color(1, 1, 1, 0.35) if f < floor_index else (Color.WHITE if f == floor_index else Color(0.75, 0.75, 0.8))
				column.add_child(ic)
			_panel_map.add_child(column)
			if f < run_map.size() - 1:
				var dash := _label(18, Color("#8a8098"))
				dash.text = "-"
				dash.size_flags_vertical = Control.SIZE_SHRINK_CENTER
				_panel_map.add_child(dash)
	_panel.visible = true


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
	var title := _label(18 if big else 9)
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
	var cost := _label(18 if not big else 27, Color.WHITE)
	cost.text = str(c.get("cost", 0))
	cost.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cost.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	cost.position = Vector2(1, 1) * k
	cost.size = Vector2(14, 14) * k
	root.add_child(cost)
	return root


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
		cv.mouse_entered.connect(func() -> void:
			cv.z_index = 10
			var t := cv.create_tween().set_parallel(true)
			t.tween_property(cv, ^"position:y", home.y - 34, 0.08)
			t.tween_property(cv, ^"scale", Vector2(1.14, 1.14), 0.08)
			t.tween_property(cv, ^"rotation", 0.0, 0.08))
		cv.mouse_exited.connect(func() -> void:
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
