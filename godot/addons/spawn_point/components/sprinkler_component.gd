class_name SprinklerComponent
extends Node
## A sprinkler waiting to be bought (see [ShopComponent]): hidden until [method activate]; then every morning (and
## right away) it waters the plots within [member radius].

const SP_NAME := "Sprinkler"
const SP_HOSTS: Array[String] = []
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["activate", "active", "water_around"]
const SP_CATEGORY := "core"

## Plots closer than this are watered (px).
@export_range(16.0, 200.0, 1.0) var radius: float = 52.0
## Starts working without being bought.
@export var start_active: bool = false

var active := false
var _entity: Node2D


func _ready() -> void:
	_entity = get_parent() as Node2D
	_entity.add_to_group(&"sprinkler")
	_set_visible.call_deferred(start_active)
	if start_active:
		active = true
	for e in get_tree().get_nodes_in_group(SP.ENTITY_GROUP):
		var days := SP.component(e, &"FarmDays") as FarmDaysComponent
		if days:
			days.day_started.connect(func(_d: int) -> void: water_around())


func _set_visible(on: bool) -> void:
	var v := _entity.get_node_or_null(^"Visual") as Node2D
	if v:
		v.visible = on


func activate() -> void:
	if active:
		return
	active = true
	_set_visible(true)
	water_around()


## Waters every growing plot within reach (only when active). Returns how many.
func water_around() -> int:
	if not active:
		return 0
	var n := 0
	for e in get_tree().get_nodes_in_group(&"farm_plot"):
		if (e as Node2D).global_position.distance_to(_entity.global_position) <= radius:
			if (SP.component(e, &"FarmPlot") as FarmPlotComponent).water():
				n += 1
	if n > 0:
		FX.burst(_entity.global_position + Vector2(0, -8), Color("#7fd0ff"), 12, 120.0, 0.5, 2.0, 120.0)
	return n
