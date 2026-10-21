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
## Seconds between foe moves (0 = instant, for tests).
@export_range(0.0, 2.0, 0.01) var pace: float = 0.45
## Map and draw seed (0 = a new run every time).
@export_range(0, 1000000) var run_seed: int = 0

const STATUS_KEYS := ["block", "poison", "weak", "vuln", "str"]
const NODE_ICON := {"fight": "sword", "elite": "skull", "rest": "campfire", "treasure": "chest", "boss": "crown"}
const NODE_NAME := {"fight": "Fight", "elite": "Elite", "rest": "Rest", "treasure": "Treasure", "boss": "Boss"}
const TYPE_COLOR := {"attack": Color("#c8463a"), "skill": Color("#3a78c8"), "power": Color("#a64ac8")}
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
var _end_button: Button
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
	_show_panel("Floor %d of %d: where next?" % [floor_index + 1, floors], "Click a room, or press 1-%d" % options.size())


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
				FX.float_text(_entity.global_position + Vector2(0, -90), "+%d" % amount, Color("#7cf07c"))
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
	if c["type"] == "attack":
		_lunge(_entity, 1.0)
	for e: Array in c["fx"]:
		var v: int = e[1]
		match e[0]:
			"dmg":
				for h in hits:
					if is_instance_valid(foe["node"]):
						deal(hero_st, foe["node"], foe["st"], v)
			"all":
				for f in alive:
					deal(hero_st, f["node"], f["st"], v)
			"blk":
				hero_st["block"] += v
				FX.float_text(_entity.global_position + Vector2(0, -80), "+%d block" % v, Color("#9ee8ff"))
				Sfx.play("pickup", 0.05, -6.0, 0.8)
			"draw":
				_draw_cards(v)
			"nrg":
				energy_left += v
			"heal":
				_health.heal(v)
				FX.float_text(_entity.global_position + Vector2(0, -80), "+%d" % v, Color("#7cf07c"))
			"poison", "weak", "vuln":
				foe["st"][e[0]] += v
			"str":
				hero_st["str"] += v
				FX.float_text(_entity.global_position + Vector2(0, -80), "+%d strength" % v, Color("#ffa300"))
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
	var pos := (node as Node2D).global_position + Vector2(0, -70)
	if blocked > 0:
		FX.float_text(pos + Vector2(0, -18), "blocked %d" % blocked, Color("#9ee8ff"))
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
	FX.float_text((node as Node2D).global_position + Vector2(0, -70), "-%d" % amount, color)
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
						deal(st, _entity, hero_st, m[1])
			"blk":
				st["block"] += m[1]
				FX.float_text(node.global_position + Vector2(0, -80), "+%d block" % m[1], Color("#9ee8ff"))
			"str":
				st["str"] += m[1]
				FX.float_text(node.global_position + Vector2(0, -80), "+%d strength" % m[1], Color("#ffa300"))
			"heal":
				var h := SP.component(node, &"Health") as HealthComponent
				if h:
					h.heal(m[1])
			"weak", "vuln", "poison":
				hero_st[m[0]] += m[1]
				FX.float_text(_entity.global_position + Vector2(0, -100), "%s %d" % [m[0], m[1]], Color("#c8a2ff"))


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

func _icon(icon_name: String) -> Texture2D:
	if not _tex.has(icon_name):
		var path := "res://sprites/art_ci_%s.png" % icon_name
		_tex[icon_name] = load(path) if ResourceLoader.exists(path) else null
	return _tex[icon_name]


func _frame(kind: String) -> Texture2D:
	var key := "frame_" + kind
	if not _tex.has(key):
		var path := "res://sprites/art_frame_%s.png" % kind
		_tex[key] = load(path) if ResourceLoader.exists(path) else null
	return _tex[key]


func _process(_delta: float) -> void:
	if _view and is_instance_valid(_view):
		_view.queue_redraw()


func _draw_world() -> void:
	var font := ThemeDB.fallback_font
	if _health and _health.current > 0:
		_draw_bars(_entity, _health.current, _health.max_health, hero_st, font)
	if phase not in ["fight", "foe_turn", "won_fight"]:
		return
	var alive := foes_alive()
	for i in alive.size():
		var f: Dictionary = alive[i]
		var n: Node2D = f["node"]
		var h := SP.component(n, &"Health") as HealthComponent
		if h == null:
			continue
		_draw_bars(n, h.current, h.max_health, f["st"], font)
		var r := _body_rect(n)
		var top := Vector2(r.get_center().x, r.position.y - 18)
		_draw_intent(f, top, font)
		if i == target and phase == "fight":
			var p := top + Vector2(0, -34)
			var bob := sin(Time.get_ticks_msec() / 160.0) * 3.0
			_view.draw_colored_polygon(PackedVector2Array([p + Vector2(-9, -8 + bob), p + Vector2(9, -8 + bob), p + Vector2(0, 3 + bob)]), GOLD)


func _draw_bars(n: Node2D, cur: int, top: int, st: Dictionary, font: Font) -> void:
	var w := 92.0
	var r := _body_rect(n)
	var p := Vector2(r.get_center().x - w / 2.0, maxf(r.end.y, n.global_position.y) + 8)
	_view.draw_rect(Rect2(p - Vector2(2, 2), Vector2(w + 4, 14)), INK)
	_view.draw_rect(Rect2(p, Vector2(w, 10)), Color("#5a1f2a"))
	_view.draw_rect(Rect2(p, Vector2(w * clampf(float(cur) / maxf(1, top), 0, 1), 10)), Color("#e8383a"))
	var label := "%d/%d" % [cur, top]
	_view.draw_string_outline(font, p + Vector2(0, 28), label, HORIZONTAL_ALIGNMENT_CENTER, w, 14, 4, INK)
	_view.draw_string(font, p + Vector2(0, 28), label, HORIZONTAL_ALIGNMENT_CENTER, w, 14, Color.WHITE)
	var x := p.x - 4
	if st.get("block", 0) > 0:
		_badge(Vector2(p.x - 22, p.y + 5), "shield", str(st["block"]), Color("#3a78c8"), font)
	var tags := []
	for k in ["str", "poison", "weak", "vuln"]:
		if st.get(k, 0) > 0:
			tags.append([k, st[k]])
	for t: Array in tags:
		var col: Color = {"str": Color("#ffa300"), "poison": Color("#5cd84a"), "weak": Color("#9a7ac8"), "vuln": Color("#ff77a8")}[t[0]]
		var txt := "%s %d" % [{"str": "STR", "poison": "PSN", "weak": "WEAK", "vuln": "VULN"}[t[0]], t[1]]
		_view.draw_string_outline(font, Vector2(x, p.y + 46), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, 4, INK)
		_view.draw_string(font, Vector2(x, p.y + 46), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, col)
		x += font.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 8


func _badge(c: Vector2, icon_name: String, text: String, color: Color, font: Font) -> void:
	var tex := _icon(icon_name)
	if tex:
		_view.draw_texture_rect(tex, Rect2(c - Vector2(12, 12), Vector2(24, 24)), false)
	else:
		_view.draw_circle(c, 11, color)
	_view.draw_string_outline(font, c + Vector2(-12, 5), text, HORIZONTAL_ALIGNMENT_CENTER, 24, 13, 4, INK)
	_view.draw_string(font, c + Vector2(-12, 5), text, HORIZONTAL_ALIGNMENT_CENTER, 24, 13, Color.WHITE)


func _draw_intent(f: Dictionary, at: Vector2, font: Font) -> void:
	var moves := intent_of(f)
	var x := at.x - 18.0 * moves.size()
	for m: Array in moves:
		var icon_name: String = {"atk": "sword", "blk": "shield", "str": "flex", "heal": "heart"}.get(m[0], "skull")
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
		var c := Vector2(x + 18, at.y)
		var tex := _icon(icon_name)
		if tex:
			_view.draw_texture_rect(tex, Rect2(c - Vector2(14, 14), Vector2(28, 28)), false)
		else:
			_view.draw_circle(c, 12, Color("#c8463a") if m[0] == "atk" else Color("#3a78c8"))
		if text != "":
			_view.draw_string_outline(font, c + Vector2(-20, 26), text, HORIZONTAL_ALIGNMENT_CENTER, 40, 16, 5, INK)
			_view.draw_string(font, c + Vector2(-20, 26), text, HORIZONTAL_ALIGNMENT_CENTER, 40, 16, Color.WHITE)
		x += 36.0


# --- screen UI ------------------------------------------------------------------------------

func _label(size: int, color := Color.WHITE) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override(&"font_size", size)
	l.add_theme_color_override(&"font_color", color)
	l.add_theme_color_override(&"font_outline_color", INK)
	l.add_theme_constant_override(&"outline_size", maxi(4, size / 4))
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _box_style(bg: Color, border: Color, width := 4) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(width)
	s.set_content_margin_all(8)
	return s


func _button(text: String) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	b.add_theme_font_size_override(&"font_size", 20)
	b.add_theme_stylebox_override(&"normal", _box_style(Color("#e8902a"), INK))
	b.add_theme_stylebox_override(&"hover", _box_style(Color("#ffb347"), INK))
	b.add_theme_stylebox_override(&"pressed", _box_style(Color("#b86a1a"), INK))
	b.add_theme_stylebox_override(&"disabled", _box_style(Color("#6a6070"), INK))
	b.add_theme_color_override(&"font_color", INK)
	b.add_theme_color_override(&"font_hover_color", INK)
	return b


func _build_ui() -> void:
	_ui = CanvasLayer.new()
	_ui.layer = 20
	add_child(_ui)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(root)
	_hand_root = Control.new()
	_hand_root.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_hand_root.offset_top = -170
	_hand_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(_hand_root)
	_energy_label = _label(30, GOLD)
	_energy_label.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_energy_label.position = Vector2(22, -120)
	_energy_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_energy_label.custom_minimum_size = Vector2(70, 70)
	_energy_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var orb := Panel.new()
	var orb_style := _box_style(Color("#e8902a"), INK, 5)
	orb_style.set_corner_radius_all(35)
	orb.add_theme_stylebox_override(&"panel", orb_style)
	orb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	orb.size = Vector2(70, 70)
	_energy_label.add_child(orb)
	orb.show_behind_parent = true
	root.add_child(_energy_label)
	_pile_label = _label(14)
	_pile_label.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_pile_label.position = Vector2(14, -42)
	root.add_child(_pile_label)
	_end_button = _button("End turn")
	_end_button.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_end_button.position = Vector2(-150, -110)
	_end_button.size = Vector2(130, 48)
	_end_button.pressed.connect(end_turn)
	root.add_child(_end_button)
	# The panel: the map, rewards.
	_panel = ColorRect.new()
	(_panel as ColorRect).color = Color(0.07, 0.06, 0.12, 0.82)
	_panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	_panel.visible = false
	root.add_child(_panel)
	var col := VBoxContainer.new()
	col.set_anchors_preset(Control.PRESET_CENTER)
	col.grow_horizontal = Control.GROW_DIRECTION_BOTH
	col.grow_vertical = Control.GROW_DIRECTION_BOTH
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_theme_constant_override(&"separation", 22)
	_panel.add_child(col)
	_panel_title = _label(34, GOLD)
	_panel_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(_panel_title)
	_panel_row = HBoxContainer.new()
	_panel_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_panel_row.add_theme_constant_override(&"separation", 26)
	col.add_child(_panel_row)
	_panel_hint = _label(16, Color("#d8d0e8"))
	_panel_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(_panel_hint)


func _show_panel(title: String, hint: String, with_skip := false) -> void:
	_refresh_ui()
	_panel_title.text = title
	_panel_hint.text = hint
	for c in _panel_row.get_children():
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
			var b := _button(NODE_NAME.get(o, o))
			b.custom_minimum_size = Vector2(150, 150)
			b.icon = _icon(NODE_ICON.get(o, "sword"))
			b.expand_icon = true
			b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			b.add_theme_constant_override(&"icon_max_width", 72)
			b.pressed.connect(func() -> void: choose(idx))
			_panel_row.add_child(b)
	if with_skip:
		var s := _button("Skip")
		s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		s.pressed.connect(skip_reward)
		_panel_row.add_child(s)
	if phase == "map":
		_panel_hint.text = hint + "\n" + _map_line()
	_panel.visible = true


func _map_line() -> String:
	var parts: PackedStringArray = []
	for i in run_map.size():
		var names: PackedStringArray = []
		for k: String in run_map[i]:
			names.append(NODE_NAME[k])
		var s := "/".join(names)
		parts.append(("[%s]" % s) if i == floor_index else s)
	return "  >  ".join(parts)


func _hide_panel() -> void:
	_panel.visible = false


func _pressed(e: InputEvent) -> bool:
	return (e is InputEventMouseButton and e.pressed and (e as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT) \
		or (e is InputEventScreenTouch and e.pressed)


func _card_view(card_name: String, big := false) -> Control:
	var c := card(card_name)
	var k := 3.0 if big else 2.0  # screen px per art px of the 56x78 frame (sprites/cards.py)
	var size := Vector2(56, 78) * k
	var root := Control.new()
	root.custom_minimum_size = size
	root.size = size
	root.pivot_offset = size / 2.0
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
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.position = Vector2(28 - 12, 29 - 12) * k
	icon.size = Vector2(24, 24) * k
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(icon)
	var title := _label(int(6.5 * k))
	title.text = card_name
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	title.position = Vector2(5, 4) * k
	title.size = Vector2(46, 9) * k
	title.clip_text = true
	root.add_child(title)
	var text := Label.new()
	text.add_theme_font_size_override(&"font_size", int(5.5 * k))
	text.add_theme_color_override(&"font_color", INK)
	text.add_theme_constant_override(&"line_spacing", -2)
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	text.text = card_text(card_name)
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	text.position = Vector2(6, 46) * k
	text.size = Vector2(44, 26) * k
	root.add_child(text)
	var cost := _label(20, Color.WHITE)
	cost.text = str(c.get("cost", 0))
	cost.position = Vector2(-6, -8)
	cost.size = Vector2(30, 30)
	cost.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var gem := Panel.new()
	var gs := _box_style(Color("#e8902a"), INK, 3)
	gs.set_corner_radius_all(15)
	gem.add_theme_stylebox_override(&"panel", gs)
	gem.size = Vector2(30, 30)
	gem.show_behind_parent = true
	gem.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cost.add_child(gem)
	root.add_child(cost)
	root.mouse_entered.connect(func() -> void:
		root.z_index = 5
		root.create_tween().tween_property(root, ^"scale", Vector2(1.12, 1.12), 0.08))
	root.mouse_exited.connect(func() -> void:
		root.z_index = 0
		root.create_tween().tween_property(root, ^"scale", Vector2.ONE, 0.08))
	return root


func _refresh_ui() -> void:
	if _hand_root == null:
		return
	for c in _hand_root.get_children():
		c.queue_free()
	var fighting := phase == "fight"
	_end_button.visible = phase in ["fight", "foe_turn"]
	_end_button.disabled = not fighting
	_energy_label.visible = phase in ["fight", "foe_turn"]
	_energy_label.text = "%d/%d" % [energy_left, energy]
	_pile_label.visible = _energy_label.visible
	_pile_label.text = "Draw %d   Discard %d" % [draw_pile.size(), discard.size()]
	if not fighting:
		return
	var n := hand.size()
	var view_w := _hand_root.get_viewport_rect().size.x if _hand_root.is_inside_tree() else 960.0
	var step := minf(116.0, (view_w - 360.0) / maxf(1, n))
	var x0 := view_w / 2.0 - step * n / 2.0
	for i in n:
		var cv := _card_view(hand[i])
		var idx := i
		var mid := (i - (n - 1) / 2.0)
		cv.position = Vector2(x0 + i * step, 12 + absf(mid) * absf(mid) * 2.0)
		cv.rotation = deg_to_rad(mid * 2.5)
		if card(hand[i]).get("cost", 0) > energy_left:
			cv.modulate = Color(0.6, 0.6, 0.65)
		cv.gui_input.connect(func(e: InputEvent) -> void:
			if _pressed(e):
				play_index(idx))
		_hand_root.add_child(cv)
