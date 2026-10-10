class_name LevelUpMenuComponent
extends Node
## Survivor-style upgrade picker. On every level of the sibling [ExperienceComponent] the game pauses
## and offers [member choices] random upgrades as cards (keys 1-3, arrows + Enter, or a click).
##
## [member upgrades] is a ";"-separated list of "Name|Description|changes". Each change is
## "[Entity:]Component.param" followed by "*factor" or "+amount"; several changes are joined with ",".
## Without "Entity:" the change applies to this entity; with it, to every current and future
## instance of that entity type (bullets, for instance).

const SP_NAME := "LevelUpMenu"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = ["Experience"]
const SP_INTERNAL: Array[String] = ["parse_upgrades", "apply_upgrade", "offer", "pick", "is_open"]
const SP_CATEGORY := "core"

const DEFAULT_UPGRADES := "Rapid Fire|Shoot 25% faster|Weapon.fire_rate*1.25;" \
	+ "Multishot|One more projectile|Weapon.projectile_count+1,Weapon.spread_deg+10;" \
	+ "Power|Bullets hit harder|Bullet:Hitbox.damage+1;" \
	+ "Piercing|Bullets pass through one more enemy|Bullet:Projectile.pierce+1;" \
	+ "Swift|Move 12% faster|TopDownMovement.max_speed*1.12;" \
	+ "Vitality|+1 max health, fully healed|Health.max_health+1,Health.current+99;" \
	+ "Magnet|Pull XP from further away|Experience.magnet_radius*1.5"

## Emitted after an upgrade is applied.
signal upgraded(upgrade_name: String, level: int)

## The upgrade pool (see the class description for the format).
@export_multiline var upgrades: String = DEFAULT_UPGRADES
## Cards offered per level.
@export_range(1, 5) var choices: int = 3
## How many times one upgrade can be taken.
@export_range(1, 99) var max_picks: int = 5

var _entity: Node
var _pool: Array[Dictionary] = []
var _picks := {}
var _queue := 0
var _offer: Array[Dictionary] = []
var _focus := 0
var _layer: CanvasLayer
var _cards: Array[Button] = []
var _auto_t := -1.0


func _ready() -> void:
	_entity = get_parent()
	process_mode = Node.PROCESS_MODE_ALWAYS
	_pool = parse_upgrades(upgrades)
	var xp := SP.component(_entity, &"Experience") as ExperienceComponent
	if xp:
		xp.leveled_up.connect(func(_l: int) -> void:
			_queue += 1
			if not is_open():
				offer())


static func parse_upgrades(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var re := RegEx.create_from_string("^(?:(\\w+):)?(\\w+)\\.(\\w+)([*+])(-?[0-9.]+)$")
	for entry in text.split(";", false):
		var parts := entry.strip_edges().split("|")
		if parts.size() != 3:
			push_warning("LevelUpMenu: bad upgrade '%s'" % entry)
			continue
		var changes: Array[Dictionary] = []
		for c in parts[2].split(",", false):
			var m := re.search(c.strip_edges())
			if m == null:
				push_warning("LevelUpMenu: bad change '%s'" % c)
				continue
			changes.append({"type": m.get_string(1), "component": m.get_string(2), "param": m.get_string(3),
					"op": m.get_string(4), "amount": float(m.get_string(5))})
		if not changes.is_empty():
			out.append({"name": parts[0].strip_edges(), "desc": parts[1].strip_edges(), "changes": changes})
	return out


func is_open() -> bool:
	return _layer != null


## Pauses the game and shows the cards for one level.
func offer() -> void:
	if _queue <= 0 or _pool.is_empty():
		return
	var avail := _pool.filter(func(u: Dictionary) -> bool: return int(_picks.get(u.name, 0)) < max_picks)
	if avail.is_empty():
		_queue = 0
		return
	avail.shuffle()
	_offer.assign(avail.slice(0, choices))
	_focus = 0
	get_tree().paused = true
	_build_ui()
	if Sfx.has_sound("powerup"):
		Sfx.play("powerup", 0.0)
	if get_tree().root.has_meta(&"sp_autopilot"):  # bots and GIF recordings pick on their own
		_auto_t = 0.15


## Applies offered card [param index] and resumes (or shows the next level's cards).
func pick(index: int) -> void:
	if not is_open() or index < 0 or index >= _offer.size():
		return
	var u: Dictionary = _offer[index]
	apply_upgrade(u)
	_picks[u.name] = int(_picks.get(u.name, 0)) + 1
	_layer.queue_free()
	_layer = null
	_cards.clear()
	_queue -= 1
	var xp := SP.component(_entity, &"Experience") as ExperienceComponent
	upgraded.emit(u.name, xp.level if xp else 0)
	if _queue > 0:
		offer()
	else:
		get_tree().paused = false
		_auto_t = -1.0


func apply_upgrade(u: Dictionary) -> void:
	for c: Dictionary in u.changes:
		var type: String = c.type
		var cur: Variant
		if type == "":
			var comp := SP.component(_entity, StringName(c.component))
			if comp == null:
				continue
			cur = comp.get(c.param)
		else:
			cur = World.type_param(StringName(type), StringName(c.component), StringName(c.param),
					World.type_default(type, StringName(c.component), StringName(c.param)))
		if cur == null:
			continue
		var value: float = float(cur) * c.amount if c.op == "*" else float(cur) + c.amount
		var new_value: Variant = int(round(value)) if typeof(cur) == TYPE_INT else value
		if type == "":
			var comp := SP.component(_entity, StringName(c.component))
			comp.set(c.param, new_value)
			if comp is HealthComponent:
				(comp as HealthComponent).current = mini((comp as HealthComponent).current, (comp as HealthComponent).max_health)
		else:
			World.set_type_param(StringName(type), StringName(c.component), StringName(c.param), new_value)


func _process(delta: float) -> void:
	if _auto_t >= 0.0 and is_open():
		_auto_t -= delta
		if _auto_t < 0.0:
			pick(randi() % _offer.size())


func _unhandled_input(event: InputEvent) -> void:
	if not is_open() or not (event is InputEventKey) or not event.pressed or event.echo:
		return
	var key := (event as InputEventKey).keycode
	if key >= KEY_1 and key < KEY_1 + _offer.size():
		pick(key - KEY_1)
	elif key in [KEY_LEFT, KEY_A]:
		_set_focus(_focus - 1)
	elif key in [KEY_RIGHT, KEY_D]:
		_set_focus(_focus + 1)
	elif key in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE]:
		pick(_focus)
	get_viewport().set_input_as_handled()


func _set_focus(i: int) -> void:
	_focus = wrapi(i, 0, _offer.size())
	if _focus < _cards.size():
		_cards[_focus].grab_focus()


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	_layer.layer = 20
	add_child(_layer)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_layer.add_child(dim)
	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override(&"separation", 18)
	dim.add_child(box)
	var xp := SP.component(_entity, &"Experience") as ExperienceComponent
	var title := Label.new()
	title.text = "LEVEL %d!  Choose an upgrade" % (xp.level - _queue + 1 if xp else 0)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override(&"font_size", 36)
	title.add_theme_color_override(&"font_color", Color("#ffec27"))
	title.add_theme_color_override(&"font_outline_color", Color.BLACK)
	title.add_theme_constant_override(&"outline_size", 6)
	box.add_child(title)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override(&"separation", 16)
	box.add_child(row)
	for i in _offer.size():
		var u: Dictionary = _offer[i]
		var b := Button.new()
		b.custom_minimum_size = Vector2(210, 130)
		b.text = "%d. %s\n\n%s" % [i + 1, u.name, u.desc]
		b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		b.add_theme_font_size_override(&"font_size", 18)
		var style := StyleBoxFlat.new()
		style.bg_color = Color("#1d2b53")
		style.border_color = Color("#29adff")
		style.set_border_width_all(3)
		style.set_corner_radius_all(10)
		var hover := style.duplicate() as StyleBoxFlat
		hover.border_color = Color("#ffec27")
		hover.bg_color = Color("#2a3b6e")
		b.add_theme_stylebox_override(&"normal", style)
		b.add_theme_stylebox_override(&"hover", hover)
		b.add_theme_stylebox_override(&"focus", hover)
		b.add_theme_stylebox_override(&"pressed", hover)
		b.pressed.connect(pick.bind(i))
		row.add_child(b)
		_cards.append(b)
	_set_focus.call_deferred(0)
