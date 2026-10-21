class_name FarmerComponent
extends Node
## The player's farming hands. Press interact (Space / E) next to something: grass where a plot goes is tilled
## with the hoe, an empty plot gets the selected seed, a growing one gets water, a ripe one is harvested into the basket; a [FarmAnimalComponent] gives its egg
## or milk; a [GatherableComponent] tree or rock takes a hit (and gives wood or stone when it breaks); at a
## [FishingSpotComponent] the first press casts and the next one, when a fish bites, reels it in.
## Keys 1-9 choose the seed. Walk into a [MarketComponent] (a stall or a shipping bin) to sell the basket.
##
## [member crops] is a ";"-separated list of "Name|#color|grow seconds|price", optionally followed by
## "|growth stages picture|icon picture" (res:// paths). [member goods] prices everything else the basket can
## hold: "Name|price|icon picture;..." (eggs, milk, wood, stone).

const SP_NAME := "Farmer"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["parse_crops", "parse_goods", "interact", "select", "sell", "nearest_plot",
	"basket_value", "crop_list", "basket", "goods_basket", "add_goods", "nearest_target"]
const SP_CATEGORY := "core"

## Emitted after a sale with the money earned.
signal sold(amount: int)
## Emitted after each action: "till", "plant", "water", "harvest", "collect", "chop", "gather", "cast" or "catch".
signal acted(action: String)

## The crops on offer (see the class description).
@export var crops: String = "Carrot|#ff9f1c|8|4;Tomato|#ff004d|14|9;Pumpkin|#ffa300|24|20"
## Prices of the other things the basket can hold (see the class description).
@export var goods: String = ""
## How far the farmer can reach a plot (px).
@export_range(8.0, 200.0, 1.0) var reach: float = 44.0
## Most crops the basket holds.
@export_range(1, 999) var basket_size: int = 12
## Show the hotbar (seed slots and the basket) at the bottom of the screen.
@export var hotbar: bool = true

var crop_list: Array[Dictionary] = []
var goods_list: Array[Dictionary] = []
var selected := 0
var basket := {}  # crop index -> count
var goods_basket := {}  # goods name -> count

var _entity: Node2D
var _layer: CanvasLayer
var _label: Label
var _slots: Array[Dictionary] = []  # {"panel", "count", "kind": "crop"|"goods", "key"}


func _ready() -> void:
	_entity = get_parent() as Node2D
	crop_list = parse_crops(crops)
	goods_list = parse_goods(goods)
	if not InputMap.has_action(&"interact"):
		InputMap.add_action(&"interact", 0.2)
		for code in [KEY_SPACE, KEY_E, KEY_ENTER]:
			var k := InputEventKey.new()
			k.physical_keycode = code
			InputMap.action_add_event(&"interact", k)
	_layer = CanvasLayer.new()
	_layer.layer = 11
	_label = Label.new()
	_label.add_theme_font_size_override(&"font_size", 18)
	_label.add_theme_color_override(&"font_outline_color", Color.BLACK)
	_label.add_theme_constant_override(&"outline_size", 5)
	_label.position = Vector2(16, 44)
	_layer.add_child(_label)
	if hotbar and _has_pictures():
		_label.visible = false
		_build_hotbar()
	add_child.call_deferred(_layer)


static func parse_crops(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for entry in text.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() >= 4:
			var c := {"name": p[0], "color": Color(p[1]), "seconds": float(p[2]), "price": int(p[3]),
				"texture": null, "icon": null}
			if p.size() >= 5 and ResourceLoader.exists(p[4]):
				c.texture = load(p[4])
			if p.size() >= 6 and ResourceLoader.exists(p[5]):
				c.icon = load(p[5])
			out.append(c)
	return out


static func parse_goods(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for entry in text.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() >= 2:
			out.append({"name": p[0], "price": int(p[1]),
				"icon": load(p[2]) if p.size() >= 3 and ResourceLoader.exists(p[2]) else null})
	return out


func _physics_process(_delta: float) -> void:
	if GameState.is_playing() and Input.is_action_just_pressed(&"interact"):
		interact()
	_update_label()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var k := (event as InputEventKey).keycode
		if k >= KEY_1 and k < KEY_1 + crop_list.size():
			select(k - KEY_1)


func select(index: int) -> void:
	selected = clampi(index, 0, maxi(crop_list.size() - 1, 0))


func nearest_plot() -> FarmPlotComponent:
	var best: FarmPlotComponent = null
	var best_d := reach
	for e in _entity.get_tree().get_nodes_in_group(&"farm_plot"):
		var d := (e as Node2D).global_position.distance_to(_entity.global_position)
		if d < best_d:
			best_d = d
			best = SP.component(e, &"FarmPlot") as FarmPlotComponent
	return best


## The closest thing within reach to work on: a plot, an animal or a gatherable (or null). An animal with
## something to give counts as closer than one without (a pat is the last resort).
func nearest_target() -> Node:
	var best: Node = null
	var best_score := INF
	for group in [&"farm_plot", &"farm_animal", &"gatherable", &"fishing_spot"]:
		var comp_name: StringName = {&"farm_plot": &"FarmPlot", &"farm_animal": &"FarmAnimal", &"gatherable": &"Gatherable",
			&"fishing_spot": &"FishingSpot"}[group]
		var limit := reach if group == &"farm_plot" else reach * 1.25  # animals and trees are bigger than a plot
		for e in _entity.get_tree().get_nodes_in_group(group):
			var d := (e as Node2D).global_position.distance_to(_entity.global_position)
			if d >= limit:
				continue
			var comp := SP.component(e, comp_name)
			var score := d
			if comp is FarmAnimalComponent and not (comp as FarmAnimalComponent).is_ready():
				score += reach * 2.0
			if score < best_score:
				best_score = score
				best = comp
	return best


## Does whatever the nearest thing needs. Returns the action taken ("" for none).
func interact() -> String:
	var target := nearest_target()
	var action := ""
	if target is FarmPlotComponent:
		action = _work_plot(target as FarmPlotComponent)
	elif target is FarmAnimalComponent:
		var item := (target as FarmAnimalComponent).collect() if not _full() else ""
		if _full() and (target as FarmAnimalComponent).is_ready():
			GameState.message("Basket full - sell it first!")
		if item != "":
			add_goods(item, 1, (target.get_parent() as Node2D).global_position)
			action = "collect"
	elif target is FishingSpotComponent:
		var fish := (target as FishingSpotComponent).use()
		if fish == "cast":
			action = "cast"
		elif fish != "":
			add_goods(fish, 1, (target as FishingSpotComponent).bobber_position())
			action = "catch"
	elif target is GatherableComponent:
		var g := target as GatherableComponent
		var where := (g.get_parent() as Node2D).global_position
		var item := g.hit()
		if item != "":
			add_goods(item, g.amount, where)
		action = "gather" if item != "" else "chop"
	if action != "":
		if Sfx.has_sound("blip"):
			Sfx.play("blip", 0.1, -4.0, {"plant": 0.9, "water": 1.2, "harvest": 1.5, "collect": 1.7, "chop": 0.7,
				"gather": 1.3, "till": 0.6, "cast": 1.0, "catch": 1.8}[action])
		acted.emit(action)
	return action


func _work_plot(plot: FarmPlotComponent) -> String:
	if crop_list.is_empty():
		return ""
	if plot.till():
		return "till"
	if plot.is_ripe():
		if _full():
			GameState.message("Basket full - sell at the market!")
			return ""
		var c := plot.harvest()
		basket[c] = int(basket.get(c, 0)) + 1
		FX.float_text(plot.get_parent().global_position + Vector2(0, -18), "+1 " + crop_list[c].name, crop_list[c].color)
		return "harvest"
	if plot.is_empty():
		var cr: Dictionary = crop_list[selected]
		plot.plant(selected, cr.seconds, cr.color, cr.texture)
		plot.water()
		return "plant"
	if plot.water():
		return "water"
	return ""


## Puts [param n] of a goods item in the basket (as far as it fits). Returns how many went in.
func add_goods(item: String, n := 1, where := Vector2.INF) -> int:
	var room := maxi(basket_size - _carried(), 0)
	var put := mini(n, room)
	if put <= 0:
		GameState.message("Basket full - sell it first!")
		return 0
	goods_basket[item] = int(goods_basket.get(item, 0)) + put
	var pos := where if where != Vector2.INF else _entity.global_position
	FX.float_text(pos + Vector2(0, -24), "+%d %s" % [put, item], Color("#fffaf0"))
	return put


func _full() -> bool:
	return _carried() >= basket_size


func _carried() -> int:
	var n := 0
	for c in basket:
		n += int(basket[c])
	for g in goods_basket:
		n += int(goods_basket[g])
	return n


func _goods_price(item: String) -> int:
	for g in goods_list:
		if g.name == item:
			return int(g.price)
	return 1


func basket_value() -> int:
	var v := 0
	for c in basket:
		v += int(basket[c]) * int(crop_list[c].price)
	for g in goods_basket:
		v += int(goods_basket[g]) * _goods_price(g)
	return v


## Sells the whole basket. Returns the money earned.
func sell() -> int:
	var amount := basket_value()
	if amount <= 0:
		return 0
	basket.clear()
	goods_basket.clear()
	GameState.add_score(amount)
	FX.float_text(_entity.global_position + Vector2(0, -26), "+$%d" % amount, Color("#ffec27"))
	if Sfx.has_sound("coin"):
		Sfx.play("coin", 0.0, 0.0, 0.8)
	sold.emit(amount)
	return amount


# --- the hotbar ---------------------------------------------------------------------------------

func _has_pictures() -> bool:
	for c in crop_list:
		if c.icon != null:
			return true
	return false


func _slot_style(selected_slot: bool) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color("#e8c08a") if selected_slot else Color("#c8925a")
	sb.border_color = Color("#ffec27") if selected_slot else Color("#5a321e")
	sb.set_border_width_all(3)
	sb.set_corner_radius_all(4)
	return sb


func _build_hotbar() -> void:
	var bar := PanelContainer.new()
	bar.name = "Hotbar"
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color("#8a5232")
	bg.border_color = Color("#3a2014")
	bg.set_border_width_all(3)
	bg.set_corner_radius_all(6)
	bg.set_content_margin_all(6)
	bar.add_theme_stylebox_override(&"panel", bg)
	var row := HBoxContainer.new()
	row.add_theme_constant_override(&"separation", 4)
	bar.add_child(row)
	for i in crop_list.size():
		_slots.append(_add_slot(row, crop_list[i].icon, str(i + 1), "crop", i))
	for g in goods_list:
		_slots.append(_add_slot(row, g.icon, "", "goods", g.name))
	bar.anchor_left = 0.5
	bar.anchor_right = 0.5
	bar.anchor_top = 1.0
	bar.anchor_bottom = 1.0
	bar.grow_horizontal = Control.GROW_DIRECTION_BOTH
	bar.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bar.offset_bottom = -10
	_layer.add_child(bar)


func _add_slot(row: HBoxContainer, icon: Variant, key: String, kind: String, id: Variant) -> Dictionary:
	var panel := Panel.new()
	panel.custom_minimum_size = Vector2(48, 48)
	panel.add_theme_stylebox_override(&"panel", _slot_style(false))
	row.add_child(panel)
	if icon != null:
		var tr := TextureRect.new()
		tr.texture = icon
		tr.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tr.position = Vector2(8, 6)
		tr.size = Vector2(32, 32)
		panel.add_child(tr)
	var count := Label.new()
	count.add_theme_font_size_override(&"font_size", 13)
	count.add_theme_color_override(&"font_outline_color", Color.BLACK)
	count.add_theme_constant_override(&"outline_size", 4)
	count.position = Vector2(26, 28)
	panel.add_child(count)
	if key != "":
		var k := Label.new()
		k.text = key
		k.add_theme_font_size_override(&"font_size", 11)
		k.add_theme_color_override(&"font_color", Color("#3a2014"))
		k.position = Vector2(5, 1)
		panel.add_child(k)
	return {"panel": panel, "count": count, "kind": kind, "id": id, "sel": false}


func _update_label() -> void:
	if not _slots.is_empty():
		for s: Dictionary in _slots:
			var n := int(basket.get(s.id, 0)) if s.kind == "crop" else int(goods_basket.get(s.id, 0))
			(s.count as Label).text = "x%d" % n if n > 0 else ""
			var sel: bool = s.kind == "crop" and int(s.id) == selected
			if sel != bool(s.sel):
				s.sel = sel
				(s.panel as Panel).add_theme_stylebox_override(&"panel", _slot_style(sel))
		return
	if _label == null:
		return
	var parts: Array[String] = []
	for i in crop_list.size():
		var cr: Dictionary = crop_list[i]
		var mark := ">" if i == selected else " "
		parts.append("%s[%d] %s $%d x%d" % [mark, i + 1, cr.name, cr.price, int(basket.get(i, 0))])
	_label.text = "  ".join(parts)
