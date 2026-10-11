class_name TowerSlotComponent
extends Node
## A build pad beside the road (tower defense). A [TowerBuilderComponent] builds a tower here when the
## player clicks or taps the pad (or presses build while standing next to it).

const SP_NAME := "TowerSlot"
const SP_HOSTS: Array[String] = ["Area2D"]
const SP_REQUIRES: Array[String] = []
const SP_INTERNAL: Array[String] = ["tower", "is_free"]
const SP_CATEGORY := "core"

## Pad size in px.
@export_range(16.0, 128.0, 1.0) var size: float = 30.0

var tower: Node2D
var _entity: Area2D
var _view: Node2D
var _t := 0.0


func _ready() -> void:
	_entity = get_parent() as Area2D
	_entity.add_to_group(&"tower_slot")
	_view = Node2D.new()
	_view.z_index = -1
	_view.draw.connect(_on_draw)
	_entity.add_child.call_deferred(_view)


func is_free() -> bool:
	return tower == null or not is_instance_valid(tower)


func _process(delta: float) -> void:
	_t += delta
	if _view and is_free():
		_view.queue_redraw()


func _on_draw() -> void:
	var h := size / 2.0
	_view.draw_rect(Rect2(-h, -h, size, size), Color(0, 0, 0, 0.25))
	_view.draw_rect(Rect2(-h + 2, -h + 2, size - 4, size - 4), Color("#c2c3c7"), false, 2.0)
	if is_free():  # a gently pulsing plus: "build here"
		var a := 0.45 + 0.35 * sin(_t * 3.0)
		_view.draw_line(Vector2(-6, 0), Vector2(6, 0), Color(1, 1, 1, a), 3.0)
		_view.draw_line(Vector2(0, -6), Vector2(0, 6), Color(1, 1, 1, a), 3.0)
