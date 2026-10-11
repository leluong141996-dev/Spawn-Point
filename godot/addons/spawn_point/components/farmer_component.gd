class_name FarmerComponent
extends Node
## The player's farming hands. Press interact (Space / E) next to a [FarmPlotComponent]: an empty plot gets
## the selected seed, a growing one gets water, a ripe one is harvested into the basket. Keys 1-3 choose
## the crop. Walk into a [MarketComponent] to sell the basket for money (score).
##
## [member crops] is a ";"-separated list of "Name|#color|grow seconds|price".

const SP_NAME := "Farmer"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["parse_crops", "interact", "select", "sell", "nearest_plot", "basket_value",
	"crop_list", "basket"]
const SP_CATEGORY := "core"

## Emitted after a sale with the money earned.
signal sold(amount: int)
## Emitted after each action: "plant", "water" or "harvest".
signal acted(action: String)

## The crops on offer (see the class description).
@export var crops: String = "Carrot|#ff9f1c|8|4;Tomato|#ff004d|14|9;Pumpkin|#ffa300|24|20"
## How far the farmer can reach a plot (px).
@export_range(8.0, 200.0, 1.0) var reach: float = 44.0
## Most crops the basket holds.
@export_range(1, 999) var basket_size: int = 12

var crop_list: Array[Dictionary] = []
var selected := 0
var basket := {}  # crop index -> count

var _entity: Node2D
var _layer: CanvasLayer
var _label: Label


func _ready() -> void:
	_entity = get_parent() as Node2D
	crop_list = parse_crops(crops)
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
	add_child.call_deferred(_layer)


static func parse_crops(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for entry in text.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() == 4:
			out.append({"name": p[0], "color": Color(p[1]), "seconds": float(p[2]), "price": int(p[3])})
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


## Does whatever the nearest plot needs. Returns the action taken ("" for none).
func interact() -> String:
	var plot := nearest_plot()
	if plot == null or crop_list.is_empty():
		return ""
	var action := ""
	if plot.is_ripe():
		if _carried() >= basket_size:
			GameState.message("Basket full - sell at the market!")
			return ""
		var c := plot.harvest()
		basket[c] = int(basket.get(c, 0)) + 1
		FX.float_text(plot.get_parent().global_position + Vector2(0, -18), "+1 " + crop_list[c].name, crop_list[c].color)
		action = "harvest"
	elif plot.is_empty():
		var cr: Dictionary = crop_list[selected]
		plot.plant(selected, cr.seconds, cr.color)
		plot.water()
		action = "plant"
	elif plot.water():
		action = "water"
	if action != "":
		if Sfx.has_sound("blip"):
			Sfx.play("blip", 0.1, -4.0, {"plant": 0.9, "water": 1.2, "harvest": 1.5}[action])
		acted.emit(action)
	return action


func _carried() -> int:
	var n := 0
	for c in basket:
		n += int(basket[c])
	return n


func basket_value() -> int:
	var v := 0
	for c in basket:
		v += int(basket[c]) * int(crop_list[c].price)
	return v


## Sells the whole basket. Returns the money earned.
func sell() -> int:
	var amount := basket_value()
	if amount <= 0:
		return 0
	basket.clear()
	GameState.add_score(amount)
	FX.float_text(_entity.global_position + Vector2(0, -26), "+$%d" % amount, Color("#ffec27"))
	if Sfx.has_sound("coin"):
		Sfx.play("coin", 0.0, 0.0, 0.8)
	sold.emit(amount)
	return amount


func _update_label() -> void:
	if _label == null:
		return
	var parts: Array[String] = []
	for i in crop_list.size():
		var cr: Dictionary = crop_list[i]
		var mark := ">" if i == selected else " "
		parts.append("%s[%d] %s $%d x%d" % [mark, i + 1, cr.name, cr.price, int(basket.get(i, 0))])
	_label.text = "  ".join(parts)
