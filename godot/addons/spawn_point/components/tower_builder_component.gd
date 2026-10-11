class_name TowerBuilderComponent
extends Node
## The player's builder (tower defense): keys 1-3 pick a tower, a click or tap on a [TowerSlotComponent]
## builds it if the gold (score) covers the cost. Kills earn gold through the rules.
##
## [member towers] is a ";"-separated list of "Entity|cost", e.g. "ArcherTower|50;CannonTower|100".

const SP_NAME := "TowerBuilder"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["parse_towers", "build_on", "select", "tower_list"]
const SP_CATEGORY := "core"
const SP_ENTITY_PARAMS: Array[String] = []

## Emitted after a tower is built.
signal built(tower: Node)

## The towers on offer (see the class description).
@export var towers: String = "ArcherTower|50;CannonTower|100"
## Gold at the start.
@export_range(0, 100000) var start_gold: int = 120

var tower_list: Array[Dictionary] = []
var selected := 0
var _layer: CanvasLayer
var _label: Label


func _ready() -> void:
	tower_list = parse_towers(towers)
	GameState.add_score.call_deferred(start_gold)
	_layer = CanvasLayer.new()
	_layer.layer = 11
	_label = Label.new()
	_label.add_theme_font_size_override(&"font_size", 18)
	_label.add_theme_color_override(&"font_outline_color", Color.BLACK)
	_label.add_theme_constant_override(&"outline_size", 5)
	_label.position = Vector2(16, 44)
	_layer.add_child(_label)
	add_child.call_deferred(_layer)


static func parse_towers(text: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for entry in text.split(";", false):
		var p := entry.strip_edges().split("|")
		if p.size() == 2:
			out.append({"entity": p[0], "cost": int(p[1])})
	return out


func select(index: int) -> void:
	selected = clampi(index, 0, maxi(tower_list.size() - 1, 0))


## Builds the selected tower on [param slot]. Returns the tower, or null (taken, or not enough gold).
func build_on(slot: TowerSlotComponent) -> Node2D:
	if slot == null or not slot.is_free() or tower_list.is_empty():
		return null
	var t: Dictionary = tower_list[selected]
	if GameState.score < int(t.cost):
		GameState.message("Not enough gold")
		return null
	var pos := (slot.get_parent() as Node2D).global_position
	var tower := World.spawn(String(t.entity), pos, {"sp_team": SP.TEAM_PLAYER})
	if tower == null:
		return null
	slot.tower = tower
	GameState.add_score(-int(t.cost))
	FX.burst(pos, Color("#ffec27"), 12, 150.0, 0.4, 3.0, 0.0)
	if Sfx.has_sound("powerup"):
		Sfx.play("powerup", 0.05)
	built.emit(tower)
	return tower


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var k := (event as InputEventKey).keycode
		if k >= KEY_1 and k < KEY_1 + tower_list.size():
			select(k - KEY_1)
	elif event is InputEventMouseButton and event.pressed and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		if not GameState.is_playing():
			return
		var world_pos := (get_parent() as Node2D).get_global_mouse_position()
		var best: TowerSlotComponent = null
		var best_d := 28.0
		for e in get_tree().get_nodes_in_group(&"tower_slot"):
			var d := (e as Node2D).global_position.distance_to(world_pos)
			if d < best_d:
				best_d = d
				best = SP.component(e, &"TowerSlot") as TowerSlotComponent
		if best:
			build_on(best)
			get_viewport().set_input_as_handled()


func _process(_delta: float) -> void:
	if _label == null:
		return
	var parts: Array[String] = []
	for i in tower_list.size():
		var t: Dictionary = tower_list[i]
		parts.append("%s[%d] %s %dg" % [">" if i == selected else " ", i + 1, String(t.entity).replace("Tower", ""), t.cost])
	_label.text = "  ".join(parts) + "    click a pad to build"
